"""
Intent Classifier for Context OS.

Classifies Intent objects into interaction levels (Notify/Review) using LLM.
"""

import json
from typing import Dict, Any, Optional

from models.intent import Intent
from utils.logger import get_logger
from utils.llm_client import LLMClient

logger = get_logger('Classifier')


class Classifier:
    """
    Classifier determines the appropriate interaction level for an Intent using LLM.

    The classifier:
    1. Receives an Intent with target and context
    2. Calls LLM to determine appropriate interaction level
    3. Validates and returns one of: Notify, Review
    4. Updates the intent.level in-place

    Interaction levels:
    - Notify: 0-turn interaction, system provides information without user response
    - Review: N-turn interaction, complex multi-turn dialogue
    """

    def __init__(self, session_config: Dict[str, Any], engine_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the Classifier.

        Args:
            session_config: Session configuration from system.yaml
            engine_config: Optional engine configuration for LLM settings
        """
        self.session_config = session_config
        self.engine_config = engine_config or {}

        self.max_turns_config = session_config.get('max_turns', {'review': -1})

        # Initialize unified LLM client if engine_config provided
        if self.engine_config:
            self.llm_client = LLMClient(self.engine_config)
            logger.info(f"Classifier initialized with LLM-based classification (model: {self.llm_client.get_model()})")
        else:
            self.llm_client = None
            logger.info("Classifier initialized with rule-based classification (no LLM)")

    def classify(self, intent: Intent) -> str:
        """
        Classify an Intent into an interaction level using LLM.

        Args:
            intent: Intent object to classify

        Returns:
            str: Interaction level ('Notify' or 'Review')
        """
        logger.info(f"Classifying intent: {intent.target}")

        try:
            # Use LLM classification if available
            level = self._call_llm_for_classification(intent)
        except Exception as e:
            logger.error(f"LLM classification failed: {e}, using fallback")
            level = 'Notify'

        # Update the intent's level (maintain side effect)
        intent.level = level
        logger.info(f"Intent classified as: {level}")
        return level

    def _call_llm_for_classification(self, intent: Intent) -> str:
        """
        Call LLM to classify intent into interaction level.

        Args:
            intent: Intent object to classify

        Returns:
            str: Classified interaction level
        """
        # Clean intent.context (signal.content, {type, data})
        content = intent.context
        # content: {type, data}
        
        text, image = '[NO TEXT]', ''
        
        if content:
            if content['type'] == 'text':
                text = content['data']
            elif content['type'] == 'image':
                image = content['data']
            elif content['type'] == 'multimodal':
                assert isinstance(content['data'], list) and len(content['data']) == 2
                # text first, then image
                text, image = content['data']
        
        # Load and format prompt from template
        system_prompt = self.llm_client.load_prompt(
            'interaction_classification_system',
        )
        
        prompt = self.llm_client.load_prompt(
            'interaction_classification_user',
            target=intent.target,
            text=text,
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

        llm_response = self.llm_client.chat_completion(messages)
        logger.debug(f"LLM classification response received: {llm_response[:100]}...")

        # Parse LLM response into level
        level = self._parse_llm_classification(llm_response)

        logger.info(f"LLM classified as: {level}")
        return level

    def _parse_llm_classification(self, llm_response: str) -> str:
        """
        Parse LLM response into interaction level.

        Args:
            llm_response: LLM response text (expected to be JSON)

        Returns:
            str: Validated interaction level
        """
        try:
            # Try to extract JSON from response (handle markdown code blocks)
            response_text = llm_response.strip()

            # Remove markdown code block markers if present
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                # Remove first line (```json or ```)
                lines = lines[1:]
                # Remove last line (```)
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                response_text = '\n'.join(lines).strip()

            # Parse JSON
            classification = json.loads(response_text)

            if not isinstance(classification, dict):
                raise ValueError("LLM response is not a JSON object")

            level = classification.get('level', '').strip()
            reasoning = classification.get('reasoning', 'No reasoning provided')

            # Validate level
            valid_levels = ['Notify', 'Review']
            if level not in valid_levels:
                raise ValueError(f"Invalid level '{level}', must be one of {valid_levels}")

            logger.debug(f"Classification reasoning: {reasoning}")
            return level

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response was: {llm_response[:500]}")
            raise ValueError(f"Invalid JSON in LLM response: {e}")

        except Exception as e:
            logger.error(f"Error parsing LLM classification: {e}")
            raise
