"""The provider contract.

Three call shapes, because that is all this pipeline needs:

``parse``     a structured artifact, validated against a Pydantic model
``write``     a long-form prose document, streamed
``research``  grounded prose, using the provider's server-side web search

Content is provider-neutral (``Text`` and ``PDF`` parts); each provider
converts to its own wire format. Same idea as ``TTSBackend`` — ship the good
defaults, keep the contract small enough that someone can add their own.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

#: Long-form documents genuinely need this much room; they are always streamed.
PROSE_MAX_TOKENS = 64_000
#: Structured artifacts are smaller, but recon with many claims is not tiny.
PARSE_MAX_TOKENS = 32_000


@dataclass
class Text:
    text: str


@dataclass
class PDF:
    """A PDF sent to the model as a document, not text-extracted first.

    Layout carries meaning in a CV, and a text extractor drops it.
    """

    path: Path

    def read(self) -> bytes:
        return Path(self.path).read_bytes()

    @property
    def name(self) -> str:
        return Path(self.path).name


Part = Text | PDF
Content = str | list[Part]


@dataclass
class Research:
    text: str
    sources: list[str] = field(default_factory=list)
    searches: list[str] = field(default_factory=list)


class ProviderError(RuntimeError):
    """Something went wrong that the user can act on. The message says what."""


class CredentialError(ProviderError):
    """No usable provider credential. The message names every way to fix it."""


class PackageMissing(ProviderError):
    """The provider's SDK is an optional extra and is not installed."""


@runtime_checkable
class Provider(Protocol):
    name: str
    default_model: str
    env_key: str
    #: Import name of the SDK, and the extra that installs it.
    package: str
    extra: str

    def available(self) -> bool:
        """True when the credential this provider needs is present."""

    def installed(self) -> bool:
        """True when this provider's SDK can be imported."""

    def parse(
        self,
        schema: type[T],
        *,
        system: str,
        content: Content,
        model: str,
        effort: str,
        max_tokens: int = PARSE_MAX_TOKENS,
    ) -> T: ...

    def write(
        self,
        *,
        system: str,
        content: Content,
        model: str,
        effort: str,
        max_tokens: int = PROSE_MAX_TOKENS,
        on_text: Callable[[str], None] | None = None,
    ) -> str: ...

    def research(
        self,
        *,
        system: str,
        content: Content,
        model: str,
        effort: str,
        max_tokens: int = PROSE_MAX_TOKENS,
        on_search: Callable[[str], None] | None = None,
    ) -> Research: ...


# -- shared helpers ----------------------------------------------------------


def as_parts(content: Content) -> list[Part]:
    return [Text(content)] if isinstance(content, str) else list(content)


def flatten_text(content: Content) -> str:
    """All the text in ``content``, for providers that take one string."""
    return "\n\n".join(p.text for p in as_parts(content) if isinstance(p, Text))


@contextmanager
def api_errors(provider: "Provider", model: str = ""):
    """Turn a provider SDK exception into something a person can act on.

    Without this, an expired key produces a forty-line Rich traceback ending
    in the SDK's own wording. The status code is the only part that matters,
    and each one has exactly one likely cause worth naming.
    """
    try:
        yield
    except ProviderError:
        raise
    except Exception as exc:
        status = _status_of(exc)
        if status is None:
            raise
        raise ProviderError(_status_message(status, provider, model, exc)) from exc


def _status_of(exc: Exception) -> int | None:
    """Every provider SDK exposes the HTTP status somewhere slightly different."""
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _status_message(status: int, provider: "Provider", model: str, exc: Exception) -> str:
    key = provider.env_key
    if status == 401:
        return (
            f"{provider.name} rejected {key}.\n"
            "The value must be the whole key and nothing else — check for a "
            "stray character at the start, surrounding quotes, or a trailing\n"
            "comment if it came from a .env file. Confirm what is actually set:\n"
            f'  python -c "import os;k=os.environ.get(\'{key}\',\'\');'
            "print(len(k), repr(k[:8]), repr(k[-4:]))\""
        )
    if status == 403:
        return (
            f"{provider.name} refused {key}: the key is valid but not permitted "
            f"to use {model or 'this model'}. Check the key's project and scopes."
        )
    if status == 404:
        return (
            f"{provider.name} has no model called {model!r} for this account.\n"
            f"Pick another with --model, or drop --model to use "
            f"{provider.default_model}."
        )
    if status == 429:
        return (
            f"{provider.name} rate-limited or out of quota. Wait and retry, or "
            "lower --effort. If this is a brand-new key, check billing is set up."
        )
    if status >= 500:
        return f"{provider.name} returned a {status}. That is their side — retry shortly."
    return f"{provider.name} returned {status}: {exc}"


def dedupe(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


#: The canonical effort ladder. Providers map onto their own.
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def clamp_effort(effort: str, allowed: tuple[str, ...]) -> str:
    """Map a requested effort onto what this provider actually supports.

    Steps *down* to the nearest supported level rather than failing, so
    `--effort max` stays usable against a provider whose ladder stops at high.
    """
    effort = (effort or "high").lower()
    if effort in allowed:
        return effort
    if effort not in EFFORTS:
        return "high" if "high" in allowed else allowed[-1]
    for candidate in reversed(EFFORTS[: EFFORTS.index(effort) + 1]):
        if candidate in allowed:
            return candidate
    return allowed[0]
