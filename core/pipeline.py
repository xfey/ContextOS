"""
Data pipeline for Context OS.

Manages adapter registration, signal routing, and queue processing.
"""

import os
import threading
import queue
import yaml
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.signal import Signal
from utils.logger import get_logger
from utils.path_helper import get_config_path

# Phase 3: Import Engine components
from engine.intent.detector import Detector
from engine.intent.classifier import Classifier
from engine.execution.react_agent import ReactAgent
from engine.execution.tool_executor import ToolExecutor
from engine.output.formatter import Formatter
from engine.output.sessionbuilder import SessionBuilder
from integrations.tools.manager import ToolManager

logger = get_logger('Pipeline')


class Pipeline:
    """
    Data pipeline that manages adapters and routes signals.

    The pipeline:
    1. Registers adapters from configuration
    2. Manages a queue of incoming signals
    3. Routes signals to the Engine layer for processing
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the pipeline.

        Args:
            config_path: Path to system.yaml config file. If None, uses default path.
        """
        # Store the config path for later updates (needed for bundled apps)
        self.system_config_path: Optional[str] = None

        # Load configuration
        self.config = self._load_config(config_path)

        # Get queue size from config
        queue_size = self.config.get('pipeline', {}).get('queue_size', 100)
        self.signal_queue = queue.Queue(maxsize=queue_size)

        # Adapter registry
        self.adapters: Dict[str, Any] = {}

        # Adapter management (similar to ToolManager)
        self.enabled_adapters: set = set()           # Track which adapters are enabled
        self.adapter_configs: Dict[str, Dict] = {}   # Store original adapter configs
        self.sources_config_path: Optional[str] = None  # Path to sources.yaml for updates

        # Processing state
        self.is_running = False
        self.processing_thread = None

        # Phase 4: Inbox reference for sending sessions
        self.inbox = None

        # Phase 3: Initialize Engine components
        self._init_engine_components()

        logger.info(f"Pipeline initialized with queue size: {queue_size}")

    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load system configuration.

        Args:
            config_path: Path to system.yaml config file

        Returns:
            dict: Configuration data
        """
        if config_path is None:
            # Use path helper to get config path (handles both dev and bundled modes)
            config_path = get_config_path('system.yaml')

        # Store the config path for later updates
        self.system_config_path = config_path

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from: {config_path}")
            return config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return {}

    def _init_engine_components(self) -> None:
        """
        Initialize Engine components for Phase 3.

        Creates instances of:
        - ToolManager
        - Detector
        - Classifier
        - ToolExecutor
        - ReactAgent
        - Formatter
        - SessionBuilder
        """
        try:
            logger.info("Initializing Engine components...")

            # Get configurations
            engine_config = self.config.get('engine', {})
            session_config = self.config.get('session', {})
            user_config = self.config.get('user', {})

            # Initialize ToolManager and load tools
            self.tool_manager = ToolManager()
            self.tool_manager.load_from_config()
            logger.info(f"ToolManager initialized with {len(self.tool_manager.tools)} tools")

            # Initialize Intent subsystem (pass user_config for language awareness)
            self.detector = Detector(engine_config, user_config)
            self.classifier = Classifier(session_config, engine_config)
            logger.info("Intent subsystem initialized")

            # Initialize Execution subsystem (ReAct-based, pass user_config for language awareness)
            self.tool_executor = ToolExecutor(self.tool_manager)
            self.react_agent = ReactAgent(engine_config, self.tool_executor, self.tool_manager, user_config)
            logger.info("Execution subsystem initialized (ReAct Agent)")

            # Initialize Output subsystem
            self.formatter = Formatter()
            self.session_builder = SessionBuilder(session_config)
            logger.info("Output subsystem initialized")

            logger.info("✓ All Engine components initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing Engine components: {e}")
            # Create dummy components to prevent errors
            self.tool_manager = None
            self.detector = None
            self.classifier = None
            self.tool_executor = None
            self.react_agent = None
            self.formatter = None
            self.session_builder = None

    def register_adapter(self, config: Dict[str, Any]) -> None:
        """
        Register an adapter from configuration.

        Args:
            config: Adapter configuration dictionary containing:
                   - name: Adapter name
                   - type: Adapter type (event/stream)
                   - enabled: Whether adapter is enabled
                   - config: Adapter-specific configuration
        """
        name = config.get('name')
        adapter_type = config.get('type')
        enabled = config.get('enabled', False)

        if not name:
            logger.error("Adapter configuration missing 'name' field")
            return

        logger.info(f"Registering adapter: {name} (type: {adapter_type}, enabled: {enabled})")

        # Store adapter configuration for later reference
        self.adapter_configs[name] = config

        # Import and instantiate adapter (regardless of enabled status)
        try:
            adapter_instance = self._create_adapter_instance(config)
            if adapter_instance:
                self.adapters[name] = adapter_instance
                logger.info(f"Adapter '{name}' registered successfully")

                # Track enabled status separately
                if enabled:
                    self.enabled_adapters.add(name)
                    logger.info(f"Adapter '{name}' marked as enabled")
            else:
                logger.warning(f"Failed to create adapter instance for '{name}'")

        except Exception as e:
            logger.error(f"Error registering adapter '{name}': {e}")

    def _create_adapter_instance(self, config: Dict[str, Any]) -> Optional[Any]:
        """
        Create adapter instance based on configuration.

        Args:
            config: Adapter configuration

        Returns:
            Adapter instance or None
        """
        name = config.get('name')
        adapter_type = config.get('type')
        adapter_config = config.get('config', {})

        # Import appropriate adapter class
        try:
            if name == 'clipboard':
                from adapters.events.clipboard import ClipboardAdapter
                return ClipboardAdapter(name, adapter_config, self.route_signal)

            elif name == 'screenshot':
                # StreamAdapter placeholder for future implementation
                logger.warning(f"Screenshot adapter not yet implemented")
                return None
                # from adapters.stream.screenshot import ScreenshotAdapter
                # return ScreenshotAdapter(name, adapter_config, self.route_signal)

            else:
                logger.warning(f"Unknown adapter: {name}")
                return None

        except ImportError as e:
            logger.error(f"Failed to import adapter '{name}': {e}")
            return None

    def load_adapters_from_config(self, sources_config_path: Optional[str] = None) -> None:
        """
        Load and register adapters from sources.yaml configuration file.

        Args:
            sources_config_path: Path to sources.yaml. If None, uses default path.
        """
        if sources_config_path is None:
            # Use path helper to get config path (handles both dev and bundled modes)
            sources_config_path = get_config_path('sources.yaml')

        # Store config path for later updates
        self.sources_config_path = sources_config_path

        try:
            with open(sources_config_path, 'r') as f:
                sources_config = yaml.safe_load(f)

            adapters_config = sources_config.get('adapters', [])
            logger.info(f"Loading {len(adapters_config)} adapters from configuration")

            for adapter_config in adapters_config:
                self.register_adapter(adapter_config)

            enabled_count = len(self.enabled_adapters)
            total_count = len(self.adapters)
            logger.info(f"Loaded {total_count} adapters ({enabled_count} enabled, {total_count - enabled_count} disabled)")

        except Exception as e:
            logger.error(f"Error loading adapters from configuration: {e}")

    def start(self) -> None:
        """
        Start the pipeline.

        Starts all registered adapters and begins signal processing.
        """
        if self.is_running:
            logger.warning("Pipeline is already running")
            return

        logger.info("Starting pipeline...")
        self.is_running = True

        # Start signal processing thread
        self.processing_thread = threading.Thread(target=self._process_signals, daemon=True)
        self.processing_thread.start()
        logger.info("Signal processing thread started")

        # Start only enabled adapters
        for name, adapter in self.adapters.items():
            if name in self.enabled_adapters:
                try:
                    logger.info(f"Starting adapter: {name}")
                    adapter.start()
                except Exception as e:
                    logger.error(f"Error starting adapter '{name}': {e}")
            else:
                logger.debug(f"Skipping disabled adapter: {name}")

        enabled_count = len(self.enabled_adapters)
        logger.info(f"Pipeline started with {enabled_count} enabled adapters (out of {len(self.adapters)} total)")

    def stop(self) -> None:
        """
        Stop the pipeline.

        Stops all adapters and signal processing.
        """
        if not self.is_running:
            logger.warning("Pipeline is not running")
            return

        logger.info("Stopping pipeline...")
        self.is_running = False

        # Stop all adapters
        for name, adapter in self.adapters.items():
            try:
                logger.info(f"Stopping adapter: {name}")
                adapter.stop()
            except Exception as e:
                logger.error(f"Error stopping adapter '{name}': {e}")

        # Wait for processing thread to finish
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=2)
            logger.info("Signal processing thread stopped")

        logger.info("Pipeline stopped")

    def set_inbox(self, inbox):
        """
        Set the inbox reference for sending sessions.

        Args:
            inbox: Inbox instance to send sessions to
        """
        self.inbox = inbox
        logger.info("Inbox connected to Pipeline")

    def route_signal(self, signal: Signal) -> None:
        """
        Route a signal from an adapter to the Engine.

        This method is called by adapters when they emit signals.
        For Phase 2, it adds signals to the queue for processing.

        Args:
            signal: Signal object to route
        """
        try:
            # Try to add signal to queue (non-blocking with timeout)
            self.signal_queue.put(signal, block=True, timeout=1.0)
            logger.debug(f"Signal queued: {signal.metadata.get('uuid')} from {signal.source}")

        except queue.Full:
            logger.warning(f"Signal queue is full, dropping signal from {signal.source}")

        except Exception as e:
            logger.error(f"Error routing signal: {e}")

    def _process_signals(self) -> None:
        """
        Process signals from the queue.

        This runs in a separate thread and processes signals as they arrive.
        For Phase 2, it logs the signals (Engine integration in Phase 3).
        """
        logger.info("Signal processing started")

        while self.is_running:
            try:
                # Get signal from queue (with timeout to allow checking is_running)
                signal = self.signal_queue.get(block=True, timeout=0.5)

                # Process the signal
                self._handle_signal(signal)

                # Mark task as done
                self.signal_queue.task_done()

            except queue.Empty:
                # No signal available, continue loop
                continue

            except Exception as e:
                logger.error(f"Error processing signal: {e}")

        logger.info("Signal processing stopped")

    def _handle_signal(self, signal: Signal) -> None:
        """
        Handle a signal from the queue.

        Phase 3: Routes signal through Engine pipeline:
        Signal → Intent → Execution → Session

        Step 2 (Classification) and Step 3 (ReAct) run in parallel for better performance.

        Args:
            signal: Signal to handle
        """
        logger.info("=" * 60)
        logger.info("SIGNAL RECEIVED")
        logger.info("=" * 60)
        logger.info(f"Source: {signal.source}")
        logger.info(f"Type: {signal.type}")
        logger.info(f"Content: {signal.content}")
        logger.info(f"UUID: {signal.metadata.get('uuid')}")
        logger.info(f"Timestamp: {signal.metadata.get('timestamp')}")
        logger.info("=" * 60)

        # Phase 3: Route through Engine pipeline
        try:
            # Check if Engine components are initialized
            if not all([self.detector, self.classifier, self.react_agent, self.formatter, self.session_builder]):
                logger.error("Engine components not initialized, skipping signal processing")
                return

            # Step 1: Detect intent from signal
            intent = self.detector.detect(signal)

            # Check if no intent was detected
            if intent is None:
                logger.info("✓ Step 1: No actionable intent detected - skipping signal processing")
                logger.info("=" * 60)
                logger.info("SIGNAL PROCESSING SKIPPED (NO INTENT)")
                logger.info("=" * 60)
                return

            logger.info(f"✓ Step 1: Intent detected: {intent.target}")

            # Steps 2 & 3: Run Classification and ReAct in parallel
            logger.info("Starting Step 2 (Classification) and Step 3 (ReAct) in parallel...")

            level = None
            react_result = None

            with ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both tasks
                future_classify = executor.submit(self.classifier.classify, intent)
                future_react = executor.submit(self.react_agent.execute, intent)

                # Wait for both to complete and collect results
                for future in as_completed([future_classify, future_react]):
                    if future == future_classify:
                        level = future.result()
                        logger.info(f"✓ Step 2: Level classified: {level}")
                    elif future == future_react:
                        react_result = future.result()
                        logger.info(f"✓ Step 3: ReAct loop completed")

            # Step 4: Format results
            formatted_content = self.formatter.format(react_result, intent)
            logger.info(f"✓ Step 4: Results formatted")

            # Step 5: Build session
            session = self.session_builder.build(formatted_content)
            logger.info(f"✓ Step 5: Session built: {session.metadata.get('uuid')}")

            # Phase 4: Send session to Inbox
            if self.inbox:
                self.inbox.add_session(session)
                logger.info("✓ Step 6: Session sent to Inbox")
            else:
                # Fallback: Log session if no inbox configured
                logger.warning("No inbox configured, logging session instead")
                self._log_session(session)

            logger.info("=" * 60)
            logger.info("SESSION PROCESSING COMPLETE")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error processing signal through Engine: {e}", exc_info=True)

    def _log_session(self, session) -> None:
        """
        Log session details for Phase 3 validation.

        Args:
            session: Session object to log
        """
        logger.info("=" * 60)
        logger.info("SESSION DETAILS")
        logger.info(f"UUID: {session.metadata.get('uuid')}")
        logger.info(f"Level: {session.level}")
        logger.info(f"Title: {session.title}")
        logger.info("=" * 60)

    def get_status(self) -> Dict[str, Any]:
        """
        Get pipeline status information.

        Returns:
            dict: Status information including adapter count, queue size, etc.
        """
        return {
            'is_running': self.is_running,
            'adapters_count': len(self.adapters),
            'adapters': list(self.adapters.keys()),
            'enabled_adapters': list(self.enabled_adapters),
            'queue_size': self.signal_queue.qsize(),
            'queue_max_size': self.signal_queue.maxsize
        }

    def enable_adapter(self, adapter_name: str) -> bool:
        """
        Enable an adapter at runtime.

        Args:
            adapter_name: Name of the adapter to enable

        Returns:
            bool: True if successful, False otherwise
        """
        # Validate adapter exists
        if adapter_name not in self.adapters:
            logger.error(f"Cannot enable adapter '{adapter_name}': adapter not found")
            return False

        # Check if already enabled
        if adapter_name in self.enabled_adapters:
            logger.info(f"Adapter '{adapter_name}' is already enabled")
            return True

        try:
            # Add to enabled set
            self.enabled_adapters.add(adapter_name)
            logger.info(f"Adapter '{adapter_name}' enabled")

            # Start the adapter if pipeline is running
            if self.is_running:
                adapter = self.adapters[adapter_name]
                adapter.start()
                logger.info(f"Adapter '{adapter_name}' started")

            # Persist to sources.yaml
            return self._update_sources_yaml(adapter_name, True)

        except Exception as e:
            logger.error(f"Error enabling adapter '{adapter_name}': {e}")
            # Revert on error
            self.enabled_adapters.discard(adapter_name)
            return False

    def disable_adapter(self, adapter_name: str) -> bool:
        """
        Disable an adapter at runtime.

        Args:
            adapter_name: Name of the adapter to disable

        Returns:
            bool: True if successful, False otherwise
        """
        # Validate adapter exists
        if adapter_name not in self.adapters:
            logger.error(f"Cannot disable adapter '{adapter_name}': adapter not found")
            return False

        # Check if already disabled
        if adapter_name not in self.enabled_adapters:
            logger.info(f"Adapter '{adapter_name}' is already disabled")
            return True

        try:
            # Stop the adapter if pipeline is running
            if self.is_running:
                adapter = self.adapters[adapter_name]
                adapter.stop()
                logger.info(f"Adapter '{adapter_name}' stopped")

            # Remove from enabled set
            self.enabled_adapters.discard(adapter_name)
            logger.info(f"Adapter '{adapter_name}' disabled")

            # Persist to sources.yaml
            return self._update_sources_yaml(adapter_name, False)

        except Exception as e:
            logger.error(f"Error disabling adapter '{adapter_name}': {e}")
            # Revert on error if was running
            if self.is_running:
                self.enabled_adapters.add(adapter_name)
            return False

    def is_adapter_enabled(self, adapter_name: str) -> bool:
        """
        Check if an adapter is enabled.

        Args:
            adapter_name: Name of the adapter

        Returns:
            bool: True if enabled, False otherwise
        """
        return adapter_name in self.enabled_adapters

    def get_all_adapters_status(self) -> List[Dict[str, Any]]:
        """
        Get status of all adapters (both enabled and disabled).

        Returns:
            list: List of adapter info dictionaries
        """
        adapters_status = []

        for name, adapter in self.adapters.items():
            config = self.adapter_configs.get(name, {})

            # Get description from adapter config
            adapter_config = config.get('config', {})
            description = f"{config.get('type', 'unknown').capitalize()} adapter"

            # Add more specific descriptions
            if name == 'clipboard':
                description = "Monitors clipboard changes for text, images, and files"
            elif name == 'screenshot':
                description = "Captures screenshots at regular intervals"

            adapter_info = {
                'name': name,
                'type': config.get('type', 'unknown'),
                'enabled': name in self.enabled_adapters,
                'description': description,
                'is_running': adapter.is_running if hasattr(adapter, 'is_running') else False
            }
            adapters_status.append(adapter_info)

        return adapters_status

    def _update_sources_yaml(self, adapter_name: str, enabled: bool) -> bool:
        """
        Update sources.yaml file with new enabled status.

        Args:
            adapter_name: Name of the adapter
            enabled: New enabled status

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.sources_config_path:
            logger.error("sources_config_path not set, cannot update configuration")
            return False

        try:
            # Read current configuration
            with open(self.sources_config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Find and update the adapter's enabled status
            adapters_config = config.get('adapters', [])
            updated = False

            for adapter_config in adapters_config:
                if adapter_config.get('name') == adapter_name:
                    adapter_config['enabled'] = enabled
                    updated = True
                    break

            if not updated:
                logger.error(f"Adapter '{adapter_name}' not found in configuration file")
                return False

            # Write back to file
            with open(self.sources_config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Updated sources.yaml: {adapter_name} enabled={enabled}")
            return True

        except Exception as e:
            logger.error(f"Error updating sources.yaml: {e}")
            return False

    def reload_engine_config(self, new_engine_config: Dict[str, Any]) -> bool:
        """
        Reload engine configuration and reinitialize LLM-dependent components.

        This method allows hot-reloading of LLM settings without restarting the application.
        It recreates Detector, Classifier, and ReactAgent with the new configuration.

        Args:
            new_engine_config: New engine configuration dict with llm_provider, llm_model,
                             llm_base_url, llm_api_key, and other engine settings

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("Reloading engine configuration...")
            logger.info(f"New LLM settings: provider={new_engine_config.get('llm_provider')}, "
                       f"model={new_engine_config.get('llm_model')}")

            # Store old config in case we need to rollback
            old_engine_config = self.config.get('engine', {})

            # Update config with new engine settings
            self.config['engine'] = new_engine_config

            # Reinitialize engine components with new config
            session_config = self.config.get('session', {})
            user_config = self.config.get('user', {})

            # Recreate components (ToolManager and ToolExecutor can be reused)
            self.detector = Detector(new_engine_config, user_config)
            logger.info("✓ Detector reinitialized")

            self.classifier = Classifier(session_config, new_engine_config)
            logger.info("✓ Classifier reinitialized")

            self.react_agent = ReactAgent(new_engine_config, self.tool_executor, self.tool_manager, user_config)
            logger.info("✓ ReactAgent reinitialized")

            # Persist to system.yaml
            if not self._update_system_yaml(new_engine_config):
                logger.warning("Failed to persist engine config to system.yaml, but runtime update succeeded")

            logger.info("✓ Engine configuration reloaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to reload engine config: {e}", exc_info=True)

            # Attempt rollback to old config
            try:
                logger.warning("Attempting to rollback to old configuration...")
                self.config['engine'] = old_engine_config
                user_config = self.config.get('user', {})
                self.detector = Detector(old_engine_config, user_config)
                self.classifier = Classifier(session_config, old_engine_config)
                self.react_agent = ReactAgent(old_engine_config, self.tool_executor, self.tool_manager, user_config)
                logger.info("✓ Rolled back to old configuration")
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")

            return False

    def _update_system_yaml(self, new_engine_config: Dict[str, Any]) -> bool:
        """
        Update system.yaml file with new engine configuration.

        Args:
            new_engine_config: New engine configuration dict

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Use the stored config path (important for bundled apps)
            system_yaml_path = self.system_config_path
            if not system_yaml_path:
                # Fallback: use path helper to get config path
                system_yaml_path = get_config_path('system.yaml')
                logger.warning("system_config_path not set, using fallback path")

            # Read current configuration
            with open(system_yaml_path, 'r') as f:
                config = yaml.safe_load(f)

            # Update engine section
            config['engine'] = new_engine_config

            # Write back to file atomically
            with open(system_yaml_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Updated system.yaml at: {system_yaml_path}")
            return True

        except Exception as e:
            logger.error(f"Error updating system.yaml: {e}")
            return False

    def get_engine_config(self) -> Dict[str, Any]:
        """
        Get current engine configuration.

        Returns:
            dict: Current engine configuration
        """
        return self.config.get('engine', {}).copy()

    def get_user_config(self) -> Dict[str, Any]:
        """
        Get current user configuration.

        Returns:
            dict: Current user configuration
        """
        return self.config.get('user', {}).copy()

    def update_user_config(self, key: str, value: Any) -> bool:
        """
        Update a user configuration field and persist to system.yaml.

        Args:
            key: Configuration key (e.g., 'default_language')
            value: New value for the configuration key

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Updating user config: {key}={value}")

            # Update in-memory config
            if 'user' not in self.config:
                self.config['user'] = {}
            self.config['user'][key] = value

            # Persist to system.yaml
            if not self._update_user_section_yaml(self.config['user']):
                logger.error("Failed to persist user config to system.yaml")
                return False

            logger.info(f"✓ User config updated: {key}={value}")
            return True

        except Exception as e:
            logger.error(f"Error updating user config: {e}")
            return False

    def _update_user_section_yaml(self, user_config: Dict[str, Any]) -> bool:
        """
        Update the 'user' section in system.yaml file.

        Args:
            user_config: Complete user configuration dict

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Use the stored config path (important for bundled apps)
            system_yaml_path = self.system_config_path
            if not system_yaml_path:
                # Fallback: use path helper to get config path
                system_yaml_path = get_config_path('system.yaml')
                logger.warning("system_config_path not set, using fallback path")

            # Read current configuration
            with open(system_yaml_path, 'r') as f:
                config = yaml.safe_load(f)

            # Update user section
            config['user'] = user_config

            # Write back to file atomically
            with open(system_yaml_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Updated system.yaml user section at: {system_yaml_path}")
            return True

        except Exception as e:
            logger.error(f"Error updating system.yaml user section: {e}")
            return False

    def sync_language_to_translator(self, language: str) -> bool:
        """
        Synchronize default language to translator tool's target_lang.

        This ensures the translator tool uses the system-wide default language.

        Args:
            language: Language name (e.g., 'Chinese', 'English')

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Syncing language '{language}' to translator tool")

            # Update translator tool config via ToolManager
            if not self.tool_manager:
                logger.error("ToolManager not available, cannot sync language")
                return False

            # Update the translator tool's target_lang config
            success = self.tool_manager.update_tool_config('translator', 'target_lang', language)

            if success:
                logger.info(f"✓ Translator tool synced to language: {language}")
            else:
                logger.error(f"Failed to sync translator tool to language: {language}")

            return success

        except Exception as e:
            logger.error(f"Error syncing language to translator: {e}")
            return False

    def reload_user_config(self) -> bool:
        """
        Reload user configuration in Detector and ReactAgent.

        This method updates the user configuration in components that depend on it,
        such as Detector and ReactAgent (for language preferences).

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("Reloading user configuration in engine components...")

            # Get current user config
            user_config = self.config.get('user', {})
            logger.info(f"User config: default_language={user_config.get('default_language', 'Chinese')}")

            # Update Detector
            if self.detector:
                self.detector.update_user_config(user_config)
                logger.info("✓ Detector user config updated")
            else:
                logger.warning("Detector not available, skipping update")

            # Update ReactAgent
            if self.react_agent:
                self.react_agent.update_user_config(user_config)
                logger.info("✓ ReactAgent user config updated")
            else:
                logger.warning("ReactAgent not available, skipping update")

            logger.info("✓ User configuration reloaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to reload user config: {e}", exc_info=True)
            return False
