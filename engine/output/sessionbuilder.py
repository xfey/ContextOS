"""
Session Builder for Context OS.

Builds Session objects from formatted content.
"""

from typing import Dict, Any, Optional, Union
from models.session import Session
from utils.logger import get_logger

logger = get_logger('SessionBuilder')


class SessionBuilder:
    """
    SessionBuilder creates Session objects from formatted content.

    Responsibilities:
    - Initialize session configuration based on interaction level
    - Create initial messages
    - Set UI configuration
    - Attach metadata
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the SessionBuilder.

        Args:
            config: Session configuration from system.yaml
        """
        self.config = config
        # Timeout disabled - not used currently
        # self.default_timeout = config.get('default_timeout', 300)
        self.max_turns = config.get('max_turns', {'review': -1})

        logger.info("SessionBuilder initialized")

    def build(self, formatted_content: Dict[str, Any]) -> Session:
        """
        Build a Session object from formatted content.

        Args:
            formatted_content: Formatted content from Formatter
            level: Interaction level ('Notify' or 'Review')

        Returns:
            Session: Built session object
        """
        level = formatted_content['level']

        # Initialize session configuration
        session_config = self._init_session_config(level)

        # Set UI configuration
        ui_config = self._set_ui_config(level)

        # Create session
        session = Session(
            level=level,
            title=formatted_content['title'],
            status='pending',
            messages=formatted_content['messages'],
            messages_to_user=formatted_content['messages_to_user'],
            config=session_config,
            ui_config=ui_config
        )

        # Attach metadata
        self._attach_metadata(session, formatted_content)

        logger.info(f"Session built: {session.metadata.get('uuid')}")
        return session

    def _init_session_config(self, level: str) -> Dict[str, Any]:
        """
        Initialize session configuration based on interaction level.

        Args:
            level: Interaction level

        Returns:
            dict: Session configuration
        """
        config = {
            # 'timeout': self.default_timeout,  # DISABLED: timeout not used currently
            'level': level
        }

        # Set max_turns based on level
        if level == 'Notify':
            config['max_turns'] = 0
        elif level == 'Review':
            config['max_turns'] = self.max_turns.get('review', -1)
        else:
            logger.warning(f"Unknown level '{level}', defaulting to Notify")
            config['max_turns'] = 0

        logger.debug(f"Session config: {config}")
        return config

    def _set_ui_config(self, level: str) -> Dict[str, Any]:
        """
        Set UI configuration based on interaction level.

        Args:
            level: Interaction level

        Returns:
            dict: UI configuration
        """
        ui_config = {
            'level': level,
        }

        # Configure UI based on level
        if level == 'Notify':
            ui_config.update({
                'show_input': False,
                'auto_dismiss': True,
                'dismiss_delay': 10,  # seconds
                'style': 'notification'
            })

        elif level == 'Review':
            ui_config.update({
                'show_input': True,
                'show_history': True,
                'style': 'dialog'
            })

        logger.debug(f"UI config: {ui_config}")
        return ui_config

    def _attach_metadata(self, session: Session, formatted_content: Dict[str, Any]) -> None:
        """
        Attach metadata to the session.

        Args:
            session: Session to update
            intent: Original intent
        """
        # Add intent metadata
        session.metadata['intent_uuid'] = formatted_content['metadata'].get('intent_uuid')
        session.metadata['source'] = formatted_content['metadata'].get('source')
        # Add original input context
        session.metadata['intent_context'] = formatted_content['metadata'].get('intent_context')     # type, data
