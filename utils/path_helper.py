"""
Path helper for bundled applications.
Handles resource path resolution for both development and bundled modes.
Also manages user config directory for writable configurations.
Includes automatic config version checking and migration.
"""

import os
import sys
import shutil
import yaml
from pathlib import Path
from typing import Union, Optional, Dict, Any
from utils.logger import logger

def get_resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for both dev and PyInstaller bundled mode.

    In development: returns path relative to project root
    In bundled app: returns path relative to PyInstaller's temporary folder (_MEIPASS)

    Args:
        relative_path: Relative path from project root (e.g., 'config/system.yaml')

    Returns:
        Absolute path to the resource
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as bundled app - use PyInstaller's temporary folder
        base_path = sys._MEIPASS
    else:
        # Running in development - use project root
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)


def get_user_config_dir() -> str:
    """
    Get writable directory for user config files.

    For bundled apps, config files must be stored in user's home directory
    because bundled resources are read-only.

    Returns:
        Path to writable config directory:
        - macOS: ~/Library/Application Support/ContextOS
        - Windows: %APPDATA%/ContextOS
        - Linux: ~/.config/contextos
    """
    if sys.platform == 'darwin':
        config_dir = os.path.expanduser('~/Library/Application Support/ContextOS')
    elif sys.platform == 'win32':
        config_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'ContextOS')
    else:
        config_dir = os.path.expanduser('~/.config/contextos')

    # Create directory if it doesn't exist
    os.makedirs(config_dir, exist_ok=True)

    return config_dir


def _get_config_version(config_path: str) -> Optional[str]:
    """
    Get version from a config file.

    Args:
        config_path: Path to config file

    Returns:
        Version string (e.g., "0.3.1") or None if not found
    """
    try:
        if not os.path.exists(config_path):
            return None

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        return config.get('config_version') if config else None
    except Exception as e:
        logger.warning(f"Failed to read version from {config_path}: {e}")
        return None


def _compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings.

    Args:
        v1: First version (e.g., "0.3.1")
        v2: Second version (e.g., "0.2.3")

    Returns:
        1 if v1 > v2, 0 if equal, -1 if v1 < v2
    """
    try:
        v1_parts = tuple(map(int, v1.split('.')))
        v2_parts = tuple(map(int, v2.split('.')))

        if v1_parts > v2_parts:
            return 1
        elif v1_parts < v2_parts:
            return -1
        else:
            return 0
    except (ValueError, AttributeError):
        return 0 if v1 == v2 else -1


def _merge_config_preserving_user_settings(user_config: Dict[str, Any],
                                           bundle_config: Dict[str, Any],
                                           config_name: str) -> Dict[str, Any]:
    """
    Merge configs, preserving user settings while updating schema.

    Strategy:
    - For system.yaml: Preserve user's LLM settings (API key, base_url, model)
    - For tools.yaml: Preserve enabled/disabled states, update tool schemas
    - For sources.yaml: Preserve enabled/disabled states

    Args:
        user_config: User's current config
        bundle_config: New config from bundle
        config_name: Config file name for context

    Returns:
        Merged config dictionary
    """
    merged = bundle_config.copy()

    if config_name == 'system.yaml':
        # Preserve LLM settings
        if 'engine' in user_config and 'engine' in merged:
            user_engine = user_config['engine']
            merged['engine']['llm_api_key'] = user_engine.get('llm_api_key', merged['engine'].get('llm_api_key'))
            merged['engine']['llm_base_url'] = user_engine.get('llm_base_url', merged['engine'].get('llm_base_url'))
            merged['engine']['llm_model'] = user_engine.get('llm_model', merged['engine'].get('llm_model'))

        # Preserve log level
        if 'system' in user_config and 'system' in merged:
            merged['system']['log_level'] = user_config['system'].get('log_level', merged['system']['log_level'])

        # Preserve user language preference
        if 'user' in user_config and 'user' in merged:
            merged['user']['default_language'] = user_config['user'].get('default_language', merged['user']['default_language'])

    elif config_name == 'tools.yaml':
        # Preserve tool enabled/disabled states
        if 'tools' in user_config and 'tools' in merged:
            user_tools = {tool['name']: tool for tool in user_config.get('tools', [])}

            for i, tool in enumerate(merged['tools']):
                tool_name = tool['name']
                if tool_name in user_tools:
                    # Preserve enabled state
                    merged['tools'][i]['enabled'] = user_tools[tool_name].get('enabled', tool['enabled'])

    elif config_name == 'sources.yaml':
        # Preserve adapter enabled/disabled states
        if 'adapters' in user_config and 'adapters' in merged:
            user_adapters = {adapter['name']: adapter for adapter in user_config.get('adapters', [])}

            for i, adapter in enumerate(merged['adapters']):
                adapter_name = adapter['name']
                if adapter_name in user_adapters:
                    # Preserve enabled state
                    merged['adapters'][i]['enabled'] = user_adapters[adapter_name].get('enabled', adapter['enabled'])

    return merged


def get_config_path(config_file: str) -> str:
    """
    Get path to a config file, handling both dev and bundled modes.

    In development: returns path to config/ directory in project
    In bundled app: returns path to user's config directory, with automatic
                    version checking and migration

    Args:
        config_file: Name of config file (e.g., 'system.yaml')

    Returns:
        Absolute path to the config file
    """
    if getattr(sys, 'frozen', False):
        # Bundled mode: use user's config directory
        user_config_dir = get_user_config_dir()
        config_path = os.path.join(user_config_dir, config_file)
        bundled_config = get_resource_path(f'config/{config_file}')

        # Check if user config exists
        if not os.path.exists(config_path):
            # First run: copy from bundle
            if os.path.exists(bundled_config):
                logger.info(f"First run: copying {config_file} to user directory")
                shutil.copy2(bundled_config, config_path)
            else:
                raise FileNotFoundError(f"Config file not found in bundle: {bundled_config}")
        else:
            # Check version and migrate if needed
            user_version = _get_config_version(config_path)
            bundle_version = _get_config_version(bundled_config)

            if user_version and bundle_version:
                version_diff = _compare_versions(bundle_version, user_version)

                if version_diff > 0:
                    # Bundle version is newer - migrate
                    logger.info(f"Migrating {config_file} from v{user_version} to v{bundle_version}")

                    try:
                        # Load both configs
                        with open(config_path, 'r') as f:
                            user_config = yaml.safe_load(f)
                        with open(bundled_config, 'r') as f:
                            bundle_config = yaml.safe_load(f)

                        # Merge configs
                        merged_config = _merge_config_preserving_user_settings(
                            user_config, bundle_config, config_file
                        )

                        # Backup old config
                        backup_path = config_path + f'.v{user_version}.backup'
                        shutil.copy2(config_path, backup_path)
                        logger.info(f"Backed up old config to: {backup_path}")

                        # Write merged config
                        with open(config_path, 'w') as f:
                            yaml.dump(merged_config, f, default_flow_style=False, sort_keys=False)

                        logger.info(f"Successfully migrated {config_file}")

                    except Exception as e:
                        logger.error(f"Error migrating {config_file}: {e}")
                        logger.info("Keeping existing config")
            elif not user_version and bundle_version:
                # User config is old (no version), force update with backup
                logger.info(f"User config {config_file} has no version, updating to v{bundle_version}")

                # Backup old config
                backup_path = config_path + '.old.backup'
                shutil.copy2(config_path, backup_path)
                logger.info(f"Backed up old config to: {backup_path}")

                # Copy new config
                shutil.copy2(bundled_config, config_path)
                logger.info(f"Updated {config_file} to latest version")

        return config_path
    else:
        # Development mode: use project's config directory
        return get_resource_path(f'config/{config_file}')


def get_prompts_path(prompt_file: str = None) -> str:
    """
    Get path to prompts directory or specific prompt file.
    Prompts are read-only resources, always loaded from bundle/project.

    Args:
        prompt_file: Optional name of specific prompt file (e.g., 'intent_detection.txt')

    Returns:
        Absolute path to prompts directory or specific prompt file
    """
    prompts_dir = get_resource_path('prompts')

    if prompt_file:
        return os.path.join(prompts_dir, prompt_file)
    else:
        return prompts_dir


def is_bundled() -> bool:
    """
    Check if running as a bundled application.

    Returns:
        True if running as bundled app, False if running in development
    """
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def ensure_user_config_initialized():
    """
    Ensure user config directory exists and all config files are copied.
    Should be called once during app initialization when running in bundled mode.
    """
    if not is_bundled():
        return

    config_files = ['system.yaml', 'sources.yaml', 'tools.yaml']
    user_config_dir = get_user_config_dir()

    logger.info(f"User config directory: {user_config_dir}")

    for config_file in config_files:
        user_config_path = os.path.join(user_config_dir, config_file)

        if not os.path.exists(user_config_path):
            bundled_config = get_resource_path(f'config/{config_file}')
            if os.path.exists(bundled_config):
                logger.info(f"Copying {config_file} to user directory")
                shutil.copy2(bundled_config, user_config_path)
            else:
                logger.warning(f"Config file not found in bundle: {bundled_config}")


# Convenience function for backward compatibility
def get_project_root() -> str:
    """
    Get project root directory.

    In development: returns actual project root
    In bundled app: returns PyInstaller's temporary folder

    Returns:
        Absolute path to project root or bundle root
    """
    if is_bundled():
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
