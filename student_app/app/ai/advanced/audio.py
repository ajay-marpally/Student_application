import numpy as np
import torch
import pyaudio
import logging
import time
from collections import deque
from silero_vad import load_silero_vad

logger = logging.getLogger(__name__)

class AdvancedAudioMonitor:
    """
    Advanced audio monitor using Silero VAD for high-precision speech detection.
    Ported from ai-proctoring-system.
    """
    def __init__(self, callback=None):
        self.callback = callback
        self.sample_rate = 16000
        self.chunk_size = 512
        self.vad_model = load_silero_vad()
        
        self.speech_state = False
        self.speech_start_ts = None
        self.silence_start_ts = None
        self.silence_grace_seconds = 1.0
        self.speech_pattern_buffer = deque(maxlen=50)
        self.sustained_speech_threshold = 0.70
        self.suspicious_seconds = 3.0 # Duration threshold
        
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.running = False

    def start(self):
        def _callback(in_data, frame_count, time_info, status):
            audio_np = np.frombuffer(in_data, dtype=np.int16).astype(np.float32)
            if audio_np.size == 0:
                speech_prob = 0.0
            else:
                audio_np /= 32768.0
                if audio_np.size > 512:
                    audio_np = audio_np[:512]
                elif audio_np.size < 512:
                    audio_np = np.pad(audio_np, (0, 512 - audio_np.size))
                audio_tensor = torch.from_numpy(audio_np)
                speech_prob = float(self.vad_model(audio_tensor, self.sample_rate).detach())

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

            data = {
                "audio_spike": audio_spike,
                "speech_probability": speech_prob,
                "speech_ratio": speech_ratio
            }
            if self.callback:
                self.callback(data)
            return (in_data, pyaudio.paContinue)

        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=_callback
        )
        self.stream.start_stream()
        self.running = True
        logger.info("Advanced Audio Monitor started with Silero VAD")

    def stop(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()
        self.running = False
