"""The only place this project talks to a model.

Every stage goes through here, so provider, model, effort, and grounding are
configured once and behave the same everywhere. The provider-specific work
lives in ``providers/``; this is the facade the stages see.

Three call shapes:

``parse``     structured stage artifacts, validated against a Pydantic model.
``write``     long-form prose. Always streamed — these documents run past 16k
              tokens and a non-streaming request would hit the HTTP timeout.
``research``  grounded recon, using the provider's server-side web search.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import Config
from .providers import (
    PARSE_MAX_TOKENS,
    PROSE_MAX_TOKENS,
    PDF,
    Content,
    Provider,
    ProviderError,
    Research,
    Text,
    default_model_for,
    select,
)
from .providers.base import T

__all__ = [
    "LLM",
    "LLMError",
    "PDF",
    "Research",
    "Text",
    "pdf_block",
    "text_block",
]

#: Kept as the public error name so stages and the CLI catch one thing.
LLMError = ProviderError


def text_block(text: str) -> Text:
    return Text(text)


def pdf_block(path: Path) -> PDF:
    return PDF(Path(path))


class LLM:
    """Config plus a provider. Stages hold one of these and nothing else."""

    def __init__(self, config: Config, *, provider: Provider | None = None):
        self.config = config
        self._provider = provider or select(config.provider)

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def model(self) -> str:
        """The configured model, or the provider's default if none was set.

        ``model = "auto"`` in peaches.toml means "whatever this provider's
        default is", so switching provider does not also require switching
        model — a claude model id sent to OpenAI is a confusing 404.
        """
        configured = (self.config.model or "").strip()
        if not configured or configured == "auto":
            return default_model_for(self.config.provider)
        return configured

    def describe(self) -> str:
        return f"{self._provider.name}/{self.model}"

    # -- the three shapes --------------------------------------------------

    def parse(
        self,
        schema: type[T],
        *,
        system: str,
        content: Content,
        effort: str | None = None,
        max_tokens: int = PARSE_MAX_TOKENS,
    ) -> T:
        """Return a validated instance of ``schema``.

        The schema is closed, which is the structural half of the CV-injection
        answer: an instruction hidden in a CV has nowhere to land, because the
        only thing this call can emit is a shape we defined.
        """
        return self._provider.parse(
            schema,
            system=system,
            content=content,
            model=self.model,
            effort=effort or self.config.parse_effort,
            max_tokens=max_tokens,
        )

    def write(
        self,
        *,
        system: str,
        content: Content,
        effort: str | None = None,
        max_tokens: int = PROSE_MAX_TOKENS,
        on_text: Callable[[str], None] | None = None,
    ) -> str:
        """Stream a long-form prose document and return the whole thing."""
        return self._provider.write(
            system=system,
            content=content,
            model=self.model,
            effort=effort or self.config.effort,
            max_tokens=max_tokens,
            on_text=on_text,
        )

    def research(
        self,
        *,
        system: str,
        content: Content,
        effort: str | None = None,
        max_tokens: int = PROSE_MAX_TOKENS,
        on_search: Callable[[str], None] | None = None,
    ) -> Research:
        """Grounded research using the provider's server-side web search."""
        return self._provider.research(
            system=system,
            content=content,
            model=self.model,
            effort=effort or self.config.effort,
            max_tokens=max_tokens,
            on_search=on_search,
        )
