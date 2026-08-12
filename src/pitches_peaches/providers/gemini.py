"""Google Gemini, via google-genai.

Two things differ from the other two providers and are worth knowing:

- The thinking ladder stops at HIGH. ``--effort xhigh`` and ``--effort max``
  step down to it rather than erroring, so the same command works everywhere.
- Google Search grounding and JSON response schemas cannot be requested on the
  same call. That is fine here, because ``research`` returns prose and only
  ``parse`` needs a schema — but it is why the two cannot be merged into one
  grounded-structured call the way you might on Anthropic.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from .base import (
    PARSE_MAX_TOKENS,
    PROSE_MAX_TOKENS,
    PDF,
    Content,
    ProviderError,
    Research,
    T,
    Text,
    as_parts,
    clamp_effort,
    dedupe,
)

EFFORTS = ("low", "medium", "high")
#: canonical effort -> Gemini thinking level
LEVELS = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH"}


class GeminiProvider:
    name = "gemini"
    default_model = "gemini-3-pro"
    env_key = "GEMINI_API_KEY"
    package = "google.genai"
    extra = "gemini"

    def __init__(self, client=None):
        self._client = client

    def available(self) -> bool:
        return bool(os.environ.get(self.env_key) or os.environ.get("GOOGLE_API_KEY"))

    def installed(self) -> bool:
        import importlib.util

        return importlib.util.find_spec(self.package) is not None

    @property
    def client(self):
        if self._client is None:
            try:
                from google import genai
            except ModuleNotFoundError as exc:
                raise ProviderError(
                    "the google-genai package is not installed. Install it with:\n"
                    '  uv tool install "pitches-peaches[gemini]"'
                ) from exc
            try:
                self._client = genai.Client()
            except Exception as exc:
                raise ProviderError(
                    f"could not create a Gemini client. Set {self.env_key} in "
                    "your environment or in .env in the run directory."
                ) from exc
        return self._client

    def _contents(self, content: Content) -> list[Any]:
        from google.genai import types

        parts = []
        for part in as_parts(content):
            if isinstance(part, Text):
                parts.append(types.Part.from_text(text=part.text))
            elif isinstance(part, PDF):
                parts.append(
                    types.Part.from_bytes(
                        data=part.read(), mime_type="application/pdf"
                    )
                )
        return [types.Content(role="user", parts=parts)]

    def _thinking(self, effort: str):
        from google.genai import types

        return types.ThinkingConfig(thinking_level=LEVELS[clamp_effort(effort, EFFORTS)])

    # -- the three shapes ------------------------------------------------

    def parse(
        self,
        schema: type[T],
        *,
        system: str,
        content: Content,
        model: str,
        effort: str,
        max_tokens: int = PARSE_MAX_TOKENS,
    ) -> T:
        from google.genai import types

        response = self.client.models.generate_content(
            model=model,
            contents=self._contents(content),
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                thinking_config=self._thinking(effort),
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed
        # The SDK returns the parsed model when it can; validate the raw JSON
        # ourselves when it could not, so a near-miss is recoverable.
        raw = (getattr(response, "text", "") or "").strip()
        if not raw:
            raise ProviderError(
                f"the model returned no {schema.__name__} "
                f"(finish reason: {_finish_reason(response)})."
            )
        try:
            return schema.model_validate_json(raw)
        except Exception as exc:
            raise ProviderError(
                f"the model did not return a valid {schema.__name__}: {exc}"
            ) from exc

    def write(
        self,
        *,
        system: str,
        content: Content,
        model: str,
        effort: str,
        max_tokens: int = PROSE_MAX_TOKENS,
        on_text: Callable[[str], None] | None = None,
    ) -> str:
        text, _ = self._stream(
            system=system,
            content=content,
            model=model,
            effort=effort,
            max_tokens=max_tokens,
            grounded=False,
            on_text=on_text,
        )
        return text

    def research(
        self,
        *,
        system: str,
        content: Content,
        model: str,
        effort: str,
        max_tokens: int = PROSE_MAX_TOKENS,
        on_search: Callable[[str], None] | None = None,
    ) -> Research:
        text, chunks = self._stream(
            system=system,
            content=content,
            model=model,
            effort=effort,
            max_tokens=max_tokens,
            grounded=True,
            on_text=None,
        )
        sources, searches = chunks
        if on_search:
            for query in searches:
                on_search(query)
        return Research(text=text, sources=dedupe(sources), searches=dedupe(searches))

    # -- one streaming path ----------------------------------------------

    def _stream(
        self,
        *,
        system: str,
        content: Content,
        model: str,
        effort: str,
        max_tokens: int,
        grounded: bool,
        on_text: Callable[[str], None] | None,
    ):
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            thinking_config=self._thinking(effort),
        )
        if grounded:
            config.tools = [types.Tool(google_search=types.GoogleSearch())]

        chunks: list[str] = []
        sources: list[str] = []
        searches: list[str] = []

        for event in self.client.models.generate_content_stream(
            model=model, contents=self._contents(content), config=config
        ):
            delta = getattr(event, "text", None)
            if delta:
                chunks.append(delta)
                if on_text:
                    on_text(delta)
            found_sources, found_searches = _grounding(event)
            sources.extend(found_sources)
            searches.extend(found_searches)

        text = "".join(chunks).strip()
        if not text:
            raise ProviderError("the model returned no text.")
        return text, (sources, searches)


# -- response walking --------------------------------------------------------


def _finish_reason(response: Any) -> str:
    for candidate in getattr(response, "candidates", None) or []:
        reason = getattr(candidate, "finish_reason", None)
        if reason:
            return str(reason)
    return "unknown"


def _grounding(event: Any) -> tuple[list[str], list[str]]:
    sources: list[str] = []
    searches: list[str] = []
    for candidate in getattr(event, "candidates", None) or []:
        metadata = getattr(candidate, "grounding_metadata", None)
        if metadata is None:
            continue
        searches.extend(str(q) for q in (getattr(metadata, "web_search_queries", None) or []))
        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None) if web else None
            if uri:
                sources.append(str(uri))
    return sources, searches
