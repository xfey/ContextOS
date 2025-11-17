"""
ReAct Agent for Context OS.

Implements the Thought-Action-Observation loop for dynamic task execution.
"""

import re
import json
from copy import deepcopy
from typing import Dict, Any, List, Tuple, Union

from models.intent import Intent
from models.session import Session
from engine.execution.tool_executor import ToolExecutor
from utils.logger import get_logger
from utils.llm_client import LLMClient

logger = get_logger('ReactAgent')


class ReactAgent:
    """
    ReactAgent implements the ReAct (Reasoning + Acting) paradigm.

    The agent:
    1. Thinks about the current situation (Thought)
    2. Decides on an action to take (Action)
    3. Executes the action and observes the result (Observation)
    4. Repeats until task is complete or max iterations reached
    """

    def __init__(self, config: Dict[str, Any], tool_executor: ToolExecutor, tool_manager: Any, user_config: Dict[str, Any] = None):
        """
        Initialize the ReactAgent.

        Args:
            config: Engine configuration from system.yaml
            tool_executor: ToolExecutor instance for executing actions
            tool_manager: ToolManager instance for getting tool schemas
            user_config: User configuration (contains default_language)
        """
        self.config = config
        self.tool_executor = tool_executor
        self.tool_manager = tool_manager
        self.user_config = user_config or {}

        # ReAct configuration
        react_config = config.get('react', {})
        self.max_iterations = react_config.get('max_iterations', 10)

        # Initialize unified LLM client
        self.llm_client = LLMClient(config)

        logger.info(f"ReactAgent initialized (max_iterations={self.max_iterations}, default_language={self.user_config.get('default_language', 'Chinese')})")

    def update_user_config(self, user_config: Dict[str, Any]) -> None:
        """
        Update user configuration (e.g., default_language).

        Args:
            user_config: New user configuration dict
        """
        self.user_config = user_config or {}
        logger.info(f"ReactAgent user config updated: default_language={self.user_config.get('default_language', 'Chinese')}")

    def execute(self, intent: Intent) -> Dict[str, Any]:
        """
        Execute ReAct loop for the given intent.

        Args:
            intent: Intent object to fulfill

        Returns:
            str: Final result string
        """
        logger.info(f"Starting ReAct loop for intent: {intent.target}")

        # Context stores (thought, action_name, action_params, observation) tuples
        context = []

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"=== ReAct Iteration {iteration}/{self.max_iterations} ===")

            try:
                # Check if this is the last iteration
                is_last_iteration = (iteration == self.max_iterations)
                if is_last_iteration:
                    logger.info(f"=== The last iteration ===")

                # Step 1: Build prompt with current context (text only)
                system_prompt, prompt = self._build_react_prompt(intent, context, is_last_iteration)
                
                # Step 1.1: Try adding image to prompt
                image = None
                if intent.context['type'] == 'image':
                    image = intent.context['data']
                elif intent.context['type'] == 'multimodal':
                    assert isinstance(intent.context['data'], list) and len(intent.context['data']) == 2
                    # text first, then image
                    image = intent.context['data'][1]
                
                llm_call_content = []
                llm_call_content.append({'type': 'text', 'text': prompt})
                if image:
                    llm_call_content.append({'type': 'image_url', 'image_url': {"url": image}})
                
                # Step 2: Call LLM to get Thought and Action
                llm_response = self._call_llm(system_prompt, llm_call_content)

                # Step 3: Parse LLM response
                thought, action_name, action_params = self._parse_llm_response(llm_response)
                logger.debug(f"Thought: {thought}")
                logger.debug(f"Action: {action_name}({action_params})")

                # Step 4: Check if finished
                if self._is_finish_action(action_name):
                    logger.debug(f"Task completed in {iteration} iterations")
                    finish_msg = self._extract_final_result(action_params)
                    return {
                        "user": llm_call_content,   # previous msgs, prompt without "finish"
                        "assistant": llm_response,       # directly use the response raw, "action+finish"
                        "system_prompt": system_prompt,
                        "raw": {
                            # assistant only: start from 3rd message
                            "assistant": finish_msg,
                        }
                    }
                
                # Step 5: Execute action and get observation
                observation = self._execute_action(action_name, action_params)
                logger.debug(f"Observation: {observation[:200]}...")

                # Step 6: Add to context for next iteration
                context.append((thought, action_name, action_params, observation))

            except Exception as e:
                logger.error(f"Error in iteration {iteration}: {e}", exc_info=True)

                # Add error to context and continue
                error_observation = f"Error: {str(e)}"
                if context:
                    # Use last thought if available (can be empty string)
                    last_thought = context[-1][0] if context else ""
                    context.append((last_thought, "error", {}, error_observation))
                else:
                    context.append(("", "error", {}, error_observation))

                # Continue to next iteration to let agent recover

        # Max iterations reached - this should not happen as last iteration forces finish
        logger.error("Reached end of loop without finish action")
        raise RuntimeError("ReAct loop completed without finish action")

    def execute_continue(self, session: Session) -> Dict[str, Any]:
        """
        Continue execution with user's new message (in the session).
        Input messages format:
            [system, user (1st react prompt & process), assistant (1st react result),
                user (2nd question-only)]
        Required output:
            [user -> user question, with 2nd react prompt & process,
                assistant -> 2nd react result]
        """
        logger.info(f"Continue conversation for session title={session.title}")
        
        # Context stores (thought, action_name, action_params, observation) tuples
        context = []
        
        # Generate payload
        payload = deepcopy(session.messages)
        assert payload[-1]['role'] == 'user'
        last_message = payload.pop()
        
        user_content = last_message['content']
        if isinstance(user_content, str):
            # hopefully this won't happen
            logger.warning("last message of user content is a string. How can it be?")
            user_content = [{"type": "text", "text": user_content}]
        user_query, image_query = "", None
        for msg in user_content:
            if msg['type'] == 'text':
                user_query = msg['text']
            elif msg['type'] == 'image_url':
                image_query = msg['image_url']

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"=== ReAct Iteration {iteration}/{self.max_iterations} ===")

            try:
                # Check if this is the last iteration
                is_last_iteration = (iteration == self.max_iterations)

                # Step 1: Build prompt with user's last message
                # apply template for follow-up query
                history = self._format_history(context)
                prompt = self.llm_client.load_prompt(
                    'react_agent_user_followup',
                    text=user_query,
                    history=history
                )

                # Add last iteration warning if needed
                if is_last_iteration:
                    prompt += "\n\n**IMPORTANT: This is the last iteration. You MUST contain the finish() action in this step to provide the final answer.**"
                
                llm_call_content = []
                llm_call_content.append({'type': 'text', 'text': prompt})
                if image_query is not None:
                    if isinstance(image_query, dict):
                        llm_call_content.append({'type': 'image_url', 'image_url': {"url": image_query}})
                    else:
                        llm_call_content.append({'type': 'image_url', 'image_url': image_query})
                
                # Step 2: concat payload and call LLM
                this_turn_message = payload + [{'role': 'user', 'content': llm_call_content}]
                llm_response = self.llm_client.chat_completion(this_turn_message)

                # Step 3: Parse LLM response
                thought, action_name, action_params = self._parse_llm_response(llm_response)
                logger.debug(f"Thought: {thought}")
                logger.debug(f"Action: {action_name}({action_params})")

                # Step 4: Check if finished
                if self._is_finish_action(action_name):
                    logger.debug(f"Task completed in {iteration} iterations")
                    finish_msg = self._extract_final_result(action_params)
                    # Update session
                    session.messages = payload + [{'role': 'user', 'content': llm_call_content}]
                    # Return new message to handler -> for _append_message and udpate_status
                    assistant_message = {"role": "assistant", "content": llm_response}
                    cleared_assistant_message = {'role': 'assistant', 'content': finish_msg}
                    return assistant_message, cleared_assistant_message
                
                # Step 5: Execute action and get observation
                observation = self._execute_action(action_name, action_params)
                logger.debug(f"Observation: {observation[:200]}...")

                # Step 6: Add to context for next iteration
                context.append((thought, action_name, action_params, observation))
            
            except Exception as e:
                logger.error(f"Error in iteration {iteration}: {e}", exc_info=True)

                # Add error to context and continue
                error_observation = f"Error: {str(e)}"
                if context:
                    # Use last thought if available (can be empty string)
                    last_thought = context[-1][0] if context else ""
                    context.append((last_thought, "error", {}, error_observation))
                else:
                    context.append(("", "error", {}, error_observation))

                # Continue to next iteration to let agent recover

        # Max iterations reached - this should not happen as last iteration forces finish
        logger.error("Reached end of loop without finish action")
        raise RuntimeError("ReAct loop completed without finish action")

    def _call_llm(self, system_prompt: str, llm_call_content: list) -> str:
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
        return llm_response

    def _build_react_prompt(self, intent: Intent, context: List[Tuple], is_last_iteration: bool = False) -> Union[str, str]:
        """
        Build ReAct prompt with tools and history.
        Note: only handle text.

        Args:
            intent: User intent
            context: List of (thought, action_name, action_params, observation) tuples
            is_last_iteration: Whether this is the last iteration (forces finish action)

        Returns:
            str: Formatted prompt
        """
        # Get available tools
        tools_description = self._format_tools_description()

        # Format intent context
        text = '[NO TEXT]'
        if intent.context['type'] == 'text':
            text = intent.context['data']
        elif intent.context['type'] == 'multimodal':
            assert isinstance(intent.context['data'], list) and len(intent.context['data']) == 2
            # text first, then image
            text = intent.context['data'][0]

        # Format history from context
        history = self._format_history(context)

        # Load and format prompt from template
        system_prompt = self.llm_client.load_prompt(
            'react_agent_system',
            tools_description=tools_description,
            user_lang=self.user_config.get('default_language', 'Chinese')
        )

        # Load and format prompt from template
        prompt = self.llm_client.load_prompt(
            'react_agent_user',
            intent_target=intent.target,
            text=text,  # remove `intent_context` -> use text-only
            history=history,
        )

        # Add last iteration warning if needed
        if is_last_iteration:
            prompt += "\n\n**IMPORTANT: This is the last iteration. You MUST contain the finish() action in this step to provide the final answer.**"

        return system_prompt, prompt

    def _format_tools_description(self) -> str:
        """
        Format available tools into readable description.

        Returns:
            str: Formatted tools description
        """
        available_tools = []
        tool_names = self.tool_manager.list_tools()

        for tool_name in tool_names:
            schema = self.tool_manager.get_tool_schema(tool_name)
            if schema:
                description = schema.get('description', f'{tool_name} tool')
                params = schema.get('parameters', {})

                tool_desc = f"- **{tool_name}**: {description}"

                if params:
                    param_list = []
                    for param_name, param_info in params.items():
                        param_desc = param_info.get('description', '')
                        param_type = param_info.get('type', 'any')
                        required = param_info.get('required', False)
                        req_marker = ' (required)' if required else ''
                        param_list.append(f"  - {param_name} ({param_type}){req_marker}: {param_desc}")

                    if param_list:
                        tool_desc += "\n" + "\n".join(param_list)

                available_tools.append(tool_desc)
            else:
                available_tools.append(f"- **{tool_name}**: {tool_name} tool")

        # Add finish action
        available_tools.append("- **finish**: Complete the task and return final result\n  - result (string) (required): The final answer to return to the user")

        return "\n".join(available_tools) if available_tools else "No tools available"

    def _format_history(self, context: List[Tuple]) -> str:
        """
        Format context history for prompt.

        Args:
            context: List of (thought, action_name, action_params, observation) tuples
                     thought can be empty string if not provided

        Returns:
            str: Formatted history
        """
        if not context:
            return ""

        history_lines = ["## Previous Steps\n"]

        for i, (thought, action_name, action_params, observation) in enumerate(context, 1):
            if action_name == "error" and not action_params:
                continue
            history_lines.append(f"**Step {i}:**")
            # Only include thought if it's not empty
            if thought:
                history_lines.append(f"<thought>{thought}</thought>")
            history_lines.append(f"<action>{action_name}({json.dumps(action_params, ensure_ascii=False)})</action>")
            history_lines.append(f"Observation: {observation}\n")

        return "\n".join(history_lines)

    def _parse_llm_response(self, response: str) -> Tuple[str, str, Dict[str, Any]]:
        """
        Parse LLM response to extract Thought and Action.

        Args:
            response: LLM response text

        Returns:
            tuple: (thought, action_name, action_params)
                   thought can be empty string if not provided
        """
        logger.debug(f"Parsing LLM response: {response}")

        # Extract Thought using <thought></thought> tags (OPTIONAL)
        thought_match = re.search(r'<thought>\s*(.+?)\s*</thought>', response, re.DOTALL | re.IGNORECASE)
        thought = thought_match.group(1).strip() if thought_match else ""

        # Extract Action using <action></action> tags (REQUIRED)
        action_match = re.search(r'<action>\s*(.+?)\s*</action>', response, re.DOTALL | re.IGNORECASE)
        if not action_match:
            raise ValueError("No Action found in LLM response")

        action_text = action_match.group(1).strip()

        # Parse action: tool_name(param1="value1", param2="value2")
        # Handle multi-line action text by removing extra whitespace
        action_text = ' '.join(action_text.split())

        # Use greedy match to capture everything until the last closing paren
        action_pattern = r'(\w+)\((.*)\)$'
        action_parse = re.search(action_pattern, action_text)

        if not action_parse:
            raise ValueError(f"Invalid Action format: {action_text}")

        action_name = action_parse.group(1)
        params_text = action_parse.group(2)

        # Parse parameters
        action_params = self._parse_action_params(params_text)

        if thought:
            logger.debug(f"Parsed: thought='{thought[:50]}...', action={action_name}, params={action_params}")
        else:
            logger.debug(f"Parsed: action={action_name}, params={action_params} (no thought)")

        return thought, action_name, action_params

    def _parse_action_params(self, params_text: str) -> Dict[str, Any]:
        """
        Parse action parameters from text.
        Supports both formats:
        - key=value: param1="value1", param2="value2"
        - JSON: {"key1": "value1", "key2": "value2"}
        
        Args:
            params_text: Parameter string
            
        Returns:
            dict: Parsed parameters
        """
        if not params_text.strip():
            return {}
        
        params_text = params_text.strip()
        
        # Try to parse as JSON first
        if params_text.startswith('{') and params_text.endswith('}'):
            try:
                import json
                return json.loads(params_text)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse as JSON: {e}, falling back to key=value parsing")
        
        # Fall back to key=value parsing
        params = {}
        
        # Find all key= patterns (or key:)
        # Support both = and : for flexibility
        key_positions = [(m.group(1), m.start(), m.end()) 
                        for m in re.finditer(r'(\w+)\s*[=:]\s*', params_text)]
        
        for key, _, eq_end in key_positions:
            remaining = params_text[eq_end:]
            
            if not remaining:
                continue
            
            quote_char = remaining[0]
            if quote_char not in ['"', "'"]:
                continue
            
            value_start = 1
            value_end = -1
            
            pos = value_start
            while pos < len(remaining):
                pos = remaining.find(quote_char, pos)
                if pos == -1:
                    break
                
                after_quote = remaining[pos + 1:].strip()
                if not after_quote or after_quote[0] in ',)':
                    value_end = pos
                    break
                
                pos += 1
            
            if value_end == -1:
                value_end = len(remaining) - 1
                if quote_char in remaining[value_start:]:
                    value_end = remaining.rfind(quote_char)
            
            value = remaining[value_start:value_end]
            params[key] = value
        
        return params

    def _execute_action(self, action_name: str, params: Dict[str, Any]) -> str:
        """
        Execute an action via ToolExecutor.

        Args:
            action_name: Name of the action/tool
            params: Parameters for the action

        Returns:
            str: Observation from execution
        """
        # Use ToolExecutor to execute the action
        return self.tool_executor.execute(action_name, params)

    def _is_finish_action(self, action_name: str) -> bool:
        """
        Check if action is the finish action.

        Args:
            action_name: Name of the action

        Returns:
            bool: True if this is a finish action
        """
        return action_name.lower() == 'finish'

    def _extract_final_result(self, params: Dict[str, Any]) -> str:
        """
        Extract final result from finish action parameters.

        Args:
            params: Parameters from finish action

        Returns:
            str: Final result
        """
        result = params.get('result', '')
        if not result:
            logger.warning("finish() action called without result parameter")
            return "Task completed (no result provided)"

        return str(result)
