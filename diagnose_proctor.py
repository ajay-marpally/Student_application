import sys
import time
import os
import traceback
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.getcwd())

print("="*60)
print("DIAGNOSIS STARTING")
print("="*60)

def step(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

try:
    # 1. Test Supabase Connectivity & Blocking
    step("1. Testing Supabase Connectivity...")
    try:
        from student_app.app.storage.supabase_client import get_supabase_client
        client = get_supabase_client()
        step("   Supabase client initialized.")
        
        # NOTE: We expect this to fail FK constraints, but we check for BLOCKING
        payload = {
            "attempt_id": "00000000-0000-0000-0000-000000000000",
            "student_id": "00000000-0000-0000-0000-000000000000",
            "exam_id": "00000000-0000-0000-0000-000000000000",
            "severity": "CLEAR",
            "event_type": "DIAGNOSIS",
            "description": "Diagnosis Test",
            "occurred_at": datetime.now().isoformat()
        }
        
        step("   Sending test log (checking for network freeze)...")
        start = time.time()
        result = client.log_ai_analysis(payload)
        elapsed = time.time() - start
        
        step(f"   Supabase call returned in {elapsed:.2f}s.")
        step(f"   Result (likely None due to FK): {result}")
        
        if elapsed > 10.0:
            step("   ⚠️ WARNING: Network call is very slow!")
            
    except Exception as e:
        step(f"   ❌ Supabase Error: {e}")

    # 2. Test Camera Blocking
    step("\n2. Testing Camera Blocking...")
    try:
        import cv2
        step("   Opening VideoCapture(0)...")
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            step("   ❌ FAIL: Camera 0 not accessible")
        else:
            step("   Camera 0 opened. Attempting read()...")
            start = time.time()
            ret, frame = cap.read()
            elapsed = time.time() - start
            
            step(f"   Camera read returned in {elapsed:.2f}s")
            
            if ret:
                step(f"   ✅ Success: Frame shape {frame.shape}")
            else:
                step("   ❌ FAIL: Camera read returned False (black/empty frame)")
            
            cap.release()
            
    except Exception as e:
        step(f"   ❌ Camera Error: {e}")

except Exception as e:
    step(f"CRITICAL DIAGNOSIS FAIL: {e}")
    traceback.print_exc()

print("="*60)
print("DIAGNOSIS COMPLETE")
print("="*60)
