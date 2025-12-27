"""
Student Exam Application - UI: Instruction Screen

Pre-exam instructions with 5-minute countdown.
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QTimer

logger = logging.getLogger(__name__)


class InstructionScreen(QWidget):
    """
    Pre-exam instruction screen with countdown timer.
    
    Displays exam rules and allows preparations before starting.
    """
    
    instructions_complete = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.student_data = {}
        self._countdown_seconds = 0
        self._timer = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Create instruction UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(20)
        
        # Header
        header = QLabel("Exam Instructions")
        header.setStyleSheet("color: white; font-size: 28px; font-weight: bold;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Student info
        self.student_info = QLabel("")
        self.student_info.setStyleSheet("color: #888888; font-size: 16px;")
        self.student_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.student_info)
        
        layout.addSpacing(20)
        
        # Instructions frame
        instructions_frame = QFrame()
        instructions_frame.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        instructions_layout = QVBoxLayout(instructions_frame)
        
        instructions_text = """
        <p style='color: #ffffff; font-size: 16px; line-height: 1.8;'>
        Please read the following instructions carefully before starting your exam:
        </p>
        
        <ol style='color: #cccccc; font-size: 14px; line-height: 2.0;'>
            <li><strong>Fullscreen Mode:</strong> The exam will run in fullscreen. 
                Attempting to exit will be recorded.</li>
            <li><strong>Camera Monitoring:</strong> Your camera will be active throughout 
                the exam. Keep your face visible at all times.</li>
            <li><strong>No External Help:</strong> Looking away, using phones, or having 
                other people nearby will be flagged.</li>
            <li><strong>Auto-Save:</strong> Your answers are saved automatically every 
                30 seconds.</li>
            <li><strong>Submission:</strong> Click 'Submit Exam' when complete. You cannot 
                return after submission.</li>
            <li><strong>Time Limit:</strong> You must complete the exam within the allotted 
                time. The exam will auto-submit when time expires.</li>
        </ol>
        
        <p style='color: #ff9900; font-size: 14px; margin-top: 20px;'>
        ⚠️ <strong>Warning:</strong> All activities are monitored. Violations may result 
        in exam termination and will be reviewed.
        </p>
        """
        
        instructions_label = QLabel(instructions_text)
        instructions_label.setWordWrap(True)
        instructions_label.setTextFormat(Qt.RichText)
        instructions_layout.addWidget(instructions_label)
        
        layout.addWidget(instructions_frame)
        
        layout.addStretch()
        
        # Countdown section
        countdown_layout = QHBoxLayout()
        countdown_layout.addStretch()
        
        countdown_container = QFrame()
        countdown_container.setStyleSheet("""
            QFrame {
                background-color: #0f3460;
                border-radius: 12px;
                padding: 20px 40px;
            }
        """)
        countdown_inner = QVBoxLayout(countdown_container)
        
        countdown_label = QLabel("Exam will start in:")
        countdown_label.setStyleSheet("color: #888888; font-size: 14px;")
        countdown_label.setAlignment(Qt.AlignCenter)
        countdown_inner.addWidget(countdown_label)
        
        self.countdown_display = QLabel("5:00")
        self.countdown_display.setStyleSheet("""
            color: #4da6ff; 
            font-size: 48px; 
            font-weight: bold;
            font-family: 'Consolas', monospace;
        """)
        self.countdown_display.setAlignment(Qt.AlignCenter)
        countdown_inner.addWidget(self.countdown_display)
        
        countdown_layout.addWidget(countdown_container)
        countdown_layout.addStretch()
        
        layout.addLayout(countdown_layout)
        
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #1a1a2e;
                border-radius: 4px;
                height: 8px;
            }
            QProgressBar::chunk {
                background-color: #4da6ff;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress)
        
        # Skip button (for testing, hidden in production)
        self.skip_btn = QPushButton("Skip Wait (Testing)")
        self.skip_btn.setStyleSheet("""
            QPushButton {
                background-color: #333;
                color: #888;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #444;
            }
        """)
        self.skip_btn.clicked.connect(self._on_skip)
        self.skip_btn.hide()  # Hide by default
        layout.addWidget(self.skip_btn, alignment=Qt.AlignCenter)
        
        # Show skip button in debug mode
        from student_app.app.config import get_config
        if get_config().debug_mode:
            self.skip_btn.show()
    
    def set_student_data(self, data: dict):
        """Set student and exam data."""
        self.student_data = data
        
        name = data.get("name", "Student")
        exam_name = data.get("exam_name", "Exam")
        duration = data.get("exam_duration", 60)
        
        self.student_info.setText(
            f"Welcome, {name} | {exam_name} | Duration: {duration} minutes"
        )
    
    def start_countdown(self, duration_minutes: int = 5):
        """Start the countdown timer."""
        from student_app.app.config import get_config
        config = get_config()
        
        # Use configured duration or default
        duration_minutes = config.thresholds.INSTRUCTION_DURATION_MINUTES
        
        # In debug mode, use shorter countdown
        if config.debug_mode:
            duration_minutes = 1
        
        self._countdown_seconds = duration_minutes * 60
        self._total_seconds = self._countdown_seconds
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_countdown)
        self._timer.start(1000)  # Update every second
        
        self._update_countdown()
    
    def _update_countdown(self):
        """Update countdown display."""
        if self._countdown_seconds <= 0:
            self._timer.stop()
            self.instructions_complete.emit()
            return
        
        # Update display
        minutes = self._countdown_seconds // 60
        seconds = self._countdown_seconds % 60
        self.countdown_display.setText(f"{minutes}:{seconds:02d}")
        
        # Update progress
        progress = 100 - (self._countdown_seconds * 100 // self._total_seconds)
        self.progress.setValue(progress)
        
        self._countdown_seconds -= 1
    
    def _on_skip(self):
        """Skip countdown (testing only)."""
        logger.info("Countdown skipped (testing)")
        if self._timer:
            self._timer.stop()
        self.instructions_complete.emit()
    
    def hideEvent(self, event):
        """Stop timer when hidden."""
        if self._timer:
            self._timer.stop()
        super().hideEvent(event)
