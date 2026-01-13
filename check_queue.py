import sqlite3
from pathlib import Path

db_path = Path.home() / ".student_exam_app" / "queue.db"

if not db_path.exists():
    print(f"[ERROR] Queue database not found at: {db_path}")
    exit(1)

print(f"[OK] Found queue database at: {db_path}")
print()

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Check if table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='upload_queue'")
if not cursor.fetchone():
    print("[ERROR] upload_queue table does not exist!")
    exit(1)

print("[OK] upload_queue table exists")
print()

# Get all items
cursor.execute("SELECT id, table_name, status, attempts, created_at, last_error FROM upload_queue ORDER BY created_at DESC LIMIT 20")
rows = cursor.fetchall()

if not rows:
    print("[WARNING] Queue is EMPTY - no items have been enqueued")
else:
    print(f"[INFO] Found {len(rows)} items in queue:\n")
    print(f"{'ID':<5} {'Table':<25} {'Status':<10} {'Attempts':<10} {'Created':<20} {'Error'}")
    print("-" * 120)
    for row in rows:
        error = row[5][:50] if row[5] else ""
        print(f"{row[0]:<5} {row[1]:<25} {row[2]:<10} {row[3]:<10} {row[4]:<20} {error}")

# Get counts by status
print("\n[INFO] Status Summary:")
cursor.execute("SELECT status, COUNT(*) FROM upload_queue GROUP BY status")
for status, count in cursor.fetchall():
    print(f"  {status}: {count}")

conn.close()
