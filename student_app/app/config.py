"""
Student Exam Application - Configuration Management

Handles loading of signed policy configuration and environment variables.
All thresholds are configurable via server-provided signed policy.
"""

import os
import json
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)


@dataclass
class ThresholdConfig:
    """Detection thresholds - configurable via policy"""
    # Head rotation thresholds
    TH_FREQ: int = 8  # 5-minute frequency threshold
    TH_BURST: int = 4  # 30-second burst threshold
    DURATION_HIGH_SECONDS: float = 8.0  # Long rotation duration
    HEAD_ROTATION_ANGLE: float = 25.0  # Degrees for left/right
    
    # Face detection
    T_ABSENT_SECONDS: float = 10.0  # Face absent threshold
    FACE_CONFIDENCE_MIN: float = 0.7  # Minimum face detection confidence
    
    # Gaze tracking
    T_GAZE_SECONDS: float = 5.0  # Gaze away threshold
    GAZE_ANGLE_THRESHOLD: float = 30.0  # Degrees for gaze away
    
    # Audio
    VOICE_ENERGY_THRESHOLD: float = 0.02  # VAD energy threshold
    MULTI_VOICE_THRESHOLD: float = 0.6  # Multi-speaker detection
    
    # Evidence
    CLIP_UPLOAD_MIN_CONFIDENCE: float = 0.6
    BUFFER_MINUTES: int = 10
    CLIP_PADDING_SECONDS: float = 5.0
    
    # UI
    AUTOSAVE_INTERVAL_SECONDS: int = 30
    INSTRUCTION_DURATION_MINUTES: int = 5
    
    # Windows
    WINDOW_CHECK_INTERVAL_MS: int = 500


@dataclass
class SupabaseConfig:
    """Supabase connection configuration"""
    url: str = ""
    key: str = ""
    service_key: str = ""  # For admin operations
    storage_bucket: str = "evidence"


@dataclass
class AppConfig:
    """Main application configuration"""
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)
    
    # Paths
    data_dir: Path = field(default_factory=lambda: Path.home() / ".student_exam_app")
    log_file: Path = field(default_factory=lambda: Path.home() / ".student_exam_app" / "app.log")
    evidence_dir: Path = field(default_factory=lambda: Path.home() / ".student_exam_app" / "evidence")
    queue_db: Path = field(default_factory=lambda: Path.home() / ".student_exam_app" / "queue.db")
    
    # Policy
    policy_public_key: Optional[bytes] = None
    policy_verified: bool = False
    
    # Runtime
    debug_mode: bool = False
    camera_index: int = 0


class ConfigManager:
    """Manages loading and verification of configuration"""
    
    # Default public key for policy verification (placeholder - replace in production)
    DEFAULT_PUBLIC_KEY = None
    
    def __init__(self):
        self.config = AppConfig()
        self._load_environment()
        self._ensure_directories()
    
    def _load_environment(self):
        """Load configuration from environment variables"""
        from dotenv import load_dotenv
        load_dotenv()
        
        # Supabase
        self.config.supabase.url = os.getenv(
            "SUPABASE_URL",
            os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
        )
        self.config.supabase.key = os.getenv(
            "SUPABASE_KEY",
            os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY", "")
        )
        self.config.supabase.service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        
        # Debug mode
        self.config.debug_mode = os.getenv("DEBUG", "false").lower() == "true"
        
        # Camera
        self.config.camera_index = int(os.getenv("CAMERA_INDEX", "0"))
        
        logger.info(f"Loaded configuration: Supabase URL = {self.config.supabase.url[:30]}...")
    
    def _ensure_directories(self):
        """Create necessary directories"""
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.evidence_dir.mkdir(parents=True, exist_ok=True)
    
    def load_policy(self, policy_path: Optional[Path] = None) -> bool:
        """
        Load and verify signed policy file.
        
        Returns True if policy is valid and applied.
        """
        if policy_path is None:
            policy_path = self.config.data_dir / "policy.json"
        
        if not policy_path.exists():
            logger.warning("No policy file found, using defaults")
            return False
        
        try:
            with open(policy_path, "r") as f:
                policy_data = json.load(f)
            
            # Verify signature if we have a public key
            if self.config.policy_public_key and "signature" in policy_data:
                if not self._verify_policy_signature(policy_data):
                    logger.error("Policy signature verification failed!")
                    return False
                self.config.policy_verified = True
            
            # Apply thresholds
            if "thresholds" in policy_data:
                self._apply_thresholds(policy_data["thresholds"])
            
            if "angles" in policy_data:
                angles = policy_data["angles"]
                if "head_rotation_threshold_degrees" in angles:
                    self.config.thresholds.HEAD_ROTATION_ANGLE = angles["head_rotation_threshold_degrees"]
                if "gaze_away_threshold_degrees" in angles:
                    self.config.thresholds.GAZE_ANGLE_THRESHOLD = angles["gaze_away_threshold_degrees"]
            
            logger.info("Policy loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load policy: {e}")
            return False
    
    def _verify_policy_signature(self, policy_data: dict) -> bool:
        """Verify RSA signature of policy data"""
        try:
            signature = bytes.fromhex(policy_data["signature"])
            
            # Create payload without signature
            payload = {k: v for k, v in policy_data.items() if k != "signature"}
            payload_bytes = json.dumps(payload, sort_keys=True).encode()
            
            # Load public key
            public_key = serialization.load_pem_public_key(self.config.policy_public_key)
            
            # Verify
            public_key.verify(
                signature,
                payload_bytes,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True
            
        except InvalidSignature:
            return False
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False
    
    def _apply_thresholds(self, thresholds: dict):
        """Apply threshold values from policy"""
        mapping = {
            "TH_FREQ": "TH_FREQ",
            "TH_BURST": "TH_BURST",
            "DURATION_HIGH_SECONDS": "DURATION_HIGH_SECONDS",
            "T_ABSENT_SECONDS": "T_ABSENT_SECONDS",
            "T_GAZE_SECONDS": "T_GAZE_SECONDS",
            "clip_upload_min_confidence": "CLIP_UPLOAD_MIN_CONFIDENCE",
            "buffer_minutes": "BUFFER_MINUTES",
            "clip_padding_seconds": "CLIP_PADDING_SECONDS",
            "autosave_interval_seconds": "AUTOSAVE_INTERVAL_SECONDS",
        }
        
        for policy_key, config_attr in mapping.items():
            if policy_key in thresholds:
                setattr(self.config.thresholds, config_attr, thresholds[policy_key])
    
    def get_default_policy(self) -> dict:
        """Generate default policy JSON for reference"""
        return {
            "thresholds": {
                "TH_FREQ": self.config.thresholds.TH_FREQ,
                "TH_BURST": self.config.thresholds.TH_BURST,
                "DURATION_HIGH_SECONDS": self.config.thresholds.DURATION_HIGH_SECONDS,
                "T_ABSENT_SECONDS": self.config.thresholds.T_ABSENT_SECONDS,
                "T_GAZE_SECONDS": self.config.thresholds.T_GAZE_SECONDS,
                "clip_upload_min_confidence": self.config.thresholds.CLIP_UPLOAD_MIN_CONFIDENCE,
                "buffer_minutes": self.config.thresholds.BUFFER_MINUTES,
                "clip_padding_seconds": self.config.thresholds.CLIP_PADDING_SECONDS,
                "autosave_interval_seconds": self.config.thresholds.AUTOSAVE_INTERVAL_SECONDS,
            },
            "angles": {
                "head_rotation_threshold_degrees": self.config.thresholds.HEAD_ROTATION_ANGLE,
                "gaze_away_threshold_degrees": self.config.thresholds.GAZE_ANGLE_THRESHOLD,
            }
        }


# Global config instance
_config_manager: Optional[ConfigManager] = None


def get_config() -> AppConfig:
    """Get the global configuration instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager.config


def get_config_manager() -> ConfigManager:
    """Get the configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
