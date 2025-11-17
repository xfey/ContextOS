#!/usr/bin/env python3
"""
Context OS: Main entrance

Demo - smart clipborad

An intelligent clipboard monitoring application that automatically detects
and provice suggestions.

Input:
- Clipboard (Event adapter)
"""

import sys
import os
import signal

from PyQt5.QtWidgets import QApplication
from core.orchestrator import Orchestrator
from utils.logger import get_logger

logger = get_logger('ContextOS')


def setup_signal_handlers(app, orchestrator):
    """
    Setup signal handlers for graceful shutdown.

    Args:
        app: QApplication instance
        orchestrator: Orchestrator instance
    """
    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully."""
        logger.info("\n" + "═" * 70)
        logger.info("Received interrupt signal, shutting down gracefully...")
        logger.info("═" * 70)

        # Stop orchestrator
        orchestrator.stop()
        # Quit application
        app.quit()

    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Also handle Ctrl+C on Unix-like systems
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)


def main():
    """Main entry point for Context OS demo"""
    try:
        # Create Qt application
        logger.info("Creating application")
        app = QApplication(sys.argv)
        app.setApplicationName("Context OS")

        # Enable Ctrl+C handling in Qt
        import signal
        signal.signal(signal.SIGINT, signal.SIG_DFL)

        # Create orchestrator
        orchestrator = Orchestrator()

        # Setup signal handlers
        setup_signal_handlers(app, orchestrator)

        # Start the system
        orchestrator.start()

        # Print system status
        status = orchestrator.get_status()

        # Run Qt event loop
        exit_code = app.exec_()

        # Cleanup
        orchestrator.stop()

        return exit_code

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        logger.error("Please check the logs for details")
        return 1


if __name__ == '__main__':
    sys.exit(main())
