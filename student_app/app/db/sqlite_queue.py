"""
Student Exam Application - DB: SQLite Queue

Local SQLite queue for offline operation and retry logic.
"""

import sqlite3
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from student_app.app.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    """Represents an item in the upload queue."""
    id: int
    table_name: str
    payload: Dict[str, Any]
    file_path: Optional[str]
    hash_sha256: str
    status: str  # pending, uploading, failed, success
    attempts: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class SQLiteQueue:
    """
    Local SQLite queue for offline operation.
    
    Stores pending uploads and provides retry logic.
    """
    
    CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS upload_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            payload TEXT NOT NULL,
            file_path TEXT,
            hash_sha256 TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """
    
    CREATE_INDEX = """
        CREATE INDEX IF NOT EXISTS idx_queue_status ON upload_queue(status)
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize SQLite queue.
        
        Args:
            db_path: Path to SQLite database file
        """
        config = get_config()
        self.db_path = db_path or config.queue_db
        
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_connection() as conn:
            conn.execute(self.CREATE_TABLE)
            conn.execute(self.CREATE_INDEX)
            conn.commit()
        
        logger.debug(f"SQLite queue initialized: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def enqueue(
        self,
        table_name: str,
        payload: Dict[str, Any],
        hash_sha256: str,
        file_path: Optional[str] = None
    ) -> int:
        """
        Add an item to the upload queue.
        
        Args:
            table_name: Target Supabase table
            payload: Data to upload (will be JSON serialized)
            hash_sha256: Integrity hash
            file_path: Optional path to evidence file
            
        Returns:
            Queue item ID
        """
        now = datetime.now().isoformat()
        
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO upload_queue 
                    (table_name, payload, file_path, hash_sha256, status, 
                     attempts, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)
                    """,
                    (
                        table_name,
                        json.dumps(payload),
                        file_path,
                        hash_sha256,
                        now,
                        now
                    )
                )
                conn.commit()
                item_id = cursor.lastrowid
        
        logger.debug(f"Enqueued item {item_id} for table {table_name}")
        return item_id
    
    def dequeue(self, status: str = 'pending') -> Optional[QueueItem]:
        """
        Get the next item from the queue.
        
        Args:
            status: Status to filter by
            
        Returns:
            QueueItem or None if queue is empty
        """
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM upload_queue 
                    WHERE status = ?
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (status,)
                ).fetchone()
                
                if not row:
                    return None
                
                # Mark as uploading
                conn.execute(
                    """
                    UPDATE upload_queue 
                    SET status = 'uploading', updated_at = ?
                    WHERE id = ?
                    """,
                    (datetime.now().isoformat(), row['id'])
                )
                conn.commit()
                
                return QueueItem(
                    id=row['id'],
                    table_name=row['table_name'],
                    payload=json.loads(row['payload']),
                    file_path=row['file_path'],
                    hash_sha256=row['hash_sha256'],
                    status='uploading',
                    attempts=row['attempts'],
                    last_error=row['last_error'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    updated_at=datetime.now()
                )
    
    def mark_success(self, item_id: int):
        """Mark an item as successfully uploaded."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE upload_queue 
                    SET status = 'success', updated_at = ?
                    WHERE id = ?
                    """,
                    (datetime.now().isoformat(), item_id)
                )
                conn.commit()
        
        logger.debug(f"Queue item {item_id} marked success")
    
    def mark_failed(self, item_id: int, error: str):
        """Mark an item as failed with error."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE upload_queue 
                    SET status = 'failed', 
                        last_error = ?,
                        attempts = attempts + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (error, datetime.now().isoformat(), item_id)
                )
                conn.commit()
        
        logger.debug(f"Queue item {item_id} marked failed: {error}")
    
    def retry_failed(self, max_attempts: int = 5) -> int:
        """
        Reset failed items for retry.
        
        Args:
            max_attempts: Maximum retry attempts
            
        Returns:
            Number of items reset
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    UPDATE upload_queue 
                    SET status = 'pending', updated_at = ?
                    WHERE status = 'failed' AND attempts < ?
                    """,
                    (datetime.now().isoformat(), max_attempts)
                )
                conn.commit()
                return cursor.rowcount
    
    def get_pending_count(self) -> int:
        """Get count of pending items."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM upload_queue WHERE status = 'pending'"
            ).fetchone()
            return row['count'] if row else 0
    
    def get_failed_count(self) -> int:
        """Get count of failed items."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM upload_queue WHERE status = 'failed'"
            ).fetchone()
            return row['count'] if row else 0
    
    def cleanup_old(self, days: int = 7):
        """
        Remove old successful uploads.
        
        Args:
            days: Remove items older than this many days
        """
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM upload_queue 
                    WHERE status = 'success' AND created_at < ?
                    """,
                    (cutoff,)
                )
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Cleaned up {cursor.rowcount} old queue items")
    
    def get_all_pending(self) -> List[QueueItem]:
        """Get all pending items."""
        items = []
        
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM upload_queue WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
            
            for row in rows:
                items.append(QueueItem(
                    id=row['id'],
                    table_name=row['table_name'],
                    payload=json.loads(row['payload']),
                    file_path=row['file_path'],
                    hash_sha256=row['hash_sha256'],
                    status=row['status'],
                    attempts=row['attempts'],
                    last_error=row['last_error'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    updated_at=datetime.fromisoformat(row['updated_at'])
                ))
        
        return items


# Global instance
_queue: Optional[SQLiteQueue] = None


def get_sqlite_queue() -> SQLiteQueue:
    """Get global SQLite queue instance."""
    global _queue
    if _queue is None:
        _queue = SQLiteQueue()
    return _queue
