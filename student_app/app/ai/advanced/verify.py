import cv2
import base64
import requests
import os
import logging
import threading
import time
from student_app.app.config import get_config

logger = logging.getLogger(__name__)

class AdvancedHybridVerifier:
    """
    Hybrid verifier using Google Gemini 1.5 Flash for cross-verification.
    Ported from ai-proctoring-system.
    """
    def __init__(self):
        config = get_config()
        self.api_key = os.getenv('GEMINI_API_KEY')
        self.enabled = bool(self.api_key)
        self.last_call_time = 0
        self.min_interval = 4.0 # Rate limit for free tier
        self.lock = threading.Lock()
        self.model_name = "gemini-2.5-flash-lite" # Use latest lite model for efficiency and stability
        
        if self.enabled:
            # Reverting to v1beta as it often has broader support for flash-lite models
            self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
            logger.info(f"AdvancedHybridVerifier initialized with model: {self.model_name}")
        else:
            logger.warning("Gemini API key not found. Hybrid verification disabled.")

    def verify_frame_async(self, frame_cv2, detection_type, callback_success, callback_fail):
        if not self.enabled:
            return

        with self.lock:
            now = time.time()
            if now - self.last_call_time < self.min_interval:
                return # Skip if too frequent
            self.last_call_time = now

        threading.Thread(
            target=self._worker, 
            args=(frame_cv2, detection_type, callback_success, callback_fail),
            daemon=True
        ).start()

    def _worker(self, frame_cv2, detection_type, callback_success, callback_fail):
        try:
            # Resize for faster upload
            h, w = frame_cv2.shape[:2]
            if w > 1024:
                scale = 1024 / w
                frame_cv2 = cv2.resize(frame_cv2, (0, 0), fx=scale, fy=scale)
            
            _, buffer = cv2.imencode('.jpg', frame_cv2)
            img_b64 = base64.b64encode(buffer).decode('utf-8')

            prompt_text = (
                f"You are a highly vigilant AI Exam Proctor. Analyze this image for academic dishonesty.\n"
                f"Specifically check for: {detection_type}. However, local detection can sometimes be inaccurate (e.g., mistaking earbuds for phones).\n\n"
                f"TASK: \n"
                f"1. Perform a DEEP SCAN for hidden devices: EARBUDS (eardopes/airpods), SMARTWATCHES, charging cases, or earpieces.\n"
                f"2. Confirm if the original flag '{detection_type}' is correct. If not, IDENTIFY what it actually is.\n"
                f"3. Check for other violations: BOOKS, handwritten notes, unauthorized papers, or other people helping.\n\n"
                f"Your response must follow this format:\n"
                f"VERDICT: [VIOLATION/CLEAN]\n"
                f"REASON: [Short explanation. If it is a violation, explicitly mention the item found, e.g., 'EARBUDS' or 'NOTEBOOK']"
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
            
            response = requests.post(self.api_url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                result_text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # Robust parsing for the new format
                verdict = "CLEAN"
                reason = result_text
                
                if "VERDICT:" in result_text.upper():
                    verdict_part = result_text.upper().split("VERDICT:")[1].split("\n")[0].strip()
                    if "VIOLATION" in verdict_part:
                        verdict = "VIOLATION"
                
                if "REASON:" in result_text.upper():
                    reason = result_text.split("REASON:")[1].strip()
                
                if verdict == "VIOLATION":
                    callback_success(detection_type, reason)
                else:
                    callback_fail(detection_type, reason)
            else:
                logger.error(f"Gemini API Error {response.status_code}: {response.text}")
                callback_fail(detection_type, f"API Error {response.status_code}")

        except Exception as e:
            logger.error(f"Gemini Verification failed: {e}")
            callback_fail(detection_type, str(e))
