"""
Translator Tool for Context OS.

Provides LLM-based text translation functionality.
"""

import json
from typing import Dict, Any, Optional
from utils.logger import get_logger
from utils.llm_client import LLMClient

logger = get_logger('TranslatorTool')


class TranslatorTool:
    """
    TranslatorTool provides LLM-based text translation.

    Uses the unified LLMClient to translate text between languages
    with high quality and natural output.
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize the TranslatorTool.

        Args:
            name: Tool name
            config: Tool configuration from tools.yaml
        """
        self.name = name
        self.config = config
        self.category = 'builtin'

        # Configuration
        self.target_lang = config.get('target_lang', 'Chinese')

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

        self.llm_client = LLMClient(engine_config)

        logger.info(f"TranslatorTool initialized: {name} (LLM-based using {self.llm_client.get_model()})")

    def execute(self, text: str, target_lang: Optional[str] = None) -> Dict[str, Any]:
        """
        Translate text to target language using LLM.

        Args:
            text: Text to translate
            target_lang: Target language code (e.g., 'zh', 'en'). If None, uses config default

        Returns:
            dict: Translation result containing:
                - original_text: Original input text
                - translated_text: Translated text
                - target_lang: Target language
                - success: Whether translation succeeded
        """
        logger.info(f"Translating text: '{text[:50]}...'")

        # Use config defaults if not specified
        if target_lang in [None, "auto", "Auto", "default", "Default"]:
            target_lang = self.target_lang

        try:
            # Perform LLM-based translation
            translation_result = self._llm_translate(text, target_lang)

            result = {
                'original_text': text,
                'translated_text': translation_result.get('translated_text', text),
                'target_lang': target_lang,
                'success': True
            }

            logger.info(f"Translation complete: '{text[:30]}...' -> '{result['translated_text'][:30]}...'")
            return result

        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return {
                'original_text': text,
                'translated_text': text,  # Return original on error
                'target_lang': target_lang,
                'error': str(e),
                'success': False
            }

    def _llm_translate(self, text: str, target_lang: str) -> Dict[str, Any]:
        """
        Perform LLM-based translation.

        Args:
            text: Text to translate
            target_lang: Target language code

        Returns:
            dict: Translation result with keys:
                - translated_text: The translated text
        """
        logger.debug(f"Calling LLM for translation to {target_lang}")

        # Expand language codes to full names for better LLM understanding
        lang_names = {
            'en': 'English',
            'English': 'English',
            'zh': 'Chinese',
            'Chinese': 'Chinese',
            'auto': 'auto-detect'
        }
        target_lang_name = lang_names.get(target_lang, target_lang)

        # Load and format prompt
        system_prompt = self.llm_client.load_prompt(
            'translator_system',
            target_lang=target_lang_name
        )

        # Call LLM
        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": text
            }
        ]

        response = self.llm_client.chat_completion(messages, temperature=0.2)

        # Parse response
        try:
            result = json.loads(response)
            logger.debug(f"Translation result: {result}")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM translation response as JSON: {e}")
            logger.warning(f"Response was: {response[:200]}")

            # Fallback: use response as translated text
            return {
                'translated_text': response.strip()
            }

    def get_schema(self) -> Dict[str, Any]:
        """
        Get the parameter schema for this tool.

        Returns:
            dict: Parameter schema
        """
        return {
            'name': self.name,
            'description': 'Translate text between languages',
            'parameters': {
                'text': {
                    'type': 'string',
                    'description': 'Text to translate',
                    'required': True
                },
                'target_lang': {
                    'type': 'string',
                    'description': f'Target language code (e.g., "zh", "en"). Use "{self.target_lang}" if not specified',
                    'required': False,
                    'default': self.target_lang
                }
            },
            'required': ['text']
        }
