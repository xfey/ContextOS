"""
Tool Manager for Context OS.

Manages tool registration, execution, and lifecycle.
"""

import os
import yaml
import time
from typing import Dict, Any, List, Optional
from utils.logger import get_logger
from utils.path_helper import get_config_path

logger = get_logger('ToolManager')


class ToolManager:
    """
    ToolManager handles tool registration and execution.

    Features:
    - Register tools from configuration
    - Execute tools with parameter validation
    - Handle timeouts and errors
    - Provide tool schemas
    """

    def __init__(self):
        """Initialize the ToolManager."""
        self.tools: Dict[str, Any] = {}  # All loaded tools (enabled and disabled)
        self.tool_schemas: Dict[str, Dict[str, Any]] = {}
        self.enabled_tools: set = set()  # Track which tools are enabled
        self.tool_configs: Dict[str, Dict[str, Any]] = {}  # Store original configs
        self.config_path: Optional[str] = None  # Path to tools.yaml
        logger.info("ToolManager initialized")

    def register(self, tool: Any) -> None:
        """
        Register a tool instance.

        Args:
            tool: Tool instance to register (must have 'name' and 'execute' method)
        """
        if not hasattr(tool, 'name'):
            raise ValueError("Tool must have a 'name' attribute")

        if not hasattr(tool, 'execute'):
            raise ValueError("Tool must have an 'execute' method")

        name = tool.name
        self.tools[name] = tool

        # Get tool schema if available
        if hasattr(tool, 'get_schema'):
            self.tool_schemas[name] = tool.get_schema()

        logger.info(f"Tool registered: {name}")

    def get(self, tool_name: str) -> Optional[Any]:
        """
        Get a tool instance by name.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool instance or None if not found or disabled
        """
        tool = self.tools.get(tool_name)
        if tool is None:
            logger.warning(f"Tool not found: {tool_name}")
            return None

        # Check if tool is enabled
        if tool_name not in self.enabled_tools:
            logger.warning(f"Tool is disabled: {tool_name}")
            return None

        return tool

    def execute(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """
        Execute a tool with parameters.

        Args:
            tool_name: Name of the tool to execute
            params: Parameters to pass to the tool

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool not found
            Exception: If tool execution fails
        """
        logger.info(f"Executing tool: {tool_name}")
        logger.debug(f"Parameters: {params}")

        # Get tool
        tool = self.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")

        # Validate parameters
        if not self._validate_params(tool, params):
            raise ValueError(f"Invalid parameters for tool: {tool_name}")

        try:
            # Execute with timeout handling
            start_time = time.time()
            result = tool.execute(**params)
            execution_time = time.time() - start_time

            logger.info(f"Tool '{tool_name}' executed successfully in {execution_time:.2f}s")
            logger.debug(f"Result: {result}")

            return result

        except TimeoutError as e:
            logger.error(f"Tool '{tool_name}' execution timeout: {e}")
            self._handle_timeout(tool_name)
            raise

        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {e}")
            raise

    def _validate_params(self, tool: Any, params: Dict[str, Any]) -> bool:
        """
        Validate parameters against tool schema.

        Args:
            tool: Tool instance
            params: Parameters to validate

        Returns:
            bool: True if valid, False otherwise
        """
        # If tool has schema, validate against it
        if hasattr(tool, 'get_schema'):
            schema = tool.get_schema()
            required_params = schema.get('required', [])

            # Check required parameters
            for param in required_params:
                if param not in params:
                    logger.warning(f"Missing required parameter: {param}")
                    return False

            logger.debug("Parameter validation passed")
            return True

        # If no schema, assume valid
        logger.debug("No schema available, skipping validation")
        return True

    def _handle_timeout(self, tool_name: str) -> None:
        """
        Handle tool execution timeout.

        Args:
            tool_name: Name of the tool that timed out
        """
        logger.warning(f"Handling timeout for tool: {tool_name}")
        # In future, could implement cleanup, retry logic, etc.

    def list_tools(self, category: Optional[str] = None, include_disabled: bool = False) -> List[str]:
        """
        List registered tools, optionally filtered by category.

        Args:
            category: Optional category filter (e.g., 'builtin', 'custom')
            include_disabled: If True, include disabled tools. Default False.

        Returns:
            list: List of tool names
        """
        if include_disabled:
            tool_names = list(self.tools.keys())
        else:
            tool_names = list(self.enabled_tools)

        if category:
            # Filter by category if tool has category attribute
            filtered = []
            for name in tool_names:
                tool = self.tools[name]
                if hasattr(tool, 'category') and tool.category == category:
                    filtered.append(name)
            return filtered

        return tool_names

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the parameter schema for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            dict: Tool schema or None if not available
        """
        return self.tool_schemas.get(tool_name)

    def load_from_config(self, config_path: Optional[str] = None) -> None:
        """
        Load and register tools from tools.yaml configuration.

        Args:
            config_path: Path to tools.yaml. If None, uses default path.
        """
        if config_path is None:
            # Use path helper to get config path (handles both dev and bundled modes)
            config_path = get_config_path('tools.yaml')

        # Store config path for later updates
        self.config_path = config_path

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            tools_config = config.get('tools', [])
            logger.info(f"Loading {len(tools_config)} tools from configuration")

            for tool_config in tools_config:
                self._load_tool_from_config(tool_config)

            logger.info(f"Loaded {len(self.tools)} tools ({len(self.enabled_tools)} enabled)")

        except Exception as e:
            logger.error(f"Error loading tools from configuration: {e}")

    def _load_tool_from_config(self, tool_config: Dict[str, Any]) -> None:
        """
        Load and register a single tool from configuration.
        Now loads ALL tools (enabled and disabled) for dynamic management.

        Args:
            tool_config: Tool configuration dictionary
        """
        name = tool_config.get('name')
        tool_type = tool_config.get('type')
        enabled = tool_config.get('enabled', False)

        if not name:
            logger.error("Tool configuration missing 'name' field")
            return

        # Store the config for later reference
        self.tool_configs[name] = tool_config

        logger.info(f"Loading tool: {name} (type: {tool_type}, enabled: {enabled})")

        try:
            # Import and instantiate tool based on type and name
            tool_instance = self._create_tool_instance(tool_config)
            if tool_instance:
                self.register(tool_instance)
                # Add to enabled set if enabled in config
                if enabled:
                    self.enabled_tools.add(name)
            else:
                logger.warning(f"Failed to create tool instance for '{name}'")

        except Exception as e:
            logger.error(f"Error loading tool '{name}': {e}")

    def _create_tool_instance(self, tool_config: Dict[str, Any]) -> Optional[Any]:
        """
        Create a tool instance from configuration.

        Args:
            tool_config: Tool configuration

        Returns:
            Tool instance or None
        """
        name = tool_config.get('name')
        tool_type = tool_config.get('type')
        config = tool_config.get('config', {})

        try:
            if tool_type == 'builtin':
                # Import builtin tools
                if name == 'llm_query':
                    from integrations.tools.builtin.llm_query import LLMQueryTool
                    return LLMQueryTool(name, config)
                elif name == 'translator':
                    from integrations.tools.builtin.translator import TranslatorTool
                    return TranslatorTool(name, config)
                elif name == 'calculator':
                    from integrations.tools.builtin.calculator import CalculatorTool
                    return CalculatorTool(name, config)
                else:
                    logger.warning(f"Unknown builtin tool: {name}")
                    return None

            elif tool_type == 'custom':
                # Custom tools would be loaded from path
                # For Phase 3, we skip custom tools
                logger.info(f"Custom tool '{name}' skipped (not implemented in Phase 3)")
                return None

            else:
                logger.warning(f"Unknown tool type: {tool_type}")
                return None

        except ImportError as e:
            logger.error(f"Failed to import tool '{name}': {e}")
            return None

    def enable_tool(self, tool_name: str) -> bool:
        """
        Enable a tool at runtime.

        Args:
            tool_name: Name of the tool to enable

        Returns:
            bool: True if successful, False otherwise
        """
        if tool_name not in self.tools:
            logger.error(f"Cannot enable tool '{tool_name}': tool not found")
            return False

        if tool_name in self.enabled_tools:
            logger.info(f"Tool '{tool_name}' is already enabled")
            return True

        # Enable the tool
        self.enabled_tools.add(tool_name)
        logger.info(f"Tool '{tool_name}' enabled")

        # Update tools.yaml
        return self._update_tools_yaml(tool_name, True)

    def disable_tool(self, tool_name: str) -> bool:
        """
        Disable a tool at runtime.

        Args:
            tool_name: Name of the tool to disable

        Returns:
            bool: True if successful, False otherwise
        """
        if tool_name not in self.tools:
            logger.error(f"Cannot disable tool '{tool_name}': tool not found")
            return False

        if tool_name not in self.enabled_tools:
            logger.info(f"Tool '{tool_name}' is already disabled")
            return True

        # Disable the tool
        self.enabled_tools.discard(tool_name)
        logger.info(f"Tool '{tool_name}' disabled")

        # Update tools.yaml
        return self._update_tools_yaml(tool_name, False)

    def get_all_tools_status(self) -> List[Dict[str, Any]]:
        """
        Get status of all tools (enabled and disabled).

        Returns:
            list: List of dictionaries with tool information
        """
        tools_status = []
        for name, tool in self.tools.items():
            config = self.tool_configs.get(name, {})

            # Get description from tool schema
            description = 'No description available'
            if hasattr(tool, 'get_schema'):
                schema = tool.get_schema()
                description = schema.get('description', description)

            tool_info = {
                'name': name,
                'type': config.get('type', 'unknown'),
                'enabled': name in self.enabled_tools,
                'description': description,
                'category': getattr(tool, 'category', 'builtin')
            }
            tools_status.append(tool_info)

        return tools_status

    def is_tool_enabled(self, tool_name: str) -> bool:
        """
        Check if a tool is enabled.

        Args:
            tool_name: Name of the tool

        Returns:
            bool: True if enabled, False otherwise
        """
        return tool_name in self.enabled_tools

    def _update_tools_yaml(self, tool_name: str, enabled: bool) -> bool:
        """
        Update tools.yaml file with new enabled status.

        Args:
            tool_name: Name of the tool
            enabled: New enabled status

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.config_path:
            logger.error("Config path not set, cannot update tools.yaml")
            return False

        try:
            # Read current config
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Update the tool's enabled status
            tools_config = config.get('tools', [])
            updated = False
            for tool_config in tools_config:
                if tool_config.get('name') == tool_name:
                    tool_config['enabled'] = enabled
                    updated = True
                    break

            if not updated:
                logger.error(f"Tool '{tool_name}' not found in config file")
                return False

            # Write back to file
            with open(self.config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Updated tools.yaml: {tool_name} enabled={enabled}")
            return True

        except Exception as e:
            logger.error(f"Error updating tools.yaml: {e}")
            return False

    def update_tool_config(self, tool_name: str, config_key: str, value: Any) -> bool:
        """
        Update a specific configuration field for a tool and persist to tools.yaml.

        This method updates the tool's configuration in memory, persists it to tools.yaml,
        and reloads the tool instance if needed.

        Args:
            tool_name: Name of the tool
            config_key: Configuration key to update (e.g., 'target_lang', 'precision')
            value: New value for the configuration key

        Returns:
            bool: True if successful, False otherwise
        """
        # Validate tool exists
        if tool_name not in self.tools:
            logger.error(f"Cannot update config for tool '{tool_name}': tool not found")
            return False

        try:
            logger.info(f"Updating tool config: {tool_name}.{config_key}={value}")

            # Update in-memory config
            if tool_name not in self.tool_configs:
                self.tool_configs[tool_name] = {'config': {}}
            if 'config' not in self.tool_configs[tool_name]:
                self.tool_configs[tool_name]['config'] = {}

            self.tool_configs[tool_name]['config'][config_key] = value

            # Persist to tools.yaml
            if not self._update_tool_config_in_yaml(tool_name, config_key, value):
                logger.error(f"Failed to persist config for tool '{tool_name}' to tools.yaml")
                return False

            # Reload tool instance with new config
            if not self.reload_tool(tool_name):
                logger.warning(f"Failed to reload tool '{tool_name}' after config update")
                # Note: Config is still persisted, so this is not a critical failure

            logger.info(f"✓ Tool config updated: {tool_name}.{config_key}={value}")
            return True

        except Exception as e:
            logger.error(f"Error updating tool config for '{tool_name}': {e}")
            return False

    def reload_tool(self, tool_name: str) -> bool:
        """
        Reload a tool instance with updated configuration.

        This recreates the tool instance with the current configuration from tool_configs.

        Args:
            tool_name: Name of the tool to reload

        Returns:
            bool: True if successful, False otherwise
        """
        if tool_name not in self.tools:
            logger.error(f"Cannot reload tool '{tool_name}': tool not found")
            return False

        if tool_name not in self.tool_configs:
            logger.error(f"Cannot reload tool '{tool_name}': config not found")
            return False

        try:
            logger.info(f"Reloading tool: {tool_name}")

            # Get current config
            tool_config = self.tool_configs[tool_name]

            # Create new tool instance with updated config
            new_tool_instance = self._create_tool_instance(tool_config)

            if new_tool_instance is None:
                logger.error(f"Failed to reload tool '{tool_name}'")
                return False

            # Replace the old instance with the new one
            self.tools[tool_name] = new_tool_instance

            logger.info(f"✓ Tool '{tool_name}' reloaded successfully")
            return True

        except Exception as e:
            logger.error(f"Error reloading tool '{tool_name}': {e}")
            return False

    def _update_tool_config_in_yaml(self, tool_name: str, config_key: str, value: Any) -> bool:
        """
        Update a specific tool's config field in tools.yaml file.

        Args:
            tool_name: Name of the tool
            config_key: Configuration key to update
            value: New value for the configuration key

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.config_path:
            logger.error("Config path not set, cannot update tools.yaml")
            return False

        try:
            # Read current config
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Find and update the tool's config field
            tools_config = config.get('tools', [])
            updated = False
            for tool_config in tools_config:
                if tool_config.get('name') == tool_name:
                    if 'config' not in tool_config:
                        tool_config['config'] = {}
                    tool_config['config'][config_key] = value
                    updated = True
                    break

            if not updated:
                logger.error(f"Tool '{tool_name}' not found in config file")
                return False

            # Write back to file
            with open(self.config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Updated tools.yaml: {tool_name}.config.{config_key}={value}")
            return True

        except Exception as e:
            logger.error(f"Error updating tools.yaml for tool '{tool_name}': {e}")
            return False
