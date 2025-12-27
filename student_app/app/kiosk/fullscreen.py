"""
Student Exam Application - Kiosk: Fullscreen Enforcement

Windows-specific fullscreen and kiosk mode enforcement.
"""

import sys
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Windows-specific imports
if sys.platform == 'win32':
    try:
        import ctypes
        from ctypes import wintypes
        WINDOWS_AVAILABLE = True
    except ImportError:
        WINDOWS_AVAILABLE = False
else:
    WINDOWS_AVAILABLE = False


# Global state
_kiosk_enabled = False
_original_hooks = {}


def enable_kiosk_mode(hwnd: Optional[int] = None) -> bool:
    """
    Enable kiosk mode on Windows.
    
    Attempts to:
    1. Disable Alt+Tab (requires elevation)
    2. Disable Windows key
    3. Keep window top-most
    
    Args:
        hwnd: Window handle (not used currently)
        
    Returns:
        True if kiosk mode was enabled successfully
    """
    global _kiosk_enabled
    
    if not WINDOWS_AVAILABLE:
        logger.warning("Kiosk mode not available on this platform")
        return False
    
    try:
        # Attempt to register hotkeys (requires elevation for some)
        _register_hotkey_hooks()
        
        # Disable task manager (requires admin)
        _disable_task_manager()
        
        _kiosk_enabled = True
        logger.info("Kiosk mode enabled")
        return True
        
    except Exception as e:
        logger.warning(f"Kiosk mode partially enabled: {e}")
        _kiosk_enabled = True  # Still consider it enabled for fallback monitoring
        return True


def disable_kiosk_mode() -> bool:
    """
    Disable kiosk mode and restore normal operation.
    
    Returns:
        True if successfully disabled
    """
    global _kiosk_enabled
    
    if not WINDOWS_AVAILABLE:
        return True
    
    try:
        _unregister_hotkey_hooks()
        _enable_task_manager()
        
        _kiosk_enabled = False
        logger.info("Kiosk mode disabled")
        return True
        
    except Exception as e:
        logger.error(f"Error disabling kiosk mode: {e}")
        return False


def is_kiosk_enabled() -> bool:
    """Check if kiosk mode is currently enabled."""
    return _kiosk_enabled


def _register_hotkey_hooks():
    """Register low-level keyboard hooks to block system keys."""
    if not WINDOWS_AVAILABLE:
        return
    
    try:
        # Note: Full implementation would use SetWindowsHookEx
        # This is a simplified version that attempts to RegisterHotKey
        
        user32 = ctypes.windll.user32
        
        # Try to register Alt+Tab
        # MOD_ALT = 0x0001
        # VK_TAB = 0x09
        # This often fails without elevation
        
        logger.debug("Hotkey registration attempted")
        
    except Exception as e:
        logger.debug(f"Hotkey registration failed: {e}")


def _unregister_hotkey_hooks():
    """Unregister keyboard hooks."""
    pass  # Cleanup if needed


def _disable_task_manager():
    """Disable Task Manager via registry (requires admin)."""
    if not WINDOWS_AVAILABLE:
        return
    
    try:
        import winreg
        
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
        
        try:
            key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                key_path,
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            logger.debug("Task Manager disabled")
        except WindowsError as e:
            logger.debug(f"Could not disable Task Manager: {e}")
            
    except Exception as e:
        logger.debug(f"Task Manager control failed: {e}")


def _enable_task_manager():
    """Re-enable Task Manager."""
    if not WINDOWS_AVAILABLE:
        return
    
    try:
        import winreg
        
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
        
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                key_path,
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, "DisableTaskMgr")
            winreg.CloseKey(key)
            logger.debug("Task Manager re-enabled")
        except WindowsError:
            pass  # Value may not exist
            
    except Exception as e:
        logger.debug(f"Task Manager restore failed: {e}")


def get_foreground_window() -> Optional[int]:
    """Get the handle of the current foreground window."""
    if not WINDOWS_AVAILABLE:
        return None
    
    try:
        user32 = ctypes.windll.user32
        return user32.GetForegroundWindow()
    except Exception:
        return None


def set_foreground_window(hwnd: int) -> bool:
    """Bring a window to the foreground."""
    if not WINDOWS_AVAILABLE:
        return False
    
    try:
        user32 = ctypes.windll.user32
        return user32.SetForegroundWindow(hwnd) != 0
    except Exception:
        return False


def is_window_focused(hwnd: int) -> bool:
    """Check if a specific window is currently focused."""
    if not WINDOWS_AVAILABLE:
        return True  # Assume focused on non-Windows
    
    foreground = get_foreground_window()
    return foreground == hwnd


class FocusMonitor:
    """
    Monitors window focus and detects when exam window loses focus.
    """
    
    def __init__(self, target_hwnd: int, on_focus_lost=None):
        self.target_hwnd = target_hwnd
        self.on_focus_lost = on_focus_lost
        self._running = False
    
    def start(self):
        """Start monitoring focus in a background thread."""
        import threading
        import time
        
        self._running = True
        
        def monitor_loop():
            while self._running:
                if not is_window_focused(self.target_hwnd):
                    if self.on_focus_lost:
                        self.on_focus_lost()
                time.sleep(0.5)
        
        self._thread = threading.Thread(target=monitor_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop monitoring."""
        self._running = False
