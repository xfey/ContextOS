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
from PyQt5.QtCore import Qt
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

        # Force light mode (disable dark mode)
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Set light palette to override system dark mode
        from PyQt5.QtGui import QPalette, QColor
        light_palette = QPalette()
        light_palette.setColor(QPalette.Window, QColor(255, 255, 255))
        light_palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
        light_palette.setColor(QPalette.Base, QColor(255, 255, 255))
        light_palette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
        light_palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        light_palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
        light_palette.setColor(QPalette.Text, QColor(0, 0, 0))
        light_palette.setColor(QPalette.Button, QColor(240, 240, 240))
        light_palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))
        light_palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        light_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        light_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        light_palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        app.setPalette(light_palette)

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
