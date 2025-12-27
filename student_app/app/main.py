"""
Student Exam Application - Main Entry Point

Production-ready Windows exam client with local AI proctoring.
"""

import sys
import os
import logging
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from student_app.app.config import get_config, get_config_manager
from student_app.app.security.integrity_check import verify_integrity
from student_app.app.security.anti_debug import check_security_environment
from student_app.app.utils.logger import setup_logging
from student_app.app.ui.main_window import MainWindow


def main():
    """Application entry point"""
    
    # Initialize configuration first
    config_manager = get_config_manager()
    config = config_manager.config
    
    # Setup logging
    setup_logging(config.log_file, config.debug_mode)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("Student Exam Application Starting")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)
    
    # Verify application integrity (tamper detection)
    if not config.debug_mode:
        integrity_ok, integrity_msg = verify_integrity()
        if not integrity_ok:
            logger.critical(f"Integrity check failed: {integrity_msg}")
            # In production, exit here
            # sys.exit(1)
        else:
            logger.info("Integrity check passed")
    
    # Security environment check
    security_issues = check_security_environment()
    if security_issues:
        for issue in security_issues:
            logger.warning(f"Security issue detected: {issue}")
        # Log but continue - actual blocking happens in exam engine
    else:
        logger.info("Security environment check passed")
    
    # Load policy configuration
    policy_loaded = config_manager.load_policy()
    if policy_loaded:
        logger.info("Policy configuration loaded")
        if config_manager.config.policy_verified:
            logger.info("Policy signature verified")
    else:
        logger.info("Using default configuration")
    
    # Verify Supabase configuration
    if not config.supabase.url or not config.supabase.key:
        logger.error("Supabase configuration missing!")
        logger.error("Set SUPABASE_URL and SUPABASE_KEY environment variables")
        # Continue for now, will fail on auth
    
    # Create Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName("Student Exam Application")
    app.setOrganizationName("ExamProctor")
    
    # Note: High DPI scaling is automatic in Qt6/PySide6
    
    # Create and show main window
    window = MainWindow(config)
    window.show()
    
    logger.info("Application UI initialized")
    
    # Start event loop
    exit_code = app.exec()
    
    logger.info(f"Application exiting with code {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
