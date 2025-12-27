"""
Student Exam Application - Authentication Module

Handles student authentication via hall ticket and biometrics.
"""

import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict
from dataclasses import dataclass

from student_app.app.storage.supabase_client import SupabaseClient, get_supabase_client
from student_app.app.utils.logger import get_audit_logger

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """Authentication result."""
    success: bool
    student_id: Optional[str] = None
    user_id: Optional[str] = None
    exam_id: Optional[str] = None
    exam_name: Optional[str] = None
    exam_duration: Optional[int] = None
    student_name: Optional[str] = None
    hall_ticket: Optional[str] = None
    photo_url: Optional[str] = None  # Reference photo for face verification
    error: Optional[str] = None


class Authenticator:
    """
    Handles student authentication for exam access.
    
    Authentication flow:
    1. Verify hall ticket exists in database
    2. Optionally verify biometric hash
    3. Check for active exam assignment
    4. Verify exam timing
    5. Log authentication attempt
    """
    
    def __init__(self, client: Optional[SupabaseClient] = None):
        """
        Initialize authenticator.
        
        Args:
            client: Supabase client (uses global if None)
        """
        self.client = client or get_supabase_client()
        self.audit = get_audit_logger()
    
    def authenticate(
        self,
        hall_ticket: str,
        biometric_hash: Optional[str] = None
    ) -> AuthResult:
        """
        Authenticate a student by hall ticket.
        
        Args:
            hall_ticket: Student's hall ticket number
            biometric_hash: Optional biometric verification hash
            
        Returns:
            AuthResult with authentication status
        """
        try:
            # Step 1: Find student by hall ticket
            student = self.client.get_student_by_hall_ticket(hall_ticket)
            
            if not student:
                self._log_auth_attempt(hall_ticket, False, "Invalid hall ticket")
                return AuthResult(
                    success=False,
                    error="Invalid hall ticket number"
                )
            
            student_id = student["id"]
            user_data = student.get("users", {})
            
            # Step 2: Verify biometric if provided
            if biometric_hash:
                if not self._verify_biometric(student_id, biometric_hash):
                    self._log_auth_attempt(hall_ticket, False, "Biometric mismatch")
                    return AuthResult(
                        success=False,
                        error="Biometric verification failed"
                    )
            
            # Step 3: Get exam assignment
            assignment = self.client.get_exam_assignment(student_id)
            
            if not assignment:
                self._log_auth_attempt(hall_ticket, False, "No exam assigned")
                return AuthResult(
                    success=False,
                    error="No exam assigned to this student"
                )
            
            exam_data = assignment.get("exams", {})
            
            # Step 4: Verify exam timing
            timing_check = self._verify_exam_timing(exam_data)
            if not timing_check[0]:
                self._log_auth_attempt(hall_ticket, False, timing_check[1])
                return AuthResult(
                    success=False,
                    error=timing_check[1]
                )
            
            # Step 5: Log successful authentication
            self._log_auth_attempt(hall_ticket, True)
            
            return AuthResult(
                success=True,
                student_id=student_id,
                user_id=student.get("user_id"),
                exam_id=assignment["exam_id"],
                exam_name=exam_data.get("name", "Exam"),
                exam_duration=exam_data.get("duration_minutes", 60),
                student_name=user_data.get("name", "Student"),
                hall_ticket=hall_ticket,
                photo_url=student.get("photo_url")  # For face verification
            )
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return AuthResult(
                success=False,
                error=f"Authentication failed: {str(e)}"
            )
    
    def _verify_biometric(self, student_id: str, biometric_hash: str) -> bool:
        """Verify biometric hash matches stored value."""
        return self.client.verify_biometric(student_id, biometric_hash)
    
    def _verify_exam_timing(self, exam_data: dict) -> Tuple[bool, str]:
        """
        Verify exam is within allowed time window.
        
        Returns:
            Tuple of (is_valid, message)
        """
        now = datetime.now(timezone.utc)
        
        start_time_str = exam_data.get("start_time")
        end_time_str = exam_data.get("end_time")
        
        if start_time_str:
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            if now < start_time:
                return False, f"Exam has not started yet. Start time: {start_time}"
        
        if end_time_str:
            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            if now > end_time:
                return False, "Exam period has ended"
        
        return True, "OK"
    
    def _log_auth_attempt(
        self,
        hall_ticket: str,
        success: bool,
        reason: Optional[str] = None
    ):
        """Log authentication attempt to audit trail."""
        self.audit.log_event(
            action="AUTH_ATTEMPT",
            entity="student",
            evidence={
                "hall_ticket": hall_ticket,
                "success": success,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Also log to Supabase if successful auth
        try:
            self.client.create_audit_log(
                action="LOGIN_ATTEMPT",
                entity="student",
                evidence={
                    "hall_ticket": hall_ticket,
                    "success": success,
                    "reason": reason
                }
            )
        except Exception as e:
            logger.warning(f"Failed to log to Supabase: {e}")
    
    def verify_clock_drift(self) -> Tuple[float, bool]:
        """
        Verify local system clock against server time.
        
        Returns:
            Tuple of (drift_seconds, is_acceptable)
        """
        try:
            import httpx
            
            # Get server time from Supabase
            url = f"{self.client.base_url}/rest/v1/"
            response = httpx.head(url, headers=self.client._default_headers())
            
            server_time_str = response.headers.get("Date")
            if server_time_str:
                from email.utils import parsedate_to_datetime
                server_time = parsedate_to_datetime(server_time_str)
                local_time = datetime.now(timezone.utc)
                
                drift = (local_time - server_time).total_seconds()
                
                # Log drift
                self.audit.log_event(
                    action="CLOCK_DRIFT_CHECK",
                    entity="system",
                    evidence={"drift_seconds": drift}
                )
                
                # Accept up to 5 minutes drift
                is_acceptable = abs(drift) < 300
                
                return drift, is_acceptable
            
            return 0.0, True
            
        except Exception as e:
            logger.warning(f"Clock drift check failed: {e}")
            return 0.0, True  # Assume OK if check fails


def get_system_fingerprint() -> str:
    """Generate a unique system fingerprint for this machine."""
    import platform
    
    components = [
        platform.node(),
        platform.machine(),
        platform.processor(),
        platform.system(),
    ]
    
    fingerprint_str = "-".join(components)
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:32]


# Global authenticator
_authenticator: Optional[Authenticator] = None


def get_authenticator() -> Authenticator:
    """Get global authenticator instance."""
    global _authenticator
    if _authenticator is None:
        _authenticator = Authenticator()
    return _authenticator
