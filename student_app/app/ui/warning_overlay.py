"""
Student Exam Application - UI: Warning Overlay

Semi-transparent warning overlay for violation alerts.
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QRect
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)


class WarningOverlay(QWidget):
    """
    Full-screen warning overlay for violations.
    
    Shows a semi-transparent overlay with warning message.
    Auto-dismisses after a timeout.
    """
    
    def __init__(self, parent=None, message: str = "", timeout_ms: int = 5000):
        super().__init__(parent)
        
        self.message = message
        self.timeout_ms = timeout_ms
        self._countdown = timeout_ms // 1000
        
        self._setup_ui()
        self._start_countdown()
    
    def _setup_ui(self):
        """Create overlay UI."""
        # Full screen overlay
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        if self.parent():
            self.setGeometry(self.parent().geometry())
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Background
        background = QWidget()
        background.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 50, 50, 0.85);
            }
        """)
        bg_layout = QVBoxLayout(background)
        bg_layout.setAlignment(Qt.AlignCenter)
        
        # Warning icon
        icon = QLabel("⚠️")
        icon.setStyleSheet("font-size: 72px;")
        icon.setAlignment(Qt.AlignCenter)
        bg_layout.addWidget(icon)
        
        # Title
        title = QLabel("VIOLATION DETECTED")
        title.setStyleSheet("""
            color: white;
            font-size: 36px;
            font-weight: bold;
        """)
        title.setAlignment(Qt.AlignCenter)
        bg_layout.addWidget(title)
        
        # Message
        message_label = QLabel(self.message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("""
            color: white;
            font-size: 20px;
            margin: 20px;
        """)
        message_label.setAlignment(Qt.AlignCenter)
        bg_layout.addWidget(message_label)
        
        # Countdown
        self.countdown_label = QLabel(f"Dismissing in {self._countdown} seconds...")
        self.countdown_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.7);
            font-size: 16px;
            margin-top: 20px;
        """)
        self.countdown_label.setAlignment(Qt.AlignCenter)
        bg_layout.addWidget(self.countdown_label)
        
        # Acknowledge button
        ack_btn = QPushButton("I Understand")
        ack_btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #ff3333;
                border: none;
                border-radius: 8px;
                padding: 15px 40px;
                font-size: 16px;
                font-weight: bold;
                margin-top: 20px;
            }
            QPushButton:hover {
                background-color: #eeeeee;
            }
        """)
        ack_btn.clicked.connect(self._dismiss)
        bg_layout.addWidget(ack_btn, alignment=Qt.AlignCenter)
        
        layout.addWidget(background)
    
    def _start_countdown(self):
        """Start auto-dismiss countdown."""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_countdown)
        self._timer.start(1000)
    
    def _update_countdown(self):
        """Update countdown display."""
        self._countdown -= 1
        
        if self._countdown <= 0:
            self._dismiss()
        else:
            self.countdown_label.setText(f"Dismissing in {self._countdown} seconds...")
    
    def _dismiss(self):
        """Dismiss the overlay."""
        if self._timer:
            self._timer.stop()
        self.close()
        self.deleteLater()
    
    def keyPressEvent(self, event):
        """Ignore all key presses (prevent escape)."""
        event.ignore()


class SmallWarningBanner(QWidget):
    """
    Small non-intrusive warning banner at the top of the screen.
    """
    
    def __init__(self, parent=None, message: str = "", timeout_ms: int = 3000):
        super().__init__(parent)
        
        self.message = message
        self.timeout_ms = timeout_ms
        
        self._setup_ui()
        
        # Auto-dismiss
        QTimer.singleShot(timeout_ms, self._dismiss)
    
    def _setup_ui(self):
        """Create banner UI."""
        self.setFixedHeight(50)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        
        self.setStyleSheet("""
            QWidget {
                background-color: #ff9900;
                border-bottom: 2px solid #cc7a00;
            }
        """)
        
        # Icon
        icon = QLabel("⚠️")
        icon.setStyleSheet("font-size: 20px;")
        layout.addWidget(icon)
        
        # Message
        msg = QLabel(self.message)
        msg.setStyleSheet("""
            color: white;
            font-size: 14px;
            font-weight: bold;
        """)
        layout.addWidget(msg)
        
        layout.addStretch()
        
        # Dismiss button
        dismiss = QPushButton("×")
        dismiss.setFixedSize(30, 30)
        dismiss.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.3);
            }
        """)
        dismiss.clicked.connect(self._dismiss)
        layout.addWidget(dismiss)
    
    def _dismiss(self):
        """Dismiss the banner."""
        self.close()
        self.deleteLater()


def show_warning_overlay(parent: QWidget, message: str, timeout_ms: int = 5000):
    """
    Show a warning overlay on top of the parent widget.
    
    Args:
        parent: Parent widget
        message: Warning message to display
        timeout_ms: Auto-dismiss timeout in milliseconds
    """
    overlay = WarningOverlay(parent, message, timeout_ms)
    overlay.show()
    return overlay


def show_warning_banner(parent: QWidget, message: str, timeout_ms: int = 3000):
    """
    Show a small warning banner at the top of the parent widget.
    
    Args:
        parent: Parent widget
        message: Warning message to display
        timeout_ms: Auto-dismiss timeout in milliseconds
    """
    banner = SmallWarningBanner(parent, message, timeout_ms)
    banner.setParent(parent)
    banner.move(0, 0)
    banner.resize(parent.width(), 50)
    banner.show()
    return banner
