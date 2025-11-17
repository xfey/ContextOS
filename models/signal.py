"""
Signal data model for Context OS.

Signal is the standardized data unit passed from Adapters to the Engine layer.
"""

from datetime import datetime
from typing import Dict, Any
from utils.helpers import generate_uuid, get_timestamp


class Signal:
    """
    Signal represents a standardized data unit from adapters.

    Attributes:
        source (str): Source identifier (adapter_id)
        type (str): Signal type ('event' or 'stream')
        content (dict): Structured data content
        metadata (dict): Metadata containing uuid and timestamp
    """

    def __init__(
        self,
        source: str,
        type: str,
        content: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ):
        """
        Initialize a Signal object.

        Args:
            source: Source identifier (adapter_id)
            type: Signal type ('event' or 'stream')
            content: Structured data content
            metadata: Optional metadata dict. If not provided, uuid and timestamp are auto-generated
        """
        self.source = source
        self.type = type
        self.content = content

        # Auto-generate metadata if not provided
        if metadata is None:
            metadata = {}

        # Ensure uuid and timestamp are present
        if 'uuid' not in metadata:
            metadata['uuid'] = generate_uuid()
        if 'timestamp' not in metadata:
            metadata['timestamp'] = get_timestamp()

        self.metadata = metadata

    def __repr__(self) -> str:
        """String representation of Signal."""
        return (
            f"Signal(source={self.source!r}, type={self.type!r}, "
            f"content={self.content!r}, metadata={self.metadata!r})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert Signal to dictionary format.

        Returns:
            dict: Signal data as dictionary
        """
        return {
            'source': self.source,
            'type': self.type,
            'content': self.content,
            'metadata': {
                'uuid': self.metadata['uuid'],
                'timestamp': self.metadata['timestamp'].isoformat()
                    if isinstance(self.metadata['timestamp'], datetime)
                    else self.metadata['timestamp'],
                **{k: v for k, v in self.metadata.items() if k not in ['uuid', 'timestamp']}
            }
        }
