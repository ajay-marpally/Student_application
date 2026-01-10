"""
Student Exam Application - AI: Event Classifier

Rule engine for classifying and aggregating detection events into
malpractice violations with severity scoring.
"""

import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import threading

from student_app.app.config import get_config

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of detection events."""
    # Head pose
    HEAD_LEFT = "head_left_rotation"
    HEAD_RIGHT = "head_right_rotation"
    HEAD_UP = "head_up"
    HEAD_DOWN = "head_down"
    
    # Face
    FACE_ABSENT = "face_absent"
    FACE_MULTIPLE = "multiple_faces"
    FACE_OCCLUDED = "face_occluded"
    
    # Gaze
    GAZE_AWAY = "gaze_away"
    EYES_CLOSED = "eyes_closed"
    
    # Object
    PHONE_DETECTED = "phone_detected"
    OBJECT_DETECTED = "suspicious_object"
    
    # Audio
    VOICE_DETECTED = "voice_detected"
    MULTI_VOICE = "multiple_voices"
    
    # System
    APP_SWITCH = "application_switch"
    SCREEN_CAPTURE = "screen_capture_detected"
    REMOTE_DESKTOP = "remote_desktop_detected"
    
    # Movement
    PERSON_SWAP = "person_swap"
    MOTION_DETECTED = "excessive_motion"
    
    # Biometric
    IMPERSONATION = "impersonation_suspected"


@dataclass
class DetectionEvent:
    """A single detection event."""
    event_type: EventType
    timestamp: datetime
    confidence: float
    duration_ms: float = 0
    details: Optional[Dict[str, Any]] = None
    
    @property
    def timestamp_iso(self) -> str:
        return self.timestamp.isoformat()


@dataclass
class Violation:
    """A classified malpractice violation."""
    violation_type: str
    severity: int  # 1-10
    description: str
    events: List[DetectionEvent] = field(default_factory=list)
    occurred_at: datetime = field(default_factory=datetime.now)
    evidence_start: Optional[datetime] = None
    evidence_end: Optional[datetime] = None
    
    def __post_init__(self):
        # Calculate evidence window from events
        if self.events:
            timestamps = [e.timestamp for e in self.events]
            self.evidence_start = min(timestamps)
            self.evidence_end = max(timestamps)


class EventClassifier:
    """
    Rule engine for classifying detection events into violations.
    
    Implements all 10 detection scenarios:
    1. Frequency-based head turns (5-min window)
    2. High-duration head rotation (>8s)
    3. Combined patterns
    4. Burst-based (30s windows)
    5. Face occlusion/absent
    6. Gaze-away
    7. Phone/object detection
    8. Multiple voices
    9. Application switch
    10. Seat swap/multiple people
    """
    
    def __init__(self):
        """
        Initialize event classifier.
        """
        self._lock = threading.Lock()
        self._listeners = []
        self.config = get_config().thresholds
        
        # Event storage with thread-safe access
        self._lock = threading.Lock()
        
        # Time-windowed event queues
        self._events: Dict[EventType, deque] = {}
        for event_type in EventType:
            self._events[event_type] = deque(maxlen=1000)
        
        # Ongoing state tracking
        self._current_head_rotation_start: Optional[datetime] = None
        self._current_head_rotation_direction: Optional[str] = None
        self._current_face_absent_start: Optional[datetime] = None
        self._current_gaze_away_start: Optional[datetime] = None
        
        # Violation tracking
        self._recent_violations: deque = deque(maxlen=100)
        self._warning_count = 0
        
        # Burst tracking for 30s windows
        self._burst_windows: Dict[str, List[datetime]] = {}
    
    def add_event(self, event: DetectionEvent):
        """
        Add a detection event for classification.
        
        Args:
            event: The detection event to process
        """
        with self._lock:
            # Store event
            self._events[event.event_type].append(event)
            
            # Process based on event type
            self._process_event(event)
    
    def _process_event(self, event: DetectionEvent):
        """Process a single event through the rule engine."""
        
        # Route to appropriate handler
        handlers = {
            EventType.HEAD_LEFT: self._handle_head_rotation,
            EventType.HEAD_RIGHT: self._handle_head_rotation,
            EventType.HEAD_UP: self._handle_head_rotation,
            EventType.HEAD_DOWN: self._handle_head_rotation,
            EventType.FACE_ABSENT: self._handle_face_absent,
            EventType.FACE_MULTIPLE: self._handle_multiple_faces,
            EventType.GAZE_AWAY: self._handle_gaze_away,
            EventType.PHONE_DETECTED: self._handle_phone_detected,
            EventType.VOICE_DETECTED: self._handle_voice_detected,
            EventType.MULTI_VOICE: self._handle_multi_voice,
            EventType.APP_SWITCH: self._handle_app_switch,
            EventType.PERSON_SWAP: self._handle_person_swap,
            EventType.IMPERSONATION: self._handle_impersonation,
            EventType.MOTION_DETECTED: self._handle_motion_detected,
        }
        
        handler = handlers.get(event.event_type)
        if handler:
            handler(event)
    
    # ==================== Scenario 1 & 2: Head Rotation ====================
    
    def _handle_head_rotation(self, event: DetectionEvent):
        """Handle head rotation events (Scenarios 1, 2, 4)."""
        if event.event_type == EventType.HEAD_LEFT: direction = "left"
        elif event.event_type == EventType.HEAD_RIGHT: direction = "right"
        elif event.event_type == EventType.HEAD_UP: direction = "up"
        else: direction = "down"
        
        # Track ongoing rotation for duration-based detection (Scenario 2)
        if self._current_head_rotation_direction == direction:
            # Continuing rotation
            if self._current_head_rotation_start:
                duration = (event.timestamp - self._current_head_rotation_start).total_seconds()
                
                # Scenario 2: Long duration rotation
                if duration >= self.config.DURATION_HIGH_SECONDS:
                    self._create_violation(
                        violation_type="high_duration_head_rotation",
                        severity=8,
                        description=f"Head turned {direction} for {duration:.1f} seconds",
                        events=[event],
                        evidence_start=self._current_head_rotation_start
                    )
                    # Reset tracking
                    self._current_head_rotation_start = None
        else:
            # New rotation direction
            self._current_head_rotation_direction = direction
            self._current_head_rotation_start = event.timestamp
        
        # Scenario 1: Frequency-based detection (5-minute window)
        self._check_frequency_based_violation(event)
        
        # Scenario 4: Burst-based detection (30-second window)
        self._check_burst_violation(event)
    
    def _check_frequency_based_violation(self, event: DetectionEvent):
        """Scenario 1: Check frequency of head turns in 5-minute window."""
        window = timedelta(minutes=5)
        cutoff = event.timestamp - window
        
        # Count events in window
        count = 0
        for e in list(self._events[EventType.HEAD_LEFT]) + list(self._events[EventType.HEAD_RIGHT]):
            if e.timestamp >= cutoff:
                count += 1
        
        if count >= self.config.TH_FREQ:
            # Calculate severity based on count
            severity = min(10, 4 + (count - self.config.TH_FREQ))
            
            self._create_violation(
                violation_type="frequent_head_rotation",
                severity=severity,
                description=f"{count} head rotations in 5 minutes (threshold: {self.config.TH_FREQ})",
                events=self._get_recent_events([
                    EventType.HEAD_LEFT, EventType.HEAD_RIGHT, 
                    EventType.HEAD_UP, EventType.HEAD_DOWN
                ], window)
            )
    
    def _check_burst_violation(self, event: DetectionEvent):
        """Scenario 4: Check for burst of rotations in 30-second window."""
        window = timedelta(seconds=30)
        cutoff = event.timestamp - window
        
        # Count events in window
        count = 0
        for e in list(self._events[EventType.HEAD_LEFT]) + list(self._events[EventType.HEAD_RIGHT]):
            if e.timestamp >= cutoff:
                count += 1
        
        if count >= self.config.TH_BURST:
            self._create_violation(
                violation_type="burst_head_rotation",
                severity=6,
                description=f"{count} head rotations in 30 seconds (threshold: {self.config.TH_BURST})",
                events=self._get_recent_events([
                    EventType.HEAD_LEFT, EventType.HEAD_RIGHT,
                    EventType.HEAD_UP, EventType.HEAD_DOWN
                ], window)
            )
    
    # ==================== Scenario 5: Face Absent/Occluded ====================
    
    def _handle_face_absent(self, event: DetectionEvent):
        """Handle face absent events (Scenario 5)."""
        if self._current_face_absent_start is None:
            self._current_face_absent_start = event.timestamp
        else:
            duration = (event.timestamp - self._current_face_absent_start).total_seconds()
            
            if duration >= self.config.T_ABSENT_SECONDS:
                self._create_violation(
                    violation_type="face_absent",
                    severity=7,
                    description=f"Face not visible for {duration:.1f} seconds",
                    events=[event],
                    evidence_start=self._current_face_absent_start
                )
                self._current_face_absent_start = None
    
    def reset_face_absent(self):
        """Reset face absent tracking when face is detected."""
        with self._lock:
            self._current_face_absent_start = None
    
    # ==================== Scenario 6: Gaze Away ====================
    
    def _handle_gaze_away(self, event: DetectionEvent):
        """Handle gaze away events (Scenario 6)."""
        if self._current_gaze_away_start is None:
            self._current_gaze_away_start = event.timestamp
        else:
            duration = (event.timestamp - self._current_gaze_away_start).total_seconds()
            
            if duration >= self.config.T_GAZE_SECONDS:
                self._create_violation(
                    violation_type="gaze_away",
                    severity=5,
                    description=f"Gaze away from screen for {duration:.1f} seconds",
                    events=[event]
                )
                self._current_gaze_away_start = None
    
    def reset_gaze_tracking(self):
        """Reset gaze tracking when looking at screen."""
        with self._lock:
            self._current_gaze_away_start = None
    
    # ==================== Scenario 7: Phone/Object Detection ====================
    
    def _handle_phone_detected(self, event: DetectionEvent):
        """Handle phone detection (Scenario 7)."""
        self._create_violation(
            violation_type="phone_detected",
            severity=9,
            description="Mobile phone detected in view",
            events=[event]
        )
    
    # ==================== Scenario 8: Multiple Voices ====================
    
    def _handle_voice_detected(self, event: DetectionEvent):
        """Handle single voice detection."""
        # Log but don't create violation for single voice
        # May want to track patterns
        pass
    
    def _handle_multi_voice(self, event: DetectionEvent):
        """Handle multiple voices detection (Scenario 8)."""
        self._create_violation(
            violation_type="multiple_voices",
            severity=8,
            description="Multiple voices detected",
            events=[event]
        )
    
    # ==================== Scenario 9: Application Switch ====================
    
    def _handle_app_switch(self, event: DetectionEvent):
        """Handle application switch (Scenario 9)."""
        self._create_violation(
            violation_type="application_switch",
            severity=10,
            description="Exam window lost focus or application switched",
            events=[event]
        )
    
    # ==================== Scenario 10: Person Swap ====================
    
    def _handle_multiple_faces(self, event: DetectionEvent):
        """Handle multiple faces detection (Scenario 10)."""
        details = event.details or {}
        face_count = details.get("count", 2)
        
        self._create_violation(
            violation_type="multiple_persons",
            severity=9,
            description=f"{face_count} faces detected in frame",
            events=[event]
        )
    
    def _handle_person_swap(self, event: DetectionEvent):
        """Handle person swap detection (Scenario 10)."""
        self._create_violation(
            violation_type="person_swap",
            severity=10,
            description="Possible person swap detected",
            events=[event]
        )
    
    def _handle_impersonation(self, event: DetectionEvent):
        """Handle impersonation detection from face verification."""
        details = event.details or {}
        similarity = details.get("similarity", 0)
        consecutive = details.get("consecutive_mismatches", 0)
        
        self._create_violation(
            violation_type="impersonation_suspected",
            severity=9,
            description=f"Face does not match reference ({consecutive} consecutive mismatches, {similarity:.1%} similarity)",
            events=[event]
        )
    
    # ==================== Scenario 11: Excessive Movement ====================

    def _handle_motion_detected(self, event: DetectionEvent):
        """Handle excessive movement (Scenario 11)."""
        self._create_violation(
            violation_type="excessive_movement",
            severity=5,
            description="Excessive body movement detected",
            events=[event]
        )

    # ==================== Scenario 3: Combined Patterns ====================
    
    def check_combined_patterns(self):
        """
        Scenario 3: Check for combined violation patterns.
        
        Called periodically to detect escalation patterns.
        """
        with self._lock:
            window = timedelta(minutes=10)
            now = datetime.now()
            cutoff = now - window
            
            # Count different violation types in window
            violation_counts: Dict[str, int] = {}
            for v in self._recent_violations:
                if v.occurred_at >= cutoff:
                    violation_counts[v.violation_type] = violation_counts.get(v.violation_type, 0) + 1
            
            # Combined detection rules
            total_violations = sum(violation_counts.values())
            
            if total_violations >= 5:
                # Multiple different violations indicate systematic cheating
                self._create_violation(
                    violation_type="combined_pattern",
                    severity=10,
                    description=f"Combined violation pattern: {total_violations} violations in 10 minutes",
                    events=[]
                )
    
    def add_listener(self, callback: Callable[[Violation], None]):
        """Add a listener for violation events."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)
                logger.debug(f"Added violation listener: {callback}")

    # ==================== Utility Methods ====================
    
    def _create_violation(
        self,
        violation_type: str,
        severity: int,
        description: str,
        events: List[DetectionEvent],
        evidence_start: Optional[datetime] = None
    ):
        """Create and emit a violation."""
        # Debounce: check if same violation type was recently created
        recent_cutoff = datetime.now() - timedelta(seconds=30)
        for v in self._recent_violations:
            if v.violation_type == violation_type and v.occurred_at >= recent_cutoff:
                logger.debug(f"Debounced violation: {violation_type}")
                return
        
        violation = Violation(
            violation_type=violation_type,
            severity=severity,
            description=description,
            events=events,
            occurred_at=datetime.now(),
            evidence_start=evidence_start
        )
        
        self._recent_violations.append(violation)
        self._warning_count += 1
        
        logger.warning(f"Violation detected: {violation_type} (severity {severity})")
        
        # Notify listeners
        with self._lock:
            listeners = list(self._listeners)
        
        for listener in listeners:
            try:
                listener(violation)
            except Exception as e:
                logger.error(f"Error in violation listener: {e}")
    
    def _get_recent_events(
        self,
        event_types: List[EventType],
        window: timedelta
    ) -> List[DetectionEvent]:
        """Get recent events of specified types within window."""
        cutoff = datetime.now() - window
        events = []
        
        for event_type in event_types:
            for e in self._events[event_type]:
                if e.timestamp >= cutoff:
                    events.append(e)
        
        return sorted(events, key=lambda e: e.timestamp)
    
    def get_violation_count(self) -> int:
        """Get total number of violations."""
        return len(self._recent_violations)
    
    def get_warning_count(self) -> int:
        """Get warning count for UI display."""
        return self._warning_count
    
    def get_recent_violations(
        self,
        count: int = 10
    ) -> List[Violation]:
        """Get most recent violations."""
        return list(self._recent_violations)[-count:]
    
    def clear_events(self):
        """Clear all stored events (for testing)."""
        with self._lock:
            for q in self._events.values():
                q.clear()
            self._recent_violations.clear()
            self._warning_count = 0


# Global instance
_classifier: Optional[EventClassifier] = None


def get_event_classifier() -> EventClassifier:
    """Get global event classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = EventClassifier()
    return _classifier
