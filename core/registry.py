"""
Component registry for Context OS.

Provides centralized component registration and management with lazy loading and singleton pattern.
"""

import os
import yaml
from typing import Dict, Any, List, Optional, Type
from utils.logger import get_logger

logger = get_logger('Registry')


class Registry:
    """
    Component registry with lazy loading and singleton pattern.

    Manages registration and retrieval of components (adapters, tools, etc.)
    from configuration files.
    """

    def __init__(self):
        """Initialize the registry."""
        self._components: Dict[str, Dict[str, Any]] = {}
        self._instances: Dict[str, Any] = {}  # Singleton instances cache
        self._config_loaded: bool = False

    def register(self, config: Dict[str, Any]) -> None:
        """
        Register a component from configuration.

        Args:
            config: Component configuration dictionary containing:
                   - name: Component name
                   - type: Component type
                   - enabled: Whether component is enabled
                   - config: Component-specific configuration
                   - Other fields as needed
        """
        if 'name' not in config:
            logger.error("Component configuration must include 'name' field")
            raise ValueError("Component configuration must include 'name' field")

        name = config['name']
        self._components[name] = config
        logger.info(f"Registered component: {name}")

    def get(self, name: str) -> Optional[Any]:
        """
        Get component instance with lazy loading and singleton pattern.

        Args:
            name: Component name

        Returns:
            Component instance if found and enabled, None otherwise
        """
        # Check if component exists
        if name not in self._components:
            logger.warning(f"Component '{name}' not found in registry")
            return None

        # Check if component is enabled
        if not self._components[name].get('enabled', False):
            logger.warning(f"Component '{name}' is disabled")
            return None

        # Return cached instance if exists (singleton pattern)
        if name in self._instances:
            logger.debug(f"Returning cached instance for component: {name}")
            return self._instances[name]

        # Lazy loading: create instance on first access
        logger.info(f"Creating new instance for component: {name}")
        instance = self._create_instance(name)

        if instance is not None:
            self._instances[name] = instance

        return instance

    def _create_instance(self, name: str) -> Optional[Any]:
        """
        Create a new instance of a component (to be extended in future phases).

        Args:
            name: Component name

        Returns:
            Component instance or None
        """
        # In Phase 1, we just return the configuration
        # In later phases, this will instantiate actual component classes
        logger.debug(f"Lazy loading for component '{name}' - returning configuration")
        return self._components[name]

    def list_by_type(self, component_type: str) -> List[Dict[str, Any]]:
        """
        List components by type.

        Args:
            component_type: Type of components to list (e.g., 'event', 'stream', 'builtin', 'custom')

        Returns:
            List of component configurations matching the type
        """
        matching_components = [
            config for config in self._components.values()
            if config.get('type') == component_type
        ]

        logger.debug(f"Found {len(matching_components)} components of type '{component_type}'")
        return matching_components

    def load_config_file(self, config_path: str, config_key: Optional[str] = None) -> None:
        """
        Load components from a YAML configuration file.

        Args:
            config_path: Path to the YAML configuration file
            config_key: Optional key to extract from config (e.g., 'adapters', 'tools')
        """
        try:
            if not os.path.exists(config_path):
                logger.error(f"Configuration file not found: {config_path}")
                raise FileNotFoundError(f"Configuration file not found: {config_path}")

            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)

            # Extract specific key if provided
            if config_key:
                components = config_data.get(config_key, [])
            else:
                components = config_data

            # Register each component
            if isinstance(components, list):
                for component_config in components:
                    self.register(component_config)
            else:
                logger.warning(f"Expected list of components in config, got {type(components)}")

            logger.info(f"Loaded configuration from: {config_path}")

        except Exception as e:
            logger.error(f"Error loading configuration file {config_path}: {e}")
            raise

    def load_all_configs(self, config_dir: Optional[str] = None) -> None:
        """
        Load all configuration files (sources.yaml and tools.yaml).

        Args:
            config_dir: Configuration directory path. If None, uses default 'config/' directory
        """
        if config_dir is None:
            # Get default config directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            config_dir = os.path.join(project_root, 'config')

        # Load sources configuration
        sources_path = os.path.join(config_dir, 'sources.yaml')
        if os.path.exists(sources_path):
            self.load_config_file(sources_path, config_key='adapters')
        else:
            logger.warning(f"Sources configuration file not found: {sources_path}")

        # Load tools configuration
        tools_path = os.path.join(config_dir, 'tools.yaml')
        if os.path.exists(tools_path):
            self.load_config_file(tools_path, config_key='tools')
        else:
            logger.warning(f"Tools configuration file not found: {tools_path}")

        self._config_loaded = True
        logger.info("All configuration files loaded successfully")

    def get_all_components(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all registered components.

        Returns:
            Dictionary of all registered components
        """
        return self._components.copy()

    def get_enabled_components(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all enabled components.

        Returns:
            Dictionary of enabled components
        """
        return {
            name: config
            for name, config in self._components.items()
            if config.get('enabled', False)
        }
