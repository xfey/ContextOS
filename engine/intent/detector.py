"""
Intent Detector for Context OS.

Detects user intent from Signal objects using LLM analysis.
"""

import os
import json
from typing import Dict, Any, Optional

from models.signal import Signal
from models.intent import Intent
from utils.logger import get_logger
from utils.llm_client import LLMClient

logger = get_logger('Detector')


class Detector:
    """
    Detector analyzes Signals and extracts user intent using LLM.

    The detector:
    1. Extracts context from Signal
    2. Calls LLM for intent analysis
    3. Parses LLM response into Intent object
    """

    def __init__(self, config: Dict[str, Any], user_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the Detector.

        Args:
            config: Engine configuration from system.yaml
            user_config: User configuration (contains default_language)
        """
        self.config = config
        self.user_config = user_config or {}

        # Initialize unified LLM client
        self.llm_client = LLMClient(config)

        logger.info(f"Detector initialized with model: {self.llm_client.get_model()}, default_language: {self.user_config.get('default_language', 'Chinese')}")

    def update_user_config(self, user_config: Dict[str, Any]) -> None:
        """
        Update user configuration (e.g., default_language).

        Args:
            user_config: New user configuration dict
        """
        self.user_config = user_config or {}
        logger.info(f"Detector user config updated: default_language={self.user_config.get('default_language', 'Chinese')}")

    def detect(self, signal: Signal) -> Optional[Intent]:
        """
        Detect intent from a Signal.

        Args:
            signal: Signal object to analyze

        Returns:
            Intent: Detected intent object, or None if no intent detected
        """
        logger.info(f"Detecting intent from signal: {signal.metadata.get('uuid')}")

        try:
            # Call LLM for intent detection
            llm_response = self._call_llm_for_intent(signal)

            # Parse LLM response into Intent
            intent = self._parse_llm_response(llm_response, signal)

            if intent is None:
                logger.info("No actionable intent detected from signal")
                return None
            else:
                logger.info(f"Intent detected: {intent.target}")
                return intent

        except Exception as e:
            logger.error(f"Error detecting intent: {e}")
            # Return a default intent on error
            return Intent(
                target=f"[ERROR]",
                source=signal.source,
                context={"type": "text", "data": str(e)},
                level="Notify",
                metadata=signal.metadata
            )

    def _call_llm_for_intent(self, signal: Signal) -> str:
        """
        Call LLM for intent recognition.

        Args:
            context: Context information extracted from Signal

        Returns:
            str: LLM response text
        """
        # Load and format prompt from template
        content = signal.content
        # content: {type, data}
        
        text, image = '[NO TEXT, IMAGE ONLY]', ''
        
        if content:
            if content['type'] == 'text':
                text = content['data']
            elif content['type'] == 'image':
                image = content['data']
            elif content['type'] == 'multimodal':
                assert isinstance(content['data'], list) and len(content['data']) == 2
                # text first, then image
                text, image = content['data']
        
        system_prompt = self.llm_client.load_prompt(
            'intent_detection_system',
            user_lang=self.user_config.get('default_language', 'Chinese')
        )
        
        prompt = self.llm_client.load_prompt(
            'intent_detection_user',
            text=text,
            source=signal.source
        )
        
        llm_call_content = []
        llm_call_content.append({'type': 'text', 'text': prompt})
        if image:
            llm_call_content.append({'type': 'image_url', 'image_url': {"url": image}})

        # Call LLM with unified client
        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": llm_call_content
            }
        ]

        return self.llm_client.chat_completion(messages)

    def _parse_llm_response(self, response: str, signal: Signal) -> Optional[Intent]:
        """
        Parse LLM response into Intent object.

        Args:
            response: LLM response text (JSON format expected)
            signal: Original signal for fallback

        Returns:
            Intent: Parsed intent object, or None if no intent detected
        """
        try:
            # Try to parse JSON response
            response_data = json.loads(response)

            target = response_data.get('target', 'unknown')

            # Check if LLM returned null/None for target (no intent)
            if target is None or target == 'null' or target == 'None':
                logger.info("LLM detected no actionable intent (target is null)")
                return None

            # Create Intent with placeholder level (will be set by Classifier)
            intent = Intent(
                target=target,
                source=signal.source,
                context=signal.content,
                level="Notify",  # Default, will be updated by Classifier,
                metadata=signal.metadata
            )
            logger.debug(f"Parsed intent: {intent}")
            return intent

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            logger.warning(f"Response was: {response[:200]}")
            intent = Intent(
                target="process text",
                source=signal.source,
                context=signal.content,
                level="Notify",
                metadata=signal.metadata
            )
            return intent
