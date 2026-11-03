"""
llm_provider.py — Provider-agnostic LLM interface

Abstracts away the differences between OpenAI, Anthropic, Mistral (and future
providers) behind a unified interface. The rest of the codebase calls this
interface instead of specific APIs.

Usage:
    from llm_provider import get_provider

    # Get provider based on config or API key prefix
    llm = get_provider(api_key="sk-...")       # → OpenAI
    llm = get_provider(api_key="sk-ant-...")    # → Anthropic
    llm = get_provider(provider="mistral", api_key="...")

    # Unified interface — same calls regardless of provider
    response = llm.complete(messages, model="default")
    for token in llm.stream(messages, model="default"):
        print(token, end="")
    embedding = llm.embed("some text")
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Generator, Optional


# ============================================================
# Base class — the contract all providers must implement
# ============================================================

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g. 'openai', 'anthropic', 'mistral')."""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model for completions."""
        ...

    @property
    @abstractmethod
    def fast_model(self) -> str:
        """Lightweight model for classification, sufficiency checks, etc."""
        ...

    @property
    @abstractmethod
    def embedding_model(self) -> str:
        """Model for text embeddings."""
        ...

    @abstractmethod
    def complete(self, messages: List[Dict], model: str = None) -> str:
        """
        Standard completion. Returns the full response text.
        
        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
            model: Model name, or None for default
        """
        ...

    @abstractmethod
    def stream(self, messages: List[Dict], model: str = None) -> Generator[str, None, None]:
        """
        Streaming completion. Yields tokens one at a time.
        
        Args:
            messages: Same format as complete()
            model: Model name, or None for default
        """
        ...

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """
        Generate an embedding vector for the given text.
        
        Returns: list of floats (the embedding vector)
        """
        ...

    def complete_with_retry(self, messages: List[Dict], model: str = None,
                            retries: int = 3, delay: float = 2) -> str:
        """Completion with automatic retry on rate limits."""
        import time
        for attempt in range(retries):
            try:
                return self.complete(messages, model)
            except Exception as e:
                if "rate limit" in str(e).lower() and attempt < retries - 1:
                    time.sleep(delay * (attempt + 1))
                    continue
                raise

    def embed_with_retry(self, text: str, retries: int = 5, delay: float = 2) -> List[float]:
        """Embedding with automatic retry on rate limits."""
        import time
        for attempt in range(retries):
            try:
                return self.embed(text)
            except Exception as e:
                if "rate limit" in str(e).lower() and attempt < retries - 1:
                    time.sleep(delay * (2 ** attempt))
                    continue
                raise


# ============================================================
# OpenAI Implementation
# ============================================================

class OpenAIProvider(LLMProvider):
    """OpenAI API provider (GPT-4, GPT-5, etc.)."""

    name = "openai"
    default_model = "gpt-5"
    fast_model = "gpt-4o-mini"
    embedding_model = "text-embedding-3-small"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)

    def complete(self, messages: List[Dict], model: str = None) -> str:
        response = self._client.responses.create(
            model=model or self.default_model,
            input=messages,
        )
        return response.output_text

    def stream(self, messages: List[Dict], model: str = None) -> Generator[str, None, None]:
        response = self._client.responses.create(
            model=model or self.default_model,
            input=messages,
            stream=True,
        )
        for event in response:
            if event.type == "response.output_text.delta":
                yield event.delta

    def embed(self, text: str) -> List[float]:
        response = self._client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )
        return response.data[0].embedding


# ============================================================
# Anthropic Implementation
# ============================================================

class AnthropicProvider(LLMProvider):
    """Anthropic API provider (Claude Sonnet, Claude Opus, etc.)."""

    name = "anthropic"
    default_model = "claude-sonnet-4-6"
    fast_model = "claude-haiku-4-5-20251001"
    embedding_model = None 

    def __init__(self, api_key: str):
        super().__init__(api_key)
        from anthropic import Anthropic
        self._client = Anthropic(api_key=api_key)

    def complete(self, messages: List[Dict], model: str = None) -> str:
        # Anthropic separates system from messages
        system_msg = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})

        # Ensure messages alternate user/assistant (Anthropic requirement)
        chat_messages = self._fix_message_order(chat_messages)

        kwargs = {
            "model": model or self.default_model,
            "messages": chat_messages,
            "max_tokens": 4096,
        }
        if system_msg:
            kwargs["system"] = system_msg

        response = self._client.messages.create(**kwargs)
        return response.content[0].text

    def stream(self, messages: List[Dict], model: str = None) -> Generator[str, None, None]:
        system_msg = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})

        chat_messages = self._fix_message_order(chat_messages)

        kwargs = {
            "model": model or self.default_model,
            "messages": chat_messages,
            "max_tokens": 4096,
        }
        if system_msg:
            kwargs["system"] = system_msg

        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

    def embed(self, text: str) -> List[float]:
        # Anthropic doesn't have a native embedding API.
        # Option 1: Use Voyage AI (Anthropic's recommended partner)
        # Option 2: Fall back to OpenAI embeddings
        # Option 3: Use a local model
        raise NotImplementedError(
            "Anthropic doesn't provide embeddings. "
            "Use VoyageAI or configure a separate embedding provider."
        )

    @staticmethod
    def _fix_message_order(messages: List[Dict]) -> List[Dict]:
        """Ensure messages alternate user/assistant as Anthropic requires."""
        if not messages:
            return [{"role": "user", "content": "Hello"}]

        fixed = []
        for m in messages:
            if fixed and fixed[-1]["role"] == m["role"]:
                # Merge consecutive same-role messages
                fixed[-1]["content"] += "\n" + m["content"]
            else:
                fixed.append(dict(m))

        # Must start with user
        if fixed[0]["role"] != "user":
            fixed.insert(0, {"role": "user", "content": "Continue."})

        return fixed


# ============================================================
# Mistral Implementation
# ============================================================

class MistralProvider(LLMProvider):
    """Mistral AI provider (Mistral Large, Codestral, etc.)."""

    name = "mistral"
    default_model = "mistral-large-latest"
    fast_model = "mistral-small-latest"
    embedding_model = "mistral-embed"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        from mistralai import Mistral
        self._client = Mistral(api_key=api_key)

    def complete(self, messages: List[Dict], model: str = None) -> str:
        response = self._client.chat.complete(
            model=model or self.default_model,
            messages=messages,
        )
        return response.choices[0].message.content

    def stream(self, messages: List[Dict], model: str = None) -> Generator[str, None, None]:
        response = self._client.chat.stream(
            model=model or self.default_model,
            messages=messages,
        )
        for event in response:
            if event.data.choices and event.data.choices[0].delta.content:
                yield event.data.choices[0].delta.content

    def embed(self, text: str) -> List[float]:
        response = self._client.embeddings.create(
            model=self.embedding_model,
            inputs=[text],
        )
        return response.data[0].embedding


# ============================================================
# Provider Factory
# ============================================================

# Registry of available providers
_PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "mistral": MistralProvider,
}


def detect_provider(api_key: str) -> str:
    """Auto-detect the provider from the API key format."""
    if not api_key:
        return "openai"  # default
    if api_key.startswith("sk-ant-"):
        return "anthropic"
    if api_key.startswith("sk-"):
        return "openai"
    if len(api_key) == 32:
        return "mistral"
    return "openai"  # default fallback


def get_provider(api_key: str, provider: str = None) -> LLMProvider:
    """
    Get an LLM provider instance.
    
    Args:
        api_key: The API key
        provider: Provider name ('openai', 'anthropic', 'mistral') or None for auto-detect
    
    Returns:
        An LLMProvider instance ready to use
    
    Example:
        llm = get_provider(api_key="sk-...")
        response = llm.complete([{"role": "user", "content": "Hello"}])
    """
    if provider is None:
        provider = detect_provider(api_key)

    provider_class = _PROVIDERS.get(provider)
    if not provider_class:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(_PROVIDERS.keys())}")

    return provider_class(api_key)


def register_provider(name: str, provider_class: type):
    """
    Register a new provider at runtime.
    
    Example:
        class MyCustomProvider(LLMProvider):
            ...
        register_provider("custom", MyCustomProvider)
    """
    if not issubclass(provider_class, LLMProvider):
        raise TypeError(f"{provider_class} must subclass LLMProvider")
    _PROVIDERS[name] = provider_class


# ============================================================
# Example: How to migrate engine.py to use this
# ============================================================
"""
BEFORE (hardcoded to OpenAI):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.responses.create(model="gpt-5", input=messages)
    result = response.output_text

AFTER (provider-agnostic):
    from llm_provider import get_provider
    llm = get_provider(api_key=api_key)
    result = llm.complete(messages)

    # Or with streaming:
    for token in llm.stream(messages):
        yield token

    # Or with a specific model:
    classification = llm.complete(messages, model=llm.fast_model)

    # Or with embeddings:
    vector = llm.embed("serial dilution protocol")

The provider is auto-detected from the API key format,
or can be explicitly specified:
    llm = get_provider(api_key="sk-ant-...", provider="anthropic")
"""