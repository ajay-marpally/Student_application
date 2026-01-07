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
from PySide6.QtGui import QFont, QPixmap, QImage, QPainter, QPainterPath, QColor, QBrush, QPen
import cv2
import os

logger = logging.getLogger(__name__)


class AuthWorker(QThread):
    """Background worker for authentication."""
    
    finished = Signal(bool, dict)  # success, data
    error = Signal(str)
    
    def __init__(self, hall_ticket: str, face_frame=None):
        super().__init__()
        self.hall_ticket = hall_ticket
        self.face_frame = face_frame
    
    def run(self):
        try:
            from student_app.app.auth import get_authenticator
            
            auth = get_authenticator()
            
            # Authenticate with frame
            result = auth.authenticate(
                hall_ticket=self.hall_ticket,
                face_frame=self.face_frame
            )
            
            if not result.success:
                self.finished.emit(False, {"error": result.error})
                return
            
            # Package student data
            data = {
                "student_id": result.student_id,
                "user_id": result.user_id,
                "hall_ticket": result.hall_ticket,
                "name": result.student_name,
                "exam_id": result.exam_id,
                "exam_name": result.exam_name,
                "exam_duration": result.exam_duration,
                "photo_url": result.photo_url
            }
            
            self.finished.emit(True, data)
            
        except Exception as e:
            logger.error(f"Auth error: {e}")
            self.error.emit(str(e))


class CameraPreview(QLabel):
    """Circular camera preview widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(280, 280)
        # Remove border/radius from stylesheet to handle it manually
        self.setStyleSheet("background-color: transparent;")
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self._cap = None
        self._timer = None
        self._current_frame = None
    
    def start(self, camera_index: int = 0):
        """Start camera preview."""
        try:
            if self._cap is not None:
                self._cap.release()
            
            # Try to open camera
            if os.name == 'nt':
                 self._cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            
            if self._cap is None or not self._cap.isOpened():
                self._cap = cv2.VideoCapture(camera_index)

            if not self._cap.isOpened():
                return
            
            # Start timer
            if self._timer:
                self._timer.stop()
                
            from PySide6.QtCore import QTimer
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update_frame)
            self._timer.start(50)
            
        except Exception as e:
            logger.error(f"Camera start error: {e}")

    def capture_frame(self):
        """Capture current frame."""
        if self._current_frame is None:
            if self._cap and self._cap.isOpened():
                ret, frame = self._cap.read()
                if ret:
                    self._current_frame = frame
                    return frame.copy()
        return self._current_frame.copy() if self._current_frame is not None else None

    def _update_frame(self):
        """Update preview with new frame."""
        if self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret:
                # Keep the frame for capture/auth
                self._current_frame = frame
                
                # Prepare display image (RGB)
                # Convert to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                
                # Crop to square (center) for display
                min_dim = min(h, w)
                start_x = (w - min_dim) // 2
                start_y = (h - min_dim) // 2
                # Memory copy is critical for QImage
                frame_sq = frame_rgb[start_y:start_y+min_dim, start_x:start_x+min_dim].copy()
                
                height, width, channel = frame_sq.shape
                bytes_per_line = channel * width
                self._display_image = QImage(frame_sq.data, width, height, bytes_per_line, QImage.Format_RGB888)
                
                # Trigger repaint
                self.update()

    def paintEvent(self, event):
        """Paint the circular camera feed."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Geometry
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        
        # 1. Setup Circular Clip Region
        # We draw everything inside this circle
        path = QPainterPath()
        path.addEllipse(0, 0, width, height)
        
        # 2. Draw Background (Black)
        # This fills the circle with black, covering any square corners
        painter.setClipPath(path)
        painter.fillPath(path, QColor("#0a0a15"))
        
        # 3. Draw Camera Image
        if hasattr(self, '_display_image') and self._display_image is not None:
            # Scale image to cover the full circle
            painter.drawImage(rect, self._display_image)
            
        # 4. Draw Border
        # We disabled clipping to draw the border smoothly on top, 
        # but since it follows the same path, it looks perfect.
        painter.setClipping(True) # Keep clipping to be safe
        
        pen = QPen(QColor("#4da6ff"))
        pen.setWidth(4)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        
        # Draw border slightly inset to ensure it's fully visible
        painter.drawEllipse(2, 2, width-4, height-4)

    
    def stop(self):
        """Stop camera preview."""
        if self._timer:
            self._timer.stop()
        if self._cap:
            self._cap.release()

    def get_available_cameras(self) -> List[int]:
        """Simple camera discovery."""
        return [0] # Minimal implementation for now


class LoginScreen(QWidget):
    """
    Login screen with circular camera view.
    """
    
    login_successful = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Create login UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(30)
        
        # Header
        header = QLabel("Student Exam Portal")
        header.setFont(QFont("Segoe UI", 32, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #ffffff;")
        layout.addWidget(header)
        
        subtitle = QLabel("Please enter your hall ticket number to begin")
        subtitle.setFont(QFont("Segoe UI", 16))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #888888;")
        layout.addWidget(subtitle)
        
        layout.addStretch()
        
        # Main content card
        content = QFrame()
        content.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border-radius: 20px;
                padding: 40px;
            }
        """)
        content_layout = QHBoxLayout(content)
        content_layout.setSpacing(50)
        
        # Left side - Circular Camera
        camera_container = QVBoxLayout()
        camera_container.setAlignment(Qt.AlignCenter)
        camera_container.setSpacing(20)
        
        self.camera_preview = CameraPreview()
        camera_container.addWidget(self.camera_preview)
        
        instruction_label = QLabel("Position your face within the circle")
        instruction_label.setFont(QFont("Segoe UI", 12))
        instruction_label.setStyleSheet("color: #4da6ff; font-style: italic;")
        instruction_label.setAlignment(Qt.AlignCenter)
        camera_container.addWidget(instruction_label)
        
        content_layout.addLayout(camera_container)
        
        # Right side - Login form
        form_container = QVBoxLayout()
        form_container.setSpacing(20)
        form_container.setAlignment(Qt.AlignCenter)
        
        # Hall ticket input
        ht_label = QLabel("Hall Ticket Number")
        ht_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        ht_label.setStyleSheet("color: #ffffff;")
        form_container.addWidget(ht_label)
        
        self.hall_ticket_input = QLineEdit()
        self.hall_ticket_input.setPlaceholderText("Enter your hall ticket number")
        self.hall_ticket_input.setMinimumHeight(50)
        self.hall_ticket_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f3460;
                color: #ffffff;
                border: 2px solid #2a4a7a;
                border-radius: 8px;
                padding: 0 15px;
                font-size: 16px;
            }
            QLineEdit:focus {
                border-color: #4da6ff;
            }
        """)
        self.hall_ticket_input.returnPressed.connect(self._on_login_clicked)
        form_container.addWidget(self.hall_ticket_input)
        
        form_container.addSpacing(10)
        
        # Login button
        self.login_btn = QPushButton("Verify & Login")
        self.login_btn.setMinimumHeight(55)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4da6ff, stop:1 #2a85ff);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5db6ff, stop:1 #3a95ff);
            }
            QPushButton:disabled {
                background-color: #2a4a7a;
            }
        """)
        self.login_btn.clicked.connect(self._on_login_clicked)
        form_container.addWidget(self.login_btn)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #ff6b6b; font-size: 13px;")
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
        self.camera_preview.start(0)
    
    def _on_login_clicked(self):
        """Handle login button click."""
        hall_ticket = self.hall_ticket_input.text().strip()
        
        if not hall_ticket:
            self.status_label.setText("Please enter your hall ticket number")
            return
            
        # Prompt user to look at camera
        msg = QMessageBox(self)
        msg.setWindowTitle("Biometric Verification")
        msg.setText("Please look directly at the camera for identity verification.")
        msg.setIcon(QMessageBox.Information)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()
            
        # Capture verification frame
        frame = self.camera_preview.capture_frame()
        if frame is None:
             self.status_label.setText("Camera error: No frame captured")
             return
        
        # Disable UI during authentication
        self.login_btn.setEnabled(False)
        self.hall_ticket_input.setEnabled(False)
        self.status_label.setText("Verifying Biometrics.....")
        self.status_label.setStyleSheet("color: #4da6ff; font-size: 14px;")
        
        # Start authentication worker
        self._worker = AuthWorker(hall_ticket, frame)
        self._worker.finished.connect(self._on_auth_finished)
        self._worker.error.connect(self._on_auth_error)
        self._worker.start()

    def _on_auth_finished(self, success: bool, data: dict):
        """Handle authentication result."""
        if success:
            # Stop camera preview
            self.camera_preview.stop()
            
            # Store camera index for later use (default to 0 since selection was removed)
            data["camera_index"] = 0
            
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
