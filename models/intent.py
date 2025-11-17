"""
Intent data model for Context OS.

Intent represents a user's needs or task goals identified from Signals.
"""

from datetime import datetime
from typing import Dict, Any


class Intent:
    """
    Intent represents a detected user intention.

    Attributes:
        target (str): Short description of the intent target (e.g., "translate to English")
        context (dict): Context information related to the intent
        level (str): Interaction level ('Notify' or 'Review')
        metadata (dict): Metadata containing uuid and timestamp
    """

    def __init__(
        self,
        target: str,
        source: str,
        context: Dict[str, Any],
        level: str,
        metadata: Dict[str, Any],
    ):
        """
        Initialize an Intent object.

        Args:
            target: Short description of the intent target
            source: Data source from Signal.source
            context: Context information related to the intent
            level: Interaction level ('Notify' or 'Review')
            metadata: Optional metadata dict. If not provided, uuid and timestamp are auto-generated
        """
        self.target = target
        self.source = source
        self.context = context
        self.level = level
        self.metadata = metadata    # directly use signal's metadata uuid & timestamp

    def __repr__(self) -> str:
        """String representation of Intent."""
        return (
            f"Intent(target={self.target!r}, source={self.source!r}, level={self.level!r}, "
            f"context={self.context!r}, metadata={self.metadata!r})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert Intent to dictionary format.

        Returns:
            dict: Intent data as dictionary
        """
        return {
            'target': self.target,
            'source': self.source,
            'context': self.context,
            'level': self.level,
            'metadata': {
                'uuid': self.metadata['uuid'],
                'timestamp': self.metadata['timestamp'].isoformat()
                    if isinstance(self.metadata['timestamp'], datetime)
                    else self.metadata['timestamp'],
                **{k: v for k, v in self.metadata.items() if k not in ['uuid', 'timestamp']}
            }
        }
