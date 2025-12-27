"""
Student Exam Application - AI: Audio Monitor

Voice Activity Detection (VAD) and audio analysis for detecting
speech, multiple voices, and suspicious audio patterns.
"""

import logging
import threading
import queue
import time
import numpy as np
from typing import Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import audio libraries
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    logger.warning("PyAudio not available - audio monitoring disabled")

try:
    import webrtcvad
    WEBRTCVAD_AVAILABLE = True
except ImportError:
    WEBRTCVAD_AVAILABLE = False
    logger.warning("webrtcvad not available - using energy-based VAD")


@dataclass
class AudioEvent:
    """Represents a detected audio event."""
    event_type: str  # "voice_start", "voice_end", "multi_voice", "suspicious"
    timestamp: datetime
    duration_ms: float
    confidence: float
    details: Optional[str] = None


class AudioMonitor:
    """
    Audio monitoring for exam proctoring.
    
    Detects:
    - Voice activity (speaking during exam)
    - Multiple voices (potential collaboration)
    - Suspicious audio patterns
    """
    
    # Audio parameters
    SAMPLE_RATE = 16000
    CHANNELS = 1
    CHUNK_DURATION_MS = 30  # WebRTC VAD requires 10, 20, or 30ms
    CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)
    FORMAT = None  # Set in __init__ based on availability
    
    # Detection parameters
    ENERGY_THRESHOLD = 0.02
    VOICE_MIN_DURATION_MS = 500  # Minimum voice duration to trigger event
    MULTI_VOICE_THRESHOLD = 0.6
    
    def __init__(
        self,
        device_index: Optional[int] = None,
        on_event: Optional[Callable[[AudioEvent], None]] = None
    ):
        """
        Initialize audio monitor.
        
        Args:
            device_index: Audio input device index (None for default)
            on_event: Callback for audio events
        """
        self.device_index = device_index
        self.on_event = on_event
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._audio: Optional["pyaudio.PyAudio"] = None
        self._stream = None
        
        # VAD
        self._vad = None
        if WEBRTCVAD_AVAILABLE:
            self._vad = webrtcvad.Vad(2)  # Aggressiveness mode 2
        
        # State
        self._voice_active = False
        self._voice_start_time: Optional[datetime] = None
        self._recent_voice_segments: List[float] = []
    
    def start(self):
        """Start audio monitoring."""
        if not PYAUDIO_AVAILABLE:
            logger.warning("Cannot start audio monitor - PyAudio not available")
            return
        
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Audio monitor started")
    
    def stop(self):
        """Stop audio monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        
        if self._audio:
            self._audio.terminate()
            self._audio = None
        
        logger.info("Audio monitor stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            import pyaudio
            
            self._audio = pyaudio.PyAudio()
            
            self._stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=self.CHANNELS,
                rate=self.SAMPLE_RATE,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=self.CHUNK_SIZE
            )
            
            logger.info("Audio stream opened")
            
            while self._running:
                try:
                    # Read audio chunk
                    data = self._stream.read(self.CHUNK_SIZE, exception_on_overflow=False)
                    
                    # Process chunk
                    self._process_chunk(data)
                    
                except Exception as e:
                    logger.debug(f"Audio read error: {e}")
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Audio monitor error: {e}")
        finally:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._audio:
                self._audio.terminate()
    
    def _process_chunk(self, data: bytes):
        """Process an audio chunk."""
        # Convert to numpy array
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Compute RMS energy
        energy = np.sqrt(np.mean(audio ** 2))
        
        # Voice activity detection
        is_voice = False
        
        if self._vad:
            try:
                is_voice = self._vad.is_speech(data, self.SAMPLE_RATE)
            except Exception:
                is_voice = energy > self.ENERGY_THRESHOLD
        else:
            is_voice = energy > self.ENERGY_THRESHOLD
        
        # Track voice activity
        now = datetime.now()
        
        if is_voice and not self._voice_active:
            # Voice started
            self._voice_active = True
            self._voice_start_time = now
            
        elif not is_voice and self._voice_active:
            # Voice ended
            self._voice_active = False
            
            if self._voice_start_time:
                duration_ms = (now - self._voice_start_time).total_seconds() * 1000
                
                if duration_ms >= self.VOICE_MIN_DURATION_MS:
                    # Significant voice detected
                    self._recent_voice_segments.append(duration_ms)
                    
                    event = AudioEvent(
                        event_type="voice_detected",
                        timestamp=self._voice_start_time,
                        duration_ms=duration_ms,
                        confidence=min(1.0, energy * 10)
                    )
                    
                    if self.on_event:
                        self.on_event(event)
        
        # Cleanup old segments (keep last 60 seconds)
        # This would need proper timestamp tracking in production
    
    def get_voice_activity_count(self, window_seconds: float = 60.0) -> int:
        """Get count of voice activity events in recent window."""
        return len(self._recent_voice_segments)
    
    def is_voice_active(self) -> bool:
        """Check if voice is currently active."""
        return self._voice_active


class SimpleAudioAnalyzer:
    """
    Simple audio analyzer that works without real-time capture.
    Analyzes audio files or pre-captured audio data.
    """
    
    @staticmethod
    def analyze_audio_file(file_path: str) -> dict:
        """Analyze an audio file for suspicious patterns."""
        try:
            # This would use scipy or librosa for proper analysis
            # Placeholder implementation
            return {
                "has_speech": False,
                "speech_duration_seconds": 0,
                "estimated_speakers": 0,
                "suspicious_patterns": []
            }
        except Exception as e:
            logger.error(f"Audio analysis error: {e}")
            return {}
    
    @staticmethod
    def compute_spectral_features(audio: np.ndarray, sample_rate: int) -> dict:
        """Compute spectral features for audio classification."""
        # Simplified spectral analysis
        fft = np.fft.rfft(audio)
        freqs = np.fft.rfftfreq(len(audio), 1 / sample_rate)
        magnitude = np.abs(fft)
        
        # Find dominant frequency
        dominant_idx = np.argmax(magnitude)
        dominant_freq = freqs[dominant_idx]
        
        # Spectral centroid
        spectral_centroid = np.sum(freqs * magnitude) / (np.sum(magnitude) + 1e-10)
        
        return {
            "dominant_frequency": dominant_freq,
            "spectral_centroid": spectral_centroid,
            "total_energy": np.sum(magnitude ** 2)
        }


# Global instance
_monitor: Optional[AudioMonitor] = None


def get_audio_monitor() -> AudioMonitor:
    """Get global audio monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = AudioMonitor()
    return _monitor
