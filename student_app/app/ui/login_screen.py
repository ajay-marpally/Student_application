"""
Student Exam Application - UI: Login Screen

Login interface with hall ticket and biometric verification.
"""

import logging
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QPixmap
import cv2

logger = logging.getLogger(__name__)


class AuthWorker(QThread):
    """Background worker for authentication."""
    
    finished = Signal(bool, dict)  # success, data
    error = Signal(str)
    
    def __init__(self, hall_ticket: str):
        super().__init__()
        self.hall_ticket = hall_ticket
    
    def run(self):
        try:
            from student_app.app.storage.supabase_client import get_supabase_client
            
            client = get_supabase_client()
            
            # Fetch student by hall ticket
            student = client.get_student_by_hall_ticket(self.hall_ticket)
            
            if not student:
                self.finished.emit(False, {"error": "Invalid hall ticket number"})
                return
            
            # Fetch exam assignment
            assignment = client.get_exam_assignment(student["id"])
            
            if not assignment:
                self.finished.emit(False, {"error": "No exam assigned"})
                return
            
            # Package student data
            data = {
                "student_id": student["id"],
                "user_id": student["user_id"],
                "hall_ticket": student["hall_ticket"],
                "name": student.get("users", {}).get("name", "Student"),
                "exam_id": assignment["exam_id"],
                "exam_name": assignment.get("exams", {}).get("name", "Exam"),
                "exam_duration": assignment.get("exams", {}).get("duration_minutes", 60),
            }
            
            self.finished.emit(True, data)
            
        except Exception as e:
            logger.error(f"Auth error: {e}")
            self.error.emit(str(e))


class CameraPreview(QLabel):
    """Camera preview widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMaximumSize(480, 360)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: #0a0a15;
                border: 2px solid #2a2a4a;
                border-radius: 8px;
            }
        """)
        self.setText("Camera Preview")
        
        self._cap = None
        self._timer = None
    
    def start(self, camera_index: int = 0):
        """Start camera preview."""
        try:
            self._cap = cv2.VideoCapture(camera_index)
            
            if not self._cap.isOpened():
                self.setText("Camera not available")
                return
            
            from PySide6.QtCore import QTimer
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update_frame)
            self._timer.start(50)  # ~20 FPS
            
        except Exception as e:
            logger.error(f"Camera error: {e}")
            self.setText(f"Camera error: {e}")
    
    def _update_frame(self):
        """Update preview with new frame."""
        if self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret:
                # Convert to Qt format
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                
                from PySide6.QtGui import QImage
                img = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888)
                
                # Scale to fit
                pixmap = QPixmap.fromImage(img).scaled(
                    self.width(), self.height(),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.setPixmap(pixmap)
    
    def stop(self):
        """Stop camera preview."""
        if self._timer:
            self._timer.stop()
        if self._cap:
            self._cap.release()
    
    def get_available_cameras(self) -> List[int]:
        """Get list of available camera indices."""
        cameras = []
        for i in range(5):  # Check first 5 indices
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cameras.append(i)
                cap.release()
        return cameras


class LoginScreen(QWidget):
    """
    Login screen with hall ticket entry and camera verification.
    """
    
    login_successful = Signal(dict)  # Emits student/exam data
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Create login UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(20)
        
        # Header
        header = QLabel("Student Exam Portal")
        header.setFont(QFont("Segoe UI", 32, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #ffffff;")
        layout.addWidget(header)
        
        subtitle = QLabel("Please enter your hall ticket number to begin")
        subtitle.setFont(QFont("Segoe UI", 14))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #888888;")
        layout.addWidget(subtitle)
        
        layout.addStretch()
        
        # Main content
        content = QFrame()
        content.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border-radius: 16px;
                padding: 30px;
            }
        """)
        content_layout = QHBoxLayout(content)
        content_layout.setSpacing(40)
        
        # Left side - Camera preview
        camera_container = QVBoxLayout()
        
        camera_label = QLabel("Camera Preview")
        camera_label.setStyleSheet("color: #ffffff; font-size: 14px;")
        camera_container.addWidget(camera_label)
        
        self.camera_preview = CameraPreview()
        camera_container.addWidget(self.camera_preview)
        
        # Camera selection
        camera_select_layout = QHBoxLayout()
        camera_select_label = QLabel("Camera:")
        camera_select_label.setStyleSheet("color: #888888;")
        camera_select_layout.addWidget(camera_select_label)
        
        self.camera_combo = QComboBox()
        self.camera_combo.setStyleSheet("""
            QComboBox {
                background-color: #0f3460;
                color: white;
                border: 1px solid #2a4a7a;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        camera_select_layout.addWidget(self.camera_combo)
        camera_container.addLayout(camera_select_layout)
        
        content_layout.addLayout(camera_container)
        
        # Right side - Login form
        form_container = QVBoxLayout()
        form_container.setSpacing(15)
        
        # Hall ticket input
        ht_label = QLabel("Hall Ticket Number")
        ht_label.setStyleSheet("color: #ffffff; font-size: 14px;")
        form_container.addWidget(ht_label)
        
        self.hall_ticket_input = QLineEdit()
        self.hall_ticket_input.setPlaceholderText("Enter your hall ticket number")
        self.hall_ticket_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f3460;
                color: #ffffff;
                border: 2px solid #2a4a7a;
                border-radius: 8px;
                padding: 15px;
                font-size: 16px;
            }
            QLineEdit:focus {
                border-color: #4da6ff;
            }
        """)
        self.hall_ticket_input.returnPressed.connect(self._on_login_clicked)
        form_container.addWidget(self.hall_ticket_input)
        
        form_container.addStretch()
        
        # Login button
        self.login_btn = QPushButton("Verify & Login")
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #4da6ff;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 15px 30px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3d96ef;
            }
            QPushButton:disabled {
                background-color: #2a4a7a;
            }
        """)
        self.login_btn.clicked.connect(self._on_login_clicked)
        form_container.addWidget(self.login_btn)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #ff6b6b; font-size: 14px;")
        form_container.addWidget(self.status_label)
        
        content_layout.addLayout(form_container)
        
        layout.addWidget(content)
        layout.addStretch()
        
        # Footer
        footer = QLabel("Proctored by AI | All activities are monitored")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #666666; font-size: 12px;")
        layout.addWidget(footer)
        
        # Initialize camera
        self._init_cameras()
    
    def _init_cameras(self):
        """Initialize camera selection."""
        cameras = self.camera_preview.get_available_cameras()
        
        if cameras:
            for idx in cameras:
                self.camera_combo.addItem(f"Camera {idx}", idx)
            
            # Start preview with first camera
            self.camera_preview.start(cameras[0])
        else:
            self.camera_combo.addItem("No cameras found", -1)
    
    def _on_camera_changed(self, index):
        """Handle camera selection change."""
        camera_idx = self.camera_combo.currentData()
        if camera_idx is not None and camera_idx >= 0:
            self.camera_preview.stop()
            self.camera_preview.start(camera_idx)
    
    def _on_login_clicked(self):
        """Handle login button click."""
        hall_ticket = self.hall_ticket_input.text().strip()
        
        if not hall_ticket:
            self.status_label.setText("Please enter your hall ticket number")
            return
        
        # Disable UI during authentication
        self.login_btn.setEnabled(False)
        self.hall_ticket_input.setEnabled(False)
        self.status_label.setText("Verifying...")
        self.status_label.setStyleSheet("color: #4da6ff; font-size: 14px;")
        
        # Start authentication worker
        self._worker = AuthWorker(hall_ticket)
        self._worker.finished.connect(self._on_auth_finished)
        self._worker.error.connect(self._on_auth_error)
        self._worker.start()
    
    def _on_auth_finished(self, success: bool, data: dict):
        """Handle authentication result."""
        if success:
            # Stop camera preview
            self.camera_preview.stop()
            
            # Store camera index for later use
            data["camera_index"] = self.camera_combo.currentData() or 0
            
            # Emit success signal
            self.login_successful.emit(data)
        else:
            error = data.get("error", "Authentication failed")
            self.status_label.setText(error)
            self.status_label.setStyleSheet("color: #ff6b6b; font-size: 14px;")
            
            # Re-enable UI
            self.login_btn.setEnabled(True)
            self.hall_ticket_input.setEnabled(True)
    
    def _on_auth_error(self, error: str):
        """Handle authentication error."""
        self.status_label.setText(f"Error: {error}")
        self.status_label.setStyleSheet("color: #ff6b6b; font-size: 14px;")
        
        # Re-enable UI
        self.login_btn.setEnabled(True)
        self.hall_ticket_input.setEnabled(True)
    
    def hideEvent(self, event):
        """Stop camera when hidden."""
        self.camera_preview.stop()
        super().hideEvent(event)
