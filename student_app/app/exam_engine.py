"""
Student Exam Application - Exam Engine

Core exam management and orchestration.
"""

import logging
import json
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass

from student_app.app.config import get_config, AppConfig
from student_app.app.auth import AuthResult, get_authenticator
from student_app.app.storage.supabase_client import get_supabase_client
from student_app.app.storage.uploader import get_background_uploader
from student_app.app.buffer import get_circular_buffer, get_clip_extractor
from student_app.app.ai.event_classifier import (
    EventClassifier, get_event_classifier, Violation, EventType, DetectionEvent
)
from student_app.app.db.sqlite_queue import get_sqlite_queue

logger = logging.getLogger(__name__)


@dataclass
class ExamState:
    """Current exam state."""
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    hall_ticket: Optional[str] = None
    exam_id: Optional[str] = None
    lab_id: Optional[str] = None
    attempt_id: Optional[str] = None
    status: str = "IDLE"  # IDLE, AUTHENTICATED, INSTRUCTIONS, ACTIVE, SUBMITTED, TERMINATED
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_minutes: int = 60
    violations: List[Violation] = None
    is_fullscreen: bool = True
    last_evidence_time: float = 0 # Global cooldown for evidence capture
    
    def __post_init__(self):
        if self.violations is None:
            self.violations = []


class ExamEngine:
    """
    Central exam orchestration engine.
    
    Coordinates:
    - Authentication
    - Exam lifecycle (start, submit, terminate)
    - AI detection services
    - Evidence capture
    - Supabase synchronization
    """
    
    def __init__(
        self,
        on_violation: Optional[Callable[[Violation], None]] = None,
        on_state_change: Optional[Callable[[ExamState], None]] = None
    ):
        """
        Initialize exam engine.
        
        Args:
            on_violation: Callback when violation detected
            on_state_change: Callback when exam state changes
        """
        self.config = get_config()
        self.state = ExamState()
        
        self.on_violation = on_violation
        self.on_state_change = on_state_change
        
        # Initialize components
        self.authenticator = get_authenticator()
        self.supabase = get_supabase_client()
        self.uploader = get_background_uploader()
        self.buffer = get_circular_buffer()
        self.clip_extractor = get_clip_extractor()
        self.classifier = get_event_classifier()
        self.queue = get_sqlite_queue()
        
        # Set up classifier callback
        self.classifier.on_violation = self._handle_violation
        
        self.last_evidence_clip = None
        self.last_clip_time = 0
        self._lock = threading.Lock()
    
    def authenticate(self, hall_ticket: str) -> AuthResult:
        """
        Authenticate a student.
        
        Args:
            hall_ticket: Student's hall ticket number
            
        Returns:
            Authentication result
        """
        result = self.authenticator.authenticate(hall_ticket)
        
        if result.success:
            with self._lock:
                self.state.student_id = result.student_id
                self.state.student_name = result.student_name
                self.state.hall_ticket = result.hall_ticket
                self.state.exam_id = result.exam_id
                self.state.duration_minutes = result.exam_duration or 60
                
                # Fetch assignment to get lab_id
                assignment = self.supabase.get_exam_assignment(result.student_id)
                if assignment:
                    self.state.lab_id = assignment.get("lab_id")
                
                self.state.status = "AUTHENTICATED"
            
            self._notify_state_change()
            logger.info(f"Student authenticated: {hall_ticket}")
        else:
            logger.warning(f"Authentication failed: {result.error}")
        
        return result
    
    def start_instructions(self):
        """Start the instruction period."""
        with self._lock:
            self.state.status = "INSTRUCTIONS"
        
        self._notify_state_change()
        logger.info("Instruction period started")
    
    def start_exam(self) -> bool:
        """
        Start the actual exam.
        
        Returns:
            True if exam started successfully
        """
        try:
            # Create exam attempt in Supabase
            import hashlib
            import platform
            
            fingerprint = hashlib.sha256(
                f"{platform.node()}-{platform.machine()}".encode()
            ).hexdigest()[:32]
            
            attempt = self.supabase.create_exam_attempt(
                student_id=self.state.student_id,
                exam_id=self.state.exam_id,
                system_fingerprint=fingerprint
            )
            
            if not attempt:
                logger.error("Failed to create exam attempt")
                return False
            
            with self._lock:
                self.state.attempt_id = attempt["id"]
                self.state.start_time = datetime.now(timezone.utc)
                self.state.status = "ACTIVE"
            
            # Start background services
            logger.info(f"[DEBUG] About to start background uploader (type: {type(self.uploader)})")
            try:
                self.uploader.start()
                logger.info("[DEBUG] Uploader.start() call completed")
            except Exception as uploader_error:
                logger.error(f"[CRITICAL] Uploader failed to start: {uploader_error}", exc_info=True)
            
            self._notify_state_change()
            logger.info(f"Exam started: attempt {self.state.attempt_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start exam: {e}")
            return False
    
    def submit_exam(self) -> bool:
        """
        Submit the exam.
        
        Returns:
            True if submitted successfully
        """
        return self._end_exam("SUBMITTED")
    
    def terminate_exam(self, reason: str) -> bool:
        """
        Forcefully terminate the exam.
        
        Args:
            reason: Termination reason
            
        Returns:
            True if terminated successfully
        """
        logger.critical(f"Exam terminated: {reason}")
        
        # Queue evidence for upload
        # Note: The provided snippet for evidence capture here is incomplete and uses undefined variables
        # (event_time, analysis_data). To maintain syntactical correctness and fulfill the instruction
        # to remove malpractice_events logging, the original malpractice_events logging call is removed.
        # If evidence capture is desired on termination, it needs to be properly implemented with defined variables.
        
        # Original malpractice_events logging removed as per instruction.
        # if self.state.attempt_id:
        #     self.supabase.create_malpractice_event(
        #         attempt_id=self.state.attempt_id,
        #         event_type="EXAM_TERMINATED",
        #         severity=10,
        #         description=reason
        #     )
        
        return self._end_exam("TERMINATED")
    
    def _end_exam(self, status: str) -> bool:
        """End the exam with given status."""
        try:
            with self._lock:
                if self.state.status not in ("ACTIVE",):
                    return False
                
                self.state.end_time = datetime.now(timezone.utc)
                self.state.status = status
            
            # Update attempt in Supabase
            if self.state.attempt_id:
                self.supabase.update_exam_attempt(
                    attempt_id=self.state.attempt_id,
                    status=status,
                    end_time=self.state.end_time
                )
            
            # Stop services
            self.uploader.stop()
            
            self._notify_state_change()
            logger.info(f"Exam ended: {status}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to end exam: {e}")
            return False
    
    def save_answer(self, question_id: str, selected_option: int, marked_review: bool = False):
        """
        Save an answer.
        
        Args:
            question_id: Question ID
            selected_option: Selected option index
            marked_review: Whether marked for review
        """
        if not self.state.attempt_id:
            return
        
        self.supabase.save_answer(
            attempt_id=self.state.attempt_id,
            question_id=question_id,
            selected_option=selected_option,
            marked_for_review=marked_review
        )
    
    def process_advanced_violation(self, violation_data: Dict, engine_result: Dict, telemetry: Dict, clip: Optional[Any] = None):
        """
        Process a violation from the advanced AI engine and log to the combined table.
        """
        from student_app.app.ai.advanced.rules import AdvancedRuleEngine # To get type hints if needed
        
        v_type = violation_data["type"]
        v_level = violation_data["level"]
        description = violation_data["message"]
        
        logger.info(f"[ADVANCED] Processing violation: {v_type} (level {v_level})")
        
        # Log to student_ai_analysis in Supabase (or Queue)
        if self.state.attempt_id:
            payload = {
                "attempt_id": self.state.attempt_id,
                "student_id": self.state.student_id,
                "exam_id": self.state.exam_id,
                "lab_id": self.state.lab_id,  # Will be None if not set, which is valid for UUID
                "student_name": self.state.student_name,
                "hall_ticket": self.state.hall_ticket,
                "severity": self._map_level_to_severity(v_level),
                "event_type": v_type,
                "description": description,
                "telemetry_data": telemetry,
                "detected_objects": violation_data.get("detected_objects") or self._extract_objects(telemetry),
            }
            
            # Merge clip data if present
            file_path = None
            if clip:
                file_path = str(clip.file_path)
                payload.update({
                    "frame_start": clip.frame_start,
                    "frame_end": clip.frame_end,
                    "file_size_bytes": clip.file_size_bytes,
                    "storage_url": clip.file_path.name,
                })
                # Enhance telemetry with clip info
                if "telemetry_data" not in payload:
                    payload["telemetry_data"] = {}
                payload["telemetry_data"].update({
                    "duration": clip.duration_seconds,
                    "file_name": clip.file_path.name,
                    "hash": clip.hash_sha256,
                    "file_size": clip.file_size_bytes,
                    "frame_count": clip.frame_count,
                    "frame_start": clip.frame_start,
                    "frame_end": clip.frame_end
                })

            # Use local queue for robustness
            import hashlib
            
            # CRITICAL FIX: If a file is attached, the hash MUST match the file for uploader.py integrity check.
            if clip:
                payload_hash = clip.hash_sha256
                logger.info(f"[QUEUE] Using file hash for integrity: {payload_hash[:16]}...")
            elif self.last_evidence_clip and (time.time() - self.last_clip_time < 15):
                # Try to attach the cached clip if this is a confirmed violation coming soon after trigger
                # but only if the payload doesn't already have one
                cached = self.last_evidence_clip
                file_path = str(cached.file_path)
                payload_hash = cached.hash_sha256
                payload.update({
                    "frame_start": cached.frame_start,
                    "frame_end": cached.frame_end,
                    "file_size_bytes": cached.file_size_bytes,
                    "storage_url": cached.file_path.name,
                })
                # Enhance telemetry with cached clip info
                if "telemetry_data" not in payload:
                    payload["telemetry_data"] = {}
                payload["telemetry_data"].update({
                    "duration": cached.duration_seconds,
                    "file_name": cached.file_path.name,
                    "hash": cached.hash_sha256,
                    "file_size": cached.file_size_bytes,
                    "frame_count": cached.frame_count,
                    "frame_start": cached.frame_start,
                    "frame_end": cached.frame_end
                })
                logger.info(f"[CACHE] Attached cached clip {cached.file_path.name} to confirmed violation")
            else:
                payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                logger.info(f"[QUEUE] Using JSON payload hash: {payload_hash[:16]}...")

            try:
                item_id = self.queue.enqueue(
                    table_name="student_ai_analysis",
                    payload=payload,
                    hash_sha256=payload_hash,
                    file_path=file_path
                )
                logger.info(f"[QUEUE] Successfully enqueued item {item_id}")
            except Exception as e:
                logger.error(f"[QUEUE ERROR] Failed to enqueue: {e}", exc_info=True)
            
            logger.info(f"AI Violation reported for {v_type}: {description}")
        else:
            logger.warning(f"[ADVANCED] No attempt_id, skipping violation logging for {v_type}")

    def _map_level_to_severity(self, level: int) -> str:
        mapping = {1: "CLEAR", 2: "LOW", 3: "MEDIUM", 4: "HIGH", 5: "CRITICAL"}
        return mapping.get(level, "MEDIUM")

    def _extract_objects(self, telemetry: Dict) -> List[str]:
        objects = []
        if telemetry.get("phone_detected"): objects.append("mobile phone")
        if telemetry.get("book_detected"): objects.append("book/notes")
        if telemetry.get("suspicious_object"): objects.append("secondary device")
        return objects

    def trigger_evidence_capture(self, engine_result: Dict) -> Optional[Any]:
        """
        Trigger an evidence clip capture centered on the start of the violation.
        Enforces a 3-second global cooldown to prevent data loss.
        """
        now = time.time()
        
        # 1. Enforce Cooldown (3 seconds)
        if now - self.state.last_evidence_time < 3:
            return None
            
        evidence_ts = engine_result.get("evidence_timestamp", now)
        # Convert float timestamp to datetime
        event_time = datetime.fromtimestamp(evidence_ts)
        
        # Context from the rule engine
        trigger_type = engine_result.get("trigger_type", "evidence_clip")
        trigger_level = engine_result.get("trigger_level", 4) # Default to HIGH
        
        # Map level to severity string for Supabase
        severity_map = {1: "INFO", 2: "LOW", 3: "MEDIUM", 4: "HIGH", 5: "CRITICAL"}
        severity_str = severity_map.get(trigger_level, "EVIDENCE")
        
        try:
            logger.info(f"📹 Evidence extraction triggered for {trigger_type} at {event_time}")
            clip = self.clip_extractor.extract_around_event(
                event_time=event_time,
                buffer=self.buffer
            )
            
            if clip and self.state.attempt_id:
                self.state.last_evidence_time = now # Update cooldown
                self.last_evidence_clip = clip
                self.last_clip_time = now
                logger.info(f"📹 Evidence extraction successful for {trigger_type} ({severity_str})")
                return clip
            
            return None
        except Exception as e:
            logger.error(f"Failed to capture evidence clip: {e}")

    def add_detection_event(self, event: DetectionEvent):
        """Add a detection event to the classifier."""
        if hasattr(self, 'classifier'):
            self.classifier.add_event(event)

    def _handle_violation(self, violation: Violation):
        """Handle a detected violation from the OLD classifier."""
        with self._lock:
            self.state.violations.append(violation)
        
        # REDIRECT to new unified logging system
        logger.info(f"[OLD CLASSIFIER] Redirecting violation to student_ai_analysis: {violation.violation_type}")
        
        violation_data = {
            "type": violation.violation_type,
            "level": min(5, max(1, violation.severity // 2)),  # Map 0-10 to 1-5
            "message": violation.description
        }
        
        telemetry = {
            "source": "legacy_classifier",
            "severity_raw": violation.severity
        }
        
        # Use the new unified handler
        self.process_advanced_violation(violation_data, {}, telemetry)
        
        # Also trigger evidence if severe
        if violation.severity >= 7 and violation.evidence_start:
            self._extract_evidence(violation)

        
        # Notify UI
        if self.on_violation:
            self.on_violation(violation)
        
        # Check for auto-termination
        if violation.severity >= 10 or len(self.state.violations) >= 3:
            high_severity = [v for v in self.state.violations if v.severity >= 8]
            if len(high_severity) >= 3:
                self.terminate_exam("Too many severe violations")
    
    def _extract_evidence(self, violation: Violation):
        """Extract and queue evidence for upload."""
        try:
            clip = self.clip_extractor.extract_around_event(
                event_time=violation.occurred_at,
                buffer=self.buffer
            )
            
            if clip:
                # Queue for upload
                import hashlib
                
                self.queue.enqueue(
                    table_name="evidence",
                    payload={
                        "attempt_id": self.state.attempt_id,
                        "event_type": violation.violation_type,
                        "captured_at": clip.start_time.isoformat(),
                        "duration_seconds": clip.duration_seconds,
                        "file_hash": clip.hash_sha256,
                        "storage_url": ""  # Will be filled by uploader
                    },
                    hash_sha256=clip.hash_sha256,
                    file_path=str(clip.file_path)
                )
                
                logger.info(f"Evidence queued: {clip.file_path.name}")
                
        except Exception as e:
            logger.error(f"Evidence extraction failed: {e}")
    
    def _notify_state_change(self):
        """Notify listeners of state change."""
        if self.on_state_change:
            self.on_state_change(self.state)
    
    def get_questions(self) -> List[Dict[str, Any]]:
        """Get exam questions."""
        if not self.state.exam_id:
            return []
        
        return self.supabase.get_exam_questions(self.state.exam_id)
    
    def get_remaining_time(self) -> int:
        """Get remaining time in seconds."""
        if not self.state.start_time:
            return self.state.duration_minutes * 60
        
        elapsed = (datetime.now(timezone.utc) - self.state.start_time).total_seconds()
        remaining = (self.state.duration_minutes * 60) - elapsed
        
        return max(0, int(remaining))
    
    def is_exam_active(self) -> bool:
        """Check if exam is currently active."""
        return self.state.status == "ACTIVE"


# Global instance
_engine: Optional[ExamEngine] = None


def get_exam_engine() -> ExamEngine:
    """Get global exam engine instance."""
    global _engine
    if _engine is None:
        _engine = ExamEngine()
    return _engine
