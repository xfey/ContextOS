"""
Session Handler for Context OS.

Manages session lifecycle and interactions.
"""

from typing import Dict, Any, Optional
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QThread

from models.session import Session
from models.intent import Intent
from utils.logger import get_logger

logger = get_logger('Handler')


class ReactWorkerThread(QThread):
    """
    Worker thread for asynchronous ReAct Agent execution to avoid blocking the UI.

    This thread performs ReAct Agent execution in the background and emits signals
    when the result is ready or an error occurs.
    """

    # Signals
    response_ready = pyqtSignal(str, dict, dict)  # session_id, response, cleared_response
    error_occurred = pyqtSignal(str, str)  # session_id, error_message

    def __init__(self, session: Session, react_agent):
        """
        Initialize the React worker thread.

        Args:
            session_id: UUID of the session
            react_agent: ReactAgent instance
            intent: Intent with conversation history
        """
        super().__init__()
        self.session = session
        self.session_id = self.session.metadata.get('uuid')
        self.react_agent = react_agent

    def run(self):
        """
        Execute the ReAct Agent in the worker thread.

        This method runs in a separate thread and emits signals when done.
        """
        try:
            logger.info(f"ReAct worker thread running for session {self.session_id}")
            response, cleared_response = self.react_agent.execute_continue(self.session)
            logger.info(f"ReAct worker thread completed for session {self.session_id}")
            self.response_ready.emit(self.session_id, response, cleared_response)
        except Exception as e:
            logger.error(f"ReAct worker thread error for session {self.session_id}: {e}", exc_info=True)
            self.error_occurred.emit(self.session_id, str(e))


class Handler(QObject):
    """
    Handler manages session lifecycle and user interactions.

    Responsibilities:
    - Process sessions based on interaction level
    - Handle user input for Review mode
    - Auto-finalize Notify sessions (max_turns=0)
    - Coordinate with Engine for multi-turn conversations
    - Manage session state transitions
    """

    # Signals
    session_completed = pyqtSignal(str)  # session_id
    session_error = pyqtSignal(str, str)  # session_id, error_message
    session_updated = pyqtSignal(str)  # session_id (for UI refresh when new message added)

    def __init__(self, config: Dict[str, Any], engine_components: Optional[Dict[str, Any]] = None):
        """
        Initialize the Handler.

        Args:
            config: Session configuration from system.yaml
            engine_components: Optional dict with engine components (detector, executor, etc.)
        """
        super().__init__()

        self.config = config
        self.engine_components = engine_components or {}

        # Get max_turns configuration
        self.max_turns_config = config.get('max_turns', {'review': -1})
        
        # Track active sessions
        self.active_sessions: Dict[str, Session] = {}

        # Timeout timers for sessions (used for auto-finalize, not timeout)
        self.timeout_timers: Dict[str, QTimer] = {}

        # Track active LLM worker threads to prevent garbage collection
        self.active_workers: list = []

        logger.info("Handler initialized")

    def handle_session(self, session: Session):
        """
        Handle a session based on its interaction level.

        This is the main entry point for session processing.

        Args:
            session: Session to handle
        """
        session_id = session.metadata.get('uuid')
        level = session.level
        max_turns = session.config.get('max_turns', 0)

        logger.info(f"Handling session {session_id} (level={level}, max_turns={max_turns})")

        # Store in active sessions
        self.active_sessions[session_id] = session

        # Update status to active
        session.update_status('active')

        # Handle based on level
        if level == 'Notify':
            # Notify mode: 0 turns, auto-finalize immediately
            logger.debug(f"Notify session - auto-finalizing")
            self._schedule_auto_finalize(session_id, delay=3000)  # 3 seconds

        elif level == 'Review':
            # Review mode: Multi-turn conversation
            logger.debug(f"Review session - multi-turn mode active")
            # UI input field should connect to on_user_input()

        else:
            logger.warning(f"Unknown session level: {level}, treating as Notify")
            self._schedule_auto_finalize(session_id, delay=3000)

    def _handle_button_content_to_message(self, button_text: str):
        btx = button_text.strip().lower()
        if btx in ['Yes', 'Approve', 'Confirm', 'OK']:
            return "User approved to confirm this message."
        elif btx in ['No', 'Reject', 'Dismiss', 'Cancel']:
            return "User rejected this message."
        else:
            logger.warning("Button info does not handled, keep unchanged.")
            return button_text

    def on_user_input(self, session_id: str, user_message: str):
        """
        Process user input for a session.

        Args:
            session_id: UUID of the session
            user_message: User's input message (Backend LLM supports image: code ready)
        """
        logger.info(f"Received user input for session {session_id}: {user_message[:50]}...")

        if session_id not in self.active_sessions:
            logger.error(f"Session not found: {session_id}")
            return

        session = self.active_sessions[session_id]

        # Detect /finish command for Review sessions
        if user_message.strip().lower() == '/finish':
            logger.info(f"Session {session_id}: /finish command received")

            # Add "/finish" as a user message to show in conversation
            self._append_message(session, dict(
                role='user',
                content=[{"type": "text", "text": "/finish"}]
            ), dict(
                role='user',
                content=[{"type": "text", "text": "You have finished this conversation."}]
            ))  # message_to_user

            # Emit signal to refresh UI to show the "/finish" message
            self.session_updated.emit(session_id)
            logger.debug(f"UI refresh triggered for /finish message in session {session_id}")

            # Now finalize the session
            self.finalize_session(session_id)
            return

        elif user_message.startswith("<||") and user_message.endswith("||>"):
            user_message = self._handle_button_content_to_message(user_message[3:-3])

        # Append user message to session
        self._append_message(session, dict(
            role='user',
            content=[{"type": "text", "text": user_message}]
        ), dict(
            role='user',
            content=[{"type": "text", "text": user_message}]
        ))
        
        # Emit signal to refresh UI immediately to show user's message
        self.session_updated.emit(session_id)
        logger.debug(f"UI refresh triggered for user message in session {session_id}")

        # Check if we should continue
        should_continue = self._check_continuation(session)

        if should_continue:
            # Send to engine for next turn
            logger.debug("Session continuing, sending to engine...")
            self._send_to_engine(session)
        else:
            # Finalize session
            logger.debug("Session complete, finalizing...")
            self.finalize_session(session_id)

    def _append_message(self, session: Session, message: Dict[str, Any], message_to_user: Dict[str, Any]):
        """
        Append a message to the session.

        Args:
            session: Session to update
            message: Message to append
        """
        session.add_message(message, message_to_user)

        # If this is an assistant message, mark session as unread
        # so the user knows there's a new response to view
        if message['role'] == 'assistant':
            session.mark_as_unread()
            # Emit signal so Inbox can refresh UI (show red dot)
            session_id = session.metadata.get('uuid')
            self.session_updated.emit(session_id)

        logger.debug(f"Message appended to session {session.metadata.get('uuid')}")

    def _send_to_engine(self, session: Session):
        """
        Send session back to engine for continued processing (non-blocking).

        This method creates a worker thread to perform the ReAct Agent execution asynchronously,
        preventing UI freezes during API calls.

        Args:
            session: Session to process
        """
        react_agent = self.engine_components['react_agent']

        # Create and configure worker thread
        worker = ReactWorkerThread(
            session=session,
            react_agent=react_agent,
        )

        # Connect signals for response/error handling
        worker.response_ready.connect(self._on_react_response)
        worker.error_occurred.connect(self._on_react_error)
        worker.finished.connect(lambda: self._cleanup_worker(worker))

        # Store reference to prevent garbage collection
        self.active_workers.append(worker)

        # Start the worker thread
        worker.start()
        logger.info(f"ReAct worker thread started for session {session.metadata.get('uuid')}")

    def _on_react_response(self, session_id: str, response: Dict[str, Any], cleared_response: Dict[str, Any]):
        """
        Handle ReAct Agent response from worker thread.

        This method runs on the main GUI thread (via signal/slot mechanism).

        Args:
            session_id: UUID of the session
            response: ReactAgent response text
        """
        logger.info(f"ReactAgent response received for session {session_id}")

        if session_id not in self.active_sessions:
            logger.warning(f"Session {session_id} no longer active, ignoring response")
            return
        session = self.active_sessions[session_id]

        # Append response to session (triggers UI update via signal)
        self._append_message(session, response, cleared_response)
        logger.info(f"Assistant response added to session {session_id}")

    def _on_react_error(self, session_id: str, error: str):
        """
        Handle ReAct Agent error from worker thread.

        This method runs on the main GUI thread (via signal/slot mechanism).

        Args:
            session_id: UUID of the session
            error: Error message
        """
        logger.error(f"ReactAgent error for session {session_id}: {error}")

        if session_id not in self.active_sessions:
            logger.warning(f"Session {session_id} no longer active, ignoring error")
            return

        session = self.active_sessions[session_id]

        # Add error message to session
        error_message = dict(
            role='assistant',
            content=f"[Error] {error}"
        )
        self._append_message(session, error_message, error_message)

    def _cleanup_worker(self, worker: ReactWorkerThread):
        """
        Clean up finished worker thread.

        Args:
            worker: Worker thread to clean up
        """
        if worker in self.active_workers:
            self.active_workers.remove(worker)
            worker.deleteLater()
            logger.debug(f"Worker thread cleaned up for session {worker.session_id}")

    def _check_continuation(self, session: Session) -> bool:
        """
        Check if session should continue based on max_turns.

        Args:
            session: Session to check

        Returns:
            bool: True if should continue, False if done
        """
        max_turns = session.config.get('max_turns', 0)

        # Notify (max_turns=0): Never continues
        if max_turns == 0:
            return False

        # Review (max_turns=-1): Always continues (until user ends)
        if max_turns == -1:
            return True

        # Other modes: Check turn count
        # Count user messages to determine turns taken
        user_messages = [m for m in session.messages if m['role'] == 'user']
        turns_taken = len(user_messages)

        should_continue = turns_taken < max_turns

        return should_continue

    def finalize_session(self, session_id: str):
        """
        Finalize a session.

        Args:
            session_id: UUID of session to finalize
        """
        logger.info(f"Finalizing session: {session_id}")

        if session_id not in self.active_sessions:
            logger.warning(f"Session not in active sessions: {session_id}")
            return

        session = self.active_sessions[session_id]

        # Update status to completed
        session.update_status('completed')

        # Cancel timeout timer if exists
        if session_id in self.timeout_timers:
            self.timeout_timers[session_id].stop()
            del self.timeout_timers[session_id]

        # Remove from active sessions
        del self.active_sessions[session_id]

        # Emit completion signal
        self.session_completed.emit(session_id)

        logger.info(f"Session finalized: {session_id}")

    def _store_to_memory(self, session: Session):
        """
        Store session to memory system (not implemented in Phase 4).

        Args:
            session: Session to store
        """
        # Placeholder for future memory integration
        logger.debug(f"Memory storage not implemented for session {session.metadata.get('uuid')}")


    def _schedule_auto_finalize(self, session_id: str, delay: int = 3000):
        """
        Schedule auto-finalization for Notify sessions.

        Args:
            session_id: UUID of session
            delay: Delay in milliseconds before finalizing (default: 3000ms)
        """
        # logger.debug(f"Scheduling auto-finalize for session {session_id} in {delay}ms")

        # Cancel existing timer if any to prevent accumulation
        if session_id in self.timeout_timers:
            old_timer = self.timeout_timers[session_id]
            if old_timer.isActive():
                old_timer.stop()
            del self.timeout_timers[session_id]

        # Create timer for delayed finalization
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._try_auto_finalize(session_id))
        timer.start(delay)

        # Store timer to prevent garbage collection
        self.timeout_timers[session_id] = timer

    def _try_auto_finalize(self, session_id: str):
        """
        Attempt to auto-finalize a session, but only if it has been read.

        If the session is unread, reschedule the check for later.

        Args:
            session_id: UUID of session to finalize
        """
        # logger.debug(f"Attempting auto-finalize for session {session_id}")

        if session_id not in self.active_sessions:
            logger.warning(f"Session not in active sessions: {session_id}")
            return

        session = self.active_sessions[session_id]

        # Check if session has been read
        if session.is_read:
            logger.info(f"Session {session_id} has been read, proceeding with finalization")
            self.finalize_session(session_id)
        else:
            # logger.debug(f"Session {session_id} is unread, rescheduling finalization check")
            # Reschedule check after 2 seconds
            self._schedule_auto_finalize(session_id, delay=3000)

    def handle_error(self, session_id: str, error: str):
        """
        Handle session error.

        Args:
            session_id: UUID of session
            error: Error message
        """
        logger.error(f"Session error: {session_id} - {error}")

        if session_id not in self.active_sessions:
            return

        session = self.active_sessions[session_id]

        # Update status to error
        session.update_status('error')

        # Append error message
        error_message = dict(role='assistant', content=f"[ERROR] {error}")
        self._append_message(session, error_message, error_message)

        # Cancel timeout if exists
        if session_id in self.timeout_timers:
            self.timeout_timers[session_id].stop()
            del self.timeout_timers[session_id]

        # Remove from active sessions
        del self.active_sessions[session_id]

        # Emit error signal
        self.session_error.emit(session_id, error)

        logger.info(f"Session error handled: {session_id}")
