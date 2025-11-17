"""
Logging system for Context OS.

Provides centralized logging with configurable log levels from system.yaml.
"""

import logging
import os
import sys
from typing import Optional
import yaml


class Logger:
    """
    Centralized logging system that reads configuration from system.yaml.
    """

    _instance: Optional[logging.Logger] = None
    _initialized: bool = False

    @classmethod
    def get_logger(cls, name: str = 'ContextOS') -> logging.Logger:
        """
        Get or create a logger instance.

        Args:
            name: Logger name (default: 'ContextOS')

        Returns:
            logging.Logger: Configured logger instance
        """
        if not cls._initialized:
            cls._initialize_logger()

        return logging.getLogger(name)

    @classmethod
    def _initialize_logger(cls):
        """Initialize the logging system with configuration from system.yaml."""
        # Read log level from system.yaml
        log_level = cls._read_log_level_from_config()

        # Configure root logger
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )

        cls._initialized = True

    @classmethod
    def _read_log_level_from_config(cls) -> int:
        """
        Read log level from system.yaml configuration file.

        Returns:
            int: Logging level constant (e.g., logging.INFO)
        """
        try:
            # Get the project root directory (assuming logger.py is in utils/)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            config_path = os.path.join(project_root, 'config', 'system.yaml')

            # Read config file
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)

                # Get log level from config
                log_level_str = config.get('system', {}).get('log_level', 'INFO')

                # Convert string to logging level
                log_level_map = {
                    'DEBUG': logging.DEBUG,
                    'INFO': logging.INFO,
                    'WARNING': logging.WARNING,
                    'ERROR': logging.ERROR,
                    'CRITICAL': logging.CRITICAL
                }

                return log_level_map.get(log_level_str.upper(), logging.INFO)
            else:
                # Default to INFO if config file not found
                print(f"Warning: Config file not found at {config_path}, using default log level INFO")
                return logging.INFO

        except Exception as e:
            # Default to INFO on any error
            print(f"Warning: Error reading log level from config: {e}, using default log level INFO")
            return logging.INFO


# Convenience function to get logger
def get_logger(name: str = 'ContextOS') -> logging.Logger:
    """
    Convenience function to get a logger instance.

    Args:
        name: Logger name

    Returns:
        logging.Logger: Configured logger instance
    """
    return Logger.get_logger(name)


# Default logger instance
logger = get_logger()
