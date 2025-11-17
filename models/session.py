"""
Session and Message data models for Context OS.

Session represents an interaction container that manages the complete user interaction flow.
Message represents a single conversation unit within a Session.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from utils.helpers import generate_uuid, get_timestamp


class Session:
    """
    Session represents a unified interaction container.

    Attributes:
        level (str): Interaction level ('Notify' or 'Review')
        status (str): Session status ('pending', 'active', 'completed', or 'error')
        messages (List): List of message dicts (role, content -> list or str)
        config (dict): Session configuration (max_turns, timeout, etc.)
        ui_config (dict): UI configuration (styles, layout, etc.)
        metadata (dict): Metadata containing uuid, created_at, updated_at
    """

    def __init__(
        self,
        level: str,
        title: str,
        status: str = 'pending',
        messages: Optional[List[Dict[str, Any]]] = None,
        messages_to_user: Optional[List[Dict[str, Any]]] = None,    # new: clear messages to user
        config: Optional[Dict[str, Any]] = None,
        ui_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_read: bool = False
    ):
        """
        Initialize a Session object.

        Args:
            level: Interaction level ('Notify' or 'Review')
            status: Session status (default: 'pending')
            messages: Optional list of message dicts
            messages_to_user: Optional list of message_to_user dicts
            config: Optional session configuration dict
            ui_config: Optional UI configuration dict
            metadata: Optional metadata dict. If not provided, uuid, created_at, updated_at are auto-generated
            is_read: Whether the session has been read by user (default: False)
        """
        self.level = level
        self.title = title
        self.status = status
        self.messages = messages if messages is not None else []
        self.messages_to_user = messages_to_user if messages_to_user is not None else []
        self.config = config if config is not None else {}
        self.ui_config = ui_config if ui_config is not None else {}
        self.is_read = is_read

        # Auto-generate metadata if not provided
        if metadata is None:
            metadata = {}

        # Ensure required metadata fields are present
        if 'uuid' not in metadata:
            metadata['uuid'] = generate_uuid()

        current_time = get_timestamp()
        if 'created_at' not in metadata:
            metadata['created_at'] = current_time
        if 'updated_at' not in metadata:
            metadata['updated_at'] = current_time

        self.metadata = metadata

    def add_message(self, message: Dict[str, Any], message_to_user: Dict[str, Any]):
        """
        Add a message to the session and update timestamp.

        Args:
            message: Message object to add
        """
        self.messages.append(message)
        self.messages_to_user.append(message_to_user)
        self.metadata['updated_at'] = get_timestamp()

    def update_status(self, status: str):
        """
        Update session status and timestamp.

        Args:
            status: New status ('pending', 'active', 'completed', or 'error')
        """
        self.status = status
        self.metadata['updated_at'] = get_timestamp()

    def mark_as_read(self):
        """
        Mark this session as read by the user.

        Sets is_read to True and updates the last_read_at timestamp.
        """
        if not self.is_read:
            self.is_read = True
            self.metadata['updated_at'] = get_timestamp()
            self.metadata['last_read_at'] = get_timestamp()

    def mark_as_unread(self):
        """
        Mark this session as unread.

        This is typically called when a new assistant message arrives
        in a multi-turn session, signaling the user should review it.
        """
        if self.is_read:
            self.is_read = False
            self.metadata['updated_at'] = get_timestamp()

    def __repr__(self) -> str:
        """String representation of Session."""
        return (
            f"Session(level={self.level!r}, status={self.status!r}, "
            f"messages={len(self.messages)}, messages_to_user={len(self.messages_to_user)})"
            f"metadata={self.metadata!r})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert Session to dictionary format.

        Returns:
            dict: Session data as dictionary
        """
        return {
            'level': self.level,
            'status': self.status,
            'is_read': self.is_read,
            'messages': self.messages,
            'messages_to_user': self.messages_to_user,
            'config': self.config,
            'ui_config': self.ui_config,
            'metadata': {
                'uuid': self.metadata['uuid'],
                'created_at': self.metadata['created_at'].isoformat()
                    if isinstance(self.metadata['created_at'], datetime)
                    else self.metadata['created_at'],
                'updated_at': self.metadata['updated_at'].isoformat()
                    if isinstance(self.metadata['updated_at'], datetime)
                    else self.metadata['updated_at'],
                **{k: v for k, v in self.metadata.items() if k not in ['uuid', 'created_at', 'updated_at']}
            }
        }
