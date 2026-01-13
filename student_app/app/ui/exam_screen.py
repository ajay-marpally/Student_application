"""
Student Exam Application - UI: Exam Screen

MCQ exam interface with question navigation and auto-save.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QButtonGroup, QRadioButton,
    QGridLayout, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread

logger = logging.getLogger(__name__)


class ProctorWorker(QThread):
    """Background worker for AI proctoring."""
    
    violation_detected = Signal(str, int)  # message, severity
    
    def __init__(self, camera_index: int = 0, photo_url: str = None):
        super().__init__()
        self.camera_index = camera_index
        self.photo_url = photo_url  # Reference photo URL for face verification
        self._running = False
    
    def run(self):
        """Main proctoring loop using Advanced AI Engine (10 FPS)."""
        import cv2
        import time
        from datetime import datetime
        from student_app.app.ai.advanced import (
            AdvancedVisualDetector, AdvancedAudioMonitor, 
            AdvancedRuleEngine, AdvancedHybridVerifier
        )
        from student_app.app.ai import get_face_verifier, is_face_verification_available
        from student_app.app.buffer import get_circular_buffer
        from student_app.app.exam_engine import get_exam_engine
        
        self._running = True
        
        # 1. Initialize Advanced Components
        detector = AdvancedVisualDetector()
        engine = AdvancedRuleEngine()
        buffer = get_circular_buffer()
        exam_engine = get_exam_engine()
        
        # 2. Audio Monitoring (Silero VAD)
        self.audio_data = {"audio_spike": False}
        def audio_callback(data):
            self.audio_data = data
        
        audio_monitor = None
        try:
            audio_monitor = AdvancedAudioMonitor(audio_callback)
            audio_monitor.start()
        except Exception as e:
            logger.error(f"Failed to start audio monitoring: {e}")
        
        # 3. Biometric Verification (Maintain existing logic)
        face_verifier = None
        try:
            if is_face_verification_available() and self.photo_url:
                face_verifier = get_face_verifier()
                if face_verifier and not face_verifier.load_reference_from_url(self.photo_url):
                    logger.warning("Could not load reference photo for impersonation check")
                    face_verifier = None
        except Exception as e:
            logger.error(f"Failed to initialize face verifier: {e}")
        
        # 4. Open Camera
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            logger.error(f"Could not open camera {self.camera_index} for proctoring")
            if audio_monitor:
                audio_monitor.stop()
            return
            
        logger.info(f"Advanced Proctoring started at 10 FPS on camera {self.camera_index}")
        
        last_frame_time = 0
        frame_interval = 0.1 # 10 FPS
        frame_count = 0
        
        try:
            while self._running:
                now_ts = time.time()
                
                # Maintain 10 FPS processing rate
                if now_ts - last_frame_time < frame_interval:
                    time.sleep(0.01)
                    continue
                last_frame_time = now_ts
                
                ret, frame = cap.read()
                if not ret:
                    continue
                
                frame_count += 1
                now_dt = datetime.now()
                
                # Add to rolling buffer
                buffer.add_frame(frame, now_dt)
                
                # 5. Advanced Visual Analysis (YOLO + MediaPipe)
                visual_data = detector.process_frame(frame)
                
                # 6. Combine with Audio and Focus Data
                # (Focus loss is checked by ExamEngine/MainWindow, we get it from state)
                focus_loss = not exam_engine.state.is_fullscreen # Simple proxy
                
                detection_payload = {
                    **visual_data,
                    "audio_spike": self.audio_data.get("audio_spike", False),
                    "focus_loss": focus_loss
                }

                # Explicit Logging for Visibility
                if frame_count % 50 == 0:
                    logger.info(f"AI: Heartbeat - analyzing at 10 FPS (Processed {frame_count} frames)")
                    
                    # Periodic summary of detections (even if not violations)
                    if frame_count % 100 == 0:
                        status = "Normal"
                        if not visual_data.get("face_present"): status = "Candidate Absent"
                        elif visual_data.get("multiple_faces"): status = "Multiple Faces"
                        elif visual_data.get("gaze_deviation"): status = "Looking Away"
                        logger.info(f"AI: Status Summary - {status}")
                
                if visual_data.get("phone_detected"): logger.info("AI: Phone detected (Verifying...)")
                if visual_data.get("book_detected"): logger.info("AI: Book detected (Verifying...)")
                if visual_data.get("suspicious_object"): logger.info("AI: Secondary device detected (Verifying...)")
                
                # 7. Rule Engine & Risk Scoring
                result = engine.process_detection(detection_payload, frame)
                
                # 8. Biometric Impersonation Check (Every 10 frames)
                if face_verifier and frame_count % 10 == 0:
                    face_verifier.verify(frame)
                    should_alert, reason = face_verifier.should_alert()
                    if should_alert:
                        result["violations"].append({
                            "type": "impersonation_suspected",
                            "level": 5,
                            "message": f"CRITICAL: {reason}"
                        })
                        result["current_risk"] = max(result["current_risk"], 100)
                        result["risk_level"] = "critical"
                        face_verifier.reset_tracking()

                # 9. Handle Evidence Capture Trigger (Consolidated)
                clip = None
                if result.get("trigger_evidence"):
                    clip = exam_engine.trigger_evidence_capture(result)

                # 10. Feed Results back to ExamEngine for DB Logging
                if result["violations"]:
                    for v in result["violations"]:
                        # Sync with ExamEngine's event system
                        # Pass the captured clip to merge violation and evidence records
                        exam_engine.process_advanced_violation(v, result, detection_payload, clip=clip)
                        
                        # Emit signal for UI warning overlays
                        if v.get("level", 0) >= 4:
                            self.violation_detected.emit(v["message"], v["level"])
        
        except Exception as e:
            logger.error(f"Critical error in proctoring loop: {e}")
        finally:
            audio_monitor.stop()
            cap.release()
            logger.info("Proctoring stopped")
    
    def stop(self):
        """Stop the proctoring loop."""
        self._running = False


class ExamScreen(QWidget):
    """
    MCQ exam interface with question navigation.
    """
    
    exam_submitted = Signal(str, dict)  # status, exam_stats
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.student_data = {}
        self.questions: List[Dict] = []
        self.answers: Dict[str, int] = {}  # question_id -> selected_option
        self.review_flags: Dict[str, bool] = {}  # question_id -> marked
        self.current_index = 0
        self.attempt_id: Optional[str] = None
        
        self._timer = None
        self._autosave_timer = None
        self._proctor_worker = None
        self._exam_active = False
        self._end_time: Optional[datetime] = None
        self.start_time: Optional[datetime] = None
        self.violations: List[str] = []  # List of violation descriptions
        self.exam_duration_minutes: int = 60
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Create exam UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Left side - Question panel (70%)
        question_panel = QFrame()
        question_panel.setStyleSheet("""
            QFrame {
                background-color: #1a1a2e;
            }
        """)
        question_layout = QVBoxLayout(question_panel)
        question_layout.setContentsMargins(30, 20, 30, 20)
        
        # Header bar
        header = QHBoxLayout()
        
        self.question_number_label = QLabel("Question 1 of 10")
        self.question_number_label.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        header.addWidget(self.question_number_label)
        
        header.addStretch()
        
        self.timer_label = QLabel("Time Left: 60:00")
        self.timer_label.setStyleSheet("""
            color: #4da6ff; 
            font-size: 18px; 
            font-weight: bold;
            font-family: 'Consolas', monospace;
        """)
        header.addWidget(self.timer_label)
        
        question_layout.addLayout(header)
        
        # Question text
        question_frame = QFrame()
        question_frame.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        question_frame_layout = QVBoxLayout(question_frame)
        
        self.question_text = QLabel("")
        self.question_text.setWordWrap(True)
        self.question_text.setStyleSheet("color: white; font-size: 18px; line-height: 1.6;")
        question_frame_layout.addWidget(self.question_text)
        
        question_layout.addWidget(question_frame)
        
        # Options
        options_frame = QFrame()
        options_frame.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border-radius: 12px;
                padding: 20px;
                margin-top: 10px;
            }
        """)
        options_layout = QVBoxLayout(options_frame)
        
        self.option_group = QButtonGroup(self)
        self.option_buttons: List[QRadioButton] = []
        
        for i in range(4):  # Support up to 4 options
            option = QRadioButton(f"Option {i+1}")
            option.setStyleSheet("""
                QRadioButton {
                    color: white;
                    font-size: 16px;
                    padding: 15px;
                    spacing: 15px;
                }
                QRadioButton::indicator {
                    width: 20px;
                    height: 20px;
                }
            """)
            option.clicked.connect(self._on_option_selected)
            self.option_group.addButton(option, i)
            self.option_buttons.append(option)
            options_layout.addWidget(option)
        
        question_layout.addWidget(options_frame)
        
        question_layout.addStretch()
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.setStyleSheet(self._nav_button_style())
        self.prev_btn.clicked.connect(self._go_previous)
        nav_layout.addWidget(self.prev_btn)
        
        self.mark_review_btn = QPushButton("Mark for Review")
        self.mark_review_btn.setStyleSheet(self._nav_button_style("#ff9900"))
        self.mark_review_btn.clicked.connect(self._toggle_review)
        nav_layout.addWidget(self.mark_review_btn)
        
        nav_layout.addStretch()
        
        self.next_btn = QPushButton("Next →")
        self.next_btn.setStyleSheet(self._nav_button_style())
        self.next_btn.clicked.connect(self._go_next)
        nav_layout.addWidget(self.next_btn)
        
        question_layout.addLayout(nav_layout)
        
        layout.addWidget(question_panel, 7)
        
        # Right side - Navigation grid (30%)
        nav_panel = QFrame()
        nav_panel.setStyleSheet("""
            QFrame {
                background-color: #0f3460;
            }
        """)
        nav_panel_layout = QVBoxLayout(nav_panel)
        nav_panel_layout.setContentsMargins(15, 20, 15, 20)
        
        # Question grid
        grid_label = QLabel("Question Navigator")
        grid_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        nav_panel_layout.addWidget(grid_label)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        
        grid_container = QWidget()
        self.question_grid = QGridLayout(grid_container)
        self.question_grid.setSpacing(8)
        self.question_buttons: List[QPushButton] = []
        
        scroll.setWidget(grid_container)
        nav_panel_layout.addWidget(scroll)
        
        # Legend
        legend_layout = QVBoxLayout()
        legend_layout.setSpacing(5)
        
        for color, text in [
            ("#4da6ff", "Current"),
            ("#00c853", "Answered"),
            ("#ff9900", "Marked for Review"),
            ("#555555", "Not Visited"),
        ]:
            row = QHBoxLayout()
            indicator = QLabel()
            indicator.setFixedSize(16, 16)
            indicator.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
            row.addWidget(indicator)
            label = QLabel(text)
            label.setStyleSheet("color: #888888; font-size: 12px;")
            row.addWidget(label)
            row.addStretch()
            legend_layout.addLayout(row)
        
        nav_panel_layout.addLayout(legend_layout)
        
        # Submit button
        self.submit_btn = QPushButton("Submit Exam")
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #00c853;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 15px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00b548;
            }
        """)
        self.submit_btn.clicked.connect(self._on_submit)
        nav_panel_layout.addWidget(self.submit_btn)
        
        layout.addWidget(nav_panel, 3)
    
    def _nav_button_style(self, color: str = "#4da6ff") -> str:
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            QPushButton:disabled {{
                background-color: #333;
            }}
        """
    
    def set_exam_data(self, student_data: dict):
        """Set exam data after login."""
        self.student_data = student_data
    
    def start_exam(self):
        """Start the exam session."""
        logger.info("Starting exam")
        
        # Get exam engine and set its state FIRST
        from student_app.app.exam_engine import get_exam_engine
        exam_engine = get_exam_engine()
        
        # Populate engine state with student/exam data
        exam_engine.state.student_id = self.student_data["student_id"]
        exam_engine.state.exam_id = self.student_data["exam_id"]
        exam_engine.state.student_name = self.student_data.get("student_name", "")
        exam_engine.state.hall_ticket = self.student_data.get("hall_ticket", "")
        exam_engine.state.lab_id = self.student_data.get("lab_id")
        
        # Now start exam (creates attempt, starts uploader)
        if not exam_engine.start_exam():
            logger.error("Failed to start exam via ExamEngine")
            return
        
        # Store attempt_id from engine
        self.attempt_id = exam_engine.state.attempt_id
        logger.info(f"Exam started with attempt_id: {self.attempt_id}")
        
        # Fetch questions
        from student_app.app.storage.supabase_client import get_supabase_client
        client = get_supabase_client()
        self.questions = client.get_exam_questions(self.student_data["exam_id"])
        
        if not self.questions:
            logger.warning("No questions found, using sample data")
            # Sample questions for testing
            self.questions = [
                {
                    "id": f"q{i}",
                    "question_text": f"Sample question {i+1}?",
                    "options": ["Option A", "Option B", "Option C", "Option D"]
                }
                for i in range(10)
            ]
        
        # Create question grid buttons
        self._create_question_grid()
        
        # Load first question
        self._load_question(0)
        
        # Start timer
        self.exam_duration_minutes = self.student_data.get("exam_duration", 60)
        self.start_time = datetime.now()
        self._end_time = self.start_time + timedelta(minutes=self.exam_duration_minutes)
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_timer)
        self._timer.start(1000)
        
        # Start auto-save
        from student_app.app.config import get_config
        autosave_interval = get_config().thresholds.AUTOSAVE_INTERVAL_SECONDS * 1000
        
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start(autosave_interval)
        
        # Start proctoring
        camera_index = self.student_data.get("camera_index", 0)
        photo_url = self.student_data.get("photo_url")  # Reference photo for face verification
        self._proctor_worker = ProctorWorker(camera_index, photo_url)
        self._proctor_worker.violation_detected.connect(self._on_violation)
        self._proctor_worker.start()
        
        self._exam_active = True
    
    def _create_question_grid(self):
        """Create question navigation grid."""
        cols = 5
        for i, q in enumerate(self.questions):
            btn = QPushButton(str(i + 1))
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(self._grid_button_style("not_visited"))
            btn.clicked.connect(lambda checked, idx=i: self._load_question(idx))
            
            row = i // cols
            col = i % cols
            self.question_grid.addWidget(btn, row, col)
            self.question_buttons.append(btn)
    
    def _grid_button_style(self, state: str) -> str:
        colors = {
            "current": "#4da6ff",
            "answered": "#00c853",
            "review": "#ff9900",
            "not_visited": "#555555",
        }
        color = colors.get(state, "#555555")
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }}
        """
    
    def _load_question(self, index: int):
        """Load a question by index."""
        if index < 0 or index >= len(self.questions):
            return
        
        self.current_index = index
        question = self.questions[index]
        
        # Update header
        self.question_number_label.setText(f"Question {index + 1} of {len(self.questions)}")
        
        # Update question text
        self.question_text.setText(question.get("question_text", ""))
        
        # Update options
        options = question.get("options", [])
        if isinstance(options, dict):
            # Handle JSONB format
            options = [options.get(str(i), f"Option {i+1}") for i in range(4)]
        
        for i, btn in enumerate(self.option_buttons):
            if i < len(options):
                btn.setText(options[i])
                btn.setVisible(True)
            else:
                btn.setVisible(False)
        
        # Restore selection
        q_id = question["id"]
        selected = self.answers.get(q_id)
        
        self.option_group.setExclusive(False)
        for btn in self.option_buttons:
            btn.setChecked(False)
        self.option_group.setExclusive(True)
        
        if selected is not None and 0 <= selected < len(self.option_buttons):
            self.option_buttons[selected].setChecked(True)
        
        # Update review button
        if self.review_flags.get(q_id):
            self.mark_review_btn.setText("Remove Review Mark")
        else:
            self.mark_review_btn.setText("Mark for Review")
        
        # Update navigation buttons
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < len(self.questions) - 1)
        
        # Update grid
        self._update_question_grid()
    
    def _update_question_grid(self):
        """Update question grid button states."""
        for i, btn in enumerate(self.question_buttons):
            q_id = self.questions[i]["id"]
            
            if i == self.current_index:
                state = "current"
            elif self.review_flags.get(q_id):
                state = "review"
            elif q_id in self.answers:
                state = "answered"
            else:
                state = "not_visited"
            
            btn.setStyleSheet(self._grid_button_style(state))
    
    def _on_option_selected(self):
        """Handle option selection."""
        selected = self.option_group.checkedId()
        if selected >= 0:
            q_id = self.questions[self.current_index]["id"]
            self.answers[q_id] = selected
            self._update_question_grid()
    
    def _go_previous(self):
        """Go to previous question."""
        self._load_question(self.current_index - 1)
    
    def _go_next(self):
        """Go to next question."""
        self._load_question(self.current_index + 1)
    
    def _toggle_review(self):
        """Toggle review flag for current question."""
        q_id = self.questions[self.current_index]["id"]
        self.review_flags[q_id] = not self.review_flags.get(q_id, False)
        
        if self.review_flags[q_id]:
            self.mark_review_btn.setText("Remove Review Mark")
        else:
            self.mark_review_btn.setText("Mark for Review")
        
        self._update_question_grid()
    
    def _update_timer(self):
        """Update exam timer."""
        if not self._end_time:
            return
        
        remaining = self._end_time - datetime.now()
        
        if remaining.total_seconds() <= 0:
            # Time's up - auto-submit
            self._timer.stop()
            self._submit_exam("SUBMITTED")
            return
        
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        
        self.timer_label.setText(f"Time Left: {minutes:02d}:{seconds:02d}")
        
        # Warning colors
        if remaining.total_seconds() < 300:  # Less than 5 minutes
            self.timer_label.setStyleSheet("""
                color: #ff6b6b;
                font-size: 18px;
                font-weight: bold;
                font-family: 'Consolas', monospace;
            """)
    
    def _autosave(self):
        """Auto-save answers."""
        if not self.attempt_id:
            return
        
        from student_app.app.storage.supabase_client import get_supabase_client
        client = get_supabase_client()
        
        for q_id, selected in self.answers.items():
            client.save_answer(
                attempt_id=self.attempt_id,
                question_id=q_id,
                selected_option=selected,
                marked_for_review=self.review_flags.get(q_id, False)
            )
        
        logger.debug(f"Auto-saved {len(self.answers)} answers")
    
    def _on_violation(self, message: str, severity: int):
        """Handle proctoring violation."""
        logger.warning(f"Violation: {message} (severity {severity})")
        
        # Track violation
        self.violations.append(message)
        
        # Record malpractice event
        if self.attempt_id:
            from student_app.app.storage.supabase_client import get_supabase_client
            
            # All violations now go through process_advanced_violation
            # which logs to student_ai_analysis table via queue
        
        # Show warning for severe violations
        if severity >= 8:
            from student_app.app.ui.warning_overlay import show_warning_overlay
            show_warning_overlay(self.window(), message)
    
    def _on_submit(self):
        """Handle submit button click."""
        # Confirm submission
        unanswered = len(self.questions) - len(self.answers)
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Confirm Submission")
        
        if unanswered > 0:
            msg.setText(f"You have {unanswered} unanswered questions.\n\nAre you sure you want to submit?")
        else:
            msg.setText("Are you sure you want to submit your exam?\n\nYou cannot make changes after submission.")
        
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        
        if msg.exec() == QMessageBox.Yes:
            self._submit_exam("SUBMITTED")
    
    def _submit_exam(self, status: str):
        """Submit the exam."""
        self._exam_active = False
        
        # Stop proctoring
        if self._proctor_worker:
            self._proctor_worker.stop()
            self._proctor_worker.wait(2000)
        
        # Stop timers
        if self._timer:
            self._timer.stop()
        if self._autosave_timer:
            self._autosave_timer.stop()
        
        # Final save
        self._autosave()
        
        # Update attempt status
        if self.attempt_id:
            from student_app.app.storage.supabase_client import get_supabase_client
            client = get_supabase_client()
            client.update_exam_attempt(
                attempt_id=self.attempt_id,
                status=status,
                end_time=datetime.now()
            )
        
        # Calculate exam statistics
        answered = len(self.answers)
        unanswered = len(self.questions) - answered
        marked_review = sum(1 for v in self.review_flags.values() if v)
        
        time_taken = 0
        if self.start_time:
            time_taken = int((datetime.now() - self.start_time).total_seconds())
        
        exam_stats = {
            "answered": answered,
            "unanswered": unanswered,
            "marked_review": marked_review,
            "total_questions": len(self.questions),
            "time_taken_seconds": time_taken,
            "time_allotted_seconds": self.exam_duration_minutes * 60,
            "violations_count": len(self.violations),
            "violations": self.violations[:10],  # Limit to 10
        }
        
        logger.info(f"Exam submitted with status: {status}, stats: {exam_stats}")
        self.exam_submitted.emit(status, exam_stats)
    
    def terminate(self, reason: str):
        """Forcefully terminate the exam."""
        logger.critical(f"Exam terminated: {reason}")
        self._submit_exam("TERMINATED")
