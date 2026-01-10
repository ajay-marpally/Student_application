"""AI detection modules for Student Exam Application"""

from student_app.app.ai.face_detector import FaceDetector, get_face_detector
# These are imported lazily or directly to avoid breaking login
# from student_app.app.ai.head_pose import HeadPoseEstimator, get_head_pose_estimator
# from student_app.app.ai.gaze import GazeTracker, get_gaze_tracker
from student_app.app.ai.audio_monitor import AudioMonitor, get_audio_monitor
from student_app.app.ai.event_classifier import EventClassifier, get_event_classifier
from student_app.app.ai.face_verifier import (
    FaceVerifier, get_face_verifier, is_face_verification_available
)

__all__ = [
    "FaceDetector", "get_face_detector",
    "HeadPoseEstimator", "get_head_pose_estimator", 
    "GazeTracker", "get_gaze_tracker",
    "AudioMonitor", "get_audio_monitor",
    "EventClassifier", "get_event_classifier",
    "FaceVerifier", "get_face_verifier", "is_face_verification_available",
]

