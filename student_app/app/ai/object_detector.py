"""
Student Exam Application - AI: Object Detection

Detects unauthorized objects (phones, books, secondary devices) using YOLOv8.
"""

import logging
import numpy as np
import time
from typing import List, Dict, Optional
from dataclasses import dataclass

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logging.warning("ultralytics.YOLO not available - Object detection disabled")

logger = logging.getLogger(__name__)

@dataclass
class ObjectDetection:
    """Represents a detected object."""
    label: str
    confidence: float
    box: List[int]  # [x1, y1, x2, y2]

class ObjectDetector:
    """
    Object detection using YOLOv8.
    
    Target labels: cell phone, book, laptop, remote, etc.
    """
    
    def __init__(self, model_path: str = "yolov8s.pt", confidence_threshold: float = 0.5):
        self.enabled = YOLO_AVAILABLE
        self.model = None
        self.confidence_threshold = confidence_threshold
        
        # Mapping for suspicious objects
        self.suspicious_labels = {
            "cell phone": "phone_detected",
            "book": "book_detected",
            "laptop": "suspicious_object",
            "remote": "suspicious_object",
            "tv": "suspicious_object",
            "tablet": "suspicious_object",
            "monitor": "suspicious_object"
        }
        
        if self.enabled:
            try:
                self.model = YOLO(model_path)
                logger.info(f"YOLO model loaded: {model_path}")
            except Exception as e:
                logger.error(f"Failed to load YOLO model: {e}")
                self.enabled = False

    def detect(self, frame: np.ndarray) -> List[ObjectDetection]:
        """Detect objects in a frame."""
        if not self.enabled or self.model is None:
            return []
            
        try:
            results = self.model(frame, verbose=False)[0]
            detections = []
            
            for box in results.boxes:
                conf = float(box.conf[0])
                if conf < self.confidence_threshold:
                    continue
                    
                cls_id = int(box.cls[0])
                label = results.names[cls_id]
                
                if label in self.suspicious_labels:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    detections.append(ObjectDetection(
                        label=self.suspicious_labels[label],
                        confidence=conf,
                        box=[x1, y1, x2, y2]
                    ))
            
            return detections
        except Exception as e:
            logger.error(f"Object detection error: {e}")
            return []

# Global instance
_detector: Optional[ObjectDetector] = None

def get_object_detector() -> ObjectDetector:
    """Get global object detector instance."""
    global _detector
    if _detector is None:
        _detector = ObjectDetector()
    return _detector
