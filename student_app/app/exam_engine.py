"""
Student Exam Application - Exam Engine

Core exam management and orchestration.
"""

import logging
import threading
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
    exam_id: Optional[str] = None
    attempt_id: Optional[str] = None
    status: str = "IDLE"  # IDLE, AUTHENTICATED, INSTRUCTIONS, ACTIVE, SUBMITTED, TERMINATED
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_minutes: int = 60
    violations: List[Violation] = None
    
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
                self.state.exam_id = result.exam_id
                self.state.duration_minutes = result.exam_duration or 60
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
            self.uploader.start()
            
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
        
        # Record termination event
        if self.state.attempt_id:
            self.supabase.create_malpractice_event(
                attempt_id=self.state.attempt_id,
                event_type="EXAM_TERMINATED",
                severity=10,
                description=reason
            )
        
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
    
    def add_detection_event(self, event: DetectionEvent):
        """
        Add a detection event from AI services.
        
        Args:
            event: Detection event
        """
        self.classifier.add_event(event)
    
    def _handle_violation(self, violation: Violation):
        """Handle a detected violation."""
        with self._lock:
            self.state.violations.append(violation)
        
        # Record in Supabase
        if self.state.attempt_id:
            self.supabase.create_malpractice_event(
                attempt_id=self.state.attempt_id,
                event_type=violation.violation_type,
                severity=violation.severity,
                description=violation.description
            )
            
            # Extract evidence clip if severe
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
