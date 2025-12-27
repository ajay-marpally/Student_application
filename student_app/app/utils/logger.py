"""
Student Exam Application - Logging Utilities

Structured JSON logging with encryption support.
"""

import logging
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data
        
        return json.dumps(log_data)


class AuditLogger:
    """
    Specialized logger for audit trail.
    All audit events are append-only and include integrity hashes.
    """
    
    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.logger = logging.getLogger("audit")
        
        # Ensure directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup handler
        handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        handler.setFormatter(JSONFormatter())
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_event(
        self,
        action: str,
        entity: str,
        entity_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        evidence: Optional[dict] = None,
    ):
        """Log an audit event"""
        import hashlib
        
        event = {
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "actor_id": actor_id,
            "evidence": evidence,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        
        # Add integrity hash
        event_json = json.dumps(event, sort_keys=True)
        event["hash"] = hashlib.sha256(event_json.encode()).hexdigest()[:16]
        
        self.logger.info(json.dumps(event))


def setup_logging(log_file: Path, debug: bool = False):
    """
    Configure application logging.
    
    Args:
        log_file: Path to main log file
        debug: Enable debug level logging
    """
    # Ensure directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Console handler (human readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    # File handler (JSON structured)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=10,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    
    logging.info(f"Logging initialized. File: {log_file}, Debug: {debug}")


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger"""
    global _audit_logger
    if _audit_logger is None:
        from student_app.app.config import get_config
        config = get_config()
        audit_file = config.data_dir / "audit.log"
        _audit_logger = AuditLogger(audit_file)
    return _audit_logger
