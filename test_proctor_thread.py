"""
Test script to verify ProctorWorker thread execution
"""
import sys
import time
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("Testing ProctorWorker Thread")
print("=" * 60)

# Test imports
print("\n1. Testing imports...")
try:
    from student_app.app.ai.head_pose import get_head_pose_estimator
    from student_app.app.ai.gaze import get_gaze_tracker
    from student_app.app.ai.object_detector import get_object_detector
    from student_app.app.ai.audio_monitor import get_audio_monitor
    from student_app.app.ai.event_classifier import get_event_classifier
    from student_app.app.ai.analysis_coordinator import AnalysisCoordinator
    print("✅ All AI imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test AI component initialization
print("\n2. Testing AI component initialization...")
try:
    hp = get_head_pose_estimator()
    print(f"   HeadPose enabled: {hp.enabled}")
    
    gz = get_gaze_tracker()
    print(f"   Gaze enabled: {gz.enabled}")
    
    od = get_object_detector()
    print(f"   ObjectDetector enabled: {od.enabled}")
    
    am = get_audio_monitor()
    print(f"   AudioMonitor has VAD: {am.vad_model is not None}")
    
    ec = get_event_classifier()
    print(f"   EventClassifier initialized: {ec is not None}")
    
    print("✅ All AI components initialized")
except Exception as e:
    print(f"❌ Initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test camera access
print("\n3. Testing camera access...")
try:
    import cv2
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print(f"✅ Camera working: Frame shape = {frame.shape}")
        else:
            print("❌ Camera opened but can't read frames")
    else:
        print("❌ Camera failed to open")
    cap.release()
except Exception as e:
    print(f"❌ Camera test failed: {e}")

# Test AnalysisCoordinator
print("\n4. Testing AnalysisCoordinator...")
try:
    import uuid
    test_attempt_id = str(uuid.uuid4())
    test_student_data = {
        "student_id": str(uuid.uuid4()),
        "exam_id": str(uuid.uuid4()),
        "lab_id": str(uuid.uuid4()),
        "name": "Test Student",
        "hall_ticket": "TEST123"
    }
    
    coordinator = AnalysisCoordinator(test_attempt_id, test_student_data)
    print(f"✅ AnalysisCoordinator created")
    print(f"   Attempt ID: {coordinator.attempt_id}")
    print(f"   Risk Score: {coordinator.risk_score}")
    
    # Test processing empty events
    coordinator.process_events([], {"gaze": {"confidence": 0.8}})
    print(f"✅ Event processing works")
    
except Exception as e:
    print(f"❌ AnalysisCoordinator test failed: {e}")
    import traceback
    traceback.print_exc()

# Test Supabase connection
print("\n5. Testing Supabase connection...")
try:
    from student_app.app.storage.supabase_client import get_supabase_client
    from student_app.app.config import get_config
    
    config = get_config()
    print(f"   Supabase URL: {config.supabase.url[:40]}...")
    print(f"   Supabase Key configured: {bool(config.supabase.key)}")
    print(f"   Service Key configured: {bool(config.supabase.service_key)}")
    
    client = get_supabase_client()
    print(f"✅ Supabase client created")
    
except Exception as e:
    print(f"❌ Supabase test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)
print("\nIf all tests passed, the ProctorWorker should work.")
print("If you're still not seeing output during exams, the issue is likely:")
print("  1. ProctorWorker thread not starting (_running flag not set)")
print("  2. Camera permission denied")
print("  3. Output being redirected/suppressed")
print("  4. Thread crashing silently in try/except")
