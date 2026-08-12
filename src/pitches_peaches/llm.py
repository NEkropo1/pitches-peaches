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
    Resolution,
    Text,
    resolve,
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
    """Config plus an already-resolved provider and model.

    The provider is *injected*, not looked up. Resolution — which provider,
    which model, and whether the credential and SDK are actually there —
    happens once in ``providers.resolve()`` at the composition root, so a
    wiring problem is reported before any stage starts rather than surfacing
    from inside recon.
    """

    def __init__(self, config: Config, provider: Provider, model: str):
        self.config = config
        self._provider = provider
        self._model = model

    @classmethod
    def from_config(cls, config: Config, *, workdir=None) -> "LLM":
        """Resolve provider and model from config. Raises with a fix if it cannot."""
        resolution = resolve(config.provider, model=config.model, workdir=workdir)
        return cls.from_resolution(config, resolution)

    @classmethod
    def from_resolution(cls, config: Config, resolution: Resolution) -> "LLM":
        return cls(config, resolution.provider, resolution.model)

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def describe(self) -> str:
        return f"{self._provider.name}/{self._model}"

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
