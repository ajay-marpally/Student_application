
import time
import sys
from datetime import datetime
from collections import deque

class VerificationMocks:
    def __init__(self):
        self.frame_count = 0
        self.start_time = time.time()
        self.logs = []
        
        # Counters
        self.face_detect_calls = 0
        self.head_pose_calls = 0
        self.object_detect_calls = 0
        self.verification_calls = 0
        self.classifier_events = 0

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = f"[{ts}] {msg}"
        print(entry)
        self.logs.append(entry)

    def run_simulation(self, duration_seconds=5):
        self.log(f"--- STARTING PIPELINE SIMULATION ({duration_seconds}s) ---")
        
        # Simulate Camera Frame Loop (30 FPS)
        target_fps = 30
        frame_interval = 1.0 / target_fps
        max_duration = duration_seconds
        
        while (time.time() - self.start_time) < max_duration:
            loop_start = time.time()
            self.frame_count += 1
            
            # --- LOGIC FROM exam_screen.py ---
            
            # 1. Skip logic (Process every 3rd frame)
            if self.frame_count % 3 != 0:
                time.sleep(frame_interval)
                continue
            
            # 2. Movement/Pose (Runs every processed frame)
            self.head_pose_calls += 1
            
            # 3. Object Detection (Runs every 15th frame)
            if self.frame_count % 15 == 0:
                self.object_detect_calls += 1
                self.log(f"[Frame {self.frame_count}] 🔍 Object Detection Running")

            # 4. Face Presence (Runs every processed frame)
            self.face_detect_calls += 1

            # 5. Face Verification (Runs every 30th frame)
            if self.frame_count % 30 == 0:
                self.verification_calls += 1
                self.log(f"[Frame {self.frame_count}] 👤 Face Verification Running")

            # 6. Status Log (Every 15th frame)
            if self.frame_count % 15 == 0:
                self.log(f"[Frame {self.frame_count}] 📊 STATUS LOG Triggered")
                
            # --- END LOGIC ---
            
            elapsed = time.time() - loop_start
            sleep_time = max(0, frame_interval - elapsed)
            time.sleep(sleep_time)
            
        self.log("--- SIMULATION COMPLETE ---")
        self.print_stats()

    def print_stats(self):
        duration = time.time() - self.start_time
        processed_frames = self.frame_count // 3
        
        print("\n" + "="*40)
        print("PIPELINE EXECUTION STATS (Simulated)")
        print("="*40)
        print(f"Total Time:       {duration:.2f}s")
        print(f"Total Frames:     {self.frame_count} (~{self.frame_count/duration:.1f} FPS input)")
        print(f"Processed Frames: {processed_frames} (~{processed_frames/duration:.1f} FPS processed)")
        print("-" * 40)
        print(f"Head Pose Calls:      {self.head_pose_calls:<4} (Expected: ~{processed_frames})")
        print(f"Face Detect Calls:    {self.face_detect_calls:<4} (Expected: ~{processed_frames})")
        print(f"Object Detect Calls:  {self.object_detect_calls:<4} (Expected: ~{self.frame_count//15})")
        print(f"Face Verify Calls:    {self.verification_calls:<4} (Expected: ~{self.frame_count//30})")
        print("="*40)

if __name__ == "__main__":
    sim = VerificationMocks()
    sim.run_simulation(duration_seconds=3)
