"""
Student Exam Application - UI: Main Window

Main application window with fullscreen kiosk enforcement.
"""

import logging
import sys
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QApplication, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QScreen

from student_app.app.config import AppConfig, get_config

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Main application window with fullscreen kiosk mode.
    
    Manages screen transitions and enforces fullscreen during exam.
    """
    
    # Signals
    exam_started = Signal()
    exam_ended = Signal(str)  # status: SUBMITTED, TERMINATED
    violation_detected = Signal(str)  # violation message
    
    def __init__(self, config: Optional[AppConfig] = None):
        super().__init__()
        
        self.config = config or get_config()
        self._exam_active = False
        self._kiosk_mode = False
        
        self._setup_window()
        self._setup_ui()
        self._setup_kiosk_monitoring()
    
    def _setup_window(self):
        """Configure window properties."""
        self.setWindowTitle("Student Exam Application")
        
        # Get primary screen
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.geometry()
            self.setGeometry(geometry)
        
        # Remove window decorations for kiosk mode
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        
        # Set minimum size
        self.setMinimumSize(1024, 768)
        
        # Dark background
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a2e;
            }
        """)
    
    def _setup_ui(self):
        """Initialize UI components."""
        # Central widget with stacked layout for screens
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        
        # Import and add screens lazily to avoid circular imports
        self._add_screens()
    
    def _add_screens(self):
        """Add all application screens."""
        # Login screen
        from student_app.app.ui.login_screen import LoginScreen
        self.login_screen = LoginScreen()
        self.login_screen.login_successful.connect(self._on_login_success)
        self.stack.addWidget(self.login_screen)
        
        # Instruction screen
        from student_app.app.ui.instruction_screen import InstructionScreen
        self.instruction_screen = InstructionScreen()
        self.instruction_screen.instructions_complete.connect(self._on_instructions_complete)
        self.stack.addWidget(self.instruction_screen)
        
        # Exam screen
        from student_app.app.ui.exam_screen import ExamScreen
        self.exam_screen = ExamScreen()
        self.exam_screen.exam_submitted.connect(self._on_exam_submitted)
        self.stack.addWidget(self.exam_screen)
        
        # Submission progress screen
        from student_app.app.ui.submission_screen import SubmissionScreen
        self.submission_screen = SubmissionScreen()
        self.submission_screen.submission_complete.connect(self._on_submission_complete)
        self.submission_screen.submission_failed.connect(self._on_submission_failed)
        self.stack.addWidget(self.submission_screen)
        
        # Completion screen
        from student_app.app.ui.completion_screen import CompletionScreen
        self.completion_screen = CompletionScreen()
        self.completion_screen.exit_requested.connect(self._on_exit_requested)
        self.stack.addWidget(self.completion_screen)
        
        # Start with login screen
        self.stack.setCurrentWidget(self.login_screen)
    
    def _setup_kiosk_monitoring(self):
        """Setup periodic checks for kiosk enforcement."""
        self._focus_timer = QTimer(self)
        self._focus_timer.timeout.connect(self._check_focus)
        # Check every 500ms when exam is active
        self._focus_timer.setInterval(500)
    
    def _check_focus(self):
        """Check if application has focus (kiosk enforcement)."""
        if not self._exam_active:
            return
        
        if not self.isActiveWindow():
            logger.warning("Application lost focus during exam!")
            
            # Emit violation signal
            self.violation_detected.emit("Application focus lost")
            
            # Report to proctoring system
            if hasattr(self, 'exam_screen'):
                self.exam_screen.report_focus_loss()
            
            # Force focus back
            self.activateWindow()
            self.raise_()
            self.showFullScreen()
    
    # ==================== Screen Transitions ====================
    
    def _on_login_success(self, student_data: dict):
        """Handle successful login."""
        logger.info(f"Login successful: {student_data.get('hall_ticket', 'unknown')}")
        
        # Pass student data to instruction screen
        self.instruction_screen.set_student_data(student_data)
        
        # Show instruction screen
        self.stack.setCurrentWidget(self.instruction_screen)
        self.instruction_screen.start_countdown()
    
    def _on_instructions_complete(self):
        """Handle instruction period complete."""
        logger.info("Instructions complete, starting exam")
        
        # Enable kiosk mode
        self.enable_kiosk_mode()
        
        # Pass exam data to exam screen
        student_data = self.instruction_screen.student_data
        self.exam_screen.set_exam_data(student_data)
        
        # Show exam screen
        self.stack.setCurrentWidget(self.exam_screen)
        self.exam_screen.start_exam()
        
        # Emit signal
        self.exam_started.emit()
    
    def _on_exam_submitted(self, status: str, exam_stats: dict = None):
        """Handle exam submission - show submission progress screen."""
        logger.info(f"Exam submission started: {status}")
        
        # Store status for later
        self._submission_status = status
        
        # Prepare exam stats if not provided
        if exam_stats is None:
            exam_stats = self._get_exam_stats()
        
        # Disable kiosk mode
        self.disable_kiosk_mode()
        
        # Emit signal
        self.exam_ended.emit(status)
        
        # Show submission screen with progress
        self.stack.setCurrentWidget(self.submission_screen)
        self.submission_screen.start_submission(exam_stats)
    
    def _get_exam_stats(self) -> dict:
        """Get exam statistics from exam screen."""
        stats = {
            "answered": 0,
            "unanswered": 0,
            "marked_review": 0,
            "total_questions": 0,
            "time_taken_seconds": 0,
            "time_allotted_seconds": 0,
            "violations_count": 0,
            "violations": [],
        }
        
        if hasattr(self, 'exam_screen'):
            # Get answers data
            answers = getattr(self.exam_screen, 'answers', {})
            questions = getattr(self.exam_screen, 'questions', [])
            
            stats["total_questions"] = len(questions)
            stats["answered"] = sum(1 for a in answers.values() if a.get('selected') is not None)
            stats["unanswered"] = stats["total_questions"] - stats["answered"]
            stats["marked_review"] = sum(1 for a in answers.values() if a.get('marked_review', False))
            
            # Get time data
            start_time = getattr(self.exam_screen, 'start_time', None)
            if start_time:
                from datetime import datetime
                elapsed = (datetime.now() - start_time).total_seconds()
                stats["time_taken_seconds"] = int(elapsed)
            
            duration = getattr(self.exam_screen, 'exam_duration_minutes', 60)
            stats["time_allotted_seconds"] = duration * 60
            
            # Get violations
            violations = getattr(self.exam_screen, 'violations', [])
            stats["violations_count"] = len(violations)
            stats["violations"] = violations[:10]  # Limit to 10
        
        return stats
    
    def _on_submission_complete(self, exam_stats: dict):
        """Handle submission progress complete - show completion screen."""
        logger.info("Submission complete, showing completion screen")
        
        status = getattr(self, '_submission_status', 'SUBMITTED')
        
        # Show completion screen
        self.stack.setCurrentWidget(self.completion_screen)
        self.completion_screen.set_exam_stats(exam_stats, status)
    
    def _on_submission_failed(self, error: str):
        """Handle submission failure."""
        logger.error(f"Submission failed: {error}")
        
        # Still show completion screen with error state
        stats = self._get_exam_stats()
        self.stack.setCurrentWidget(self.completion_screen)
        self.completion_screen.set_exam_stats(stats, "TERMINATED")
    
    def _on_exit_requested(self):
        """Handle exit request from completion screen."""
        logger.info("Exit requested by user")
        QApplication.quit()
    
    # ==================== Kiosk Mode ====================
    
    def enable_kiosk_mode(self):
        """Enable kiosk mode (fullscreen with monitoring)."""
        self._kiosk_mode = True
        self._exam_active = True
        
        # Ensure fullscreen
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        
        # Start focus monitoring
        self._focus_timer.start()
        
        # Windows-specific kiosk enforcement
        self._enable_windows_kiosk()
        
        logger.info("Kiosk mode enabled")
    
    def disable_kiosk_mode(self):
        """Disable kiosk mode."""
        self._kiosk_mode = False
        self._exam_active = False
        
        # Stop focus monitoring
        self._focus_timer.stop()
        
        # Restore normal window
        self._disable_windows_kiosk()
        
        logger.info("Kiosk mode disabled")
    
    def _enable_windows_kiosk(self):
        """Windows-specific kiosk enforcement."""
        if sys.platform != 'win32':
            return
        
        try:
            from student_app.app.kiosk.fullscreen import enable_kiosk_mode
            enable_kiosk_mode(self.winId())
        except Exception as e:
            logger.warning(f"Could not enable Windows kiosk: {e}")
    
    def _disable_windows_kiosk(self):
        """Disable Windows-specific kiosk enforcement."""
        if sys.platform != 'win32':
            return
        
        try:
            from student_app.app.kiosk.fullscreen import disable_kiosk_mode
            disable_kiosk_mode()
        except Exception as e:
            logger.warning(f"Could not disable Windows kiosk: {e}")
    
    # ==================== Event Handlers ====================
    
    def closeEvent(self, event):
        """Handle window close attempt."""
        if self._exam_active:
            # Prevent closing during exam
            event.ignore()
            
            # Force fullscreen
            self.showFullScreen()
            
            logger.warning("Close attempt blocked during exam")
        else:
            event.accept()
    
    def keyPressEvent(self, event):
        """Handle key presses."""
        # Block Alt+F4, Alt+Tab during exam
        if self._exam_active:
            modifiers = event.modifiers()
            
            if modifiers & Qt.AltModifier:
                if event.key() in (Qt.Key_F4, Qt.Key_Tab):
                    event.ignore()
                    logger.warning(f"Blocked Alt+{'F4' if event.key() == Qt.Key_F4 else 'Tab'}")
                    return
        
        super().keyPressEvent(event)
    
    def changeEvent(self, event):
        """Handle window state changes."""
        super().changeEvent(event)
        
        if self._exam_active:
            # Prevent minimizing
            if self.windowState() & Qt.WindowMinimized:
                self.showFullScreen()
    
    # ==================== Public Methods ====================
    
    def show_warning(self, message: str):
        """Show a warning overlay."""
        from student_app.app.ui.warning_overlay import show_warning_overlay
        show_warning_overlay(self, message)
    
    def terminate_exam(self, reason: str):
        """Forcefully terminate the exam."""
        logger.critical(f"Exam terminated: {reason}")
        
        if hasattr(self, 'exam_screen') and self._exam_active:
            self.exam_screen.terminate(reason)
