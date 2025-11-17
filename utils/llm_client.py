"""
LLM Client for Context OS.

Centralized LLM client management with prompt template loading.
"""

import os
from typing import Dict, Any, List, Optional, Tuple
from openai import OpenAI

from utils.logger import get_logger
from utils.path_helper import get_prompts_path

logger = get_logger('LLMClient')


class LLMClient:
    """
    Unified LLM client for all engine components.

    Features:
    - Centralized OpenAI client initialization
    - Configuration from system.yaml (base_url, api_key, model)
    - Prompt template loading from external files
    - Built-in retry logic and error handling
    """

    def __init__(self, config: Dict[str, Any], prompts_dir: Optional[str] = None):
        """
        Initialize the LLM client.

        Args:
            config: Engine configuration from system.yaml
            prompts_dir: Optional custom prompts directory path
        """
        self.config = config

        # LLM configuration from system.yaml
        self.llm_provider = config.get('llm_provider', 'openai')
        self.llm_model = config.get('llm_model', 'gpt-4')
        self.llm_base_url = config.get('llm_base_url', 'https://api.openai.com/v1')
        self.llm_api_key = config.get('llm_api_key', '')
        self.llm_timeout = config.get('llm_timeout', 60)
        self.max_retries = config.get('max_retries', 3)

        # Prompts directory
        if prompts_dir is None:
            # Use path helper to get prompts directory (handles both dev and bundled modes)
            self.prompts_dir = get_prompts_path()
        else:
            self.prompts_dir = prompts_dir

        # Validate configuration
        if not self.llm_api_key:
            logger.warning("LLM API key not configured! Set 'llm_api_key' in system.yaml")

        # Initialize OpenAI client
        self.client = OpenAI(
            base_url=self.llm_base_url,
            api_key=self.llm_api_key,
        )

        logger.debug(f"LLMClient initialized (provider: {self.llm_provider}, model: {self.llm_model})")
        logger.debug(f"Prompts directory: {self.prompts_dir}")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None
    ) -> str:
        """
        Perform a chat completion with retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 2.0)
            timeout: Optional request timeout (uses config default if None)
            max_retries: Optional max retries (uses config default if None)

        Returns:
            str: LLM response content

        Raises:
            Exception: If all retries fail
        """
        timeout = timeout or self.llm_timeout
        max_retries = max_retries or self.max_retries

        for attempt in range(max_retries):
            try:
                logger.debug(f"Calling LLM (attempt {attempt + 1}/{max_retries})...")

                response = self.client.chat.completions.create(
                    model=self.llm_model,
                    messages=messages,
                    temperature=temperature,
                    timeout=timeout
                )

                result = response.choices[0].message.content
                logger.debug(f"LLM response received ({len(result)} chars)")
                return result

            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"LLM call failed after {max_retries} retries")
                    raise

        raise Exception(f"LLM call failed after {max_retries} retries")

    def load_prompt(self, prompt_name: str, **kwargs) -> str:
        """
        Load a prompt template from file and format with variables.

        Args:
            prompt_name: Name of the prompt file (without .txt extension)
            **kwargs: Variables to substitute in the template

        Returns:
            str: Formatted prompt text

        Raises:
            FileNotFoundError: If prompt file doesn't exist
            KeyError: If required template variables are missing
        """
        prompt_path = os.path.join(self.prompts_dir, f"{prompt_name}.txt")

        if not os.path.exists(prompt_path):
            logger.error(f"Prompt file not found: {prompt_path}")
            raise FileNotFoundError(f"Prompt template '{prompt_name}' not found at {prompt_path}")

        # Read prompt template
        with open(prompt_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # Format with provided variables
        try:
            formatted_prompt = template.format(**kwargs)
            logger.debug(f"Loaded and formatted prompt: {prompt_name}")
            return formatted_prompt

        except KeyError as e:
            logger.error(f"Missing template variable in prompt '{prompt_name}': {e}")
            raise KeyError(f"Missing required variable {e} for prompt '{prompt_name}'")

    def get_model(self) -> str:
        """Get the current model name."""
        return self.llm_model

    def get_provider(self) -> str:
        """Get the current provider name."""
        return self.llm_provider

    @staticmethod
    def validate_config(config: Dict[str, Any], timeout: int = 5) -> Tuple[bool, str]:
        """
        Validate LLM configuration by testing API connection.

        Args:
            config: Engine configuration dict with llm_provider, llm_model, llm_base_url, llm_api_key
            timeout: Timeout in seconds for validation test (default: 5)

        Returns:
            Tuple[bool, str]: (success, error_message)
                - (True, "Success") if validation passes
                - (False, error_message) if validation fails
        """
        try:
            # Extract configuration
            provider = config.get('llm_provider', 'openai')
            model = config.get('llm_model', '')
            base_url = config.get('llm_base_url', '')
            api_key = config.get('llm_api_key', '')

            # Validate required fields
            if not model:
                return False, "Model name is required"
            if not base_url:
                return False, "Base URL is required"
            if not api_key:
                return False, "API key is required"

            # Create temporary client for testing
            test_client = OpenAI(
                base_url=base_url,
                api_key=api_key,
            )

            # Perform a minimal test call
            logger.debug(f"Validating LLM config: provider={provider}, model={model}")

            response = test_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a test assistant."},
                    {"role": "user", "content": "Say 'OK'"}
                ],
                timeout=timeout
            )

            # Check if we got a valid response
            if response.choices and len(response.choices) > 0:
                logger.info(f"LLM config validation successful: {provider}/{model}")
                return True, "Success"
            else:
                return False, "Invalid response from LLM API"

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"LLM config validation failed: {error_msg}")

            # Provide user-friendly error messages
            if "authentication" in error_msg.lower() or "api_key" in error_msg.lower() or "401" in error_msg:
                return False, "Authentication failed - invalid API key"
            elif "timeout" in error_msg.lower():
                return False, f"Connection timeout - check base URL and network"
            elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                return False, "Network error - cannot reach API endpoint"
            elif "model" in error_msg.lower() or "404" in error_msg:
                return False, f"Model '{config.get('llm_model', 'unknown')}' not found or not accessible"
            else:
                return False, f"Validation failed: {error_msg[:100]}"
