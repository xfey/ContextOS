"""
Inbox for Context OS.

Main UI window providing session management with dual-pane interface.
"""

from typing import Dict, Any, Optional, List
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QStackedWidget, QLabel, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QCloseEvent

from models.session import Session
from interfaces.utils import SessionListWidget
from interfaces.renderer import Renderer
from interfaces.notification import NotificationManager
from interfaces.settings_dialog import SettingsDialog
from interfaces.macos_tray import MacOSTrayIcon
from utils.logger import get_logger

logger = get_logger('Inbox')


class Inbox(QMainWindow):
    """
    Inbox is the main UI window for Context OS.

    Features:
    - Dual-pane interface (session list + detail view)
    - Session queue management
    - Integration with Handler for session processing
    - Statistics tracking
    """

    # Signals for thread-safe operations
    session_added_signal = pyqtSignal(Session)
    session_updated_signal = pyqtSignal(str, dict)

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Inbox.

        Args:
            config: Inbox configuration from system.yaml
        """
        super().__init__()

        # Configuration
        self.config = config
        self.max_display_sessions = config.get('max_display_sessions', 20)
        self.auto_archive_completed = config.get('auto_archive_completed', True)
        self.archive_delay = config.get('archive_delay', 60)

        # State
        self.sessions: Dict[str, Session] = {}
        self.handler = None
        self.renderer = Renderer()
        self.current_session_id = None  # Fix for Issue 1: Track currently displayed session
        self.tool_manager = None  # Will be set via set_tool_manager()
        self.pipeline = None  # Will be set via set_pipeline()
        self.orchestrator = None  # Will be set via set_orchestrator()

        # UI components (will be created in initialize())
        self.session_list = None
        self.detail_view = None
        self.empty_label = None
        self.tray_icon = None  # Native macOS menu bar icon
        self.notification_manager = None  # Notification manager for system notifications

        logger.info("Inbox created (not yet initialized)")

    def initialize(self):
        """
        Initialize the Inbox UI.

        Must be called from the main Qt thread.
        """
        logger.info("Initializing Inbox UI...")

        # Setup window
        self.setWindowTitle("ContextOS")
        self.resize(1000, 700)

        # Create menu bar
        self._create_menu_bar()

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create main layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        main_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins

        # Create splitter for dual-pane layout (no title bar)
        splitter = QSplitter(Qt.Horizontal)
        # Make splitter background white to blend with the interface
        splitter.setStyleSheet("""
            QSplitter {
                background-color: white;
            }
            QSplitter::handle {
                background-color: white;
            }
        """)

        # Left pane: Session list with footer
        left_pane_widget = QWidget()
        left_pane_layout = QVBoxLayout()
        left_pane_layout.setContentsMargins(0, 0, 0, 0)
        left_pane_layout.setSpacing(0)
        left_pane_widget.setLayout(left_pane_layout)

        # Session list
        self.session_list = SessionListWidget()
        self.session_list.session_selected.connect(self._on_session_selected)
        # Set light gray background for left panel
        self.session_list.setStyleSheet("""
            QListWidget {
                background-color: #f5f5f5;
                border: none;
            }
        """)
        left_pane_layout.addWidget(self.session_list)

        # Footer with logo and version
        footer = self._create_footer()
        left_pane_layout.addWidget(footer)

        splitter.addWidget(left_pane_widget)

        # Right pane: Detail view (stacked widget for different views)
        self.detail_view = QStackedWidget()
        # Set white background for right panel
        self.detail_view.setStyleSheet("""
            QStackedWidget {
                background-color: white;
            }
        """)

        # Create empty state view
        self.empty_label = QLabel("Select a session to view details")
        self.empty_label.setAlignment(Qt.AlignCenter)
        empty_font = QFont()
        empty_font.setPointSize(14)
        empty_font.setItalic(True)
        self.empty_label.setFont(empty_font)
        self.empty_label.setStyleSheet("color: #999; background-color: white;")
        self.detail_view.addWidget(self.empty_label)
        splitter.addWidget(self.detail_view)

        # Set splitter sizes (25% left, 75% right) and make left panel non-resizable
        splitter.setSizes([250, 750])
        # Disable resizing of the left panel by making it non-collapsible and fixed
        splitter.setCollapsible(0, False)  # Left panel cannot collapse
        splitter.setCollapsible(1, False)  # Right panel cannot collapse
        # Make the splitter handle non-interactive by disabling it
        splitter.handle(1).setEnabled(False)
        # Hide the splitter handle visually
        splitter.setHandleWidth(0)
        main_layout.addWidget(splitter)

        # Connect signals for thread-safe operations
        self.session_added_signal.connect(self._add_session_slot)
        self.session_updated_signal.connect(self._update_session_slot)

        # Initialize native macOS menu bar icon
        self._init_tray_icon()

        # Initialize native macOS notification manager
        self.notification_manager = NotificationManager(
            on_notification_clicked=self.open_session_by_id
        )
        # Request notification authorization on startup
        self.notification_manager.request_authorization()
        logger.info("✓ NotificationManager initialized with native macOS notifications")

        logger.info("✓ Inbox UI initialized")

    def set_handler(self, handler):
        """
        Set the handler for processing sessions.

        Args:
            handler: Handler instance
        """
        self.handler = handler

        # Connect handler signals to inbox slots
        if hasattr(handler, 'session_completed'):
            handler.session_completed.connect(self._on_session_completed)
        if hasattr(handler, 'session_error'):
            handler.session_error.connect(self._on_session_error)
        if hasattr(handler, 'session_updated'):
            handler.session_updated.connect(self._on_session_updated)

        logger.debug("Handler connected to Inbox")

    def set_tool_manager(self, tool_manager):
        """
        Set the tool manager for settings access.

        Args:
            tool_manager: ToolManager instance
        """
        self.tool_manager = tool_manager
        logger.info("ToolManager connected to Inbox")

    def set_pipeline(self, pipeline):
        """
        Set the pipeline for adapter settings access.

        Args:
            pipeline: Pipeline instance
        """
        self.pipeline = pipeline
        logger.info("Pipeline connected to Inbox")

    def set_orchestrator(self, orchestrator):
        """
        Set the orchestrator for LLM config reload access.

        Args:
            orchestrator: Orchestrator instance
        """
        self.orchestrator = orchestrator
        logger.info("Orchestrator connected to Inbox")

    def add_session(self, session: Session):
        """
        Add a new session to the inbox (thread-safe).

        This method can be called from any thread.

        Args:
            session: Session to add
        """
        # Emit signal for thread-safe GUI update
        self.session_added_signal.emit(session)

    def _add_session_slot(self, session: Session):
        """
        Internal slot for adding session (runs on GUI thread).

        Args:
            session: Session to add
        """
        session_id = session.metadata.get('uuid')
        logger.info(f"Adding session to inbox: {session_id}")

        # Check if we've reached max sessions
        if len(self.sessions) >= self.max_display_sessions:
            logger.warning(f"Max sessions reached ({self.max_display_sessions}), removing oldest")
            self._remove_oldest_completed()

        # Store session
        self.sessions[session_id] = session

        # Add to list widget
        self.session_list.add_session(session)

        # Update tray icon to show unread count
        self.update_tray_icon()

        # Show system notification for new session
        if self.notification_manager:
            self.notification_manager.show_notification(session)
            logger.debug(f"System notification triggered for session: {session_id}")

        # Dispatch to handler
        if self.handler:
            self.dispatch_to_handler(session)
        else:
            logger.warning("No handler configured, session not processed")

        logger.debug(f"Session added successfully: {session_id}")

    def update_session(self, session_id: str, updates: Dict[str, Any]):
        """
        Update an existing session (thread-safe).

        Args:
            session_id: UUID of session to update
            updates: Dictionary of updates to apply
        """
        # Emit signal for thread-safe GUI update
        self.session_updated_signal.emit(session_id, updates)

    def _update_session_slot(self, session_id: str, updates: Dict[str, Any]):
        """
        Internal slot for updating session (runs on GUI thread).

        Args:
            session_id: UUID of session to update
            updates: Dictionary of updates
        """
        if session_id not in self.sessions:
            logger.warning(f"Session not found for update: {session_id}")
            return

        session = self.sessions[session_id]

        # Apply updates
        for key, value in updates.items():
            if hasattr(session, key):
                setattr(session, key, value)
                logger.debug(f"Updated session.{key} for {session_id}")

        # Update list item
        self.session_list.update_session_item(session_id, session)

        logger.debug(f"Session updated: {session_id}")

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get a session by ID.

        Args:
            session_id: UUID of session

        Returns:
            Session or None if not found
        """
        return self.sessions.get(session_id)

    def list_sessions(self, filters: Optional[Dict[str, Any]] = None) -> List[Session]:
        """
        List sessions, optionally filtered.

        Args:
            filters: Optional filter criteria (e.g., {'status': 'active'})

        Returns:
            List of sessions
        """
        sessions = list(self.sessions.values())

        if filters:
            # Apply filters
            for key, value in filters.items():
                sessions = [s for s in sessions if getattr(s, key, None) == value]

        return sessions

    def remove_session(self, session_id: str):
        """
        Remove a session from the inbox.

        Args:
            session_id: UUID of session to remove
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.session_list.remove_session(session_id)
            # Update tray icon after removal
            self.update_tray_icon()
            logger.info(f"Removed session: {session_id}")
        else:
            logger.warning(f"Session not found for removal: {session_id}")

    def archive_session(self, session_id: str):
        """
        Archive a session (for future implementation).

        Currently just removes the session.

        Args:
            session_id: UUID of session to archive
        """
        logger.info(f"Archiving session: {session_id}")
        # Future: move to separate archive list
        self.remove_session(session_id)

    def clear_all(self):
        """Clear all sessions from the inbox."""
        count = len(self.sessions)
        self.sessions.clear()
        self.session_list.clear_all()

        # Reset detail view to empty
        self.detail_view.setCurrentWidget(self.empty_label)

        logger.info(f"Cleared {count} sessions from inbox")

    def dispatch_to_handler(self, session: Session):
        """
        Dispatch session to handler for processing.

        Args:
            session: Session to process
        """
        if not self.handler:
            logger.error("No handler configured")
            return

        logger.debug(f"Dispatching session to handler: {session.metadata.get('uuid')}")
        self.handler.handle_session(session)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get inbox statistics.

        Returns:
            dict: Statistics including counts by status
        """
        stats = {
            'total': len(self.sessions),
            'pending': 0,
            'active': 0,
            'completed': 0,
            'error': 0
        }

        for session in self.sessions.values():
            status = session.status
            if status in stats:
                stats[status] += 1

        return stats

    def _create_menu_bar(self):
        """Create menu bar with File menu and Settings option."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        # Settings action
        settings_action = QAction("Settings...", self)
        settings_action.setShortcut("Ctrl+,")  # Standard settings shortcut
        settings_action.triggered.connect(self._open_settings_dialog)
        file_menu.addAction(settings_action)

        # Separator
        file_menu.addSeparator()

        # Quit action
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")  # Cmd+Q on macOS
        quit_action.triggered.connect(self._quit_application)
        file_menu.addAction(quit_action)

        logger.info("Menu bar created")

    def _open_settings_dialog(self):
        """Open the settings dialog for tool and adapter management."""
        if not self.tool_manager:
            logger.warning("Cannot open settings: ToolManager not set")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Settings Unavailable",
                "Settings are not available at this time.\nToolManager is not initialized."
            )
            return

        logger.info("Opening settings dialog...")
        # Pass tool_manager, pipeline, and orchestrator to settings dialog
        dialog = SettingsDialog(self.tool_manager, self.pipeline, self.orchestrator, self)
        dialog.exec_()
        logger.info("Settings dialog closed")

    def _quit_application(self):
        """Quit the application completely (not just hide to tray)."""
        logger.info("Quit requested via menu")
        from PyQt5.QtWidgets import QApplication
        QApplication.quit()

    def _create_footer(self) -> QWidget:
        """
        Create footer widget with logo and version information.

        Returns:
            QWidget: Footer widget
        """
        footer_widget = QWidget()
        footer_layout = QHBoxLayout()
        footer_widget.setLayout(footer_layout)
        footer_layout.setContentsMargins(2, 2, 2, 2)  # Left, Top, Right, Bottom - tight margins
        footer_layout.setSpacing(0)  # Remove default spacing, we'll add custom spacing

        # Set same background color as left panel
        footer_widget.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                border: none;
            }
        """)

        # Settings icon button (clickable)
        from PyQt5.QtWidgets import QPushButton
        settings_btn = QPushButton("⚙")  # Settings gear icon
        settings_btn.setFixedSize(40, 40)
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setToolTip("Settings")
        settings_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #999999;
                font-size: 32px;
                border-radius: 20px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.05);
                color: #666666;
            }
            QPushButton:pressed {
                background-color: rgba(0, 0, 0, 0.1);
            }
        """)
        settings_btn.clicked.connect(self._open_settings_dialog)
        footer_layout.addWidget(settings_btn)

        # Add stretch to push content to the left
        footer_layout.addStretch()

        return footer_widget

    def _init_tray_icon(self):
        """Initialize the native macOS system tray icon."""
        # Get logo path - use path helper for bundled app support
        from utils.path_helper import get_resource_path
        logo_path = get_resource_path('docs/logo_menubar.png')

        # Create native macOS tray icon
        self.tray_icon = MacOSTrayIcon(self)

        # Set initial icon (no badge)
        self.tray_icon.set_icon(logo_path, badge_count=0)
        self.tray_icon.set_tooltip("Context OS")

        # Connect tray icon click to show window
        self.tray_icon.activated.connect(self.show_window)

        # Show tray icon (NSStatusItem is shown by default)
        self.tray_icon.show()

        logger.info("✓ macOS native tray icon initialized")

    def show_window(self):
        """Show the main window and bring it to front."""
        self.show()
        self.raise_()
        self.activateWindow()
        logger.debug("Window shown and activated")

    def open_session_by_id(self, session_id: str):
        """
        Open a specific session by its ID.

        This method:
        1. Shows the Inbox window if it's hidden
        2. Finds the session in the list
        3. Selects it to display in the detail view

        Used by notification clicks to navigate directly to a session.

        Args:
            session_id: UUID of the session to open
        """
        logger.info(f"Opening session from notification click: {session_id}")

        # Show window if hidden
        self.show_window()

        # Check if session exists
        if session_id not in self.sessions:
            logger.warning(f"Session {session_id} not found in inbox")
            return

        # Trigger selection in the session list (this will handle all the rendering)
        self.session_list.select_session_by_id(session_id)

        logger.debug(f"Session {session_id} opened successfully")

    def closeEvent(self, event: QCloseEvent):
        """
        Override close event to hide window instead of quitting.

        Args:
            event: Close event
        """
        # Hide window instead of closing
        event.ignore()
        self.hide()
        logger.debug("Window close event: hiding to tray")

    def update_tray_icon(self):
        """Update the native system tray icon to show current unread count."""
        if not self.tray_icon:
            return

        # Count unread sessions
        unread_count = sum(1 for session in self.sessions.values() if not session.is_read)

        # Get logo path - use path helper for bundled app support
        from utils.path_helper import get_resource_path
        logo_path = get_resource_path('docs/logo_menubar.png')

        # Update icon with badge count
        self.tray_icon.set_icon(logo_path, badge_count=unread_count)

        # Update tooltip
        if unread_count > 0:
            tooltip = f"Context OS - {unread_count} unread message{'s' if unread_count != 1 else ''}"
        else:
            tooltip = "Context OS"
        self.tray_icon.set_tooltip(tooltip)

        logger.debug(f"Tray icon updated: {unread_count} unread")

    def _connect_session_signals(self, widget: QWidget, session: Session):
        """
        Connect interactive UI elements to handler for Review mode.

        Args:
            widget: Rendered widget from Renderer
            session: Session object
        """
        if not self.handler:
            logger.warning("No handler configured, cannot connect signals")
            return

        session_id = session.metadata.get('uuid')
        level = session.level

        try:
            if level == 'Review':
                # Connect input field and send button
                self._connect_review_inputs(widget, session_id)
            else:
                # Notify mode doesn't need connections
                logger.debug(f"Session level '{level}' does not require signal connections")

        except Exception as e:
            logger.error(f"Error connecting session signals: {e}", exc_info=True)

    def _connect_review_inputs(self, widget: QWidget, session_id: str):
        """
        Connect Review mode input field and send button to handler.

        Args:
            widget: Rendered widget
            session_id: UUID of the session
        """
        # Check if widget has the expected attributes
        if not hasattr(widget, 'input_field') or not hasattr(widget, 'send_button'):
            logger.warning("Review widget missing input_field or send_button attributes")
            return

        input_field = widget.input_field
        send_button = widget.send_button

        # Create a handler function for sending messages
        def send_message():
            message = input_field.text().strip()
            if message:
                # Disable button and input field while processing
                # (UI will be refreshed with new enabled button when response arrives)
                send_button.setEnabled(False)
                send_button.setText("Sending...")
                input_field.setEnabled(False)

                logger.info(f"Review session {session_id}: User message = '{message}'")
                self.handler.on_user_input(session_id, message)
                input_field.clear()
                logger.debug(f"Input field cleared for session {session_id}")
            else:
                logger.debug("Empty message, not sending")

        # Connect both send button click and Enter key press
        send_button.clicked.connect(send_message)
        input_field.returnPressed.connect(send_message)

        logger.info(f"Connected input field and send button for Review session {session_id}")

    def _refresh_detail_view(self, session: Session):
        """
        Refresh the detail view for the given session.

        This is called when a session's state changes while it's being displayed.

        Args:
            session: Session to refresh
        """
        session_id = session.metadata.get('uuid')
        logger.debug(f"Refreshing detail view for session {session_id}")

        try:
            # Re-render the session
            widget = self.renderer.render(session)

            # Remove old widget (keep only empty label)
            while self.detail_view.count() > 1:
                old_widget = self.detail_view.widget(1)
                self.detail_view.removeWidget(old_widget)
                old_widget.deleteLater()

            # Add new widget
            self.detail_view.addWidget(widget)
            self.detail_view.setCurrentWidget(widget)

            # Connect interactive elements to handler
            self._connect_session_signals(widget, session)

            logger.debug("Detail view refreshed successfully")

        except Exception as e:
            logger.error(f"Error refreshing detail view: {e}", exc_info=True)

    def _on_session_selected(self, session: Session):
        """
        Handle session selection from list.

        Args:
            session: Selected session
        """
        session_id = session.metadata.get('uuid')
        logger.debug(f"Session selected: {session_id}")

        # Fix for Issue 1: Track currently displayed session
        self.current_session_id = session_id

        # Mark session as read when user views it
        if not session.is_read:
            session.mark_as_read()
            # Refresh the list item to remove red dot
            self.session_list.update_session_item(session_id, session)
            # Update tray icon to reflect new unread count
            self.update_tray_icon()
            logger.info(f"Session {session_id} marked as read")

        # Render session
        try:
            widget = self.renderer.render(session)

            # Remove old widgets (keep only empty label + current)
            while self.detail_view.count() > 1:
                old_widget = self.detail_view.widget(1)
                self.detail_view.removeWidget(old_widget)
                old_widget.deleteLater()

            # Add new widget
            self.detail_view.addWidget(widget)
            self.detail_view.setCurrentWidget(widget)

            # Connect interactive elements to handler
            self._connect_session_signals(widget, session)

            logger.debug("Session rendered in detail view")

        except Exception as e:
            logger.error(f"Error rendering session: {e}", exc_info=True)

    def _on_session_completed(self, session_id: str):
        """
        Handle session completion signal from Handler.

        Args:
            session_id: UUID of completed session
        """
        logger.debug(f"Session completed: {session_id}")

        # Update session status to completed
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.update_status('completed')

            # Update the list item to reflect completion (removes red dot, grays out)
            self.session_list.update_session_item(session_id, session)

            # Fix for Issue 1: If this session is currently displayed, refresh the detail view
            if self.current_session_id == session_id:
                logger.info(f"Refreshing detail view for completed session {session_id}")
                self._refresh_detail_view(session)

            logger.info(f"Session {session_id} marked as completed in UI")

    def _on_session_error(self, session_id: str, error_message: str):
        """
        Handle session error signal from Handler.

        Args:
            session_id: UUID of session with error
            error_message: Error message
        """
        logger.warning(f"Session error: {session_id} - {error_message}")

        # Update session status to error
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.update_status('error')

            # Update the list item
            self.session_list.update_session_item(session_id, session)

            logger.info(f"Session {session_id} marked as error in UI")

    def _on_session_updated(self, session_id: str):
        """
        Handle session update signal from Handler.

        This is called when a session is updated (e.g., new assistant message added),
        which marks the session as unread and requires UI refresh to show red dot.

        Args:
            session_id: UUID of updated session
        """
        logger.debug(f"Session updated: {session_id}")

        if session_id in self.sessions:
            session = self.sessions[session_id]
            # Refresh the list item to show/hide red dot based on is_read status
            self.session_list.update_session_item(session_id, session)
            # Update tray icon to reflect unread count changes
            self.update_tray_icon()
            logger.info(f"Session {session_id} UI refreshed (new message indicator updated)")

            # If this session is currently displayed, refresh the detail view to show new messages
            if self.current_session_id == session_id:
                logger.info(f"Refreshing detail view for currently displayed session {session_id}")
                self._refresh_detail_view(session)

                # Mark as read since user is actively viewing this session
                if not session.is_read:
                    session.mark_as_read()
                    self.session_list.update_session_item(session_id, session)
                    # Update tray icon after marking as read
                    self.update_tray_icon()
                    logger.info(f"Currently displayed session {session_id} marked as read (user is viewing)")

    def _remove_oldest_completed(self):
        """Remove the oldest completed session to make room for new ones."""
        # Find oldest completed session
        oldest_session = None
        oldest_time = None

        for session in self.sessions.values():
            if session.status == 'completed':
                created_at = session.metadata.get('created_at')
                if oldest_time is None or created_at < oldest_time:
                    oldest_time = created_at
                    oldest_session = session

        # Remove if found
        if oldest_session:
            session_id = oldest_session.metadata.get('uuid')
            logger.info(f"Removing oldest completed session: {session_id}")
            self.remove_session(session_id)
