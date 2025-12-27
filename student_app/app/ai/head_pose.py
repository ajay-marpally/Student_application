"""
Student Exam Application - AI: Head Pose Estimation

Estimates head orientation (yaw, pitch, roll) using MediaPipe Face Mesh.
"""

import cv2
import numpy as np
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass
import mediapipe as mp

logger = logging.getLogger(__name__)


@dataclass
class HeadPose:
    """Head pose angles in degrees."""
    yaw: float    # Left/Right rotation (-180 to 180, negative=left)
    pitch: float  # Up/Down rotation (-180 to 180, negative=up)
    roll: float   # Tilt (-180 to 180)
    confidence: float
    
    def is_looking_left(self, threshold: float = 25.0) -> bool:
        """Check if head is turned left beyond threshold."""
        return self.yaw < -threshold
    
    def is_looking_right(self, threshold: float = 25.0) -> bool:
        """Check if head is turned right beyond threshold."""
        return self.yaw > threshold
    
    def is_looking_up(self, threshold: float = 20.0) -> bool:
        """Check if head is tilted up beyond threshold."""
        return self.pitch < -threshold
    
    def is_looking_down(self, threshold: float = 20.0) -> bool:
        """Check if head is tilted down beyond threshold."""
        return self.pitch > threshold


class HeadPoseEstimator:
    """
    Head pose estimation using MediaPipe Face Mesh.
    
    Uses 3D-2D point correspondences to solve for rotation angles.
    """
    
    # 3D model points for pose estimation (nose tip, chin, eyes, mouth corners)
    MODEL_POINTS = np.array([
        (0.0, 0.0, 0.0),          # Nose tip
        (0.0, -330.0, -65.0),     # Chin
        (-225.0, 170.0, -135.0),  # Left eye left corner
        (225.0, 170.0, -135.0),   # Right eye right corner
        (-150.0, -150.0, -125.0), # Left mouth corner
        (150.0, -150.0, -125.0),  # Right mouth corner
    ], dtype=np.float64)
    
    # MediaPipe landmark indices for the points above
    LANDMARK_INDICES = [1, 152, 33, 263, 61, 291]  # Updated for Face Mesh
    
    def __init__(
        self,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.7
    ):
        """
        Initialize head pose estimator.
        
        Args:
            min_detection_confidence: Minimum confidence for face detection
            min_tracking_confidence: Minimum confidence for tracking
        """
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )
        
        # Camera matrix will be computed based on frame size
        self._camera_matrix = None
        self._dist_coeffs = np.zeros((4, 1))
        self._frame_size = None
    
    def _get_camera_matrix(self, frame_size: Tuple[int, int]) -> np.ndarray:
        """Get or compute camera matrix for frame size."""
        if self._frame_size != frame_size:
            self._frame_size = frame_size
            h, w = frame_size
            
            # Approximate camera matrix (assuming no lens distortion)
            focal_length = w
            center = (w / 2, h / 2)
            
            self._camera_matrix = np.array([
                [focal_length, 0, center[0]],
                [0, focal_length, center[1]],
                [0, 0, 1]
            ], dtype=np.float64)
        
        return self._camera_matrix
    
    def estimate(self, frame: np.ndarray) -> Optional[HeadPose]:
        """
        Estimate head pose from a frame.
        
        Args:
            frame: BGR image from OpenCV
            
        Returns:
            HeadPose object or None if no face detected
        """
        if frame is None or frame.size == 0:
            return None
        
        h, w = frame.shape[:2]
        camera_matrix = self._get_camera_matrix((h, w))
        
        # Convert to RGB for MediaPipe
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)
        
        if not results.multi_face_landmarks:
            return None
        
        # Get landmarks for first face
        landmarks = results.multi_face_landmarks[0]
        
        # Extract 2D image points
        image_points = np.array([
            (landmarks.landmark[idx].x * w, landmarks.landmark[idx].y * h)
            for idx in self.LANDMARK_INDICES
        ], dtype=np.float64)
        
        # Solve PnP for rotation
        success, rotation_vector, translation_vector = cv2.solvePnP(
            self.MODEL_POINTS,
            image_points,
            camera_matrix,
            self._dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )
        
        if not success:
            return None
        
        # Convert rotation vector to Euler angles
        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        pose_matrix = cv2.hconcat([rotation_matrix, translation_vector])
        
        # Decompose projection matrix
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(
            cv2.vconcat([pose_matrix, np.array([[0, 0, 0, 1]])])
        )
        
        yaw = euler_angles[1, 0]
        pitch = euler_angles[0, 0]
        roll = euler_angles[2, 0]
        
        # Calculate confidence based on landmark visibility
        visibility = np.mean([
            landmarks.landmark[idx].visibility 
            for idx in self.LANDMARK_INDICES
            if hasattr(landmarks.landmark[idx], 'visibility')
        ]) if hasattr(landmarks.landmark[0], 'visibility') else 0.9
        
        return HeadPose(
            yaw=float(yaw),
            pitch=float(pitch),
            roll=float(roll),
            confidence=float(visibility)
        )
    
    def get_landmarks(self, frame: np.ndarray) -> Optional[List[Tuple[int, int]]]:
        """
        Get all face landmarks for a frame.
        
        Returns list of (x, y) coordinates for all 468 landmarks.
        """
        if frame is None or frame.size == 0:
            return None
        
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)
        
        if not results.multi_face_landmarks:
            return None
        
        landmarks = results.multi_face_landmarks[0]
        return [
            (int(lm.x * w), int(lm.y * h))
            for lm in landmarks.landmark
        ]
    
    def draw_pose(
        self,
        frame: np.ndarray,
        pose: HeadPose,
        color: Tuple[int, int, int] = (0, 255, 0)
    ) -> np.ndarray:
        """Draw pose information on frame."""
        output = frame.copy()
        
        # Draw pose text
        text_lines = [
            f"Yaw: {pose.yaw:.1f}",
            f"Pitch: {pose.pitch:.1f}",
            f"Roll: {pose.roll:.1f}",
        ]
        
        y_offset = 30
        for line in text_lines:
            cv2.putText(
                output,
                line,
                (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2
            )
            y_offset += 25
        
        return output
    
    def close(self):
        """Release resources."""
        self.face_mesh.close()


# Global instance
_estimator: Optional[HeadPoseEstimator] = None


def get_head_pose_estimator() -> HeadPoseEstimator:
    """Get global head pose estimator instance."""
    global _estimator
    if _estimator is None:
        _estimator = HeadPoseEstimator()
    return _estimator
