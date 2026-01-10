"""
Student Exam Application - AI: Audio Monitor

Upgraded Audio Monitor using Silero VAD for robust speech detection.
Ported from ai-proctoring-system/main.py.
"""

import logging
import threading
import time
import numpy as np
from typing import Optional, Callable, Dict
from datetime import datetime
from collections import deque

try:
    import torch
    from silero_vad import load_silero_vad
    SILERO_AVAILABLE = True
except ImportError:
    SILERO_AVAILABLE = False
    logging.warning("silero-vad or torch not available - Audio monitoring will be limited")

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    logging.warning("PyAudio not available - Audio monitoring disabled")

logger = logging.getLogger(__name__)

class AudioMonitor:
    def __init__(self, callback: Optional[Callable[[Dict], None]] = None):
        self.callback = callback
        self.config = None
        self.running = False
        self.stream = None
        self.p = None
        
        self.sample_rate = 16000
        self.chunk_size = 512
        
        self.vad_model = None
        if SILERO_AVAILABLE:
            try:
                self.vad_model = load_silero_vad()
                logger.info("Silero VAD Loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load Silero VAD: {e}")
                # We don't modify the global flag here to avoid scoping issues 
                # and because vad_model=None already indicates failure.
                self.vad_model = None

        self.speech_state = False
        self.speech_start_ts = None
        self.silence_start_ts = None
        self.silence_grace_seconds = 1.0
        self.speech_pattern_buffer = deque(maxlen=50)
        self.sustained_speech_threshold = 0.70
        self.suspicious_seconds = 3.0

    def start(self):
        if not PYAUDIO_AVAILABLE:
            logger.warning("PyAudio not available - cannot start Audio Monitor")
            return
            
        from student_app.app.config import get_config
        self.config = get_config()
        self.suspicious_seconds = 3.0 # Default

        self.p = pyaudio.PyAudio()
        self.running = True
        
        def _audio_callback(in_data, frame_count, time_info, status):
            if not self.running:
                return (None, pyaudio.paAbort)
                
            audio_np = np.frombuffer(in_data, dtype=np.int16).astype(np.float32)
            if audio_np.size == 0:
                speech_prob = 0.0
            else:
                audio_np /= 32768.0
                if audio_np.size > 512:
                    audio_np = audio_np[:512]
                elif audio_np.size < 512:
                    audio_np = np.pad(audio_np, (0, 512 - audio_np.size))
                
                if SILERO_AVAILABLE and self.vad_model:
                    try:
                        audio_tensor = torch.from_numpy(audio_np)
                        speech_prob = float(self.vad_model(audio_tensor, self.sample_rate).detach())
                    except Exception as e:
                        logger.error(f"VAD prediction error: {e}")
                        speech_prob = 0.0
                else:
                    # Fallback to energy based
                    speech_prob = np.sqrt(np.mean(audio_np**2)) * 10
            
            now = time.time()
            audio_spike = False
            
            if speech_prob > 0.6:
                self.speech_pattern_buffer.append(1)
                if not self.speech_state:
                    self.speech_state = True
                    self.speech_start_ts = now
                self.silence_start_ts = None
            else:
                self.speech_pattern_buffer.append(0)
                if self.speech_state:
                    if self.silence_start_ts is None:
                        self.silence_start_ts = now
                    elif now - self.silence_start_ts > self.silence_grace_seconds:
                        self.speech_state = False
                        self.speech_start_ts = None
                        self.silence_start_ts = None
            
            speech_ratio = 0.0
            if len(self.speech_pattern_buffer) >= 40:
                speech_ratio = sum(self.speech_pattern_buffer) / len(self.speech_pattern_buffer)
                if speech_ratio > self.sustained_speech_threshold:
                    if self.speech_start_ts and (now - self.speech_start_ts) >= self.suspicious_seconds:
                        audio_spike = True
            
            if self.callback:
                self.callback({
                    "audio_spike": audio_spike,
                    "speech_probability": speech_prob,
                    "speech_ratio": speech_ratio
                })
                
            return (in_data, pyaudio.paContinue)

        try:
            self.stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=_audio_callback
            )
            self.stream.start_stream()
            logger.info("Audio Monitor stream started")
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            self.running = False

    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
            self.stream = None
        if self.p:
            try:
                self.p.terminate()
            except:
                pass
            self.p = None
        logger.info("Audio Monitor stopped")

# Global instance
_monitor: Optional[AudioMonitor] = None

def get_audio_monitor() -> AudioMonitor:
    """Get global audio monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = AudioMonitor()
    return _monitor
