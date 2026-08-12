"""OpenAI, via the Responses API.

Responses rather than Chat Completions because the server-side ``web_search``
tool, structured outputs, and the reasoning-effort control all live there.

The effort ladder happens to line up with Anthropic's — OpenAI accepts
``low``/``medium``/``high``/``xhigh``/``max`` — so ``--effort`` means the same
thing on both. Gemini is the one that needs mapping.
"""

from __future__ import annotations

import base64
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

WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search"}
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _input(content: Content) -> list[dict[str, Any]]:
    """One user message whose content is a list of typed parts."""
    parts: list[dict[str, Any]] = []
    for part in as_parts(content):
        if isinstance(part, Text):
            parts.append({"type": "input_text", "text": part.text})
        elif isinstance(part, PDF):
            encoded = base64.standard_b64encode(part.read()).decode("ascii")
            parts.append(
                {
                    "type": "input_file",
                    "filename": part.name,
                    "file_data": f"data:application/pdf;base64,{encoded}",
                }
            )
    return [{"role": "user", "content": parts}]


class OpenAIProvider:
    name = "openai"
    default_model = "gpt-5.4-mini"
    env_key = "OPENAI_API_KEY"
    package = "openai"
    extra = "openai"

    def __init__(self, client=None):
        self._client = client

    def available(self) -> bool:
        return bool(os.environ.get(self.env_key))

    def installed(self) -> bool:
        import importlib.util

        return importlib.util.find_spec(self.package) is not None

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ModuleNotFoundError as exc:
                raise ProviderError(
                    "the openai package is not installed. Install it with:\n"
                    '  uv tool install "pitches-peaches[openai]"'
                ) from exc
            try:
                self._client = OpenAI()
            except Exception as exc:
                raise ProviderError(
                    f"could not create an OpenAI client. Set {self.env_key} in "
                    "your environment or in .env in the run directory."
                ) from exc
        return self._client

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
        response = self.client.responses.parse(
            model=model,
            instructions=system,
            input=_input(content),
            max_output_tokens=max_tokens,
            reasoning={"effort": clamp_effort(effort, EFFORTS)},
            text_format=schema,
        )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ProviderError(
                f"the model did not return a valid {schema.__name__} "
                f"(status: {getattr(response, 'status', 'unknown')}; "
                f"incomplete: {getattr(response, 'incomplete_details', None)})."
            )
        return parsed

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
        return self._stream(
            system=system,
            content=content,
            model=model,
            effort=effort,
            max_tokens=max_tokens,
            tools=None,
            on_text=on_text,
        )[0]

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
        text, response = self._stream(
            system=system,
            content=content,
            model=model,
            effort=effort,
            max_tokens=max_tokens,
            tools=[WEB_SEARCH_TOOL],
            on_text=None,
        )
        searches = _searches_in(response)
        if on_search:
            for query in searches:
                on_search(query)
        return Research(
            text=text, sources=dedupe(_sources_in(response)), searches=dedupe(searches)
        )

    # -- one streaming path, used by both prose shapes --------------------

    def _stream(
        self,
        *,
        system: str,
        content: Content,
        model: str,
        effort: str,
        max_tokens: int,
        tools: list[dict[str, Any]] | None,
        on_text: Callable[[str], None] | None,
    ) -> tuple[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": system,
            "input": _input(content),
            "max_output_tokens": max_tokens,
            "reasoning": {"effort": clamp_effort(effort, EFFORTS)},
        }
        if tools:
            kwargs["tools"] = tools

        chunks: list[str] = []
        with self.client.responses.stream(**kwargs) as stream:
            for event in stream:
                # Only the visible answer; reasoning summaries have their own
                # event types and must not land in the document.
                if getattr(event, "type", None) == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    chunks.append(delta)
                    if on_text:
                        on_text(delta)
            response = stream.get_final_response()

        text = "".join(chunks).strip()
        if not text:
            # Streaming produced nothing usable; fall back to the assembled text.
            text = (getattr(response, "output_text", "") or "").strip()
        if not text:
            raise ProviderError(
                "the model returned no text "
                f"(status: {getattr(response, 'status', 'unknown')}; "
                f"incomplete: {getattr(response, 'incomplete_details', None)})."
            )
        return text, response


# -- response walking --------------------------------------------------------


def _searches_in(response: Any) -> list[str]:
    """Queries from web_search_call items, when the API reports them."""
    out: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "web_search_call":
            continue
        action = getattr(item, "action", None)
        query = getattr(action, "query", None) if action else None
        if query:
            out.append(str(query))
    return out


def _sources_in(response: Any) -> list[str]:
    """URLs from url_citation annotations on the output text."""
    out: list[str] = []
    for item in getattr(response, "output", None) or []:
        for block in getattr(item, "content", None) or []:
            for annotation in getattr(block, "annotations", None) or []:
                if getattr(annotation, "type", None) == "url_citation":
                    url = getattr(annotation, "url", None)
                    if url:
                        out.append(str(url))
    return out
