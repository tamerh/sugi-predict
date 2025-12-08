"""Factory for creating LLM providers."""

import os
from typing import Optional

from ..core.config import get_config, LLMProviderConfig
from .base import LLMProvider
from .gemini_provider import GeminiProvider


def create_manual_provider(fine_tuning_file: Optional[str] = None) -> LLMProvider:
    """
    Create manual LLM provider for development with Claude Code.

    Args:
        fine_tuning_file: Optional path to save fine-tuning data

    Returns:
        ClaudeManualProvider instance
    """
    from .claude_manual_provider import ClaudeManualProvider
    return ClaudeManualProvider(fine_tuning_file=fine_tuning_file)


def create_llm_provider(
    provider_name: Optional[str] = None,
    provider_config: Optional[LLMProviderConfig] = None
) -> LLMProvider:
    """
    Create LLM provider instance.

    Args:
        provider_name: Provider name ("anthropic", "openai", "gemini")
                      If None, uses default from config
        provider_config: Optional provider config override

    Returns:
        LLM provider instance

    Raises:
        ValueError: If provider not found or API key missing
    """
    config = get_config()

    # Use default provider if not specified
    if provider_name is None:
        provider_name = config.llm.default_provider

    if not provider_name:
        raise ValueError("No provider specified and no default provider configured")

    # Get provider config
    if provider_config is None:
        if provider_name not in config.llm.providers:
            raise ValueError(f"Provider '{provider_name}' not configured")
        provider_config = config.llm.providers[provider_name]

    # Get API key from environment
    api_key = None
    if provider_config.api_key_env:
        api_key = os.getenv(provider_config.api_key_env)

    # Check for direct API key in environment (fallback)
    if not api_key:
        api_key = os.getenv(f"{provider_name.upper()}_API_KEY")

    if not api_key:
        raise ValueError(
            f"API key not found for provider '{provider_name}'. "
            f"Set {provider_config.api_key_env or f'{provider_name.upper()}_API_KEY'} environment variable."
        )

    # Create provider instance
    if provider_name == "gemini":
        return GeminiProvider(
            model=provider_config.model,
            api_key=api_key,
            max_tokens=provider_config.max_tokens,
            temperature=provider_config.temperature,
            timeout=provider_config.timeout
        )
    elif provider_name == "anthropic":
        # Import dynamically to avoid import errors if not installed
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            model=provider_config.model,
            api_key=api_key,
            max_tokens=provider_config.max_tokens,
            temperature=provider_config.temperature,
            timeout=provider_config.timeout
        )
    elif provider_name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(
            model=provider_config.model,
            api_key=api_key,
            max_tokens=provider_config.max_tokens,
            temperature=provider_config.temperature,
            timeout=provider_config.timeout
        )
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


def get_default_provider() -> LLMProvider:
    """
    Get default LLM provider instance.

    Returns:
        Default LLM provider
    """
    return create_llm_provider()
