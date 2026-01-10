"""
Student Exam Application - Supabase Client

REST API client for Supabase database and storage operations.
"""

import logging
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path
import httpx

from student_app.app.config import get_config, SupabaseConfig

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Supabase REST API client for database and storage operations.
    
    Handles all communication with Supabase backend including:
    - Authentication and student lookup
    - Exam data fetching
    - Answer submission
    - Evidence upload
    - Malpractice event logging
    """
    
    # Read-only tables
    READ_TABLES = {
        "users", "students", "exams", "questions", 
        "exam_assignments", "exam_centres", "exam_labs", "cctv_cameras"
    }
    
    # Writable tables
    WRITE_TABLES = {
        "exam_attempts", "answers", "malpractice_events", 
        "evidence", "cctv_evidence", "audit_logs", "student_ai_analysis"
    }
    
    def __init__(self, config: Optional[SupabaseConfig] = None):
        if config is None:
            config = get_config().supabase
        
        self.config = config
        self.base_url = config.url.rstrip('/')
        self.api_key = config.key
        self.service_key = config.service_key or config.key
        
        # HTTP client with retry support
        self._client = httpx.Client(
            timeout=30.0,
            headers=self._default_headers(),
        )
        
        self._async_client: Optional[httpx.AsyncClient] = None
    
    def _default_headers(self, use_service_key: bool = False) -> Dict[str, str]:
        """Get default headers for API requests."""
        key = self.service_key if use_service_key else self.api_key
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
    
    def _rest_url(self, table: str) -> str:
        """Get PostgREST URL for a table."""
        return f"{self.base_url}/rest/v1/{table}"
    
    def _storage_url(self, bucket: str, path: str = "") -> str:
        """Get Storage URL for a bucket/path."""
        url = f"{self.base_url}/storage/v1/object/{bucket}"
        if path:
            url += f"/{path}"
        return url
    
    # ==================== READ OPERATIONS ====================
    
    def get_student_by_hall_ticket(self, hall_ticket: str) -> Optional[Dict]:
        """
        Fetch student record by hall ticket number.
        
        Args:
            hall_ticket: Student's hall ticket number
            
        Returns:
            Student record with user info, or None if not found
        """
        try:
            url = self._rest_url("students")
            params = {
                "hall_ticket": f"eq.{hall_ticket}",
                "select": "*,users(*),photo_url"
            }
            
            response = self._client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data:
                return data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error fetching student: {e}")
            return None
    
    def verify_biometric(self, student_id: str, biometric_hash: str) -> bool:
        """
        Verify student's biometric hash.
        
        Args:
            student_id: Student UUID
            biometric_hash: Hash to verify
            
        Returns:
            True if biometric matches
        """
        try:
            url = self._rest_url("students")
            params = {
                "id": f"eq.{student_id}",
                "select": "biometric_hash"
            }
            
            response = self._client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data and data[0].get("biometric_hash"):
                stored_hash = data[0]["biometric_hash"]
                return stored_hash == biometric_hash
            return False
            
        except Exception as e:
            logger.error(f"Error verifying biometric: {e}")
            return False
    
    def get_exam_assignment(self, student_id: str) -> Optional[Dict]:
        """
        Get exam assignment for a student.
        
        Args:
            student_id: Student UUID
            
        Returns:
            Exam assignment with exam details, or None
        """
        try:
            url = self._rest_url("exam_assignments")
            params = {
                "student_id": f"eq.{student_id}",
                "select": "*,exams(*)"
            }
            
            response = self._client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data:
                return data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error fetching exam assignment: {e}")
            return None
    
    def get_exam_questions(self, exam_id: str) -> List[Dict]:
        """
        Fetch all questions for an exam.
        
        Args:
            exam_id: Exam UUID
            
        Returns:
            List of question records
        """
        try:
            url = self._rest_url("questions")
            params = {
                "exam_id": f"eq.{exam_id}",
                "select": "id,question_text,options",
                "order": "created_at.asc"
            }
            
            response = self._client.get(url, params=params)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching questions: {e}")
            return []
    
    # ==================== WRITE OPERATIONS ====================
    
    def create_exam_attempt(
        self,
        student_id: str,
        exam_id: str,
        system_fingerprint: str
    ) -> Optional[Dict]:
        """
        Create a new exam attempt.
        
        Args:
            student_id: Student UUID
            exam_id: Exam UUID
            system_fingerprint: System identification hash
            
        Returns:
            Created attempt record, or None on failure
        """
        try:
            url = self._rest_url("exam_attempts")
            payload = {
                "student_id": student_id,
                "exam_id": exam_id,
                "system_fingerprint": system_fingerprint,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "status": "IN_PROGRESS",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            response = self._client.post(
                url, 
                json=payload,
                headers=self._default_headers(use_service_key=True)
            )
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Created exam attempt: {data[0]['id']}")
            return data[0]
            
        except Exception as e:
            logger.error(f"Error creating exam attempt: {e}")
            return None
    
    def update_exam_attempt(
        self,
        attempt_id: str,
        status: str,
        end_time: Optional[datetime] = None
    ) -> bool:
        """
        Update exam attempt status.
        
        Args:
            attempt_id: Attempt UUID
            status: New status (IN_PROGRESS, SUBMITTED, TERMINATED)
            end_time: Optional end time
            
        Returns:
            True if successful
        """
        try:
            url = self._rest_url("exam_attempts")
            params = {"id": f"eq.{attempt_id}"}
            
            payload = {"status": status}
            if end_time:
                payload["end_time"] = end_time.isoformat()
            
            response = self._client.patch(
                url,
                params=params,
                json=payload,
                headers=self._default_headers(use_service_key=True)
            )
            response.raise_for_status()
            
            logger.info(f"Updated attempt {attempt_id} to {status}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating exam attempt: {e}")
            return False
    
    def save_answer(
        self,
        attempt_id: str,
        question_id: str,
        selected_option: Optional[int],
        marked_for_review: bool = False
    ) -> bool:
        """
        Save or update an answer.
        
        Uses upsert to handle both new answers and updates.
        
        Args:
            attempt_id: Exam attempt UUID
            question_id: Question UUID
            selected_option: Selected option index (0-based), or None
            marked_for_review: Whether marked for review
            
        Returns:
            True if successful
        """
        try:
            url = self._rest_url("answers")
            
            payload = {
                "attempt_id": attempt_id,
                "question_id": question_id,
                "selected_option": selected_option,
                "marked_for_review": marked_for_review,
                "answered_at": datetime.now(timezone.utc).isoformat() if selected_option is not None else None,
            }
            
            # Use upsert with conflict resolution
            headers = self._default_headers(use_service_key=True)
            headers["Prefer"] = "resolution=merge-duplicates,return=representation"
            
            response = self._client.post(
                url,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            return True
            
        except Exception as e:
            logger.error(f"Error saving answer: {e}")
            return False
    
    def create_malpractice_event(
        self,
        attempt_id: str,
        event_type: str,
        severity: int,
        description: str,
        occurred_at: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Create a malpractice event record.
        
        Args:
            attempt_id: Exam attempt UUID
            event_type: Type of violation (e.g., "head_rotation", "face_absent")
            severity: Severity score (1-10)
            description: Human-readable description
            occurred_at: When the event occurred
            
        Returns:
            Created event ID, or None on failure
        """
        try:
            url = self._rest_url("malpractice_events")
            
            payload = {
                "attempt_id": attempt_id,
                "event_type": event_type,
                "severity": min(max(severity, 1), 10),  # Clamp to 1-10
                "source": "STUDENT_AI",
                "description": description,
                "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
            }
            
            response = self._client.post(
                url,
                json=payload,
                headers=self._default_headers(use_service_key=True)
            )
            response.raise_for_status()
            
            data = response.json()
            event_id = data[0]["id"]
            logger.info(f"Created malpractice event: {event_id} ({event_type})")
            return event_id
            
        except Exception as e:
            logger.error(f"Error creating malpractice event: {e}")
            return None
    
    def create_evidence(
        self,
        malpractice_id: str,
        evidence_type: str,
        storage_url: str,
        hash_sha256: str,
        captured_at: datetime
    ) -> Optional[str]:
        """
        Create an evidence record linked to a malpractice event.
        
        Args:
            malpractice_id: Malpractice event UUID
            evidence_type: Type (IMAGE, AUDIO, VIDEO, LOG)
            storage_url: Supabase Storage URL
            hash_sha256: SHA-256 hash of evidence file
            captured_at: When evidence was captured
            
        Returns:
            Created evidence ID, or None on failure
        """
        try:
            url = self._rest_url("evidence")
            
            payload = {
                "malpractice_id": malpractice_id,
                "evidence_type": evidence_type,
                "storage_url": storage_url,
                "hash_sha256": hash_sha256,
                "captured_at": captured_at.isoformat(),
            }
            
            response = self._client.post(
                url,
                json=payload,
                headers=self._default_headers(use_service_key=True)
            )
            response.raise_for_status()
            
            data = response.json()
            evidence_id = data[0]["id"]
            logger.info(f"Created evidence record: {evidence_id}")
            return evidence_id
            
        except Exception as e:
            logger.error(f"Error creating evidence: {e}")
            return None
    
    def create_audit_log(
        self,
        action: str,
        entity: str,
        entity_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        evidence: Optional[Dict] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Create an audit log entry.
        
        Args:
            action: Action performed
            entity: Entity type affected
            entity_id: Entity UUID
            actor_id: User performing action
            evidence: Additional evidence data (JSONB)
            ip_address: Client IP address
            
        Returns:
            True if successful
        """
        try:
            url = self._rest_url("audit_logs")
            
            payload = {
                "action": action,
                "entity": entity,
                "entity_id": entity_id,
                "actor_id": actor_id,
                "ip_address": ip_address,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            response = self._client.post(
                url,
                json=payload,
                headers=self._default_headers(use_service_key=True)
            )
            response.raise_for_status()
            return True
            
        except Exception as e:
            msg = f"Error creating audit log: {e}"
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                msg += f" | Response: {e.response.text}"
            logger.error(msg)
            return False
    
    def log_ai_analysis(self, payload: Dict[str, Any]) -> Optional[str]:
        """
        Log AI analysis telemetry or incident to the staging table.
        
        Args:
            payload: Row data matching student_ai_analysis schema
            
        Returns:
            Created log ID, or None on failure
        """
        try:
            url = self._rest_url("student_ai_analysis")
            
            response = self._client.post(
                url,
                json=payload,
                headers=self._default_headers(use_service_key=True)
            )
            response.raise_for_status()
            
            data = response.json()
            log_id = data[0]["id"]
            logger.debug(f"Logged AI analysis: {log_id} ({payload.get('event_type')})")
            return log_id
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Error logging AI analysis: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error logging AI analysis: {e}")
            return None

    def update_ai_analysis(self, log_id: str, payload: Dict[str, Any]) -> bool:
        """Update existing AI analysis record."""
        try:
            url = self._rest_url("student_ai_analysis")
            params = {"id": f"eq.{log_id}"}
            response = self._client.patch(
                url,
                params=params,
                json=payload,
                headers=self._default_headers(use_service_key=True)
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Error updating AI analysis: {e}")
            return False

    # ==================== STORAGE OPERATIONS ====================
    
    def upload_evidence_file(
        self,
        file_path: Path,
        bucket: Optional[str] = None
    ) -> Optional[str]:
        """
        Upload an evidence file to Supabase Storage.
        
        Args:
            file_path: Local path to file
            bucket: Storage bucket name (defaults to config)
            
        Returns:
            Public URL of uploaded file, or None on failure
        """
        try:
            bucket = bucket or self.config.storage_bucket
            # Generate unique storage path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            storage_path = f"{timestamp}_{file_path.name}"
            
            # Read file
            with open(file_path, "rb") as f:
                file_data = f.read()
            
            # Determine content type
            suffix = file_path.suffix.lower()
            content_types = {
                ".mp4": "video/mp4",
                ".webm": "video/webm",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
            }
            content_type = content_types.get(suffix, "application/octet-stream")
            
            # Upload
            url = self._storage_url(bucket, storage_path)
            headers = {
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": content_type,
            }
            
            response = self._client.post(url, content=file_data, headers=headers)
            response.raise_for_status()
            
            # Return public URL
            public_url = f"{self.base_url}/storage/v1/object/public/{bucket}/{storage_path}"
            logger.info(f"Uploaded evidence: {public_url}")
            return public_url
            
        except Exception as e:
            logger.error(f"Error uploading evidence: {e}")
            return None
    
    def close(self):
        """Close HTTP client connections."""
        self._client.close()
        if self._async_client:
            # Note: Should be called from async context
            pass


# Global client instance
_client: Optional[SupabaseClient] = None


def get_supabase_client() -> SupabaseClient:
    """Get global Supabase client instance."""
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client
