"""
Student Exam Application - Buffer: Clip Extractor

Extracts video clips from the circular buffer for evidence.
"""

import logging
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from dataclasses import dataclass
import cv2
import numpy as np

from student_app.app.config import get_config
from student_app.app.buffer.circular_buffer import CircularBuffer, get_circular_buffer, BufferedFrame

logger = logging.getLogger(__name__)


@dataclass
class ExtractedClip:
    """Represents an extracted evidence clip."""
    file_path: Path
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    frame_count: int
    hash_sha256: str
    file_size_bytes: int
    encoding_format: str = "mp4"
    
    def to_dict(self) -> dict:
        return {
            "file_path": str(self.file_path),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": self.duration_seconds,
            "frame_count": self.frame_count,
            "hash_sha256": self.hash_sha256,
            "file_size_bytes": self.file_size_bytes,
            "encoding_format": self.encoding_format
        }


class ClipExtractor:
    """
    Extracts video clips from the circular buffer.
    
    Creates evidence clips with:
    - Configurable padding around events
    - Multiple encoding formats
    - SHA-256 integrity hashes
    """
    
    # Encoding parameters
    FOURCC_MP4 = cv2.VideoWriter_fourcc(*'mp4v')
    FOURCC_AVI = cv2.VideoWriter_fourcc(*'XVID')
    
    def __init__(
        self,
        output_dir: Optional[Path] = None,
        default_fps: int = 15
    ):
        """
        Initialize clip extractor.
        
        Args:
            output_dir: Directory for output clips
            default_fps: Default FPS for output videos
        """
        config = get_config()
        self.output_dir = output_dir or config.evidence_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.default_fps = default_fps
        self.padding_seconds = config.thresholds.CLIP_PADDING_SECONDS
    
    def extract_clip(
        self,
        start_time: datetime,
        end_time: datetime,
        buffer: Optional[CircularBuffer] = None,
        padding_seconds: Optional[float] = None
    ) -> Optional[ExtractedClip]:
        """
        Extract a video clip from the buffer.
        
        Args:
            start_time: Start of clip
            end_time: End of clip
            buffer: CircularBuffer to use (uses global if None)
            padding_seconds: Padding to add before/after
            
        Returns:
            ExtractedClip with file path and metadata, or None on failure
        """
        buffer = buffer or get_circular_buffer()
        padding = padding_seconds if padding_seconds is not None else self.padding_seconds
        
        # Apply padding
        padded_start = start_time - timedelta(seconds=padding)
        padded_end = end_time + timedelta(seconds=padding)
        
        # Get frames from buffer
        frames = buffer.get_frames_in_range(padded_start, padded_end)
        
        if not frames:
            logger.warning(f"No frames found in range {padded_start} to {padded_end}")
            return None
        
        logger.info(f"Extracting clip: {len(frames)} frames from {padded_start} to {padded_end}")
        
        # Generate output filename
        timestamp_str = start_time.strftime("%Y%m%d_%H%M%S_%f")
        output_path = self.output_dir / f"evidence_{timestamp_str}.mp4"
        
        # Write video
        success = self._write_video(frames, output_path)
        
        if not success:
            logger.error(f"Failed to write video: {output_path}")
            return None
        
        # Calculate hash
        file_hash = self._compute_hash(output_path)
        file_size = output_path.stat().st_size
        
        actual_start = frames[0].timestamp
        actual_end = frames[-1].timestamp
        duration = (actual_end - actual_start).total_seconds()
        
        clip = ExtractedClip(
            file_path=output_path,
            start_time=actual_start,
            end_time=actual_end,
            duration_seconds=duration,
            frame_count=len(frames),
            hash_sha256=file_hash,
            file_size_bytes=file_size
        )
        
        logger.info(f"Clip extracted: {output_path} ({duration:.1f}s, {file_hash[:16]}...)")
        return clip
    
    def extract_around_event(
        self,
        event_time: datetime,
        buffer: Optional[CircularBuffer] = None,
        padding_seconds: Optional[float] = None
    ) -> Optional[ExtractedClip]:
        """
        Extract a clip centered around an event.
        
        Args:
            event_time: Time of the event
            buffer: CircularBuffer to use
            padding_seconds: Padding before and after event
            
        Returns:
            ExtractedClip or None
        """
        padding = padding_seconds if padding_seconds is not None else self.padding_seconds
        
        return self.extract_clip(
            start_time=event_time - timedelta(seconds=padding),
            end_time=event_time + timedelta(seconds=padding),
            buffer=buffer,
            padding_seconds=0  # Already applied padding
        )
    
    def extract_multiple_events(
        self,
        events: List[datetime],
        buffer: Optional[CircularBuffer] = None,
        merge_threshold_seconds: float = 10.0
    ) -> List[ExtractedClip]:
        """
        Extract clips for multiple events, merging nearby events.
        
        Args:
            events: List of event timestamps
            buffer: CircularBuffer to use
            merge_threshold_seconds: Merge events closer than this
            
        Returns:
            List of extracted clips
        """
        if not events:
            return []
        
        # Sort events
        sorted_events = sorted(events)
        
        # Merge nearby events into time ranges
        ranges: List[Tuple[datetime, datetime]] = []
        current_start = sorted_events[0]
        current_end = sorted_events[0]
        
        for event_time in sorted_events[1:]:
            if (event_time - current_end).total_seconds() <= merge_threshold_seconds:
                # Extend current range
                current_end = event_time
            else:
                # Start new range
                ranges.append((current_start, current_end))
                current_start = event_time
                current_end = event_time
        
        ranges.append((current_start, current_end))
        
        # Extract clip for each range
        clips = []
        for start, end in ranges:
            clip = self.extract_clip(start, end, buffer)
            if clip:
                clips.append(clip)
        
        return clips
    
    def _write_video(
        self,
        frames: List[BufferedFrame],
        output_path: Path
    ) -> bool:
        """Write frames to video file."""
        if not frames:
            return False
        
        try:
            # Get frame dimensions
            height, width = frames[0].frame.shape[:2]
            
            # Calculate actual FPS from timestamps
            if len(frames) > 1:
                total_time = (frames[-1].timestamp - frames[0].timestamp).total_seconds()
                actual_fps = len(frames) / max(total_time, 0.1)
            else:
                actual_fps = self.default_fps
            
            # Create video writer
            writer = cv2.VideoWriter(
                str(output_path),
                self.FOURCC_MP4,
                actual_fps,
                (width, height)
            )
            
            if not writer.isOpened():
                logger.error("Failed to open video writer")
                return False
            
            # Write frames
            for buffered in frames:
                writer.write(buffered.frame)
            
            writer.release()
            return True
            
        except Exception as e:
            logger.error(f"Video write error: {e}")
            return False
    
    def _compute_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    def create_thumbnail(
        self,
        clip: ExtractedClip,
        frame_index: int = 0
    ) -> Optional[Path]:
        """
        Create a thumbnail image from a clip.
        
        Args:
            clip: The extracted clip
            frame_index: Which frame to use (0 = first)
            
        Returns:
            Path to thumbnail image
        """
        try:
            cap = cv2.VideoCapture(str(clip.file_path))
            
            # Seek to frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return None
            
            # Generate thumbnail path
            thumb_path = clip.file_path.with_suffix('.jpg')
            
            # Resize if too large
            max_dim = 320
            h, w = frame.shape[:2]
            if max(h, w) > max_dim:
                scale = max_dim / max(h, w)
                frame = cv2.resize(frame, None, fx=scale, fy=scale)
            
            cv2.imwrite(str(thumb_path), frame)
            return thumb_path
            
        except Exception as e:
            logger.error(f"Thumbnail creation error: {e}")
            return None


# Global instance
_extractor: Optional[ClipExtractor] = None


def get_clip_extractor() -> ClipExtractor:
    """Get global clip extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = ClipExtractor()
    return _extractor
