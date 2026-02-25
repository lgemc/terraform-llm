"""AI model client for generating Terraform code."""

import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class ModelClient(ABC):
    """Abstract base class for AI model clients."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text from prompt.

        Args:
            prompt: Input prompt
            **kwargs: Additional model parameters

        Returns:
            Generated text
        """
        pass

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Generate response from chat messages.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            **kwargs: Additional model parameters

        Returns:
            Generated response
        """
        pass


class AnthropicClient(ModelClient):
    """Client for Anthropic Claude models."""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "claude-haiku-4-5-20251001"
    ):
        """
        Initialize Anthropic client.

        Args:
            api_key: API key (defaults to ANTHROPIC_API_KEY env var)
            model: Model identifier
        """
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. "
                "Install it with: pip install anthropic"
            )

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("API key required (set ANTHROPIC_API_KEY or pass api_key)")

        self.model = model
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt using Claude."""
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, **kwargs)

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate response from chat messages."""
        max_tokens = kwargs.pop("max_tokens", 4096)
        temperature = kwargs.pop("temperature", 1.0)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
            **kwargs,
        )

        return response.content[0].text


class OpenAIClient(ModelClient):
    """Client for OpenAI models."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        """
        Initialize OpenAI client.

        Args:
            api_key: API key (defaults to OPENAI_API_KEY env var)
            model: Model identifier
        """
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not installed. Install it with: pip install openai"
            )

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("API key required (set OPENAI_API_KEY or pass api_key)")

        self.model = model
        self.client = openai.OpenAI(api_key=self.api_key)

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt using OpenAI."""
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, **kwargs)

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate response from chat messages."""
        temperature = kwargs.pop("temperature", 1.0)
        max_tokens = kwargs.pop("max_tokens", None)

        completion_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }

        if max_tokens:
            completion_kwargs["max_tokens"] = max_tokens

        response = self.client.chat.completions.create(**completion_kwargs)

        return response.choices[0].message.content


def create_client(
    provider: str = "anthropic",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> ModelClient:
    """
    Factory function to create a model client.

    Args:
        provider: Model provider ('anthropic' or 'openai')
        api_key: Optional API key
        model: Optional model identifier

    Returns:
        ModelClient instance
    """
    if provider.lower() == "anthropic":
        kwargs = {"api_key": api_key} if api_key else {}
        if model:
            kwargs["model"] = model
        return AnthropicClient(**kwargs)

    elif provider.lower() == "openai":
        kwargs = {"api_key": api_key} if api_key else {}
        if model:
            kwargs["model"] = model
        return OpenAIClient(**kwargs)

    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'anthropic' or 'openai'")
