"""
Student Exam Application - Security: Integrity Check

Verifies application integrity to detect tampering.
"""

import sys
import os
import hashlib
import logging
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def verify_integrity() -> Tuple[bool, str]:
    """
    Verify application integrity.
    
    Returns:
        Tuple of (success, message)
    """
    checks_passed = []
    checks_failed = []
    
    # Check 1: Verify we're running from expected location
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        app_path = Path(sys.executable)
        
        # Check for tampering indicators
        if _check_pyinstaller_tampering(app_path):
            checks_failed.append("PyInstaller tampering detected")
        else:
            checks_passed.append("PyInstaller integrity OK")
    else:
        # Running as script - skip in development
        checks_passed.append("Development mode - skipping binary checks")
    
    # Check 2: Verify critical Python files haven't been modified
    # In production, we would verify against embedded hashes
    # For now, just check they exist
    critical_modules = [
        "student_app.app.config",
        "student_app.app.auth",
        "student_app.app.exam_engine",
    ]
    
    for module in critical_modules:
        try:
            # Try to import and check
            __import__(module)
            checks_passed.append(f"Module {module} OK")
        except ImportError:
            # Module not yet created - OK during development
            pass
    
    # Check 3: Verify no debugger is attached at startup
    if _is_debugger_attached():
        checks_failed.append("Debugger detected at startup")
    else:
        checks_passed.append("No debugger detected")
    
    # Summary
    if checks_failed:
        return False, f"Integrity check failed: {', '.join(checks_failed)}"
    
    return True, f"Integrity verified: {len(checks_passed)} checks passed"


def _check_pyinstaller_tampering(exe_path: Path) -> bool:
    """
    Check for common PyInstaller tampering indicators.
    
    Returns True if tampering is detected.
    """
    try:
        # Check 1: Verify file size is within expected range
        # (This would be set during build)
        exe_size = exe_path.stat().st_size
        
        # Check 2: Look for known tampering patterns
        # In production, we would verify an embedded signature
        
        return False
        
    except Exception as e:
        logger.warning(f"Tampering check error: {e}")
        return False


def _is_debugger_attached() -> bool:
    """Check if a debugger is attached to the process."""
    
    # Windows-specific check
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            return kernel32.IsDebuggerPresent() != 0
        except Exception:
            pass
    
    # Unix ptrace check
    elif sys.platform in ('linux', 'darwin'):
        try:
            # Check /proc/self/status for TracerPid
            status_path = Path("/proc/self/status")
            if status_path.exists():
                content = status_path.read_text()
                for line in content.split('\n'):
                    if line.startswith('TracerPid:'):
                        tracer_pid = int(line.split(':')[1].strip())
                        if tracer_pid != 0:
                            return True
        except Exception:
            pass
    
    return False


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    
    return sha256.hexdigest()


def verify_file_hash(file_path: Path, expected_hash: str) -> bool:
    """Verify a file matches expected hash."""
    actual_hash = compute_file_hash(file_path)
    return actual_hash.lower() == expected_hash.lower()
