"""
Student Exam Application - UI: Submission Screen

Animated submission progress with status updates.
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QFont, QPainter, QColor, QConicalGradient

logger = logging.getLogger(__name__)


class SpinnerWidget(QWidget):
    """Animated circular spinner with gradient."""
    
    def __init__(self, parent=None, size: int = 80):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._size = size
        
        # Animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(16)  # ~60 FPS
    
    def _rotate(self):
        self._angle = (self._angle + 4) % 360
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Create gradient spinner
        center = self._size // 2
        radius = (self._size - 10) // 2
        
        gradient = QConicalGradient(center, center, self._angle)
        gradient.setColorAt(0, QColor("#4da6ff"))
        gradient.setColorAt(0.25, QColor("#667eea"))
        gradient.setColorAt(0.5, QColor("#764ba2"))
        gradient.setColorAt(0.75, QColor("#667eea"))
        gradient.setColorAt(1, QColor("#4da6ff"))
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        
        # Draw outer ring
        painter.drawEllipse(5, 5, self._size - 10, self._size - 10)
        
        # Cut out inner circle (create ring effect)
        painter.setBrush(QColor("#1a1a2e"))
        inner_size = self._size - 24
        inner_offset = 12
        painter.drawEllipse(inner_offset, inner_offset, inner_size, inner_size)
    
    def stop(self):
        self._timer.stop()


class PulsingDots(QWidget):
    """Three pulsing dots animation."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 30)
        self._dots = [0.3, 0.6, 1.0]  # Opacity of each dot
        self._phase = 0
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(150)
    
    def _animate(self):
        self._phase = (self._phase + 1) % 3
        # Shift opacities
        self._dots = [
            1.0 if self._phase == 0 else 0.3 if self._phase == 2 else 0.6,
            1.0 if self._phase == 1 else 0.3 if self._phase == 0 else 0.6,
            1.0 if self._phase == 2 else 0.3 if self._phase == 1 else 0.6,
        ]
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        dot_size = 12
        spacing = 30
        start_x = (self.width() - (3 * dot_size + 2 * spacing)) // 2
        y = (self.height() - dot_size) // 2
        
        for i, opacity in enumerate(self._dots):
            color = QColor("#4da6ff")
            color.setAlphaF(opacity)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(start_x + i * (dot_size + spacing), y, dot_size, dot_size)
    
    def stop(self):
        self._timer.stop()


class SubmissionScreen(QWidget):
    """
    Submission progress screen with animated indicators.
    
    Shows upload progress and status updates during exam submission.
    """
    
    submission_complete = Signal(dict)  # Emits exam stats when done
    submission_failed = Signal(str)  # Emits error message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._exam_stats = {}
        self._current_step = 0
        self._steps = [
            ("Saving your answers...", 30),
            ("Processing proctoring data...", 50),
            ("Uploading evidence clips...", 80),
            ("Finalizing submission...", 95),
            ("Complete!", 100),
        ]
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Create submission UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(30)
        
        layout.addStretch(2)
        
        # Central container
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #16213e, stop:1 #1a1a3e
                );
                border-radius: 24px;
                padding: 40px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(30)
        container_layout.setAlignment(Qt.AlignCenter)
        
        # Spinner
        spinner_container = QWidget()
        spinner_layout = QVBoxLayout(spinner_container)
        spinner_layout.setAlignment(Qt.AlignCenter)
        
        self.spinner = SpinnerWidget(size=100)
        spinner_layout.addWidget(self.spinner, alignment=Qt.AlignCenter)
        
        container_layout.addWidget(spinner_container)
        
        # Status title
        self.status_title = QLabel("Submitting Your Exam")
        self.status_title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        self.status_title.setAlignment(Qt.AlignCenter)
        self.status_title.setStyleSheet("color: #ffffff;")
        container_layout.addWidget(self.status_title)
        
        # Status message
        self.status_message = QLabel("Please wait while we process your submission...")
        self.status_message.setFont(QFont("Segoe UI", 14))
        self.status_message.setAlignment(Qt.AlignCenter)
        self.status_message.setStyleSheet("color: #888888;")
        container_layout.addWidget(self.status_message)
        
        # Progress bar container
        progress_container = QFrame()
        progress_container.setStyleSheet("""
            QFrame {
                background-color: #0a0a15;
                border-radius: 8px;
            }
        """)
        progress_container.setFixedHeight(16)
        progress_container.setMaximumWidth(400)
        
        # Progress fill (we'll animate this)
        self.progress_fill = QFrame(progress_container)
        self.progress_fill.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da6ff, stop:1 #667eea
                );
                border-radius: 8px;
            }
        """)
        self.progress_fill.setGeometry(0, 0, 0, 16)
        
        container_layout.addWidget(progress_container, alignment=Qt.AlignCenter)
        
        # Percentage label
        self.percentage_label = QLabel("0%")
        self.percentage_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.percentage_label.setAlignment(Qt.AlignCenter)
        self.percentage_label.setStyleSheet("color: #4da6ff;")
        container_layout.addWidget(self.percentage_label)
        
        # Pulsing dots
        self.dots = PulsingDots()
        container_layout.addWidget(self.dots, alignment=Qt.AlignCenter)
        
        layout.addWidget(container, alignment=Qt.AlignCenter)
        
        # Warning message
        warning = QLabel("⚠️ Please do not close this window")
        warning.setFont(QFont("Segoe UI", 12))
        warning.setAlignment(Qt.AlignCenter)
        warning.setStyleSheet("color: #ff9900;")
        layout.addWidget(warning)
        
        layout.addStretch(2)
        
        # Store progress container for width calculation
        self._progress_container = progress_container
    
    def start_submission(self, exam_stats: dict):
        """Start the submission process with exam statistics."""
        self._exam_stats = exam_stats
        self._current_step = 0
        
        logger.info(f"Starting submission with stats: {exam_stats}")
        
        # Start step progression
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._advance_step)
        self._progress_timer.start(1200)  # Advance every 1.2 seconds
        
        # Set initial state
        self._update_progress(0)
    
    def _advance_step(self):
        """Advance to the next submission step."""
        if self._current_step >= len(self._steps):
            self._progress_timer.stop()
            self._complete_submission()
            return
        
        step_text, progress = self._steps[self._current_step]
        self.status_message.setText(step_text)
        self._update_progress(progress)
        
        self._current_step += 1
    
    def _update_progress(self, percentage: int):
        """Update progress bar and percentage."""
        self.percentage_label.setText(f"{percentage}%")
        
        # Animate progress bar width
        container_width = self._progress_container.width()
        if container_width > 0:
            target_width = int(container_width * percentage / 100)
            self.progress_fill.setFixedWidth(target_width)
    
    def _complete_submission(self):
        """Handle submission completion."""
        self.spinner.stop()
        self.dots.stop()
        
        self.status_title.setText("Submission Complete!")
        self.status_title.setStyleSheet("color: #00d9a5;")
        self.status_message.setText("Your exam has been submitted successfully.")
        
        # Brief delay before transitioning
        QTimer.singleShot(1500, lambda: self.submission_complete.emit(self._exam_stats))
    
    def set_error(self, message: str):
        """Display an error state."""
        self.spinner.stop()
        self.dots.stop()
        
        self.status_title.setText("Submission Error")
        self.status_title.setStyleSheet("color: #ff6b6b;")
        self.status_message.setText(message)
        
        self.submission_failed.emit(message)
    
    def resizeEvent(self, event):
        """Handle resize to update progress bar."""
        super().resizeEvent(event)
        # Re-apply current progress to adjust for new size
        if hasattr(self, '_current_step') and self._current_step > 0:
            _, progress = self._steps[min(self._current_step - 1, len(self._steps) - 1)]
            self._update_progress(progress)
