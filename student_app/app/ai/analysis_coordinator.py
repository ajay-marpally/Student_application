"""
Student Exam Application - AI: Analysis Coordinator

Orchestrates all AI detectors, ports the RuleEngine logic from main.py,
and handles logging to the student_ai_analysis staging table.
"""

import logging
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from pathlib import Path

from student_app.app.config import get_config
from student_app.app.storage.supabase_client import get_supabase_client
from student_app.app.buffer.circular_buffer import get_circular_buffer
from student_app.app.ai.event_classifier import EventType
from student_app.app.ai.hybrid_verifier import get_hybrid_verifier

logger = logging.getLogger(__name__)

class AnalysisCoordinator:
    """
    The 'Brain' of the proctoring system.
    
    Responsibilities:
    1. Port RuleEngine logic (0-100 risk score, decay, bands).
    2. Orchestrate Heartbeat logging (every 5s).
    3. Orchestrate Incident logging (Severity >= HIGH).
    4. Handle Terminal Logging (Emoji style for debug parity).
    5. Trigger Evidence Capture & Upload.
    """
    
    def __init__(self, attempt_id: str, student_data: Dict[str, Any]):
        self.attempt_id = attempt_id
        # student_data contains: student_id, exam_id, lab_id, name, hall_ticket
        self.student_data = student_data
        self.config = get_config()
        self.supabase = get_supabase_client()
        self.buffer = get_circular_buffer()
        self.verifier = get_hybrid_verifier()
        
        # Risk Scoring State (Ported from main.py)
        self.risk_score = 0.0
        self.session_risk_score = 0.0
        self.last_decay_time = time.time()
        self.last_heartbeat_time = 0.0
        self.heartbeat_interval = 5.0  # Seconds
        
        # Incident Tracking
        self.last_incident_time = 0.0
        self.incident_cooldown = 15.0  # Seconds
        self.pending_verifications = {} # v_key -> timestamp
        self.confirmed_violations = {}  # v_key -> record (reason, time)
        
        # Aggregation state for heartbeats
        self.aggregated_events = set()
        
        # Define detector types (matching main.py logic)
        self.AI_TYPES = ["phone_detected", "book_detected", "multiple_faces", "suspicious_object", "impersonation_suspected"]
        
        # Locks for thread safety
        self._lock = threading.Lock()
        
        logger.info(f"AnalysisCoordinator initialized for attempt: {attempt_id}")
        self._log_ai_status()

    def _log_ai_status(self):
        """Log a summary of which AI components are active."""
        from student_app.app.ai.head_pose import get_head_pose_estimator
        from student_app.app.ai.gaze import get_gaze_tracker
        from student_app.app.ai.audio_monitor import get_audio_monitor
        from student_app.app.ai.object_detector import get_object_detector
        
        status = {
            "Object Detection (YOLO)": "ACTIVE" if get_object_detector().enabled else "OFF",
            "Head Pose (MediaPipe)": "ACTIVE" if get_head_pose_estimator().enabled else "OFF (MISSING LIB)",
            "Gaze Tracking (MediaPipe)": "ACTIVE" if get_gaze_tracker().enabled else "OFF (MISSING LIB)",
            "Audio Analysis (Silero)": "ACTIVE" if get_audio_monitor().vad_model else "FALLBACK (ENERGY)",
            "Hybrid Verification": "ACTIVE" if self.verifier.enabled else "OFF (NO API KEY)"
        }
        
        self.log_message("📊 AI SYSTEMS STATUS SUMMARY:")
        for component, state in status.items():
            self.log_message(f"  - {component}: {state}")
        self.log_message("------------------------------------------------------------")

    def log_message(self, message: str):
        """Standard emoji-style log for terminal debugging parity."""
        # Using print directly for immediate terminal feedback as requested by user
        current_time = datetime.now().strftime('%H:%M:%S')
        print(f"[{current_time}] {message}", flush=True)
        logger.info(message)
        
        # ALSO write to the dedicated debug log file
        try:
            debug_log = self.config.data_dir / "proctor_debug.log"
            debug_log.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] {message}\n")
                f.flush()
        except:
            pass

    def _get_risk_band(self, score: float) -> str:
        """Map score to severity band."""
        bands = self.config.thresholds.RISK_BANDS
        if score >= bands["critical"]: return "CRITICAL"
        if score >= bands["high"]: return "HIGH"
        if score >= bands["medium"]: return "MEDIUM"
        if score >= bands["low"]: return "LOW"
        return "CLEAR"

    def apply_decay(self):
        """Apply risk decay (Ported from main.py)."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_decay_time
            if elapsed >= 1.0:
                decay = self.config.thresholds.RISK_DECAY_PER_SEC * elapsed
                self.risk_score = max(0, self.risk_score - decay)
                self.last_decay_time = now

    def process_events(self, events: List[Any], telemetry: Dict[str, Any]):
        """
        Process detection events and update state with strict Gemini verification for objects.
        """
        with self._lock:
            self.apply_decay()
            
            score_increase = 0
            event_descriptions = []
            ai_targets_to_verify = []
            
            # 1. Classify Events
            for event in events:
                event_key = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                points = self.config.thresholds.VIOLATION_POINTS.get(event_key, 0)
                
                if event_key in self.AI_TYPES:
                    # AI Object detection - ALWAYS requires Gemini verification
                    ai_targets_to_verify.append(event_key)
                    # While pending, we only add a tiny points bump to show activity
                    score_increase = max(score_increase, 2.0)
                    event_descriptions.append(f"Verifying {event_key}...")
                else:
                    # Behavioral detection - Behavioral/Automatic (Gaze, Head, Absence, etc.)
                    score_increase = max(score_increase, points)
                    event_descriptions.append(event_key)
            
            # 2. Check for Confirmed AI Violations (Expired after 15s)
            now_ts = time.time()
            for vtype in list(self.confirmed_violations.keys()):
                if now_ts - self.confirmed_violations[vtype]["time"] > 15.0:
                    del self.confirmed_violations[vtype]
            
            # If AI was already confirmed, promote it to full points
            for target in ai_targets_to_verify:
                if target in self.confirmed_violations:
                    points = self.config.thresholds.VIOLATION_POINTS.get(target, 100)
                    score_increase = max(score_increase, points)
                    desc = f"(AI Verified) {target}: {self.confirmed_violations[target]['reason']}"
                    if desc not in event_descriptions:
                        event_descriptions.append(desc)

            # 3. Update Risk State
            if score_increase > 0:
                self.risk_score = max(self.risk_score, score_increase)
                self.session_risk_score = max(self.session_risk_score, self.risk_score)
            
            current_severity = self._get_risk_band(self.risk_score)

            # 4. Immediate Terminal Log for violations (even if not heartbeat time)
            if event_descriptions and score_increase > 0:
                emoji = "🚨" if current_severity in ["HIGH", "CRITICAL"] else "⚠️"
                message = f"{emoji} [DETECTION] Risk: {self.risk_score:.1f} ({current_severity}) | Events: {', '.join(event_descriptions)}"
                self.log_message(message)

            # 5. Trigger Gemini for new AI targets
            if self.verifier.enabled:
                for target in ai_targets_to_verify:
                    if target not in self.pending_verifications and target not in self.confirmed_violations:
                        self._trigger_gemini_verification(target, telemetry)

            # 6. Heartbeat Logging (Terminal + DB) - Periodic status sync
            if now_ts - self.last_heartbeat_time >= self.heartbeat_interval:
                heartbeat_events = list(event_descriptions) or ["MONITOR_OK"]
                self._send_heartbeat(current_severity, telemetry, heartbeat_events)
                self.last_heartbeat_time = now_ts
                
            # 7. Incident Handling (Immediate for Behavioral High/Critical, or Confirmed AI)
            # LOGIC: Only trigger incident if it's a non-AI high violation OR a confirmed AI violation
            has_urgent_behavioral = any(e.event_type.value not in self.AI_TYPES and 
                                         self.config.thresholds.VIOLATION_POINTS.get(e.event_type.value, 0) >= self.config.thresholds.RISK_BANDS["high"] 
                                         for e in events)
            
            has_confirmed_ai = any(t in self.confirmed_violations for t in ai_targets_to_verify)
            
            if (has_urgent_behavioral or has_confirmed_ai) and current_severity in ["HIGH", "CRITICAL"]:
                if now_ts - self.last_incident_time >= self.incident_cooldown:
                    confirmed_descs = [d for d in event_descriptions if "Verifying" not in d]
                    if confirmed_descs:
                        self._handle_incident(current_severity, telemetry, confirmed_descs)
                        self.last_incident_time = now_ts

    def _trigger_gemini_verification(self, target: str, telemetry: Dict[str, Any]):
        """Trigger asynchronous Gemini verification."""
        self.pending_verifications[target] = time.time()
        self.log_message(f"🤖 AI CROSS-CHECK: Verifying {target}...")
        
        frames = self.buffer.get_frames_around(datetime.now(), padding_seconds=0.5)
        if not frames:
            return
            
        frame = frames[-1].frame
        
        def on_verified(is_violation, feedback):
            with self._lock:
                if target in self.pending_verifications:
                    del self.pending_verifications[target]
                
                if is_violation:
                    self.log_message(f"✅ AI CONFIRMED: {target} ({feedback})")
                    self.confirmed_violations[target] = {
                        "time": time.time(),
                        "reason": feedback
                    }
                    # We don't log the incident here; the next loop cycle will see it in confirmed_violations
                else:
                    self.log_message(f"🛡️ AI CROSS-CHECK: [REJECTED] {target}. Reason: {feedback}")
                    # Keep risk score low for this target in next cycle
        
        self.verifier.verify_async(frame, target, on_verified)

    def _send_heartbeat(self, severity: str, telemetry: Dict[str, Any], events: List[str]):
        """Log heartbeat to DB and Terminal."""
        emoji = "✅" if severity == "CLEAR" else "⚠️"
        event_str = f" | Events: {', '.join(events)}" if events else ""
        
        # Terminal Log (User Parity)
        self.log_message(f"{emoji} Risk: {self.risk_score:.1f} ({severity}) {event_str}")
        
        # DB Log
        payload = {
            "attempt_id": self.attempt_id,
            "student_id": self.student_data["student_id"],
            "exam_id": self.student_data["exam_id"],
            "lab_id": self.student_data.get("lab_id"),
            "student_name": self.student_data.get("name"),
            "hall_ticket": self.student_data.get("hall_ticket"),
            "severity": severity,
            "event_type": "MONITOR_OK" if severity == "CLEAR" else "TELEMETRY",
            "description": f"AI Status Check: {severity}",
            "telemetry_data": telemetry,
            "occurred_at": datetime.now(timezone.utc).isoformat()
        }
        self.supabase.log_ai_analysis(payload)

    def _handle_incident(self, severity: str, telemetry: Dict[str, Any], events: List[str]):
        """Capture evidence and log high-severity incident."""
        self.log_message(f"📹 Evidence Triggered: {severity} ({', '.join(events)})")
        
        # 1. Generate Clip
        clip_path = self._generate_evidence_clip(severity)
        
        storage_url = None
        if clip_path and clip_path.exists():
            # 2. Upload to Supabase
            storage_url = self.supabase.upload_evidence_file(clip_path)
            
        # 3. Log Incident to DB
        raw_event = events[0] if events else "INCIDENT"
        event_type = raw_event.replace("(AI Verified) ", "").upper()
        
        payload = {
            "attempt_id": self.attempt_id,
            "student_id": self.student_data["student_id"],
            "exam_id": self.student_data["exam_id"],
            "lab_id": self.student_data.get("lab_id"),
            "student_name": self.student_data.get("name"),
            "hall_ticket": self.student_data.get("hall_ticket"),
            "severity": severity,
            "event_type": event_type,
            "description": f"Incident Detected: {', '.join(events)}",
            "telemetry_data": telemetry,
            "storage_url": storage_url,
            "review_status": "PENDING",
            "occurred_at": datetime.now(timezone.utc).isoformat()
        }
        self.supabase.log_ai_analysis(payload)

    def _generate_evidence_clip(self, severity: str) -> Optional[Path]:
        """Extract MP4 clip from circular buffer."""
        try:
            now = datetime.now()
            # Get 10s clip around now
            # circular_buffer returns BufferedFrame objects
            frames = self.buffer.get_frames_around(now, padding_seconds=5.0)
            
            if not frames:
                logger.warning("No frames in buffer for evidence clip")
                return None
            
            ts = now.strftime("%Y%m%d_%H%M%S")
            filename = f"evidence_{self.attempt_id[:8]}_{ts}_{severity.lower()}.mp4"
            filepath = self.config.evidence_dir / filename
            
            import cv2
            h, w = frames[0].frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(str(filepath), fourcc, 10.0, (w, h))
            
            for f in frames:
                out.write(f.frame)
            out.release()
            
            return filepath
        except Exception as e:
            logger.error(f"Error generating clip: {e}")
            return None
