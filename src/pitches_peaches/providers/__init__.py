"""Provider registry and resolution.

``resolve()`` is the single composition root: it decides which provider and
model a run uses, and it is the only place that turns a missing credential or a
missing SDK into an error. Everything downstream is handed a ready ``Provider``
rather than looking one up, so a wiring problem surfaces before any stage runs
instead of halfway through recon.

The default is ``auto``: use whichever provider you have a key for. Nothing in
the default path is Anthropic-specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .anthropic import AnthropicProvider
from .base import (
    PARSE_MAX_TOKENS,
    PROSE_MAX_TOKENS,
    PDF,
    Content,
    CredentialError,
    PackageMissing,
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
    "CredentialError",
    "PackageMissing",
    "Part",
    "Provider",
    "ProviderError",
    "Research",
    "Resolution",
    "Text",
    "all_providers",
    "clamp_effort",
    "names",
    "resolve",
    "select",
]

#: Order matters: it is the `auto` priority, and it is reported when it applies.
_PROVIDERS: dict[str, type] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}

AUTO = "auto"


def names() -> list[str]:
    return list(_PROVIDERS)


def all_providers() -> list[Provider]:
    return [cls() for cls in _PROVIDERS.values()]


def select(name: str = AUTO) -> Provider:
    """Construct a provider by name, without checking anything.

    Use ``resolve()`` in application code — this is the low-level constructor,
    kept for tests and for callers that already know what they want.
    """
    name = (name or AUTO).lower()
    if name == AUTO:
        return resolve(AUTO).provider
    if name not in _PROVIDERS:
        raise ProviderError(
            f"unknown provider {name!r}. Choose one of: "
            f"{', '.join(_PROVIDERS)}, {AUTO}"
        )
    return _PROVIDERS[name]()


@dataclass
class Resolution:
    """What a run will actually use, and why."""

    provider: Provider
    model: str
    #: Human-readable explanation, shown when the choice was not explicit.
    reason: str

    @property
    def name(self) -> str:
        return self.provider.name

    def describe(self) -> str:
        return f"{self.name}/{self.model}"


def resolve(
    requested: str | None = None,
    *,
    model: str | None = None,
    workdir: Path | None = None,
) -> Resolution:
    """Pick the provider and model for this run, or explain why we cannot.

    ``requested`` may be a provider name, ``auto``, or None (same as ``auto``).
    ``model`` may be an explicit model id, ``auto``, or None — anything falsy
    or ``auto`` means the chosen provider's own default, so switching provider
    never also requires switching model.
    """
    # Blank counts as auto: an empty provider= line in peaches.toml means
    # "you didn't choose", not "choose a provider named empty string".
    requested = (requested or "").strip().lower() or AUTO

    if requested == AUTO:
        resolution = _resolve_auto(workdir)
    else:
        if requested not in _PROVIDERS:
            raise ProviderError(
                f"unknown provider {requested!r}. Choose one of: "
                f"{', '.join(_PROVIDERS)}, {AUTO}"
            )
        provider = _PROVIDERS[requested]()
        _require_credential(provider, workdir)
        _require_package(provider)
        resolution = Resolution(provider, provider.default_model, "you asked for it")

    chosen = (model or "").strip()
    if chosen and chosen.lower() != AUTO:
        resolution.model = chosen
    return resolution


# -- the auto path -----------------------------------------------------------


def _resolve_auto(workdir: Path | None) -> Resolution:
    candidates = [p for p in all_providers() if p.available()]

    if not candidates:
        raise CredentialError(_no_credential_message(workdir))

    usable = [p for p in candidates if p.installed()]
    if not usable:
        # They have a key, but its SDK is an optional extra they did not install.
        raise PackageMissing(_package_message(candidates[0]))

    picked = usable[0]
    if len(usable) == 1:
        reason = f"the only provider you have a key for ({picked.env_key})"
    else:
        others = ", ".join(p.name for p in usable[1:])
        reason = (
            f"first of several you have keys for; also available: {others}. "
            f"Pin one with --provider, or provider = \"...\" in peaches.toml"
        )
    return Resolution(picked, picked.default_model, reason)


# -- errors that say what to do ----------------------------------------------


def _require_credential(provider: Provider, workdir: Path | None) -> None:
    if provider.available():
        return

    lines = [
        f"The {provider.name} provider needs {provider.env_key}, which is not set.",
    ]

    others = [p for p in all_providers() if p.name != provider.name and p.available()]
    if others:
        other = others[0]
        lines += [
            "",
            f"You do have {other.env_key} set. To use it, either:",
            f"  peaches ... --provider {other.name}",
            f"  PEACHES_PROVIDER={other.name} peaches ...",
            f'  provider = "{other.name}"   in peaches.toml',
            "",
            "Or drop --provider entirely — the default picks whichever key is set.",
        ]
    else:
        lines += ["", _no_credential_message(workdir)]

    raise CredentialError("\n".join(lines))


def _require_package(provider: Provider) -> None:
    if not provider.installed():
        raise PackageMissing(_package_message(provider))


def _package_message(provider: Provider) -> str:
    return (
        f"The {provider.name} provider needs the `{provider.package}` package, "
        "which is not installed.\n"
        f'  uv tool install --force "pitches-peaches[{provider.extra}]"\n'
        "or, from a checkout:\n"
        f'  uv tool install --force --editable ".[{provider.extra}]"'
    )


def _no_credential_message(workdir: Path | None) -> str:
    rows = []
    for provider in all_providers():
        installed = "" if provider.installed() else "   (SDK not installed)"
        rows.append(
            f"  {provider.env_key:<20} --provider {provider.name:<10} "
            f"default model: {provider.default_model}{installed}"
        )

    where = Path(workdir).resolve() if workdir else Path.cwd()
    return "\n".join(
        [
            "No provider credential found.",
            "",
            "Set one of these in your shell, or in a .env file in the run directory:",
            "",
            *rows,
            "",
            f"The run directory here is {where}, so that would be:",
            f"  {where / '.env'}",
            "",
            "There is a template to copy: .env.sample",
        ]
    )
