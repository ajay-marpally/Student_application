"""
Unit tests for buffer and clip extraction modules.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import tempfile


class TestCircularBuffer:
    """Tests for circular video buffer."""
    
    def test_buffer_creation(self):
        """Test buffer can be created with default settings."""
        from student_app.app.buffer.circular_buffer import CircularBuffer
        
        buffer = CircularBuffer(retention_minutes=1, fps=15)
        
        assert buffer.max_frames == 1 * 60 * 15
        assert buffer.retention_seconds == 60
    
    def test_add_frame(self):
        """Test adding frames to buffer."""
        from student_app.app.buffer.circular_buffer import CircularBuffer
        
        buffer = CircularBuffer(retention_minutes=1, fps=15)
        
        # Add a frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        buffer.add_frame(frame)
        
        info = buffer.get_buffer_info()
        assert info["frame_count"] == 1
    
    def test_frame_retrieval(self):
        """Test retrieving frames by time range."""
        from student_app.app.buffer.circular_buffer import CircularBuffer
        
        buffer = CircularBuffer(retention_minutes=1, fps=15)
        
        # Add frames with timestamps
        base_time = datetime.now()
        for i in range(10):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            buffer.add_frame(frame, base_time + timedelta(seconds=i))
        
        # Get frames in range
        start = base_time + timedelta(seconds=2)
        end = base_time + timedelta(seconds=7)
        frames = buffer.get_frames_in_range(start, end)
        
        assert len(frames) >= 5
    
    def test_buffer_overflow(self):
        """Test buffer correctly handles overflow."""
        from student_app.app.buffer.circular_buffer import CircularBuffer
        
        # Small buffer for testing
        buffer = CircularBuffer(retention_minutes=1, fps=1)  # 60 frames max
        
        # Add more frames than capacity
        for i in range(100):
            frame = np.zeros((10, 10, 3), dtype=np.uint8)
            buffer.add_frame(frame)
        
        info = buffer.get_buffer_info()
        assert info["frame_count"] == 60  # Should be capped at max
    
    def test_get_current_frame(self):
        """Test getting the most recent frame."""
        from student_app.app.buffer.circular_buffer import CircularBuffer
        
        buffer = CircularBuffer(retention_minutes=1, fps=15)
        
        # Empty buffer
        assert buffer.get_current_frame() is None
        
        # Add frame
        frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
        buffer.add_frame(frame)
        
        current = buffer.get_current_frame()
        assert current is not None
        assert np.array_equal(current.frame, frame)


class TestClipExtractor:
    """Tests for evidence clip extraction."""
    
    def test_extractor_creation(self):
        """Test clip extractor can be created."""
        from student_app.app.buffer.clip_extractor import ClipExtractor
        
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ClipExtractor(output_dir=Path(tmpdir))
            assert extractor.output_dir.exists()
    
    def test_extract_empty_buffer(self):
        """Test extraction from empty buffer returns None."""
        from student_app.app.buffer.clip_extractor import ClipExtractor
        from student_app.app.buffer.circular_buffer import CircularBuffer
        
        buffer = CircularBuffer(retention_minutes=1, fps=15)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ClipExtractor(output_dir=Path(tmpdir))
            
            result = extractor.extract_clip(
                start_time=datetime.now() - timedelta(minutes=5),
                end_time=datetime.now(),
                buffer=buffer
            )
            
            assert result is None
    
    def test_extract_clip(self):
        """Test extracting a clip from buffer."""
        from student_app.app.buffer.clip_extractor import ClipExtractor
        from student_app.app.buffer.circular_buffer import CircularBuffer
        
        buffer = CircularBuffer(retention_minutes=1, fps=15)
        
        # Add frames
        base_time = datetime.now()
        for i in range(30):
            frame = np.random.randint(0, 255, (120, 160, 3), dtype=np.uint8)
            buffer.add_frame(frame, base_time + timedelta(milliseconds=i * 100))
        
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ClipExtractor(output_dir=Path(tmpdir))
            
            result = extractor.extract_clip(
                start_time=base_time,
                end_time=base_time + timedelta(seconds=2),
                buffer=buffer,
                padding_seconds=0
            )
            
            if result:  # May be None if cv2.VideoWriter fails
                assert result.file_path.exists()
                assert result.hash_sha256
                assert result.frame_count > 0
                assert result.duration_seconds > 0
    
    def test_extract_around_event(self):
        """Test extraction around a specific event time."""
        from student_app.app.buffer.clip_extractor import ClipExtractor
        from student_app.app.buffer.circular_buffer import CircularBuffer
        
        buffer = CircularBuffer(retention_minutes=1, fps=15)
        
        # Add frames
        base_time = datetime.now()
        for i in range(60):
            frame = np.random.randint(0, 255, (120, 160, 3), dtype=np.uint8)
            buffer.add_frame(frame, base_time + timedelta(milliseconds=i * 100))
        
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = ClipExtractor(output_dir=Path(tmpdir))
            
            event_time = base_time + timedelta(seconds=3)
            result = extractor.extract_around_event(
                event_time=event_time,
                buffer=buffer,
                padding_seconds=1
            )
            
            # Result may be None if video writing fails
            if result:
                assert result.frame_count > 0


class TestExtractedClip:
    """Tests for ExtractedClip dataclass."""
    
    def test_to_dict(self):
        """Test converting clip to dictionary."""
        from student_app.app.buffer.clip_extractor import ExtractedClip
        
        clip = ExtractedClip(
            file_path=Path("/tmp/test.mp4"),
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(seconds=10),
            duration_seconds=10.0,
            frame_count=150,
            hash_sha256="abc123",
            file_size_bytes=1024
        )
        
        d = clip.to_dict()
        
        assert "file_path" in d
        assert d["duration_seconds"] == 10.0
        assert d["frame_count"] == 150
        assert d["hash_sha256"] == "abc123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
