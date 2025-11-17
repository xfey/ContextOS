"""
Output Formatter for Context OS.

Formats execution results into user-friendly content.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from models.intent import Intent
from utils.logger import get_logger

logger = get_logger('Formatter')


class Formatter:
    """
    Formatter transforms execution results into user-friendly content.

    Responsibilities:
    - Structure content (text, lists, cards)
    - Add contextual information
    """

    def __init__(self):
        """Initialize the Formatter."""
        logger.info("Formatter initialized")

    def format(self, react_result: Dict[str, Any], intent: Intent) -> Dict[str, Any]:
        """
        Format ReactAgent results (expects plain text final result).

        Args:
            react_result: Final result string from ReactAgent.execute()
            intent: Original intent

        Returns:
            dict: Formatted content ready for Session
        """
        logger.info(f"Formatting results for intent: {intent.target}")

        # Capitalize title
        title = intent.target or 'Result' # Use intent target as title
        title = title[0].upper() + title[1:]
        
        # directly use OpenAI format messages
        messages = [
            {
                "role": "system",
                "content": react_result['system_prompt']
                # str
            },
            {
                "role": "user",
                "content": react_result['user'] # react prompt & process
                # list of dicts{type, text/image_url}
            },
            {
                "role": "assistant",
                "content": react_result['assistant']    # react final
                # str
            }
        ]
        
        messages_to_user = [
            {
                "role": "assistant",
                "content": react_result['raw']['assistant']    # react final
                # str
            }
        ]
        
        # Build content with title from intent and timestamp from intent metadata
        formatted_output = {
            'type': 'text',
            'level': intent.level,
            'title': title,
            'messages': messages,
            # new: messages_to_user
            # cleared messages without format, start from assistant (3rd)
            'messages_to_user': messages_to_user,
            'metadata': {
                'intent_uuid': intent.metadata.get('uuid'),
                'intent_context': intent.context,
                'source': intent.source,
                'timestamp': intent.metadata.get('timestamp', None) or datetime.now().isoformat(),
            }
        }
        return formatted_output
