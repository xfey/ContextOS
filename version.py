"""
Central version management for Context OS.

This file contains the single source of truth for version information.
All other parts of the application should import from here.
"""

# Version follows semantic versioning: MAJOR.MINOR.PATCH
# - MAJOR: Incompatible API/config changes
# - MINOR: New features, backward compatible
# - PATCH: Bug fixes, backward compatible
__version__ = "0.3.1"

# Application metadata
APP_NAME = "ContextOS"
APP_DISPLAY_NAME = "ContextOS"
APP_BUNDLE_ID = "com.xfey.contextos"

# Minimum config version required
# If user's config version is older, it will be migrated
MIN_CONFIG_VERSION = "0.3.1"

def get_version() -> str:
    """Get the current application version."""
    return __version__

def get_version_tuple() -> tuple:
    """Get version as tuple for comparison."""
    return tuple(map(int, __version__.split('.')))

def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings.

    Args:
        v1: First version string (e.g., "0.3.1")
        v2: Second version string (e.g., "0.2.3")

    Returns:
        1 if v1 > v2
        0 if v1 == v2
        -1 if v1 < v2
    """
    try:
        v1_tuple = tuple(map(int, v1.split('.')))
        v2_tuple = tuple(map(int, v2.split('.')))

        if v1_tuple > v2_tuple:
            return 1
        elif v1_tuple < v2_tuple:
            return -1
        else:
            return 0
    except (ValueError, AttributeError):
        # If version parsing fails, assume they're different
        return 0 if v1 == v2 else -1
