"""Anthropic — the default provider.

Grounding is the server-side ``web_search_20260209`` tool. Its dynamic
filtering already runs code under the hood, which is why the code execution
tool is deliberately *not* declared alongside it — a second execution
environment confuses the model.
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

WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search_20260209", "name": "web_search"}

#: A server-tool turn can pause; cap the resumes so a loop cannot run away.
MAX_RESUMES = 6
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _blocks(content: Content) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for part in as_parts(content):
        if isinstance(part, Text):
            out.append({"type": "text", "text": part.text})
        elif isinstance(part, PDF):
            out.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(part.read()).decode("ascii"),
                    },
                }
            )
    return out


class AnthropicProvider:
    name = "anthropic"
    default_model = "claude-opus-5"
    env_key = "ANTHROPIC_API_KEY"

    def __init__(self, client=None):
        self._client = client

    def available(self) -> bool:
        return bool(os.environ.get(self.env_key))

    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ModuleNotFoundError as exc:  # pragma: no cover
                raise ProviderError(
                    "the anthropic package is not installed: uv pip install anthropic"
                ) from exc
            try:
                self._client = anthropic.Anthropic()
            except Exception as exc:
                raise ProviderError(
                    f"could not create an Anthropic client. Set {self.env_key} in "
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
        response = self.client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": _blocks(content)}],
            thinking={"type": "adaptive"},
            output_config={"effort": clamp_effort(effort, EFFORTS)},
            output_format=schema,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ProviderError(
                f"the model did not return a valid {schema.__name__} "
                f"(stop reason: {response.stop_reason})."
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
        chunks: list[str] = []
        with self.client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": _blocks(content)}],
            thinking={"type": "adaptive"},
            output_config={"effort": clamp_effort(effort, EFFORTS)},
        ) as stream:
            for delta in stream.text_stream:
                chunks.append(delta)
                if on_text:
                    on_text(delta)
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            raise ProviderError(_refusal(final))
        return "".join(chunks).strip()

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
        """A server-tool turn can stop with ``pause_turn`` when the server-side
        loop hits its iteration limit. Resuming means re-sending the assistant
        turn as-is — no extra "continue" message, which would only confuse it.
        """
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": _blocks(content)}
        ]
        chunks: list[str] = []
        sources: list[str] = []
        searches: list[str] = []

        for _ in range(MAX_RESUMES + 1):
            with self.client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=[WEB_SEARCH_TOOL],
                thinking={"type": "adaptive"},
                output_config={"effort": clamp_effort(effort, EFFORTS)},
            ) as stream:
                for delta in stream.text_stream:
                    chunks.append(delta)
                final = stream.get_final_message()

            if final.stop_reason == "refusal":
                raise ProviderError(_refusal(final))

            for query in _searches_in(final.content):
                searches.append(query)
                if on_search:
                    on_search(query)
            sources.extend(_sources_in(final.content))

            if final.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": final.content})
        else:
            raise ProviderError(
                "the research turn kept pausing past the resume limit; "
                "try a narrower posting or a lower --effort."
            )

        return Research(
            text="".join(chunks).strip(),
            sources=dedupe(sources),
            searches=dedupe(searches),
        )


# -- response walking --------------------------------------------------------


def _refusal(message: Any) -> str:
    details = getattr(message, "stop_details", None)
    category = getattr(details, "category", None) if details else None
    suffix = f" (category: {category})" if category else ""
    return (
        "the model declined this request" + suffix + ". If the posting or CV "
        "touches a restricted area, try --model claude-sonnet-5, or trim the input."
    )


def _searches_in(blocks) -> list[str]:
    out = []
    for block in blocks:
        if getattr(block, "type", None) == "server_tool_use":
            query = (getattr(block, "input", None) or {}).get("query")
            if query:
                out.append(str(query))
    return out


def _sources_in(blocks) -> list[str]:
    """Pull result URLs out of web_search_tool_result blocks.

    On success ``content`` is a list of results; on failure it is a single
    error object. Branch on that before iterating, or an exhausted search
    budget looks like a crash.
    """
    out: list[str] = []
    for block in blocks:
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        content = getattr(block, "content", None)
        if not isinstance(content, list):
            continue
        for result in content:
            url = getattr(result, "url", None)
            if url:
                out.append(str(url))
    return out
