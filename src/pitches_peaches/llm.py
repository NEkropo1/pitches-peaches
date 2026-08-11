"""The only place this project talks to Anthropic.

Every stage goes through here, so model, effort, thinking, and grounding are
configured once and behave the same everywhere.

Three call shapes:

``parse``     structured stage artifacts, validated against a Pydantic model.
``write``     long-form prose. Always streamed — these documents run past 16k
              tokens and a non-streaming request would hit the HTTP timeout.
``research``  grounded recon, using the server-side web search tool.

Grounding is the server-side ``web_search_20260209`` tool. Its dynamic
filtering already runs code under the hood, which is why the code execution
tool is deliberately *not* declared alongside it — a second execution
environment confuses the model.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

import anthropic
from pydantic import BaseModel

from .config import Config

T = TypeVar("T", bound=BaseModel)

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20260209",
    "name": "web_search",
}

#: Long-form documents genuinely need this much room; they are always streamed.
PROSE_MAX_TOKENS = 64_000
#: Structured artifacts are smaller, but recon with many claims is not tiny.
PARSE_MAX_TOKENS = 32_000
#: A server-tool turn can pause; cap the resumes so a loop cannot run away.
MAX_RESUMES = 6


class LLMError(RuntimeError):
    pass


@dataclass
class Research:
    text: str
    sources: list[str] = field(default_factory=list)
    searches: list[str] = field(default_factory=list)


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def pdf_block(path: Path) -> dict[str, Any]:
    """A PDF as a document content block.

    The model reads the PDF directly. We deliberately do not shell out to a
    PDF library — layout matters for a CV, and a text extractor loses it.
    """
    data = base64.standard_b64encode(Path(path).read_bytes()).decode("ascii")
    return {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": data},
    }


class LLM:
    def __init__(self, config: Config, *, client: anthropic.Anthropic | None = None):
        self.config = config
        self._client = client

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            try:
                self._client = anthropic.Anthropic()
            except Exception as exc:  # missing key, bad env
                raise LLMError(
                    "could not create an Anthropic client. Set ANTHROPIC_API_KEY "
                    "in your environment or in .env in the run directory."
                ) from exc
        return self._client

    # -- the three shapes --------------------------------------------------

    def parse(
        self,
        schema: type[T],
        *,
        system: str,
        content: str | list[dict[str, Any]],
        effort: str | None = None,
        max_tokens: int = PARSE_MAX_TOKENS,
    ) -> T:
        """Return a validated instance of ``schema``.

        The schema is closed, which is the structural half of the CV-injection
        answer: an instruction hidden in a CV has nowhere to land, because the
        only thing this call can emit is a shape we defined.
        """
        response = self.client.messages.parse(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": _as_content(content)}],
            thinking={"type": "adaptive"},
            output_config={"effort": effort or self.config.parse_effort},
            output_format=schema,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError(
                f"the model did not return a valid {schema.__name__} "
                f"(stop reason: {response.stop_reason})."
            )
        return parsed

    def write(
        self,
        *,
        system: str,
        content: str | list[dict[str, Any]],
        effort: str | None = None,
        max_tokens: int = PROSE_MAX_TOKENS,
        on_text: Callable[[str], None] | None = None,
    ) -> str:
        """Stream a long-form prose document and return the whole thing."""
        chunks: list[str] = []
        with self.client.messages.stream(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": _as_content(content)}],
            thinking={"type": "adaptive"},
            output_config={"effort": effort or self.config.effort},
        ) as stream:
            for delta in stream.text_stream:
                chunks.append(delta)
                if on_text:
                    on_text(delta)
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            raise LLMError(_refusal_message(final))
        return "".join(chunks).strip()

    def research(
        self,
        *,
        system: str,
        content: str | list[dict[str, Any]],
        effort: str | None = None,
        max_tokens: int = PROSE_MAX_TOKENS,
        on_search: Callable[[str], None] | None = None,
    ) -> Research:
        """Grounded research using the server-side web search tool.

        A server-tool turn can stop with ``pause_turn`` when the server-side
        loop hits its iteration limit. Resuming means re-sending the assistant
        turn as-is — no extra "continue" message, which would only confuse it.
        """
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": _as_content(content)}
        ]
        chunks: list[str] = []
        sources: list[str] = []
        searches: list[str] = []

        for _ in range(MAX_RESUMES + 1):
            with self.client.messages.stream(
                model=self.config.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=[WEB_SEARCH_TOOL],
                thinking={"type": "adaptive"},
                output_config={"effort": effort or self.config.effort},
            ) as stream:
                for delta in stream.text_stream:
                    chunks.append(delta)
                final = stream.get_final_message()

            if final.stop_reason == "refusal":
                raise LLMError(_refusal_message(final))

            for query in _searches_in(final.content):
                searches.append(query)
                if on_search:
                    on_search(query)
            sources.extend(_sources_in(final.content))

            if final.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": final.content})
        else:
            raise LLMError(
                "the research turn kept pausing past the resume limit; "
                "try a narrower posting or a lower --effort."
            )

        return Research(
            text="".join(chunks).strip(),
            sources=_dedupe(sources),
            searches=_dedupe(searches),
        )


# -- helpers -----------------------------------------------------------------


def _as_content(content: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [text_block(content)] if isinstance(content, str) else content


def _refusal_message(message: Any) -> str:
    details = getattr(message, "stop_details", None)
    category = getattr(details, "category", None) if details else None
    suffix = f" (category: {category})" if category else ""
    return (
        "the model declined this request" + suffix + ". If the posting or CV "
        "touches a restricted area, try --model claude-sonnet-5, or trim the input."
    )


def _searches_in(blocks: Iterable[Any]) -> list[str]:
    out = []
    for block in blocks:
        if getattr(block, "type", None) == "server_tool_use":
            query = (getattr(block, "input", None) or {}).get("query")
            if query:
                out.append(str(query))
    return out


def _sources_in(blocks: Iterable[Any]) -> list[str]:
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


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
