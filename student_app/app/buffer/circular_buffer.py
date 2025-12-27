"""
Student Exam Application - Buffer: Circular Video Buffer

Rolling buffer for video frames with configurable retention.
Enables extraction of evidence clips from past events.
"""

import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Generator
from dataclasses import dataclass
import numpy as np
import cv2

from student_app.app.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class BufferedFrame:
    """A frame stored in the buffer."""
    frame: np.ndarray
    timestamp: datetime
    frame_number: int


class CircularBuffer:
    """
    Thread-safe circular buffer for video frames.
    
    Maintains a rolling window of recent frames for evidence extraction.
    Default retention: 10 minutes at 15 FPS = 9000 frames.
    """
    
    def __init__(
        self,
        retention_minutes: Optional[int] = None,
        fps: int = 15
    ):
        """
        Initialize circular buffer.
        
        Args:
            retention_minutes: Minutes of video to retain
            fps: Expected frames per second
        """
        config = get_config()
        retention_minutes = retention_minutes or config.thresholds.BUFFER_MINUTES
        
        self.retention_seconds = retention_minutes * 60
        self.fps = fps
        self.max_frames = retention_minutes * 60 * fps
        
        self._lock = threading.RLock()
        self._frames: deque = deque(maxlen=self.max_frames)
        self._frame_counter = 0
        
        # Audio buffer (parallel storage)
        self._audio_chunks: deque = deque(maxlen=self.retention_seconds * 50)  # ~50 chunks/sec
        
        logger.info(f"Circular buffer initialized: {retention_minutes} min, ~{self.max_frames} frames")
    
    def add_frame(self, frame: np.ndarray, timestamp: Optional[datetime] = None):
        """
        Add a frame to the buffer.
        
        Args:
            frame: OpenCV BGR frame
            timestamp: Frame timestamp (uses current time if not provided)
        """
        if frame is None:
            return
        
        timestamp = timestamp or datetime.now()
        
        with self._lock:
            self._frame_counter += 1
            
            buffered = BufferedFrame(
                frame=frame.copy(),  # Copy to prevent external modification
                timestamp=timestamp,
                frame_number=self._frame_counter
            )
            
            self._frames.append(buffered)
    
    def add_audio_chunk(self, audio_data: bytes, timestamp: Optional[datetime] = None):
        """
        Add an audio chunk to the buffer.
        
        Args:
            audio_data: Raw audio bytes
            timestamp: Chunk timestamp
        """
        timestamp = timestamp or datetime.now()
        
        with self._lock:
            self._audio_chunks.append((timestamp, audio_data))
    
    def get_frames_in_range(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[BufferedFrame]:
        """
        Get all frames within a time range.
        
        Args:
            start_time: Start of range
            end_time: End of range
            
        Returns:
            List of frames in range
        """
        with self._lock:
            return [
                f for f in self._frames
                if start_time <= f.timestamp <= end_time
            ]
    
    def get_frames_around(
        self,
        center_time: datetime,
        padding_seconds: float = 5.0
    ) -> List[BufferedFrame]:
        """
        Get frames around a specific time.
        
        Args:
            center_time: Center timestamp
            padding_seconds: Seconds before and after
            
        Returns:
            List of frames in padded range
        """
        padding = timedelta(seconds=padding_seconds)
        return self.get_frames_in_range(
            center_time - padding,
            center_time + padding
        )
    
    def get_audio_in_range(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> bytes:
        """
        Get audio data within a time range.
        
        Args:
            start_time: Start of range
            end_time: End of range
            
        Returns:
            Concatenated audio bytes
        """
        with self._lock:
            chunks = [
                data for ts, data in self._audio_chunks
                if start_time <= ts <= end_time
            ]
            return b''.join(chunks)
    
    def get_current_frame(self) -> Optional[BufferedFrame]:
        """Get the most recent frame."""
        with self._lock:
            if self._frames:
                return self._frames[-1]
            return None
    
    def get_buffer_info(self) -> dict:
        """Get buffer statistics."""
        with self._lock:
            if not self._frames:
                return {
                    "frame_count": 0,
                    "duration_seconds": 0,
                    "memory_mb": 0
                }
            
            oldest = self._frames[0].timestamp
            newest = self._frames[-1].timestamp
            duration = (newest - oldest).total_seconds()
            
            # Estimate memory usage
            if self._frames:
                frame_size = self._frames[0].frame.nbytes
                memory_bytes = len(self._frames) * frame_size
                memory_mb = memory_bytes / (1024 * 1024)
            else:
                memory_mb = 0
            
            return {
                "frame_count": len(self._frames),
                "duration_seconds": duration,
                "memory_mb": memory_mb,
                "oldest_timestamp": oldest.isoformat(),
                "newest_timestamp": newest.isoformat()
            }
    
    def iter_frames(self) -> Generator[BufferedFrame, None, None]:
        """Iterate over all buffered frames."""
        with self._lock:
            for frame in self._frames:
                yield frame
    
    def clear(self):
        """Clear all buffered data."""
        with self._lock:
            self._frames.clear()
            self._audio_chunks.clear()
            logger.info("Circular buffer cleared")


class BufferManager:
    """
    Manages the circular buffer with automatic cleanup and statistics.
    """
    
    def __init__(self):
        self.buffer = CircularBuffer()
        self._running = False
        self._stats_thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start buffer management."""
        self._running = True
        self._stats_thread = threading.Thread(target=self._stats_loop, daemon=True)
        self._stats_thread.start()
        logger.info("Buffer manager started")
    
    def stop(self):
        """Stop buffer management."""
        self._running = False
        if self._stats_thread:
            self._stats_thread.join(timeout=2.0)
            self._stats_thread = None
    
    def _stats_loop(self):
        """Periodic statistics logging."""
        while self._running:
            time.sleep(60)  # Log every minute
            if self._running:
                info = self.buffer.get_buffer_info()
                logger.debug(
                    f"Buffer stats: {info['frame_count']} frames, "
                    f"{info['duration_seconds']:.1f}s, "
                    f"{info['memory_mb']:.1f}MB"
                )


# Global instances
_buffer: Optional[CircularBuffer] = None
_manager: Optional[BufferManager] = None


def get_circular_buffer() -> CircularBuffer:
    """Get global circular buffer instance."""
    global _buffer
    if _buffer is None:
        _buffer = CircularBuffer()
    return _buffer


def get_buffer_manager() -> BufferManager:
    """Get global buffer manager instance."""
    global _manager
    if _manager is None:
        _manager = BufferManager()
    return _manager
