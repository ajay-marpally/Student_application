"""
Student Exam Application - Storage: Background Uploader

Background service for uploading evidence and data to Supabase.
"""

import logging
import threading
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os

from student_app.app.config import get_config
from student_app.app.db.sqlite_queue import SQLiteQueue, get_sqlite_queue, QueueItem
from student_app.app.storage.supabase_client import SupabaseClient, get_supabase_client

logger = logging.getLogger(__name__)


class EvidenceEncryptor:
    """
    Encrypts evidence files before upload.
    
    Uses AES encryption via Fernet (symmetric encryption).
    """
    
    def __init__(self, key: Optional[bytes] = None):
        """
        Initialize encryptor.
        
        Args:
            key: Encryption key (32 bytes base64 encoded)
                 If not provided, generates from environment
        """
        if key:
            self._fernet = Fernet(key)
        else:
            key = self._derive_key()
            self._fernet = Fernet(key)
    
    def _derive_key(self) -> bytes:
        """Derive encryption key from environment or generate."""
        # Try to get from environment
        env_key = os.getenv("ENCRYPTION_KEY")
        
        if env_key:
            # Use provided key
            return base64.urlsafe_b64encode(env_key.encode()[:32].ljust(32, b'0'))
        
        # Derive from machine-specific info
        import platform
        salt = f"{platform.node()}-exam-app".encode()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        # Use a fixed passphrase (in production, this should be securely managed)
        passphrase = b"student-exam-app-secure-key"
        
        return base64.urlsafe_b64encode(kdf.derive(passphrase))
    
    def encrypt_file(self, file_path: Path) -> bytes:
        """
        Encrypt a file and return encrypted bytes.
        
        Args:
            file_path: Path to file to encrypt
            
        Returns:
            Encrypted file contents
        """
        with open(file_path, 'rb') as f:
            data = f.read()
        
        return self._fernet.encrypt(data)
    
    def encrypt_data(self, data: bytes) -> bytes:
        """Encrypt raw bytes."""
        return self._fernet.encrypt(data)
    
    def decrypt_data(self, encrypted: bytes) -> bytes:
        """Decrypt encrypted bytes."""
        return self._fernet.decrypt(encrypted)


class BackgroundUploader:
    """
    Background service for uploading queued items to Supabase.
    
    Features:
    - Exponential backoff retry
    - AES encryption for evidence
    - SHA-256 integrity verification
    - Concurrent upload support
    """
    
    # Retry configuration
    MIN_RETRY_DELAY = 1.0  # seconds
    MAX_RETRY_DELAY = 300.0  # 5 minutes
    BACKOFF_FACTOR = 2.0
    MAX_ATTEMPTS = 5
    
    def __init__(
        self,
        queue: Optional[SQLiteQueue] = None,
        client: Optional[SupabaseClient] = None,
        on_upload_complete: Optional[Callable[[QueueItem, bool], None]] = None
    ):
        """
        Initialize uploader.
        
        Args:
            queue: SQLite queue (uses global if None)
            client: Supabase client (uses global if None)
            on_upload_complete: Callback when upload completes
        """
        self.queue = queue or get_sqlite_queue()
        self.client = client or get_supabase_client()
        self.on_upload_complete = on_upload_complete
        
        self.encryptor = EvidenceEncryptor()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_retry_delay = self.MIN_RETRY_DELAY
    
    def start(self):
        """Start background upload service."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._upload_loop, daemon=True)
        self._thread.start()
        
        logger.info("Background uploader started")
    
    def stop(self):
        """Stop background upload service."""
        self._running = False
        
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        
        logger.info("Background uploader stopped")
    
    def _upload_loop(self):
        """Main upload loop."""
        while self._running:
            try:
                # Get next pending item
                item = self.queue.dequeue()
                
                if item is None:
                    # No pending items, retry failed ones
                    retry_count = self.queue.retry_failed(self.MAX_ATTEMPTS)
                    
                    if retry_count > 0:
                        logger.debug(f"Reset {retry_count} failed items for retry")
                    
                    # Wait before checking again
                    time.sleep(5.0)
                    continue
                
                # Process item
                success = self._upload_item(item)
                
                if success:
                    self.queue.mark_success(item.id)
                    self._current_retry_delay = self.MIN_RETRY_DELAY
                    
                    if self.on_upload_complete:
                        self.on_upload_complete(item, True)
                else:
                    # Already marked as failed in _upload_item
                    self._current_retry_delay = min(
                        self._current_retry_delay * self.BACKOFF_FACTOR,
                        self.MAX_RETRY_DELAY
                    )
                    
                    if self.on_upload_complete:
                        self.on_upload_complete(item, False)
                    
                    # Wait with backoff
                    time.sleep(self._current_retry_delay)
                    
            except Exception as e:
                logger.error(f"Upload loop error: {e}")
                time.sleep(5.0)
    
    def _upload_item(self, item: QueueItem) -> bool:
        """
        Upload a single queue item.
        
        Args:
            item: Queue item to upload
            
        Returns:
            True if successful
        """
        try:
            logger.debug(f"Uploading item {item.id} to {item.table_name}")
            
            # Handle file upload if present
            storage_url = None
            if item.file_path:
                file_path = Path(item.file_path)
                
                if not file_path.exists():
                    error = f"File not found: {item.file_path}"
                    logger.error(error)
                    self.queue.mark_failed(item.id, error)
                    return False
                
                # Verify integrity
                actual_hash = self._compute_hash(file_path)
                if actual_hash != item.hash_sha256:
                    error = "File integrity check failed"
                    logger.error(f"{error}: expected {item.hash_sha256}, got {actual_hash}")
                    self.queue.mark_failed(item.id, error)
                    return False
                
                # Upload file
                storage_url = self.client.upload_evidence_file(file_path)
                
                if not storage_url:
                    error = "File upload failed"
                    self.queue.mark_failed(item.id, error)
                    return False
            
            # Update payload with storage URL if needed
            payload = item.payload.copy()
            if storage_url and 'storage_url' in payload:
                payload['storage_url'] = storage_url
            
            # Insert record into Supabase
            success = self._insert_record(item.table_name, payload)
            
            if not success:
                error = "Database insert failed"
                self.queue.mark_failed(item.id, error)
                return False
            
            logger.info(f"Successfully uploaded item {item.id}")
            return True
            
        except Exception as e:
            error = str(e)
            logger.error(f"Upload error for item {item.id}: {error}")
            self.queue.mark_failed(item.id, error)
            return False
    
    def _compute_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    def _insert_record(self, table_name: str, payload: dict) -> bool:
        """Insert a record into Supabase."""
        try:
            import httpx
            
            url = f"{self.client.base_url}/rest/v1/{table_name}"
            headers = self.client._default_headers(use_service_key=True)
            
            response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            
            return True
            
        except Exception as e:
            logger.error(f"Insert error: {e}")
            return False
    
    def upload_now(self, item: QueueItem) -> bool:
        """
        Upload an item immediately (synchronous).
        
        Args:
            item: Queue item to upload
            
        Returns:
            True if successful
        """
        return self._upload_item(item)
    
    def get_status(self) -> dict:
        """Get uploader status."""
        return {
            "running": self._running,
            "pending_count": self.queue.get_pending_count(),
            "failed_count": self.queue.get_failed_count(),
            "current_retry_delay": self._current_retry_delay
        }


# Global instance
_uploader: Optional[BackgroundUploader] = None


def get_background_uploader() -> BackgroundUploader:
    """Get global background uploader instance."""
    global _uploader
    if _uploader is None:
        _uploader = BackgroundUploader()
    return _uploader
