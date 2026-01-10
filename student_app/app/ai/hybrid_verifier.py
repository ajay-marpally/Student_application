"""
Student Exam Application - AI: Hybrid Verifier

Uses Gemini 1.5 Flash to verify high-severity detection events (e.g., phone detected, earbuds).
Ported from ai-proctoring-system/main.py.
"""

import logging
import threading
import time
import base64
import json
import cv2
import numpy as np
import requests
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

class HybridVerifier:
    """
    Validates AI detections using Gemini 1.5 Flash.
    Acts as a "Proctor Overlook" for high-severity incidents.
    """
    
    def __init__(self):
        from student_app.app.config import get_config
        self.config = get_config()
        
        gemini_cfg = getattr(self.config, 'gemini', None)
        if gemini_cfg:
            self.enabled = gemini_cfg.ENABLED
            self.api_key = gemini_cfg.API_KEY
            self.model_name = gemini_cfg.MODEL_NAME
        else:
            self.enabled = False
            self.api_key = None
            self.model_name = "gemini-1.5-flash"
        
        self.last_call_time = 0
        self.min_interval = 4.0  # Rate limiting for free tier
        self.lock = threading.Lock()
        
        if self.enabled and self.api_key:
            path_name = self.model_name if self.model_name.startswith('models/') else f"models/{self.model_name}"
            self.api_url = f"https://generativelanguage.googleapis.com/v1beta/{path_name}:generateContent?key={self.api_key}"
            logger.info(f"HybridVerifier initialized: {self.model_name}")
        else:
            self.enabled = False
            if not self.api_key:
                logger.warning("Gemini API key missing - HybridVerifier disabled")

    def verify_async(self, frame: np.ndarray, detection_type: str, callback: Callable[[bool, str], None]):
        """
        Verify a frame asynchronously.
        
        Args:
            frame: The frame to verify
            detection_type: The type of detection flagged by local AI
            callback: Function called with (is_violation, gemini_feedback)
        """
        if not self.enabled:
            return

        with self.lock:
            now = time.time()
            if now - self.last_call_time < self.min_interval:
                logger.debug("HybridVerifier: Rate limit hit, skipping")
                return
            self.last_call_time = now

        threading.Thread(
            target=self._worker, 
            args=(frame.copy(), detection_type, callback),
            daemon=True
        ).start()

    def _worker(self, frame: np.ndarray, detection_type: str, callback: Callable[[bool, str], None]):
        try:
            # Resize for faster upload
            h, w = frame.shape[:2]
            if w > 1024:
                scale = 1024 / w
                frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
            
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            img_b64 = base64.b64encode(buffer).decode('utf-8')

            prompt_text = (
                f"You are a highly vigilant AI Exam Proctor. Analyze this image for academic dishonesty.\n"
                f"BACKGROUND: The local system flagged: {detection_type}.\n\n"
                f"TASK: \n"
                f"1. Perform a DEEP SCAN for hidden devices: earbuds (eardopes/airpods), smartwatches, charging cases, or earpieces.\n"
                f"2. Confirm if the original flag '{detection_type}' is correct. If not, IDENTIFY what it actually is.\n"
                f"3. Check for other violations: unauthorized papers, other people, or candidate looking away from the screen area.\n\n"
                f"RESULT FORMAT:\n"
                f"If any violation is found, reply: 'VIOLATION: <Object Name> - <1-2 short sentences describing why it is a violation>'.\n"
                f"Example: 'VIOLATION: EARBUDS - The candidate is wearing white wireless earbuds in both ears.'\n"
                f"If clean, reply 'CLEAR'."
            )
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt_text},
                        {"inline_data": {
                            "mime_type": "image/jpeg",
                            "data": img_b64
                        }}
                    ]
                }]
            }
            
            headers = {'Content-Type': 'application/json'}
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                try:
                    result_text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                    logger.info(f"Gemini Verification Result: {result_text}")
                    
                    is_violation = result_text.startswith("VIOLATION:")
                    callback(is_violation, result_text)
                except (KeyError, IndexError) as e:
                    logger.error(f"Gemini Parse Error: {e}")
                    callback(True, f"Parse Error: {str(e)}") # Default to True (keep local flag) if API fails but we have suspicion
            else:
                logger.error(f"Gemini API Error {response.status_code}: {response.text}")
                callback(True, f"API Error: {response.status_code}")

        except Exception as e:
            logger.error(f"HybridVerifier worker error: {e}")
            callback(True, f"Error: {str(e)}")

# Global instance
_verifier: Optional[HybridVerifier] = None

def get_hybrid_verifier() -> HybridVerifier:
    """Get global hybrid verifier instance."""
    global _verifier
    if _verifier is None:
        _verifier = HybridVerifier()
    return _verifier
