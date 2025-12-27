"""
Unit tests for face verification module.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


class TestFaceVerifier:
    """Tests for biometric face verification."""
    
    def test_verification_available_check(self):
        """Test checking if face_recognition is available."""
        from student_app.app.ai.face_verifier import is_face_verification_available
        
        # Should return True or False without error
        result = is_face_verification_available()
        assert isinstance(result, bool)
    
    @pytest.mark.skipif(
        not pytest.importorskip("face_recognition", reason="face_recognition not installed"),
        reason="face_recognition not available"
    )
    def test_verifier_creation(self):
        """Test face verifier can be created."""
        from student_app.app.ai.face_verifier import FaceVerifier
        
        verifier = FaceVerifier()
        
        assert verifier is not None
        assert verifier.match_threshold == 0.6
        assert verifier.consecutive_threshold == 5
    
    @pytest.mark.skipif(
        not pytest.importorskip("face_recognition", reason="face_recognition not installed"),
        reason="face_recognition not available"
    )
    def test_not_ready_without_reference(self):
        """Test verifier is not ready without loading reference."""
        from student_app.app.ai.face_verifier import FaceVerifier
        
        verifier = FaceVerifier()
        
        assert verifier.is_ready is False
    
    @pytest.mark.skipif(
        not pytest.importorskip("face_recognition", reason="face_recognition not installed"),
        reason="face_recognition not available"
    )
    def test_consecutive_mismatch_tracking(self):
        """Test consecutive mismatch tracking."""
        from student_app.app.ai.face_verifier import FaceVerifier
        
        verifier = FaceVerifier(consecutive_threshold=3)
        
        # Simulate mismatches
        for _ in range(3):
            verifier._track_result(is_match=False)
        
        should_alert, reason = verifier.should_alert()
        assert should_alert is True
        assert "consecutive" in reason.lower()
    
    @pytest.mark.skipif(
        not pytest.importorskip("face_recognition", reason="face_recognition not installed"),
        reason="face_recognition not available"
    )
    def test_reset_on_match(self):
        """Test consecutive count resets on match."""
        from student_app.app.ai.face_verifier import FaceVerifier
        
        verifier = FaceVerifier(consecutive_threshold=5)
        
        # Add some mismatches
        for _ in range(4):
            verifier._track_result(is_match=False)
        
        # Should not alert yet
        should_alert, _ = verifier.should_alert()
        assert should_alert is False
        
        # Match resets the count
        verifier._track_result(is_match=True)
        
        stats = verifier.get_stats()
        assert stats["consecutive_mismatches"] == 0
    
    @pytest.mark.skipif(
        not pytest.importorskip("face_recognition", reason="face_recognition not installed"),
        reason="face_recognition not available"
    )
    def test_verify_without_reference_returns_match(self):
        """Test verify returns match=True when no reference loaded."""
        from student_app.app.ai.face_verifier import FaceVerifier
        import numpy as np
        
        verifier = FaceVerifier()
        
        # Create dummy frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        result = verifier.verify(frame)
        
        # Should default to match when no reference
        assert result.is_match is True
        assert "No reference loaded" in result.message
    
    @pytest.mark.skipif(
        not pytest.importorskip("face_recognition", reason="face_recognition not installed"),
        reason="face_recognition not available"
    )
    def test_stats_output(self):
        """Test stats output format."""
        from student_app.app.ai.face_verifier import FaceVerifier
        
        verifier = FaceVerifier()
        stats = verifier.get_stats()
        
        assert "reference_loaded" in stats
        assert "consecutive_mismatches" in stats
        assert "match_threshold" in stats
        assert "consecutive_threshold" in stats


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""
    
    def test_result_fields(self):
        """Test VerificationResult has required fields."""
        from student_app.app.ai.face_verifier import VerificationResult
        
        result = VerificationResult(
            is_match=True,
            similarity=0.85,
            distance=0.3,
            confidence=0.9,
            message="Test"
        )
        
        assert result.is_match is True
        assert result.similarity == 0.85
        assert result.distance == 0.3
        assert result.confidence == 0.9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
