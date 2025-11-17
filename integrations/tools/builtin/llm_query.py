"""
LLM Query Tool for Context OS.

A builtin tool that queries the LLM for reasoning, synthesis, or general tasks.
This tool enables dynamic LLM calls as part of execution plans.
"""

from typing import Dict, Any, Optional, List
from utils.logger import get_logger
from utils.llm_client import LLMClient

logger = get_logger('LLMQueryTool')


class LLMQueryTool:
    """
    LLMQueryTool enables LLM queries as a registered tool.

    This tool is used for:
    - General reasoning tasks
    - Synthesizing information from multiple sources
    - Processing user requests that don't map to specific tools
    - Fallback handling when no specific tool is available
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize the LLM Query tool.

        Args:
            name: Tool name (should be 'llm_query')
            config: Tool configuration from tools.yaml
        """
        self.name = name
        self.category = 'builtin'
        self.config = config

        # Tool-specific settings with defaults
        self.temperature = config.get('temperature', 0.2)
        self.max_tokens = config.get('max_tokens', None)

        # Initialize LLM client with system config
        # The tool config should include engine config for LLM access
        engine_config = config.get('engine_config', {})
        if not engine_config:
            # Try to load from system config if not provided
            import os
            import yaml
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                'config', 'system.yaml'
            )
            try:
                with open(config_path, 'r') as f:
                    system_config = yaml.safe_load(f)
                    engine_config = system_config.get('engine', {})
            except Exception as e:
                logger.warning(f"Could not load system config: {e}")
                engine_config = {}

        # Initialize unified LLM client
        self.llm_client = LLMClient(engine_config)

        logger.info(f"LLMQueryTool '{name}' initialized (model: {self.llm_client.get_model()})")

    def execute(self, prompt: str) -> str:
        """
        Execute an LLM query.

        Args:
            prompt: The prompt/query to send to the LLM

        Returns:
            str: LLM response text

        Raises:
            ValueError: If prompt is empty or invalid
            Exception: If LLM call fails
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("Prompt must be a non-empty string")

        logger.debug(f"Executing LLM query with prompt: {prompt[:100]}...")
    
        # Build messages for LLM
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that processes user requests. Use any previous results provided to complete the current task."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        # Call LLM with configured settings
        try:
            result = self.llm_client.chat_completion(
                messages,
                temperature=self.temperature
            )
            logger.debug(f"LLM response received: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"LLM query failed: {e}")
            raise

    def get_schema(self) -> Dict[str, Any]:
        """
        Get the tool's parameter schema.

        Returns:
            dict: Tool schema with name, description, and parameters
        """
        return {
            'name': self.name,
            'description': 'Query the LLM for reasoning, synthesis, or general task processing. Useful for tasks that do not map to specific tools or require flexible intelligence.',
            'category': self.category,
            'parameters': {
                'prompt': {
                    'type': 'string',
                    'description': 'The prompt/query to send to the LLM. Should be clear and specific about what you want the LLM to do.',
                    'required': True
                }
            },
            'required': ['prompt']
        }
