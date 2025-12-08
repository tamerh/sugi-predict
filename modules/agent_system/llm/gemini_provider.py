"""Google Gemini LLM provider with function calling support."""

import json
from typing import Any, AsyncIterator, Dict, List
import google.generativeai as genai

from .base import LLMProvider, LLMResponse, Message, FunctionCall, ToolDefinition


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider."""

    def __init__(self, model: str, api_key: str, **kwargs):
        """
        Initialize Gemini provider.

        Args:
            model: Model name (e.g., "gemini-2.0-flash-lite", "gemini-1.5-pro")
            api_key: Google API key
            **kwargs: Additional configuration
        """
        super().__init__(model, api_key, **kwargs)

        # Configure Gemini
        genai.configure(api_key=self.api_key)
        self.client = genai.GenerativeModel(model)

    def _messages_to_gemini_format(self, messages: List[Message]) -> List[Dict]:
        """
        Convert messages to Gemini format.

        Args:
            messages: List of Message objects

        Returns:
            Gemini-formatted messages
        """
        gemini_messages = []

        for msg in messages:
            # Gemini uses "model" instead of "assistant"
            role = "model" if msg.role == "assistant" else msg.role

            # Skip system messages (handled separately in Gemini)
            if role == "system":
                continue

            gemini_messages.append({
                "role": role,
                "parts": [{"text": msg.content}]
            })

        return gemini_messages

    def _extract_system_prompt(self, messages: List[Message]) -> str:
        """Extract system prompt from messages."""
        for msg in messages:
            if msg.role == "system":
                return msg.content
        return ""

    async def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> LLMResponse:
        """Chat completion without function calling."""

        # Extract system instruction
        system_instruction = self._extract_system_prompt(messages)

        # Convert messages
        gemini_messages = self._messages_to_gemini_format(messages)

        # Create model with system instruction if present
        if system_instruction:
            model = genai.GenerativeModel(
                self.model,
                system_instruction=system_instruction
            )
        else:
            model = self.client

        # Generate response
        response = await model.generate_content_async(
            gemini_messages,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                **kwargs
            )
        )

        return LLMResponse(
            content=response.text,
            finish_reason=str(response.candidates[0].finish_reason) if response.candidates else "stop",
            usage={
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count
            },
            model=self.model
        )

    async def chat_with_functions(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tool_choice: str = "auto",
        **kwargs
    ) -> LLMResponse:
        """Chat completion with function calling support."""

        # Extract system instruction
        system_instruction = self._extract_system_prompt(messages)

        # Convert tool definitions to Gemini format
        gemini_tools = []
        for tool in tools:
            gemini_tools.append({
                "function_declarations": [{
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }]
            })

        # Convert messages
        gemini_messages = self._messages_to_gemini_format(messages)

        # Create model with system instruction and tools
        model_config = {"model_name": self.model}
        if system_instruction:
            model_config["system_instruction"] = system_instruction

        model = genai.GenerativeModel(**model_config, tools=gemini_tools)

        # Generate response
        response = await model.generate_content_async(
            gemini_messages,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                **kwargs
            )
        )

        # Parse response
        content = ""
        function_call = None

        if response.candidates:
            candidate = response.candidates[0]

            # Check for function call
            if candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        function_call = FunctionCall(
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {}
                        )
                    elif hasattr(part, 'text'):
                        content += part.text

        return LLMResponse(
            content=content,
            function_call=function_call,
            finish_reason=str(response.candidates[0].finish_reason) if response.candidates else "stop",
            usage={
                "prompt_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "completion_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
                "total_tokens": response.usage_metadata.total_token_count if response.usage_metadata else 0
            },
            model=self.model
        )

    async def stream(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream chat completion."""

        # Extract system instruction
        system_instruction = self._extract_system_prompt(messages)

        # Convert messages
        gemini_messages = self._messages_to_gemini_format(messages)

        # Create model
        if system_instruction:
            model = genai.GenerativeModel(
                self.model,
                system_instruction=system_instruction
            )
        else:
            model = self.client

        # Stream response
        response_stream = await model.generate_content_async(
            gemini_messages,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                **kwargs
            ),
            stream=True
        )

        async for chunk in response_stream:
            if chunk.text:
                yield chunk.text
