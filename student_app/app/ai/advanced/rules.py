import time
import logging
from typing import Dict, List, Any
from .verify import AdvancedHybridVerifier

logger = logging.getLogger(__name__)

class AdvancedRuleEngine:
    """
    Unified Rule Engine for interpreting multi-sensor proctoring data.
    Aligns with industry standards for violation naming and risk calculation.
    """
    
    def __init__(self):
        # Risk thresholds (0-100)
        self.risk_score = 0
        self.session_risk_score = 0
        
        # Violation tracking for throttling and sequence detection
        self.last_report_times = {}
        self.violation_start_times = {}
        self.confirmed_violations = {} # Gemini confirmed
        self.pending_verifications = {}
        
        # Points mapping (Industry Standard Weights)
        self.points = {
            "phone_detected": 100,  # Critical
            "book_detected": 40,    # High
            "multiple_faces": 80,   # High
            "suspicious_object": 60,# High
            "gaze_deviation": 15,   # Medium
            "audio_spike": 5,       # Low
            "candidate_absent": 20, # Medium
            "focus_loss": 12        # Medium
        }
        
        # Hybrid Verifier (Gemini)
        self.verifier = AdvancedHybridVerifier()
        
        self.last_decay_time = time.time()
        self.decay_rate = 5 # pts/sec - Matches reference system

    def _apply_decay(self, now):
        """Gradually decrease risk score when behavior is clean."""
        elapsed = now - self.last_decay_time
        if elapsed > 1.0:
            decay_amount = elapsed * self.decay_rate
            self.risk_score = max(0, self.risk_score - decay_amount)
            self.last_decay_time = now

    def process_detection(self, detection_data, frame=None):
        now = time.time()
        self._apply_decay(now)
        
        violations = []
        score_increase = 0
        trigger_evidence = False
        evidence_timestamp = now
        
        # Trigger Metadata to pass to ExamEngine
        trigger_type = None
        trigger_level = 0
        
        # 1. Update Start Times for active detections
        for key, active in detection_data.items():
            if active and key not in self.violation_start_times:
                self.violation_start_times[key] = now
            elif not active and key in self.violation_start_times:
                del self.violation_start_times[key]

        # 2. AI Verification (Gemini) - Sequential Triggering
        check_targets = []
        if detection_data.get("phone_detected"): check_targets.append("mobile phone")
        if detection_data.get("book_detected"): check_targets.append("book/notes")
        if detection_data.get("multiple_faces"): check_targets.append("multiple people")
        if detection_data.get("suspicious_object"): check_targets.append("suspicious object")
        
        # 2a. Initiate Verification for objects in view
        for target in check_targets:
            v_key = target.lower()
            if v_key not in self.confirmed_violations and v_key not in self.pending_verifications:
                if frame is not None:
                    # Save the start time of the local detection to center the clip later
                    local_key = v_key.replace("mobile phone", "phone_detected").replace("book/notes", "book_detected").replace("multiple people", "multiple_faces").replace("suspicious object", "suspicious_object")
                    start_time = self.violation_start_times.get(local_key, now)
                    
                    self.pending_verifications[v_key] = start_time
                    self.verifier.verify_frame_async(
                        frame, target, self._on_verified, self._on_rejected
                    )
                
                # Silent evidence trigger (no violation log until confirmed)
                trigger_evidence = True
                score_increase += 2

        # 2b. Process Confirmed Results (Persistent even if object hidden)
        for v_key in list(self.confirmed_violations.keys()):
            details = self.confirmed_violations[v_key]
            v_type = details.get("v_type", v_key.replace(" ", "_").upper())
            pts = self.points.get(v_type.lower(), 100)
            
            # Check Throttling for DB reporting
            if now - self.last_report_times.get(v_type, 0) > 10:
                violations.append({
                    "type": v_type,
                    "level": 5 if pts >= 100 else 4,
                    "message": f"CRITICAL (AI Verified): {details['reason']}",
                    "detected_objects": details.get("objects", [])
                })
                self.last_report_times[v_type] = now
                evidence_timestamp = details["start_time"]
                # We don't trigger new evidence here, we rely on the one triggered at 2a
                # trigger_evidence = False 
            
            score_increase += pts
            
            # If the object is no longer in view, we decay the entry after 15s
            # but we keep it around long enough to ensure it's logged at least once
            if v_key not in [t.lower() for t in check_targets]:
                if now - details["time"] > 15:
                    del self.confirmed_violations[v_key]

        # 3. Local Behavioral Checks (Immediate Triggering)
        if detection_data.get("candidate_absent"):
            pts = self.points.get("candidate_absent", 20)
            if now - self.last_report_times.get("CANDIDATE_ABSENT", 0) > 15:
                violations.append({"type": "CANDIDATE_ABSENT", "level": 4, "message": "Candidate absent from camera view"})
                self.last_report_times["CANDIDATE_ABSENT"] = now
                trigger_evidence = True
                evidence_timestamp = self.violation_start_times.get("candidate_absent", now)
            score_increase += pts

        if detection_data.get("multiple_faces") and "multiple people" not in self.confirmed_violations:
            if now - self.last_report_times.get("MULTIPLE_PEOPLE_DETECTED", 0) > 15:
                violations.append({"type": "MULTIPLE_PEOPLE_DETECTED", "level": 4, "message": "Multiple people detected in frame"})
                self.last_report_times["MULTIPLE_PEOPLE_DETECTED"] = now
                trigger_evidence = True
                evidence_timestamp = self.violation_start_times.get("multiple_faces", now)
            score_increase += 50

        if detection_data.get("audio_spike"):
            if now - self.last_report_times.get("SPEECH_DETECTED", 0) > 15:
                violations.append({"type": "SPEECH_DETECTED", "level": 3, "message": "Significant voice activity detected"})
                self.last_report_times["SPEECH_DETECTED"] = now
            score_increase += self.points.get("audio_spike", 5)

        if detection_data.get("focus_loss"):
            if now - self.last_report_times.get("WINDOW_FOCUS_LOST", 0) > 15:
                violations.append({"type": "WINDOW_FOCUS_LOST", "level": 3, "message": "Application lost focus"})
                self.last_report_times["WINDOW_FOCUS_LOST"] = now
            score_increase += self.points.get("focus_loss", 12)

        # 4. Gaze and Head Pose (Direction-specific)
        if detection_data.get("gaze_deviation") or detection_data.get("head_orientation_issue"):
            g_label = detection_data.get("gaze_label", "GAZE")
            h_label = detection_data.get("head_label", "HEAD")
            
            direction = "AWAY"
            if "LEFT" in g_label or "LEFT" in h_label: direction = "LEFT"
            elif "RIGHT" in g_label or "RIGHT" in h_label: direction = "RIGHT"
            elif "UP" in g_label or "UP" in h_label: direction = "UP"
            elif "DOWN" in g_label or "DOWN" in h_label: direction = "DOWN"
            
            v_type = f"LOOKING_{direction}"
            if now - self.last_report_times.get(v_type, 0) > 10:
                violations.append({"type": v_type, "level": 4, "message": f"Visual attention diverted: {direction}"})
                self.last_report_times[v_type] = now
                trigger_evidence = True
                evidence_timestamp = min(self.violation_start_times.get("gaze_deviation", now), 
                                      self.violation_start_times.get("head_orientation_issue", now))
            score_increase += self.points.get("gaze_deviation", 20)

        # Update Scores
        if score_increase > 0:
            self.risk_score = min(100, max(self.risk_score, score_increase))
        self.session_risk_score = max(self.session_risk_score, self.risk_score)
        
        # Identify Primary Trigger for Evidence
        if trigger_evidence:
            if violations:
                # Get highest level violation to represent the clip
                top_v = max(violations, key=lambda x: x.get("level", 0))
                trigger_type = top_v["type"]
                trigger_level = top_v["level"]
            else:
                # Default "Suspicious Activity" if silent trigger (e.g. mobile verification started)
                trigger_type = "SUSPICIOUS_OBJECT_VERIFICATION"
                trigger_level = 2

        # Cleanup confirmed violations after 15s delay
        to_remove = [k for k, v in self.confirmed_violations.items() if now - v["time"] > 15]
        for k in to_remove: del self.confirmed_violations[k]
        
        return {
            "current_risk": self.risk_score,
            "risk_level": self._get_band(self.risk_score),
            "session_risk": self.session_risk_score,
            "session_band": self._get_band(self.session_risk_score),
            "violations": violations,
            "trigger_evidence": trigger_evidence,
            "evidence_timestamp": evidence_timestamp,
            "trigger_type": trigger_type,
            "trigger_level": trigger_level
        }

    def _get_band(self, score):
        if score < 15: return "low"
        if score < 45: return "medium"
        if score < 75: return "high"
        return "critical"

    def _on_verified(self, detection_type, reason):
        """Callback for successful AI verification."""
        v_key = detection_type.lower()
        start_time = self.pending_verifications.get(v_key, time.time())
        if v_key in self.pending_verifications: del self.pending_verifications[v_key]
        
        # Industry standard mapping for verified objects
        v_type_map = {
            "mobile phone": "VERIFIED_MOBILE_PHONE",
            "book/notes": "UNAUTHORIZED_MATERIAL",
            "multiple people": "MULTIPLE_PEOPLE_CONFIRMED",
            "suspicious object": "PROHIBITED_ITEM_DETECTED"
        }
        
        # Use Reason to refine naming if possible
        v_type = v_type_map.get(v_key, v_key.replace(" ", "_").upper())
        reason_upper = reason.upper()
        
        # KEYWORD PROMOTION: Refine naming based on Gemini's discovery
        if any(kw in reason_upper for kw in ["EARBUD", "EARPHONE", "EARDOPE", "AIRPOD", "HEADPHONE"]):
            v_key = "earbuds" # Promote the key so we don't spam mobile/earbuds duplicates
            v_type = "EARBUDS_DETECTED"
        elif any(kw in reason_upper for kw in ["SMARTWATCH", "WATCH", "WRIST DEVICE", "GLUCOSE MONITOR"]):
            v_key = "smartwatch"
            v_type = "SMARTWATCH_DETECTED"
        elif any(kw in reason_upper for kw in ["BOOK", "PAPER", "NOTE", "PAGE", "DOCUMENT"]):
            v_key = "book/notes"
            v_type = "UNAUTHORIZED_MATERIAL"
        elif any(kw in reason_upper for kw in ["TABLET", "IPAD", "KINDLE", "SECONDARY MONITOR"]):
            v_key = "suspicious object"
            v_type = "PROHIBITED_ITEM_DETECTED"

        # Parse objects from reason if possible for DB column
        objects = []
        reason_lower = reason.lower()
        if "phone" in reason_lower: objects.append("cell phone")
        if any(kw in reason_lower for kw in ["book", "paper", "note", "page"]): objects.append("book/paper")
        if any(kw in reason_lower for kw in ["earbud", "earphone", "airpod"]): objects.append("earbuds")
        if "watch" in reason_lower: objects.append("smartwatch")

        self.confirmed_violations[v_key] = {
            "time": time.time(),
            "start_time": start_time,
            "reason": reason,
            "v_type": v_type,
            "objects": objects
        }
        logger.info(f"AI VERIFIED: {detection_type} -> {v_type} ({reason})")

    def _on_rejected(self, detection_type, reason):
        """Callback for AI rejection (false positive)."""
        v_key = detection_type.lower()
        if v_key in self.pending_verifications: del self.pending_verifications[v_key]
        logger.info(f"AI REJECTED: {detection_type} ({reason})")
