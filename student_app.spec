# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller spec file for Student Exam Application.

Build command:
    pyinstaller student_app.spec --clean

Output:
    dist/student_client.exe
"""

import sys
from pathlib import Path

# Get project root
project_root = Path(SPECPATH)

# Collect all source files
app_path = project_root / 'student_app' / 'app'

# Analysis configuration
a = Analysis(
    [str(app_path / 'main.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # Include model files if present
        # (str(app_path / 'ai' / 'models'), 'student_app/app/ai/models'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'cv2',
        'numpy',
        'mediapipe',
        'httpx',
        'cryptography',
        'student_app.app.config',
        'student_app.app.auth',
        'student_app.app.exam_engine',
        'student_app.app.ui.main_window',
        'student_app.app.ui.login_screen',
        'student_app.app.ui.instruction_screen',
        'student_app.app.ui.exam_screen',
        'student_app.app.ui.warning_overlay',
        'student_app.app.ai.face_detector',
        'student_app.app.ai.head_pose',
        'student_app.app.ai.gaze',
        'student_app.app.ai.audio_monitor',
        'student_app.app.ai.event_classifier',
        'student_app.app.buffer.circular_buffer',
        'student_app.app.buffer.clip_extractor',
        'student_app.app.storage.supabase_client',
        'student_app.app.storage.uploader',
        'student_app.app.security.integrity_check',
        'student_app.app.security.anti_debug',
        'student_app.app.kiosk.fullscreen',
        'student_app.app.db.sqlite_queue',
        'student_app.app.utils.logger',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
    ],
    noarchive=False,
)

# Remove unnecessary files to reduce size
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='student_client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if Path('assets/icon.ico').exists() else None,
    version='assets/version_info.txt' if Path('assets/version_info.txt').exists() else None,
)
