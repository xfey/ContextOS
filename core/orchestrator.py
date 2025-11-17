"""
Orchestrator for Context OS.

Coordinates system startup, shutdown, and component integration.
"""

import yaml
from typing import Dict, Any, Optional

from core.pipeline import Pipeline
from interfaces.inbox import Inbox
from interfaces.handler import Handler
from utils.logger import get_logger
from utils.path_helper import get_config_path, ensure_user_config_initialized

logger = get_logger('Orchestrator')


class Orchestrator:
    """
    Orchestrator coordinates the entire Context OS system.

    Responsibilities:
    - Load system configuration
    - Initialize all components (Pipeline, Inbox, Handler)
    - Connect components together
    - Manage system lifecycle (start/stop)
    - Provide system status
    """

    def __init__(self):
        """Initialize the Orchestrator."""
        self.config: Dict[str, Any] = {}
        self.pipeline: Optional[Pipeline] = None
        self.inbox: Optional[Inbox] = None
        self.handler: Optional[Handler] = None
        self.is_running = False

        logger.debug("Orchestrator created")

    def start(self):
        """
        Start the entire Context OS system.

        Performs the following steps:
        1. Load system configuration
        2. Initialize Inbox with UI
        3. Initialize Handler
        4. Initialize Pipeline (with Engine components)
        5. Connect Pipeline to Inbox
        6. Load and start adapters
        7. Show Inbox window
        """
        if self.is_running:
            logger.warning("System is already running")
            return

        logger.info("=" * 60)
        logger.info("Starting Context OS System")
        logger.info("=" * 60)

        try:
            # Step 0: Ensure user config is initialized (for bundled apps)
            ensure_user_config_initialized()

            # Step 1: Load configuration
            logger.info("Step 1: Loading system configuration...")
            self._load_configuration()

            # Step 2: Initialize Inbox
            logger.info("Step 2: Initializing Inbox...")
            inbox_config = self.config.get('inbox', {})
            self.inbox = Inbox(inbox_config)
            self.inbox.initialize()  # Must be called on GUI thread

            # Step 3: Initialize Pipeline (includes Engine components)
            logger.info("Step 3: Initializing Pipeline with Engine...")
            self.pipeline = Pipeline()

            # Step 4: Initialize Handler with engine components from Pipeline
            logger.info("Step 4: Initializing Handler...")
            session_config = self.config.get('session', {})

            # Pass engine components from Pipeline to Handler for multi-turn conversations
            engine_components = {
                'detector': self.pipeline.detector,
                'classifier': self.pipeline.classifier,
                'tool_executor': self.pipeline.tool_executor,
                'react_agent': self.pipeline.react_agent,
                'formatter': self.pipeline.formatter,
                'session_builder': self.pipeline.session_builder
            }
            self.handler = Handler(session_config, engine_components=engine_components)

            # Step 5: Connect components
            logger.info("Step 5: Connecting components...")
            self.inbox.set_handler(self.handler)
            self.inbox.set_tool_manager(self.pipeline.tool_manager)  # Connect tool manager for settings
            self.inbox.set_pipeline(self.pipeline)  # Connect pipeline for adapter settings
            self.inbox.set_orchestrator(self)  # For LLM config hot-reload support
            self.pipeline.set_inbox(self.inbox)

            # Step 6: Load adapters
            self.pipeline.load_adapters_from_config()
            adapter_count = len(self.pipeline.adapters)
            logger.info("Step 6: Loading {adapter_count} adapters...")

            # Step 7: Start Pipeline
            logger.info("Step 7: Starting Pipeline...")
            self.pipeline.start()

            # Step 8: Show window once at startup, then accessible via system tray icon
            logger.info("Step 8: Showing Inbox window at startup...")
            self.inbox.show()  # Show window once at startup

            self.is_running = True
            self._print_system_status()

        except Exception as e:
            logger.error(f"Failed to start system: {e}", exc_info=True)
            self.stop()
            raise

    def stop(self):
        """
        Stop the Context OS system.

        Performs graceful shutdown:
        1. Stop Pipeline (stops adapters)
        2. Close Inbox window
        3. Cleanup resources
        """
        if not self.is_running:
            logger.warning("System is not running")
            return

        logger.info("=" * 60)
        logger.info("Stopping Context OS System")
        logger.info("=" * 60)

        try:
            # Stop Pipeline (stops all adapters)
            if self.pipeline:
                logger.info("Stopping Pipeline...")
                self.pipeline.stop()

            # Close Inbox window
            if self.inbox:
                logger.info("Closing Inbox...")
                self.inbox.close()

            self.is_running = False

        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)

    def get_status(self) -> Dict[str, Any]:
        """
        Get system status information.

        Returns:
            dict: Status information including component states
        """
        status = {
            'is_running': self.is_running,
            'components': {
                'pipeline': self.pipeline is not None,
                'inbox': self.inbox is not None,
                'handler': self.handler is not None
            }
        }

        if self.pipeline:
            pipeline_status = self.pipeline.get_status()
            status['pipeline'] = pipeline_status

        if self.inbox:
            inbox_stats = self.inbox.get_stats()
            status['inbox'] = inbox_stats

        return status

    def _load_configuration(self):
        """Load system configuration from YAML files."""
        # Use path helper to get config path (handles both dev and bundled modes)
        system_config_path = get_config_path('system.yaml')

        try:
            with open(system_config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Loaded system config from: {system_config_path}")
        except Exception as e:
            logger.error(f"Failed to load system config: {e}")
            raise

    def _print_system_status(self):
        """Print current system status to log."""
        status = self.get_status()

        logger.info("=" * 60)
        logger.info("SYSTEM STATUS")
        logger.info(f"Running: {status['is_running']}")

        if 'pipeline' in status and isinstance(status['pipeline'], dict):
            pipeline_status = status['pipeline']
            logger.info(f"Pipeline:")
            logger.info(f"  Adapters: {pipeline_status.get('adapters', [])}")
            logger.info(f"  Queue: {pipeline_status.get('queue_size', 0)}/{pipeline_status.get('queue_max_size', 0)}")

        if 'inbox' in status and isinstance(status['inbox'], dict):
            inbox_stats = status['inbox']
            logger.info(f"Inbox:")
            logger.info(f"  Total sessions: {inbox_stats.get('total', 0)}")
            logger.info(f"  Active: {inbox_stats.get('active', 0)}")
            logger.info(f"  Completed: {inbox_stats.get('completed', 0)}")

        logger.info("=" * 60 + "\n")

    def update_handler_components(self):
        """
        Update Handler's engine component references after Pipeline reload.

        This method should be called after Pipeline.reload_engine_config() to ensure
        the Handler uses the new engine components (Detector, Classifier, ReactAgent)
        with updated LLM configuration.

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.handler or not self.pipeline:
            logger.error("Cannot update handler components: handler or pipeline not initialized")
            return False

        try:
            logger.info("Updating Handler's engine component references...")

            # Update handler's engine_components dictionary with new instances from Pipeline
            self.handler.engine_components = {
                'detector': self.pipeline.detector,
                'classifier': self.pipeline.classifier,
                'tool_executor': self.pipeline.tool_executor,
                'react_agent': self.pipeline.react_agent,
                'formatter': self.pipeline.formatter,
                'session_builder': self.pipeline.session_builder
            }

            logger.info("✓ Handler components updated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to update handler components: {e}")
            return False
