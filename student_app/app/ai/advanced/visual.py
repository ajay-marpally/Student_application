import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO
import logging
import time
from collections import deque
from student_app.app.config import get_config

logger = logging.getLogger(__name__)

class AdvancedVisualDetector:
    """
    Advanced multimodal visual detector integrating YOLOv8 and MediaPipe.
    Ported from ai-proctoring-system.
    """
    def __init__(self):
        config = get_config()
        self.face_detection = mp.solutions.face_detection.FaceDetection(
            min_detection_confidence=0.5
        )
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True
        )
        self.pose = mp.solutions.pose.Pose(
            min_detection_confidence=0.5
        )
        
        # YOLOv8 for object detection
        yolo_path = "yolov8s.pt" # Assuming it will be in the root or data dir
        self.yolo = YOLO(yolo_path)
        
        # Buffers and thresholds
        self.face_count_buffer = deque(maxlen=15)
        self.movement_buffer = deque(maxlen=3)
        self.last_pose_landmarks = None
        self.movement_threshold = 0.15
        
        # Duration Counters (10 FPS)
        self.gaze_consecutive_count = 0
        self.gaze_target_frames = 5 * 10 # 5 seconds
        self.head_turn_consecutive_count = 0 
        self.head_turn_target_frames = 2 * 10 # 2 seconds
        
        # 3D Model Points for Head Pose Estimation
        self.model_points = np.array([
            (0.0, 0.0, 0.0),             # Nose tip
            (0.0, -330.0, -65.0),        # Chin
            (-225.0, 170.0, -135.0),     # Left eye left corner
            (225.0, 170.0, -135.0),      # Right eye right corner
            (-150.0, -150.0, -125.0),    # Left Mouth corner
            (150.0, -150.0, -125.0)      # Right Mouth corner
        ])
        
        self.last_face_present_ts = time.time()
        self.debug_frame_count = 0

    def get_head_pose(self, image_points, size):
        focal_length = size[1]
        center = (size[1] / 2, size[0] / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype="double")

        dist_coeffs = np.zeros((4, 1))
        success, rotation_vector, translation_vector = cv2.solvePnP(
            self.model_points, 
            image_points, 
            camera_matrix, 
            dist_coeffs, 
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return 0, 0, 0

        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        proj_matrix = np.hstack((rotation_matrix, translation_vector))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)

        pitch = euler_angles[0][0]
        yaw = euler_angles[1][0]
        roll = euler_angles[2][0]

        return pitch, yaw, roll

    def process_frame(self, frame):
        self.debug_frame_count += 1
        now = time.time()
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # 1. Face Detection
        face_results = self.face_detection.process(rgb_frame)
        raw_num_faces = len(face_results.detections) if face_results.detections else 0
        self.face_count_buffer.append(raw_num_faces)
        
        multiple_faces = False
        if len(self.face_count_buffer) >= 5:
            count_more_than_one = sum(1 for c in self.face_count_buffer if c > 1)
            multiple_faces = count_more_than_one > (len(self.face_count_buffer) * 0.4)
            
        face_present = raw_num_faces >= 1
        if face_present:
            self.last_face_present_ts = now

        # 2. Gaze and Head Pose
        mesh_results = self.face_mesh.process(rgb_frame)
        gaze_deviation_instant = False
        head_orientation_instant = False
        yaw, pitch, roll = 0, 0, 0
        avg_gaze_ratio_x, avg_gaze_ratio_y = 0.5, 0.5

        if mesh_results.multi_face_landmarks:
            landmarks = mesh_results.multi_face_landmarks[0].landmark
            
            # Gaze Estimation
            left_iris, right_iris = landmarks[468], landmarks[473]
            le_o, le_i = landmarks[33], landmarks[133]
            re_o, re_i = landmarks[263], landmarks[362]
            le_t, le_b = landmarks[159], landmarks[145]
            re_t, re_b = landmarks[386], landmarks[374]

            lw = le_i.x - le_o.x + 1e-6
            rw = re_o.x - re_i.x + 1e-6
            lh = le_b.y - le_t.y + 1e-6
            rh = re_b.y - re_t.y + 1e-6

            grx = ((left_iris.x - le_o.x) / lw + (re_o.x - right_iris.x) / rw) / 2.0
            gry = ((left_iris.y - le_t.y) / lh + (right_iris.y - re_t.y) / rh) / 2.0
            avg_gaze_ratio_x, avg_gaze_ratio_y = grx, gry

            # Thresholds
            t_l, t_r, t_t, t_b = 0.40, 0.65, 0.35, 0.75
            iris_deviation = grx < t_l or grx > t_r or gry < t_t or gry > t_b

            # Head Pose
            h, w, _ = frame.shape
            face_3d = []
            for idx in [1, 152, 263, 33, 291, 61]:
                lm = landmarks[idx]
                face_3d.append([int(lm.x * w), int(lm.y * h)])
            pitch, yaw, roll = self.get_head_pose(np.array(face_3d, dtype="double"), (h, w))
            
            # Head orientation
            head_orientation_instant = abs(yaw) > 20 or abs(pitch) > 15
            
            instant_deviation = iris_deviation or head_orientation_instant
            if instant_deviation:
                self.gaze_consecutive_count += 1
            else:
                self.gaze_consecutive_count = max(0, self.gaze_consecutive_count - 3)
            
            if head_orientation_instant:
                self.head_turn_consecutive_count += 1
            else:
                self.head_turn_consecutive_count = max(0, self.head_turn_consecutive_count - 2)

        elif face_present:
            # Face detected but mesh lost usually means extreme angle
            self.gaze_consecutive_count += 1
            self.head_turn_consecutive_count += 1
        else:
            self.gaze_consecutive_count = 0
            self.head_turn_consecutive_count = 0

        # Check sustained triggers
        gaze_deviation = self.gaze_consecutive_count >= self.gaze_target_frames
        head_orientation_issue = self.head_turn_consecutive_count >= self.head_turn_target_frames

        # 3. Movement Detection
        pose_results = self.pose.process(rgb_frame)
        excessive_movement = False
        if pose_results.pose_landmarks:
            current = pose_results.pose_landmarks.landmark
            if self.last_pose_landmarks:
                diffs = []
                for i in [0, 11, 12, 23, 24]:
                    dx = current[i].x - self.last_pose_landmarks[i].x
                    dy = current[i].y - self.last_pose_landmarks[i].y
                    diffs.append((dx*dx + dy*dy)**0.5)
                avg_move = sum(diffs) / len(diffs)
                self.movement_buffer.append(avg_move > self.movement_threshold)
                if len(self.movement_buffer) >= 3:
                    excessive_movement = sum(self.movement_buffer) >= 2
            self.last_pose_landmarks = current

        # 4. Object Detection
        phone_detected = False
        book_detected = False
        suspicious_object = False
        try:
            results = self.yolo.predict(frame, conf=0.37, verbose=False)
            for r in results:
                for cls_id in r.boxes.cls:
                    label = r.names[int(cls_id)].lower()
                    if label in ['cell phone', 'mobile', 'phone', 'smartphone']:
                        phone_detected = True
                    elif label in ['book', 'notebook', 'paper', 'magazine']:
                        book_detected = True
                    elif label in ['laptop', 'tablet', 'monitor', 'tv', 'remote', 'mouse', 'keyboard']:
                        suspicious_object = True
                    elif label in ['earbuds', 'headset', 'headphones', 'earphone']:
                        suspicious_object = True
        except Exception:
            pass

        # Determine labels
        gaze_label = "GAZE"
        if mesh_results.multi_face_landmarks:
            if grx < t_l: gaze_label = "GAZE_LEFT"
            elif grx > t_r: gaze_label = "GAZE_RIGHT"
            elif gry < t_t: gaze_label = "GAZE_UP"
            elif gry > t_b: gaze_label = "GAZE_DOWN"
        
        head_label = "HEAD"
        if mesh_results.multi_face_landmarks or face_present:
            if yaw < -20: head_label = "HEAD_LEFT"
            elif yaw > 20: head_label = "HEAD_RIGHT"
            elif pitch < -15: head_label = "HEAD_UP"
            elif pitch > 15: head_label = "HEAD_DOWN"

        return {
            "face_present": face_present,
            "multiple_faces": multiple_faces,
            "candidate_absent": (now - self.last_face_present_ts) > 15, 
            "gaze_deviation": gaze_deviation,
            "head_orientation_issue": head_orientation_issue,
            "excessive_movement": excessive_movement,
            "phone_detected": phone_detected,
            "book_detected": book_detected,
            "suspicious_object": suspicious_object,
            "yaw": yaw,
            "pitch": pitch,
            "avg_gaze_ratio_x": avg_gaze_ratio_x,
            "avg_gaze_ratio_y": avg_gaze_ratio_y,
            "gaze_label": gaze_label,
            "head_label": head_label
        }
