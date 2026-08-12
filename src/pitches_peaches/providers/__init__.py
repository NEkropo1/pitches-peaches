"""Provider registry.

Anthropic is the default and the only one whose SDK is a hard dependency;
OpenAI and Gemini are optional extras, so a plain install stays lean.

    peaches run ... --provider openai
    PEACHES_PROVIDER=gemini peaches run ...
"""

from __future__ import annotations

from .anthropic import AnthropicProvider
from .base import (
    PARSE_MAX_TOKENS,
    PROSE_MAX_TOKENS,
    PDF,
    Content,
    Part,
    Provider,
    ProviderError,
    Research,
    Text,
    clamp_effort,
)
from .gemini import GeminiProvider
from .openai import OpenAIProvider

__all__ = [
    "PARSE_MAX_TOKENS",
    "PROSE_MAX_TOKENS",
    "PDF",
    "Content",
    "Part",
    "Provider",
    "ProviderError",
    "Research",
    "Text",
    "clamp_effort",
    "default_model_for",
    "names",
    "select",
]

_PROVIDERS: dict[str, type] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


def names() -> list[str]:
    return list(_PROVIDERS)


def select(name: str = "anthropic") -> Provider:
    """Return the named provider. ``auto`` picks the first with a credential."""
    name = (name or "anthropic").lower()

    if name == "auto":
        for candidate in _PROVIDERS.values():
            provider = candidate()
            if provider.available():
                return provider
        raise ProviderError(
            "no provider credential found. Set one of:\n  "
            + "\n  ".join(f"{p().env_key}  (--provider {n})" for n, p in _PROVIDERS.items())
        )

    if name not in _PROVIDERS:
        raise ProviderError(
            f"unknown provider {name!r}. Choose one of: {', '.join(_PROVIDERS)}, auto"
        )
    return _PROVIDERS[name]()


def default_model_for(name: str) -> str:
    """The model to use when the config does not name one."""
    return select(name).default_model
