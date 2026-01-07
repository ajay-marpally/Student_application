"""
Student Exam Application - AI: Face Verifier

Biometric face verification using face_recognition library.
Compares live camera feed against stored reference photo.
Implements threshold-based detection to reduce false positives.
"""

import logging
import threading
import time
import hashlib
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import cv2
import httpx

logger = logging.getLogger(__name__)

# Try to import face_recognition
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    logger.warning("face_recognition not available - install with: pip install face_recognition")


@dataclass 
class VerificationResult:
    """Result of face verification."""
    is_match: bool
    similarity: float  # 0.0 to 1.0 (1.0 = perfect match)
    distance: float    # Lower = better match
    confidence: float
    message: str = ""


class FaceVerifier:
    """
    Biometric face verification for exam proctoring.
    
    Features:
    - Downloads reference photo from URL
    - Extracts 128-dimension face encoding
    - Compares live face against reference
    - Uses sliding window to reduce false positives
    - Only triggers alert when mismatch persists
    """
    
    # Detection thresholds
    MATCH_THRESHOLD = 0.6        # Distance threshold (lower = more strict)
    ALERT_AFTER_CONSECUTIVE = 5  # Consecutivemismatches before alert
    WINDOW_SECONDS = 30          # Time window for mismatch tracking
    MIN_CONFIDENCE = 0.7         # Minimum confidence to consider result
    
    def __init__(
        self,
        match_threshold: Optional[float] = None,
        consecutive_threshold: Optional[int] = None
    ):
        """
        Initialize face verifier.
        
        Args:
            match_threshold: Distance threshold for matching (default 0.6)
            consecutive_threshold: Consecutive mismatches before alert (default 5)
        """
        if not FACE_RECOGNITION_AVAILABLE:
            raise RuntimeError("face_recognition library not available")
        
        self.match_threshold = match_threshold or self.MATCH_THRESHOLD
        self.consecutive_threshold = consecutive_threshold or self.ALERT_AFTER_CONSECUTIVE
        
        # Reference encoding
        self._reference_encoding: Optional[np.ndarray] = None
        self._reference_loaded = False
        
        # Mismatch tracking for false positive reduction
        self._mismatch_times: deque = deque(maxlen=100)
        self._consecutive_mismatches = 0
        self._lock = threading.Lock()
        
        # Cache for encoding
        self._encoding_cache: dict = {}
    
    def load_reference_from_url(self, photo_url: str) -> bool:
        """
        Load reference face from URL.
        
        Args:
            photo_url: URL to student's reference photo
            
        Returns:
            True if reference loaded successfully
        """
        try:
            logger.info(f"Loading reference photo from: {photo_url}")
            
            # Download image
            response = httpx.get(photo_url, timeout=30.0)
            response.raise_for_status()
            
            # Convert to numpy array
            image_array = np.frombuffer(response.content, dtype=np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
            if image is None:
                logger.error("Failed to decode reference image")
                return False
            
            # Convert BGR to RGB for face_recognition
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Extract face encoding
            encodings = face_recognition.face_encodings(rgb_image)
            
            if not encodings:
                logger.error("No face found in reference image")
                return False
            
            self._reference_encoding = encodings[0]
            self._reference_loaded = True
            
            logger.info("Reference face encoding loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load reference photo: {e}")
            return False
    
    def load_reference_from_file(self, file_path: Path) -> bool:
        """
        Load reference face from local file.
        
        Args:
            file_path: Path to reference image
            
        Returns:
            True if loaded successfully
        """
        try:
            image = face_recognition.load_image_file(str(file_path))
            encodings = face_recognition.face_encodings(image)
            
            if not encodings:
                logger.error("No face found in reference image")
                return False
            
            self._reference_encoding = encodings[0]
            self._reference_loaded = True
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load reference image: {e}")
            return False
    
    def verify(self, frame: np.ndarray) -> VerificationResult:
        """
        Verify face in frame against reference.
        
        Args:
            frame: BGR image from OpenCV
            
        Returns:
            VerificationResult with match status and similarity
        """
        if not self._reference_loaded:
            return VerificationResult(
                is_match=False,  # Security: Fail closed if no reference exists
                similarity=0.0,
                distance=1.0,
                confidence=0.0,
                message="No reference photo loaded"
            )
        
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Find faces in frame
            face_locations = face_recognition.face_locations(rgb_frame, model="hog")
            
            if not face_locations:
                return VerificationResult(
                    is_match=False, # Security: Fail closed if no face in frame
                    similarity=0.0,
                    distance=1.0,
                    confidence=0.0,
                    message="No face detected in frame"
                )
            
            # Get encoding for the largest face
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            
            if not face_encodings:
                return VerificationResult(
                    is_match=False, # Security: Fail closed if face can't be encoded
                    similarity=0.0,
                    distance=1.0,
                    confidence=0.0,
                    message="Could not encode detected face"
                )
            
            # Compare with reference
            live_encoding = face_encodings[0]
            distance = face_recognition.face_distance(
                [self._reference_encoding], 
                live_encoding
            )[0]
            
            # Convert distance to similarity (0-1, higher is better)
            similarity = 1.0 - min(distance, 1.0)
            
            # Determine if match
            is_match = distance <= self.match_threshold
            confidence = min(1.0, max(0.0, 1.0 - (distance / 1.5)))
            
            # Track result (Only if a face was actually detected)
            self._track_result(is_match)
            
            return VerificationResult(
                is_match=is_match,
                similarity=similarity,
                distance=float(distance),
                confidence=confidence,
                message="" if is_match else "Face does not match reference"
            )
            
        except Exception as e:
            logger.error(f"Face verification error: {e}")
            return VerificationResult(
                is_match=False,  # Security: Fail closed on processing error
                similarity=0.0,
                distance=1.0,
                confidence=0.0,
                message=f"Verification system error: {str(e)}"
            )
    
    def _track_result(self, is_match: Optional[bool]):
        """
        Track verification results for false positive reduction.
        
        Args:
            is_match: Match result, or None if no face detected in frame.
        """
        with self._lock:
            now = datetime.now()
            
            # Use None to indicate face was absent - we don't increment/reset
            if is_match is None:
                return

            if is_match:
                # Reset consecutive count on actual match
                self._consecutive_mismatches = 0
            else:
                # Track mismatch ONLY if face was present but didn't match
                self._consecutive_mismatches += 1
                self._mismatch_times.append(now)
    
    def should_alert(self) -> Tuple[bool, str]:
        """
        Check if impersonation alert should be triggered.
        
        Uses consecutive mismatch count and time window to reduce false positives.
        
        Returns:
            Tuple of (should_alert, reason)
        """
        with self._lock:
            # Check consecutive mismatches
            if self._consecutive_mismatches >= self.consecutive_threshold:
                return True, f"{self._consecutive_mismatches} consecutive face mismatches"
            
            # Check mismatches in time window
            window_cutoff = datetime.now() - timedelta(seconds=self.WINDOW_SECONDS)
            recent_mismatches = sum(1 for t in self._mismatch_times if t >= window_cutoff)
            
            # Alert if too many mismatches in window (more than 60% of checks)
            if recent_mismatches >= 10:
                return True, f"{recent_mismatches} face mismatches in {self.WINDOW_SECONDS}s"
            
            return False, ""
    
    def reset_tracking(self):
        """Reset mismatch tracking."""
        with self._lock:
            self._mismatch_times.clear()
            self._consecutive_mismatches = 0
    
    def get_stats(self) -> dict:
        """Get verification statistics."""
        with self._lock:
            window_cutoff = datetime.now() - timedelta(seconds=self.WINDOW_SECONDS)
            recent_mismatches = sum(1 for t in self._mismatch_times if t >= window_cutoff)
            
            return {
                "reference_loaded": self._reference_loaded,
                "consecutive_mismatches": self._consecutive_mismatches,
                "recent_mismatches": recent_mismatches,
                "match_threshold": self.match_threshold,
                "consecutive_threshold": self.consecutive_threshold
            }
    
    @property
    def is_ready(self) -> bool:
        """Check if verifier is ready (reference loaded)."""
        return self._reference_loaded


# Global instance
_verifier: Optional[FaceVerifier] = None


def get_face_verifier() -> Optional[FaceVerifier]:
    """
    Get global face verifier instance.
    
    Returns None if face_recognition is not available.
    """
    global _verifier
    
    if not FACE_RECOGNITION_AVAILABLE:
        return None
    
    if _verifier is None:
        _verifier = FaceVerifier()
    
    return _verifier


def is_face_verification_available() -> bool:
    """Check if face verification is available."""
    return FACE_RECOGNITION_AVAILABLE
