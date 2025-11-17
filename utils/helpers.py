"""
Helper utility functions for Context OS.
"""

import uuid
from datetime import datetime


def generate_uuid() -> str:
    """
    Generate a unique identifier.

    Returns:
        str: A UUID string
    """
    return str(uuid.uuid4())


def get_timestamp() -> datetime:
    """
    Get the current timestamp.

    Returns:
        datetime: Current datetime object
    """
    return datetime.now()
