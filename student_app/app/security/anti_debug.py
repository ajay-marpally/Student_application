"""
Student Exam Application - Security: Anti-Debug & Environment Check

Detects debuggers, VMs, screen recorders, and other security threats.
"""

import sys
import os
import subprocess
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


# Known virtualization indicators
VM_INDICATORS = {
    "processes": [
        "vmtoolsd", "vmwaretray", "vmwareuser",  # VMware
        "vboxservice", "vboxtray",  # VirtualBox
        "vmusrvc", "vmsrvc",  # Virtual PC
        "xenservice",  # Xen
        "qemu-ga",  # QEMU
    ],
    "registry_keys": [
        r"SOFTWARE\VMware, Inc.\VMware Tools",
        r"SOFTWARE\Oracle\VirtualBox Guest Additions",
        r"HARDWARE\DEVICEMAP\Scsi\Scsi Port 0\Scsi Bus 0\Target Id 0\Logical Unit Id 0",
    ],
    "files": [
        r"C:\Windows\System32\drivers\vmmouse.sys",
        r"C:\Windows\System32\drivers\vmhgfs.sys",
        r"C:\Windows\System32\drivers\VBoxMouse.sys",
        r"C:\Windows\System32\drivers\VBoxGuest.sys",
    ],
}

# Known debugger processes
DEBUGGER_PROCESSES = [
    "ollydbg", "x64dbg", "x32dbg", "windbg",
    "ida", "ida64", "idag", "idag64",
    "immunity debugger", "radare2", "r2",
    "ghidra", "binaryninja",
    "processhacker", "procmon", "procexp",
    "wireshark", "fiddler", "charles",
]

# Screen recorder processes
SCREEN_RECORDERS = [
    "obs", "obs64", "obs32",
    "camtasia", "snagit",
    "bandicam", "action",
    "fraps", "dxtory",
    "screencast-o-matic", "loom",
    "nvidia share", "geforce experience",
    "xbox game bar", "gamebar",
    "flashback", "screenflow",
    "streamlabs",
]

# Remote desktop indicators
REMOTE_DESKTOP = [
    "teamviewer", "anydesk", "ammyy",
    "vnc", "realvnc", "tightvnc", "ultravnc",
    "rdpclip", "mstsc",  # Remote Desktop
    "parsec", "splashtop",
    "chrome remote desktop",
    "logmein", "gotomeeting",
]

# Virtual camera drivers
VIRTUAL_CAMERAS = [
    "obs virtual camera",
    "manycam", "xsplit",
    "snap camera", "mmdevapi",
    "droidcam", "iriun",
    "epoccam", "camo",
]


def check_security_environment() -> List[str]:
    """
    Comprehensive security environment check.
    
    Returns list of security issues found (empty if clean).
    """
    issues = []
    
    # Check for debuggers
    debuggers = detect_debuggers()
    if debuggers:
        issues.extend([f"Debugger detected: {d}" for d in debuggers])
    
    # Check for VMs
    vm_detected = detect_virtualization()
    if vm_detected:
        issues.append(f"Virtual machine detected: {vm_detected}")
    
    # Check for screen recorders
    recorders = detect_screen_recorders()
    if recorders:
        issues.extend([f"Screen recorder detected: {r}" for r in recorders])
    
    # Check for remote desktop
    remote = detect_remote_desktop()
    if remote:
        issues.extend([f"Remote desktop detected: {r}" for r in remote])
    
    # Check for virtual cameras
    vcams = detect_virtual_cameras()
    if vcams:
        issues.extend([f"Virtual camera detected: {v}" for v in vcams])
    
    return issues


def detect_debuggers() -> List[str]:
    """Detect running debugger processes."""
    detected = []
    
    if sys.platform == 'win32':
        # Windows: Check running processes
        try:
            import ctypes
            
            # IsDebuggerPresent check
            if ctypes.windll.kernel32.IsDebuggerPresent():
                detected.append("kernel32.IsDebuggerPresent")
            
            # Check for debugger processes
            running = _get_running_processes_windows()
            for proc in running:
                proc_lower = proc.lower()
                for debugger in DEBUGGER_PROCESSES:
                    if debugger in proc_lower:
                        detected.append(proc)
                        break
                        
        except Exception as e:
            logger.debug(f"Debugger detection error: {e}")
    
    elif sys.platform in ('linux', 'darwin'):
        # Unix: Check for ptrace
        try:
            status_path = Path("/proc/self/status")
            if status_path.exists():
                for line in status_path.read_text().split('\n'):
                    if line.startswith('TracerPid:'):
                        pid = int(line.split(':')[1].strip())
                        if pid != 0:
                            detected.append(f"TracerPid: {pid}")
        except Exception:
            pass
    
    return detected


def detect_virtualization() -> Optional[str]:
    """Detect if running in a virtual machine."""
    
    if sys.platform == 'win32':
        try:
            import ctypes
            import winreg
            
            # Check registry for VM indicators
            for key_path in VM_INDICATORS["registry_keys"]:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    winreg.CloseKey(key)
                    return f"Registry: {key_path}"
                except WindowsError:
                    pass
            
            # Check for VM-specific files
            for file_path in VM_INDICATORS["files"]:
                if Path(file_path).exists():
                    return f"File: {file_path}"
            
            # Check running processes
            running = _get_running_processes_windows()
            for proc in running:
                proc_lower = proc.lower()
                for vm_proc in VM_INDICATORS["processes"]:
                    if vm_proc in proc_lower:
                        return f"Process: {proc}"
                        
        except Exception as e:
            logger.debug(f"VM detection error: {e}")
    
    elif sys.platform == 'linux':
        try:
            # Check DMI info
            dmi_path = Path("/sys/class/dmi/id/product_name")
            if dmi_path.exists():
                product = dmi_path.read_text().strip().lower()
                vm_products = ["virtual", "vmware", "virtualbox", "kvm", "qemu", "xen"]
                for vm in vm_products:
                    if vm in product:
                        return f"DMI: {product}"
        except Exception:
            pass
    
    elif sys.platform == 'darwin':
        try:
            # Check for VM extensions
            result = subprocess.run(
                ["sysctl", "machdep.cpu.features"],
                capture_output=True, text=True, timeout=5
            )
            if "VMX" in result.stdout:
                # Hardware virtualization, but could be legit
                pass
        except Exception:
            pass
    
    return None


def detect_screen_recorders() -> List[str]:
    """Detect running screen recording software."""
    detected = []
    
    if sys.platform == 'win32':
        running = _get_running_processes_windows()
        for proc in running:
            proc_lower = proc.lower()
            for recorder in SCREEN_RECORDERS:
                if recorder in proc_lower:
                    detected.append(proc)
                    break
    
    elif sys.platform == 'darwin':
        # macOS: Check for known recorders
        try:
            result = subprocess.run(
                ["pgrep", "-l", "-f", "QuickTimePlayer|OBS|ScreenFlow"],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                detected.extend(result.stdout.strip().split('\n'))
        except Exception:
            pass
    
    return detected


def detect_remote_desktop() -> List[str]:
    """Detect remote desktop software."""
    detected = []
    
    if sys.platform == 'win32':
        try:
            import ctypes
            
            # Check if running in remote session
            SM_REMOTESESSION = 0x1000
            if ctypes.windll.user32.GetSystemMetrics(SM_REMOTESESSION):
                detected.append("Windows Remote Session")
            
            # Check for remote desktop processes
            running = _get_running_processes_windows()
            for proc in running:
                proc_lower = proc.lower()
                for remote in REMOTE_DESKTOP:
                    if remote in proc_lower:
                        detected.append(proc)
                        break
                        
        except Exception as e:
            logger.debug(f"Remote desktop detection error: {e}")
    
    return detected


def detect_virtual_cameras() -> List[str]:
    """Detect virtual camera drivers."""
    detected = []
    
    if sys.platform == 'win32':
        running = _get_running_processes_windows()
        for proc in running:
            proc_lower = proc.lower()
            for vcam in VIRTUAL_CAMERAS:
                if vcam in proc_lower:
                    detected.append(proc)
                    break
    
    # Additional OpenCV-based detection could be added here
    # by checking camera properties for virtual indicators
    
    return detected


def _get_running_processes_windows() -> List[str]:
    """Get list of running process names on Windows."""
    processes = []
    
    try:
        # Use WMIC for process list
        result = subprocess.run(
            ["wmic", "process", "get", "name"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        for line in result.stdout.split('\n'):
            proc = line.strip()
            if proc and proc != "Name":
                processes.append(proc)
                
    except Exception as e:
        logger.debug(f"Process list error: {e}")
        
        # Fallback: use psutil if available
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                try:
                    processes.append(proc.info['name'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except ImportError:
            pass
    
    return processes
