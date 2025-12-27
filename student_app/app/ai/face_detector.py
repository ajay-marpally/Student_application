"""
Student Exam Application - AI: Face Detector

Uses OpenCV DNN module for accurate face detection.
Model: SSD with ResNet-10 backbone (res10_300x300_ssd_iter_140000.caffemodel)
"""

import cv2
import numpy as np
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FaceDetection:
    """Represents a detected face."""
    x: int
    y: int
    width: int
    height: int
    confidence: float
    
    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    @property
    def area(self) -> int:
        return self.width * self.height
    
    def to_rect(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


class FaceDetector:
    """
    Face detection using OpenCV DNN.
    
    Uses the SSD face detector with ResNet-10 backbone for robust detection
    of faces at various angles and lighting conditions.
    """
    
    # Model files (bundled with application)
    MODEL_FILE = "res10_300x300_ssd_iter_140000_fp16.caffemodel"
    CONFIG_FILE = "deploy.prototxt"
    
    # Detection parameters
    INPUT_SIZE = (300, 300)
    SCALE_FACTOR = 1.0
    MEAN_VALUES = (104.0, 177.0, 123.0)
    
    def __init__(
        self,
        model_path: Optional[Path] = None,
        confidence_threshold: float = 0.7
    ):
        """
        Initialize face detector.
        
        Args:
            model_path: Path to model directory (contains .caffemodel and .prototxt)
            confidence_threshold: Minimum confidence for detection
        """
        self.confidence_threshold = confidence_threshold
        self._net = None
        
        # Find model files
        if model_path is None:
            # Look in common locations
            possible_paths = [
                Path(__file__).parent / "models",
                Path(__file__).parent.parent.parent / "models",
                Path.home() / ".student_exam_app" / "models",
            ]
            for p in possible_paths:
                if (p / self.MODEL_FILE).exists():
                    model_path = p
                    break
        
        self.model_path = model_path
        self._load_model()
    
    def _load_model(self):
        """Load the DNN model."""
        try:
            if self.model_path and (self.model_path / self.MODEL_FILE).exists():
                model_file = str(self.model_path / self.MODEL_FILE)
                config_file = str(self.model_path / self.CONFIG_FILE)
                
                self._net = cv2.dnn.readNetFromCaffe(config_file, model_file)
                self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                
                logger.info("Face detector model loaded from files")
            else:
                # Use OpenCV's built-in Haar cascade as fallback
                logger.warning("DNN model not found, using Haar cascade fallback")
                self._use_haar_fallback = True
                self._haar_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                )
                
        except Exception as e:
            logger.error(f"Error loading face detector model: {e}")
            self._use_haar_fallback = True
            self._haar_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
    
    def detect(self, frame: np.ndarray) -> List[FaceDetection]:
        """
        Detect faces in a frame.
        
        Args:
            frame: BGR image from OpenCV
            
        Returns:
            List of detected faces
        """
        if frame is None or frame.size == 0:
            return []
        
        if hasattr(self, '_use_haar_fallback') and self._use_haar_fallback:
            return self._detect_haar(frame)
        
        return self._detect_dnn(frame)
    
    def _detect_dnn(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detect faces using DNN model."""
        h, w = frame.shape[:2]
        
        # Prepare input blob
        blob = cv2.dnn.blobFromImage(
            frame,
            self.SCALE_FACTOR,
            self.INPUT_SIZE,
            self.MEAN_VALUES,
            swapRB=False,
            crop=False
        )
        
        self._net.setInput(blob)
        detections = self._net.forward()
        
        faces = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            
            if confidence > self.confidence_threshold:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                x1, y1, x2, y2 = box.astype(int)
                
                # Ensure coordinates are within frame
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(w, x2)
                y2 = min(h, y2)
                
                faces.append(FaceDetection(
                    x=x1,
                    y=y1,
                    width=x2 - x1,
                    height=y2 - y1,
                    confidence=float(confidence)
                ))
        
        return faces
    
    def _detect_haar(self, frame: np.ndarray) -> List[FaceDetection]:
        """Fallback detection using Haar cascade."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        rects = self._haar_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        faces = []
        for (x, y, w, h) in rects:
            faces.append(FaceDetection(
                x=x,
                y=y,
                width=w,
                height=h,
                confidence=0.8  # Fixed confidence for Haar
            ))
        
        return faces
    
    def count_faces(self, frame: np.ndarray) -> int:
        """Quick face count."""
        return len(self.detect(frame))
    
    def get_largest_face(self, frame: np.ndarray) -> Optional[FaceDetection]:
        """Get the largest detected face (assumed to be the student)."""
        faces = self.detect(frame)
        if not faces:
            return None
        return max(faces, key=lambda f: f.area)
    
    def draw_detections(
        self,
        frame: np.ndarray,
        faces: List[FaceDetection],
        color: Tuple[int, int, int] = (0, 255, 0)
    ) -> np.ndarray:
        """Draw face detections on frame for visualization."""
        output = frame.copy()
        
        for face in faces:
            cv2.rectangle(
                output,
                (face.x, face.y),
                (face.x + face.width, face.y + face.height),
                color,
                2
            )
            
            label = f"{face.confidence:.2f}"
            cv2.putText(
                output,
                label,
                (face.x, face.y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2
            )
        
        return output


# Global instance
_detector: Optional[FaceDetector] = None


def get_face_detector() -> FaceDetector:
    """Get global face detector instance."""
    global _detector
    if _detector is None:
        _detector = FaceDetector()
    return _detector
