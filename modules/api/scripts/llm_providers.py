"""
LLM Provider Abstraction Layer for BioYoda RAG

Provides a unified interface for multiple LLM providers:
- Anthropic Claude (primary)
- OpenAI GPT-4 (alternative)
- Google Gemini (alternative)
- Local models via Ollama/vLLM (future)

Usage:
    provider = get_llm_provider(config)
    response = provider.generate(prompt="What is CRISPR?", max_tokens=1000)
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
import tiktoken

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        self.model = model
        self.api_key = api_key
        self.kwargs = kwargs

    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        **kwargs
    ) -> str:
        """
        Generate text response from prompt

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-1.0)
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def get_cost_estimate(self, input_text: str, output_text: str) -> float:
        """
        Estimate cost of API call

        Args:
            input_text: Input prompt
            output_text: Generated response

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in text for this provider"""
        pass


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider"""

    # Cost per 1M tokens (as of Oct 2024)
    INPUT_COST_PER_1M = 3.0   # $3 per 1M input tokens
    OUTPUT_COST_PER_1M = 15.0  # $15 per 1M output tokens

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022", **kwargs):
        super().__init__(model=model, api_key=api_key, **kwargs)

        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
            logger.info(f"✅ Anthropic provider initialized with model: {model}")
        except ImportError:
            raise ImportError(
                "anthropic package not found. Install it with: pip install anthropic"
            )

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        **kwargs
    ) -> str:
        """Generate response using Claude"""
        try:
            start_time = time.time()

            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"Claude response generated in {elapsed_ms:.0f}ms")

            # Extract text from response
            return response.content[0].text

        except Exception as e:
            logger.error(f"Anthropic API error: {str(e)}")
            raise

    def get_cost_estimate(self, input_text: str, output_text: str) -> float:
        """Estimate cost for Claude API call"""
        input_tokens = self.count_tokens(input_text)
        output_tokens = self.count_tokens(output_text)

        input_cost = (input_tokens / 1_000_000) * self.INPUT_COST_PER_1M
        output_cost = (output_tokens / 1_000_000) * self.OUTPUT_COST_PER_1M

        return input_cost + output_cost

    def count_tokens(self, text: str) -> int:
        """
        Approximate token count for Claude
        Uses tiktoken cl100k_base as approximation (Claude uses similar)
        """
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except:
            # Fallback: rough estimate (1 token ≈ 4 chars)
            return len(text) // 4


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4 provider"""

    # Cost per 1M tokens (GPT-4 Turbo)
    INPUT_COST_PER_1M = 10.0   # $10 per 1M input tokens
    OUTPUT_COST_PER_1M = 30.0  # $30 per 1M output tokens

    def __init__(self, api_key: str, model: str = "gpt-4-turbo-preview", **kwargs):
        super().__init__(model=model, api_key=api_key, **kwargs)

        try:
            import openai
            self.client = openai.OpenAI(api_key=api_key)
            logger.info(f"✅ OpenAI provider initialized with model: {model}")
        except ImportError:
            raise ImportError(
                "openai package not found. Install it with: pip install openai"
            )

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        **kwargs
    ) -> str:
        """Generate response using GPT-4"""
        try:
            start_time = time.time()

            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"GPT-4 response generated in {elapsed_ms:.0f}ms")

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise

    def get_cost_estimate(self, input_text: str, output_text: str) -> float:
        """Estimate cost for OpenAI API call"""
        input_tokens = self.count_tokens(input_text)
        output_tokens = self.count_tokens(output_text)

        input_cost = (input_tokens / 1_000_000) * self.INPUT_COST_PER_1M
        output_cost = (output_tokens / 1_000_000) * self.OUTPUT_COST_PER_1M

        return input_cost + output_cost

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken for GPT-4"""
        try:
            encoding = tiktoken.encoding_for_model(self.model)
            return len(encoding.encode(text))
        except:
            # Fallback
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))


class LocalProvider(LLMProvider):
    """Local LLM provider (Ollama, vLLM, etc.)"""

    def __init__(
        self,
        model: str = "llama3.1:70b",
        base_url: str = "http://localhost:11434",
        **kwargs
    ):
        super().__init__(model=model, **kwargs)
        self.base_url = base_url

        try:
            import requests
            self.requests = requests
            # Test connection
            response = requests.get(f"{base_url}/api/tags", timeout=5)
            response.raise_for_status()
            logger.info(f"✅ Local provider initialized with model: {model} at {base_url}")
        except ImportError:
            raise ImportError(
                "requests package not found. Install it with: pip install requests"
            )
        except Exception as e:
            logger.warning(f"Could not connect to local LLM server at {base_url}: {e}")

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        **kwargs
    ) -> str:
        """Generate response using local model (Ollama)"""
        try:
            start_time = time.time()

            response = self.requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens
                    }
                },
                timeout=120  # 2 minutes timeout
            )
            response.raise_for_status()

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"Local model response generated in {elapsed_ms:.0f}ms")

            return response.json()["response"]

        except Exception as e:
            logger.error(f"Local LLM error: {str(e)}")
            raise

    def get_cost_estimate(self, input_text: str, output_text: str) -> float:
        """Local models have zero API cost"""
        return 0.0

    def count_tokens(self, text: str) -> int:
        """Approximate token count for local models"""
        # Rough estimate for Llama-based models
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except:
            return len(text) // 4


class GeminiProvider(LLMProvider):
    """Google Gemini provider"""

    # Cost per 1M tokens (Gemini 1.5 Flash - as of Oct 2024)
    # Flash: $0.075 per 1M input, $0.30 per 1M output
    # Pro: $3.50 per 1M input, $10.50 per 1M output
    INPUT_COST_PER_1M = 0.075   # Flash pricing
    OUTPUT_COST_PER_1M = 0.30

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", **kwargs):
        super().__init__(model=model, api_key=api_key, **kwargs)

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(model)
            logger.info(f"✅ Gemini provider initialized with model: {model}")
        except ImportError:
            raise ImportError(
                "google-generativeai package not found. Install it with: pip install google-generativeai"
            )

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        **kwargs
    ) -> str:
        """Generate response using Gemini"""
        try:
            start_time = time.time()

            # Configure generation parameters
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": 0.95,
            }

            response = self.client.generate_content(
                prompt,
                generation_config=generation_config
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"Gemini response generated in {elapsed_ms:.0f}ms")

            return response.text

        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            raise

    def get_cost_estimate(self, input_text: str, output_text: str) -> float:
        """Estimate cost for Gemini API call"""
        input_tokens = self.count_tokens(input_text)
        output_tokens = self.count_tokens(output_text)

        input_cost = (input_tokens / 1_000_000) * self.INPUT_COST_PER_1M
        output_cost = (output_tokens / 1_000_000) * self.OUTPUT_COST_PER_1M

        return input_cost + output_cost

    def count_tokens(self, text: str) -> int:
        """
        Approximate token count for Gemini
        Uses tiktoken as approximation
        """
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except:
            # Fallback: rough estimate (1 token ≈ 4 chars)
            return len(text) // 4


def get_llm_provider(config: Dict) -> LLMProvider:
    """
    Factory function to get LLM provider based on configuration

    Args:
        config: Configuration dict with keys:
            - provider: "anthropic" | "openai" | "gemini" | "local"
            - model: Model name
            - api_key: API key (for cloud providers)
            - base_url: Base URL (for local providers)

    Returns:
        LLMProvider instance

    Examples:
        # Anthropic Claude
        config = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "api_key": "sk-ant-..."
        }

        # Google Gemini
        config = {
            "provider": "gemini",
            "model": "gemini-1.5-flash",
            "api_key": "your-google-ai-studio-key"
        }

        provider = get_llm_provider(config)
    """
    provider_type = config.get("provider", "anthropic").lower()

    if provider_type == "anthropic":
        return AnthropicProvider(
            api_key=config["api_key"],
            model=config.get("model", "claude-3-5-sonnet-20241022")
        )

    elif provider_type == "openai":
        return OpenAIProvider(
            api_key=config["api_key"],
            model=config.get("model", "gpt-4-turbo-preview")
        )

    elif provider_type == "gemini":
        return GeminiProvider(
            api_key=config["api_key"],
            model=config.get("model", "gemini-1.5-flash")
        )

    elif provider_type == "local":
        return LocalProvider(
            model=config.get("model", "llama3.1:70b"),
            base_url=config.get("base_url", "http://localhost:11434")
        )

    else:
        raise ValueError(
            f"Unknown provider: {provider_type}. "
            f"Supported providers: anthropic, openai, gemini, local"
        )


# Convenience function for testing
def test_provider(config: Dict, test_prompt: str = "What is CRISPR gene editing?"):
    """
    Test LLM provider with a simple prompt

    Args:
        config: Provider configuration
        test_prompt: Test question
    """
    provider = get_llm_provider(config)

    print(f"\n🧪 Testing {config['provider']} provider with model: {provider.model}")
    print(f"📝 Prompt: {test_prompt}\n")

    start_time = time.time()
    response = provider.generate(prompt=test_prompt, max_tokens=500)
    elapsed = time.time() - start_time

    print(f"✅ Response ({elapsed:.2f}s):\n{response}\n")

    # Cost estimate
    cost = provider.get_cost_estimate(test_prompt, response)
    print(f"💰 Estimated cost: ${cost:.4f}\n")

    return response


if __name__ == "__main__":
    # Example usage
    import os

    # Test Anthropic (if API key available)
    if os.getenv("ANTHROPIC_API_KEY"):
        config = {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "api_key": os.getenv("ANTHROPIC_API_KEY")
        }
        test_provider(config)

    # Test OpenAI (if API key available)
    if os.getenv("OPENAI_API_KEY"):
        config = {
            "provider": "openai",
            "model": "gpt-4-turbo-preview",
            "api_key": os.getenv("OPENAI_API_KEY")
        }
        test_provider(config)
