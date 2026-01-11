"""
Student Exam Application - AI: Gaze Tracking

Tracks eye gaze direction using MediaPipe Face Mesh.
"""

import cv2
import numpy as np
import logging
logger = logging.getLogger(__name__)

from typing import Optional, Tuple, List
from dataclasses import dataclass
try:
    import mediapipe as mp
    try:
        import mediapipe.solutions.face_mesh as mp_face_mesh
    except (ImportError, AttributeError):
        # Fallback for versions where solutions is hidden under python
        import mediapipe.python.solutions.face_mesh as mp_face_mesh
    MP_AVAILABLE = True
except (ImportError, AttributeError):
    MP_AVAILABLE = False
    mp = None
    mp_face_mesh = None

if not MP_AVAILABLE:
    logger.warning("MediaPipe solutions not found - Gaze tracking will be disabled")


@dataclass
class GazeDirection:
    """Represents gaze direction."""
    horizontal: float  # -1 (left) to 1 (right)
    vertical: float    # -1 (up) to 1 (down)
    confidence: float
    
    def is_looking_away(
        self,
        horizontal_threshold: float = 0.5,
        vertical_threshold: float = 0.4
    ) -> bool:
        """Check if gaze is significantly away from center."""
        return (
            abs(self.horizontal) > horizontal_threshold or
            abs(self.vertical) > vertical_threshold
        )
    
    @property
    def angle_degrees(self) -> float:
        """Get gaze angle from center in degrees."""
        return np.degrees(np.arctan2(self.vertical, self.horizontal))


class GazeTracker:
    """
    Eye gaze tracking using MediaPipe Face Mesh.
    
    Analyzes iris position relative to eye bounds to determine gaze direction.
    """
    
    # MediaPipe Face Mesh landmark indices for eyes
    # Left eye
    LEFT_EYE_OUTER = 33
    LEFT_EYE_INNER = 133
    LEFT_EYE_TOP = 159
    LEFT_EYE_BOTTOM = 145
    LEFT_IRIS_CENTER = 468  # Refined landmark
    
    # Right eye  
    RIGHT_EYE_OUTER = 362
    RIGHT_EYE_INNER = 263
    RIGHT_EYE_TOP = 386
    RIGHT_EYE_BOTTOM = 374
    RIGHT_IRIS_CENTER = 473  # Refined landmark
    
    def __init__(
        self,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.7
    ):
        """
        Initialize gaze tracker.
        
        Args:
            min_detection_confidence: Minimum confidence for detection
            min_tracking_confidence: Minimum confidence for tracking
        """
        self.enabled = MP_AVAILABLE
        self.mp_face_mesh = mp_face_mesh
        self.face_mesh = None
        
        if self.enabled:
            try:
                self.face_mesh = self.mp_face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=1,
                    refine_landmarks=True,  # Enable iris landmarks
                    min_detection_confidence=min_detection_confidence,
                    min_tracking_confidence=min_tracking_confidence
                )
            except Exception as e:
                logger.error(f"Failed to initialize MediaPipe FaceMesh: {e}")
                self.enabled = False
    
    def track(self, frame: np.ndarray) -> Optional[GazeDirection]:
        """
        Track gaze direction in a frame.
        
        Args:
            frame: BGR image from OpenCV
            
        Returns:
            GazeDirection object or None if eyes not detected
        """
        if not self.enabled or frame is None or frame.size == 0:
            return None
        
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)
        
        if not results.multi_face_landmarks:
            return None
        
        landmarks = results.multi_face_landmarks[0]
        
        # Get left eye gaze
        left_gaze = self._compute_eye_gaze(
            landmarks, w, h,
            self.LEFT_EYE_OUTER, self.LEFT_EYE_INNER,
            self.LEFT_EYE_TOP, self.LEFT_EYE_BOTTOM,
            self.LEFT_IRIS_CENTER
        )
        
        # Get right eye gaze
        right_gaze = self._compute_eye_gaze(
            landmarks, w, h,
            self.RIGHT_EYE_OUTER, self.RIGHT_EYE_INNER,
            self.RIGHT_EYE_TOP, self.RIGHT_EYE_BOTTOM,
            self.RIGHT_IRIS_CENTER
        )
        
        if left_gaze is None and right_gaze is None:
            return None
        
        # Average both eyes
        if left_gaze is not None and right_gaze is not None:
            horizontal = (left_gaze[0] + right_gaze[0]) / 2
            vertical = (left_gaze[1] + right_gaze[1]) / 2
            confidence = (left_gaze[2] + right_gaze[2]) / 2
        elif left_gaze is not None:
            horizontal, vertical, confidence = left_gaze
        else:
            horizontal, vertical, confidence = right_gaze
        
        return GazeDirection(
            horizontal=horizontal,
            vertical=vertical,
            confidence=confidence
        )
    
    def _compute_eye_gaze(
        self,
        landmarks,
        frame_width: int,
        frame_height: int,
        outer_idx: int,
        inner_idx: int,
        top_idx: int,
        bottom_idx: int,
        iris_idx: int
    ) -> Optional[Tuple[float, float, float]]:
        """Compute gaze for a single eye."""
        try:
            # Get landmark positions
            outer = landmarks.landmark[outer_idx]
            inner = landmarks.landmark[inner_idx]
            top = landmarks.landmark[top_idx]
            bottom = landmarks.landmark[bottom_idx]
            iris = landmarks.landmark[iris_idx]
            
            # Convert to pixel coordinates
            outer_pt = np.array([outer.x * frame_width, outer.y * frame_height])
            inner_pt = np.array([inner.x * frame_width, inner.y * frame_height])
            top_pt = np.array([top.x * frame_width, top.y * frame_height])
            bottom_pt = np.array([bottom.x * frame_width, bottom.y * frame_height])
            iris_pt = np.array([iris.x * frame_width, iris.y * frame_height])
            
            # Eye center
            eye_center_x = (outer_pt[0] + inner_pt[0]) / 2
            eye_center_y = (top_pt[1] + bottom_pt[1]) / 2
            
            # Eye dimensions
            eye_width = abs(inner_pt[0] - outer_pt[0])
            eye_height = abs(bottom_pt[1] - top_pt[1])
            
            if eye_width < 5 or eye_height < 3:  # Too small to analyze
                return None
            
            # Iris offset from center, normalized to -1 to 1
            horizontal = (iris_pt[0] - eye_center_x) / (eye_width / 2)
            vertical = (iris_pt[1] - eye_center_y) / (eye_height / 2)
            
            # Clamp to reasonable range
            horizontal = np.clip(horizontal, -1.5, 1.5)
            vertical = np.clip(vertical, -1.5, 1.5)
            
            # Confidence based on eye openness
            openness = eye_height / eye_width
            confidence = min(1.0, openness / 0.3)  # Eyes with aspect > 0.3 get full confidence
            
            return (horizontal, vertical, confidence)
            
        except (IndexError, AttributeError) as e:
            logger.debug(f"Eye gaze computation error: {e}")
            return None
    
    def is_eyes_closed(self, frame: np.ndarray, threshold: float = 0.15) -> bool:
        """
        Detect if eyes are closed.
        
        Args:
            frame: BGR image
            threshold: Aspect ratio threshold (lower = more closed)
            
        Returns:
            True if eyes appear closed
        """
        if not self.enabled or frame is None or frame.size == 0:
            return False
        
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)
        
        if not results.multi_face_landmarks:
            return False
        
        landmarks = results.multi_face_landmarks[0]
        
        # Check both eyes
        for eye_top, eye_bottom, eye_outer, eye_inner in [
            (self.LEFT_EYE_TOP, self.LEFT_EYE_BOTTOM, 
             self.LEFT_EYE_OUTER, self.LEFT_EYE_INNER),
            (self.RIGHT_EYE_TOP, self.RIGHT_EYE_BOTTOM,
             self.RIGHT_EYE_OUTER, self.RIGHT_EYE_INNER)
        ]:
            top = landmarks.landmark[eye_top]
            bottom = landmarks.landmark[eye_bottom]
            outer = landmarks.landmark[eye_outer]
            inner = landmarks.landmark[eye_inner]
            
            eye_height = abs(bottom.y - top.y) * h
            eye_width = abs(inner.x - outer.x) * w
            
            if eye_width > 0:
                aspect_ratio = eye_height / eye_width
                if aspect_ratio < threshold:
                    return True
        
        return False
    
    def draw_gaze(
        self,
        frame: np.ndarray,
        gaze: GazeDirection,
        color: Tuple[int, int, int] = (0, 255, 0)
    ) -> np.ndarray:
        """Draw gaze information on frame."""
        output = frame.copy()
        h, w = output.shape[:2]
        
        # Draw gaze indicator
        center = (w // 2, 50)
        end_x = int(center[0] + gaze.horizontal * 50)
        end_y = int(center[1] + gaze.vertical * 30)
        
        cv2.circle(output, center, 40, color, 2)
        cv2.arrowedLine(output, center, (end_x, end_y), color, 2)
        
        status = "AWAY" if gaze.is_looking_away() else "OK"
        cv2.putText(
            output,
            f"Gaze: {status}",
            (10, h - 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255) if status == "AWAY" else (0, 255, 0),
            2
        )
        
        return output
    
    def close(self):
        """Release resources."""
        self.face_mesh.close()


# Global instance
_tracker: Optional[GazeTracker] = None


def get_gaze_tracker() -> GazeTracker:
    """Get global gaze tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = GazeTracker()
    return _tracker
