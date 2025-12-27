"""
Student Exam Application - UI: Completion Screen

Post-exam summary with statistics and violations display.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea, QApplication, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

logger = logging.getLogger(__name__)


class StatCard(QFrame):
    """Individual statistic card with icon and value."""
    
    def __init__(
        self,
        title: str,
        value: str,
        icon: str = "📊",
        color: str = "#4da6ff",
        parent=None
    ):
        super().__init__(parent)
        self._setup_ui(title, value, icon, color)
    
    def _setup_ui(self, title: str, value: str, icon: str, color: str):
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1e2a4a, stop:1 #16213e
                );
                border-radius: 16px;
                border: 1px solid #2a3a5a;
            }}
        """)
        self.setFixedSize(180, 140)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        
        # Icon
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI Emoji", 24))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        
        # Value
        value_label = QLabel(value)
        value_label.setFont(QFont("Segoe UI", 28, QFont.Bold))
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet(f"color: {color};")
        layout.addWidget(value_label)
        
        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 11))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #888888;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)


class CompletionScreen(QWidget):
    """
    Post-exam completion screen with statistics and summary.
    
    Displays exam results, time taken, violations, and exit option.
    """
    
    exit_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._exam_stats = {}
        self._setup_ui()
    
    def _setup_ui(self):
        """Create completion UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 40, 50, 40)
        layout.setSpacing(25)
        
        # Header with status
        self.header_frame = QFrame()
        self.header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00d9a5, stop:1 #00b894
                );
                border-radius: 16px;
                padding: 20px;
            }
        """)
        header_layout = QVBoxLayout(self.header_frame)
        
        # Status icon
        self.status_icon = QLabel("✓")
        self.status_icon.setFont(QFont("Segoe UI", 48))
        self.status_icon.setAlignment(Qt.AlignCenter)
        self.status_icon.setStyleSheet("color: white;")
        header_layout.addWidget(self.status_icon)
        
        # Status title
        self.status_title = QLabel("Exam Submitted Successfully")
        self.status_title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        self.status_title.setAlignment(Qt.AlignCenter)
        self.status_title.setStyleSheet("color: white;")
        header_layout.addWidget(self.status_title)
        
        # Status subtitle
        self.status_subtitle = QLabel("Your answers have been saved and submitted.")
        self.status_subtitle.setFont(QFont("Segoe UI", 14))
        self.status_subtitle.setAlignment(Qt.AlignCenter)
        self.status_subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.85);")
        header_layout.addWidget(self.status_subtitle)
        
        layout.addWidget(self.header_frame)
        
        # Statistics section
        stats_title = QLabel("Exam Summary")
        stats_title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        stats_title.setStyleSheet("color: #ffffff;")
        layout.addWidget(stats_title)
        
        # Stats cards container
        self.stats_container = QHBoxLayout()
        self.stats_container.setSpacing(20)
        self.stats_container.setAlignment(Qt.AlignCenter)
        
        # Placeholder cards (will be updated with real data)
        self.answered_card = StatCard("Answered", "0", "✅", "#00d9a5")
        self.unanswered_card = StatCard("Unanswered", "0", "⭕", "#ff9900")
        self.review_card = StatCard("Marked for Review", "0", "🔖", "#4da6ff")
        self.time_card = StatCard("Time Taken", "0m", "⏱️", "#667eea")
        
        self.stats_container.addWidget(self.answered_card)
        self.stats_container.addWidget(self.unanswered_card)
        self.stats_container.addWidget(self.review_card)
        self.stats_container.addWidget(self.time_card)
        
        layout.addLayout(self.stats_container)
        
        # Violations section (conditionally shown)
        self.violations_frame = QFrame()
        self.violations_frame.setStyleSheet("""
            QFrame {
                background-color: #2a1a1a;
                border: 1px solid #4a2a2a;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        violations_layout = QVBoxLayout(self.violations_frame)
        
        violations_header = QHBoxLayout()
        violations_icon = QLabel("⚠️")
        violations_icon.setFont(QFont("Segoe UI Emoji", 16))
        violations_header.addWidget(violations_icon)
        
        self.violations_title = QLabel("Proctoring Alerts")
        self.violations_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.violations_title.setStyleSheet("color: #ff9900;")
        violations_header.addWidget(self.violations_title)
        violations_header.addStretch()
        
        violations_layout.addLayout(violations_header)
        
        self.violations_label = QLabel("No violations recorded during your exam.")
        self.violations_label.setFont(QFont("Segoe UI", 12))
        self.violations_label.setStyleSheet("color: #888888;")
        self.violations_label.setWordWrap(True)
        violations_layout.addWidget(self.violations_label)
        
        layout.addWidget(self.violations_frame)
        
        # Timestamp
        self.timestamp_label = QLabel("")
        self.timestamp_label.setFont(QFont("Segoe UI", 12))
        self.timestamp_label.setAlignment(Qt.AlignCenter)
        self.timestamp_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.timestamp_label)
        
        layout.addStretch()
        
        # Exit button
        exit_container = QHBoxLayout()
        exit_container.addStretch()
        
        self.exit_btn = QPushButton("Exit Application")
        self.exit_btn.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.exit_btn.setFixedSize(220, 55)
        self.exit_btn.setCursor(Qt.PointingHandCursor)
        self.exit_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4da6ff, stop:1 #667eea
                );
                color: white;
                border: none;
                border-radius: 12px;
                padding: 15px 40px;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5db6ff, stop:1 #778efa
                );
            }
            QPushButton:pressed {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3d96ef, stop:1 #5a6eda
                );
            }
        """)
        self.exit_btn.clicked.connect(self._on_exit)
        exit_container.addWidget(self.exit_btn)
        
        exit_container.addStretch()
        layout.addLayout(exit_container)
        
        # Footer
        footer = QLabel("Thank you for completing your exam. Your results will be available soon.")
        footer.setFont(QFont("Segoe UI", 11))
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #555555;")
        layout.addWidget(footer)
    
    def set_exam_stats(self, stats: dict, status: str = "SUBMITTED"):
        """
        Set exam statistics to display.
        
        Args:
            stats: Dictionary with keys:
                - answered: int
                - unanswered: int
                - marked_review: int
                - total_questions: int
                - time_taken_seconds: int
                - time_allotted_seconds: int
                - violations_count: int
                - violations: List[str]
            status: "SUBMITTED" or "TERMINATED"
        """
        self._exam_stats = stats
        
        # Update header based on status
        if status == "TERMINATED":
            self.header_frame.setStyleSheet("""
                QFrame {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 #ff6b6b, stop:1 #ee5a5a
                    );
                    border-radius: 16px;
                    padding: 20px;
                }
            """)
            self.status_icon.setText("⚠")
            self.status_title.setText("Exam Session Terminated")
            self.status_subtitle.setText(
                "Your exam session was terminated due to policy violations. "
                "Please contact the invigilator."
            )
        
        # Update stat cards
        answered = stats.get("answered", 0)
        unanswered = stats.get("unanswered", 0)
        review = stats.get("marked_review", 0)
        time_seconds = stats.get("time_taken_seconds", 0)
        
        # Format time
        minutes = time_seconds // 60
        seconds = time_seconds % 60
        time_str = f"{minutes}m {seconds}s" if seconds else f"{minutes}m"
        
        # Recreate cards with actual values
        self._update_stat_card(self.answered_card, str(answered), "✅", "#00d9a5")
        self._update_stat_card(self.unanswered_card, str(unanswered), "⭕", 
                               "#ff6b6b" if unanswered > 0 else "#ff9900")
        self._update_stat_card(self.review_card, str(review), "🔖", "#4da6ff")
        self._update_stat_card(self.time_card, time_str, "⏱️", "#667eea")
        
        # Update violations section
        violations_count = stats.get("violations_count", 0)
        violations = stats.get("violations", [])
        
        if violations_count > 0:
            self.violations_frame.show()
            self.violations_title.setText(f"Proctoring Alerts ({violations_count})")
            
            if violations:
                # Show first few violations
                violations_text = "\n".join([f"• {v}" for v in violations[:5]])
                if len(violations) > 5:
                    violations_text += f"\n• ... and {len(violations) - 5} more"
                self.violations_label.setText(violations_text)
            else:
                self.violations_label.setText(
                    f"{violations_count} alerts were recorded during your exam session."
                )
        else:
            self.violations_frame.hide()
        
        # Update timestamp
        self.timestamp_label.setText(
            f"Submitted at {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        )
    
    def _update_stat_card(self, card: StatCard, value: str, icon: str, color: str):
        """Update a stat card's value display."""
        # Find and update the value label
        for child in card.findChildren(QLabel):
            font = child.font()
            if font.pointSize() >= 24:  # The value label has large font
                child.setText(value)
                child.setStyleSheet(f"color: {color};")
                break
    
    def _on_exit(self):
        """Handle exit button click."""
        logger.info("User requested exit from completion screen")
        self.exit_requested.emit()
        QApplication.quit()
