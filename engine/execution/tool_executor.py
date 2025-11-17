"""
Tool Executor for Context OS.

Simplified tool execution wrapper for ReAct Agent.
"""

from typing import Dict, Any
from utils.logger import get_logger

logger = get_logger('ToolExecutor')


class ToolExecutor:
    """
    ToolExecutor executes individual tool calls and returns observations.

    Responsibilities:
    - Execute single tool call via ToolManager
    - Return string observations for ReactAgent
    - Handle errors and timeouts gracefully
    - Extract text from various tool result formats
    """

    def __init__(self, tool_manager: Any):
        """
        Initialize the ToolExecutor.

        Args:
            tool_manager: ToolManager instance
        """
        self.tool_manager = tool_manager
        logger.info("ToolExecutor initialized")

    def execute(self, tool_name: str, params: Dict[str, Any]) -> str:
        """
        Execute a single tool and return observation string.

        Args:
            tool_name: Name of the tool to call
            params: Parameters for the tool

        Returns:
            str: Observation string (result or error message)
        """
        logger.info(f"Executing tool: {tool_name}")
        logger.debug(f"Parameters: {params}")

        try:
            # Check if tool exists and is enabled
            if not self.tool_manager.is_tool_enabled(tool_name):
                if tool_name in self.tool_manager.tools:
                    return f"Error: Tool '{tool_name}' is currently disabled. Please enable it in settings."
                else:
                    return f"Error: Tool '{tool_name}' not found."

            # Validate parameters
            if not self._validate_params(tool_name, params):
                return f"Error: Invalid parameters for tool '{tool_name}'"

            # Execute tool via ToolManager
            result = self.tool_manager.execute(tool_name, params)

            # Extract text from result
            observation = self._extract_text_from_result(result)

            logger.info(f"Tool '{tool_name}' executed successfully")
            logger.debug(f"Observation: {observation[:200]}...")

            return observation

        except TimeoutError as e:
            logger.error(f"Tool '{tool_name}' timed out: {e}")
            return self._handle_timeout(tool_name)

        except Exception as e:
            logger.error(f"Tool '{tool_name}' failed: {e}")
            return self._handle_error(e, tool_name)

    def _validate_params(self, tool_name: str, params: Dict[str, Any]) -> bool:
        """
        Validate parameters for a tool.

        Args:
            tool_name: Name of the tool
            params: Parameters to validate

        Returns:
            bool: True if valid, False otherwise
        """
        if not isinstance(params, dict):
            logger.warning(f"Parameters for '{tool_name}' must be a dict")
            return False

        # Get tool schema for validation
        tool = self.tool_manager.get(tool_name)
        if tool is None:
            logger.warning(f"Tool '{tool_name}' not found")
            return False

        # Basic validation passed
        return True

    def _extract_text_from_result(self, result: Any) -> str:
        """
        Extract displayable text from any result type (tool-agnostic).

        This method handles various result formats that tools may return,
        extracting the most relevant text for display to the user.

        Args:
            result: Result from tool execution (dict, string, or other)

        Returns:
            str: Extracted text suitable for observation
        """
        if isinstance(result, dict):
            # Try common field names (tool-agnostic approach)
            display_fields = ['translated_text', 'text', 'message', 'answer', 'result', 'value', 'content']
            for field in display_fields:
                if field in result:
                    return str(result[field])

            # Handle error dicts
            if 'error' in result:
                return f"Error: {result['error']}"

            # Fallback: format all key-value pairs (skip internal fields)
            formatted_pairs = []
            for key, value in result.items():
                if not key.startswith('_') and key not in ['success']:
                    formatted_pairs.append(f"{key}: {value}")

            return '\n'.join(formatted_pairs) if formatted_pairs else str(result)

        # For string or primitive types
        return str(result) if result is not None else 'No result'

    def _handle_error(self, error: Exception, tool_name: str) -> str:
        """
        Handle tool execution error.

        Args:
            error: Exception that occurred
            tool_name: Name of the tool that failed

        Returns:
            str: Error message for ReactAgent to observe
        """
        error_type = type(error).__name__
        error_message = str(error)

        observation = f"Error executing tool '{tool_name}': {error_type} - {error_message}"

        logger.error(observation)
        return observation

    def _handle_timeout(self, tool_name: str) -> str:
        """
        Handle tool execution timeout.

        Args:
            tool_name: Name of the tool that timed out

        Returns:
            str: Timeout message for ReactAgent to observe
        """
        observation = f"Tool '{tool_name}' execution timed out. The operation took too long to complete."

        logger.error(observation)
        return observation
