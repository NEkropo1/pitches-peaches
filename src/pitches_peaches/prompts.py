"""Load prompt text from ``prompts/*.md``.

Prompts live on disk, not in string literals, for two reasons: a user can tune
the voice of their own dossiers without touching Python, and the prompts stay
reviewable as prose.

Placeholders are ``{{name}}``. ``{{voice}}`` expands to the shared voice rules
in ``_voice.md`` so every prompt inherits them without repeating them.

The pattern requires ``\\w+`` between the braces, which is what keeps the TTS
pause markers the narration prompt teaches — ``{{pause:900}}`` — from being
mistaken for placeholders. The colon is doing real work; do not loosen the
pattern to allow punctuation.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent / "prompts"
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class PromptError(RuntimeError):
    pass


@lru_cache(maxsize=None)
def _raw(name: str) -> str:
    path = PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise PromptError(f"no prompt file at {path}")
    return path.read_text(encoding="utf-8")


def render(name: str, **values: object) -> str:
    """Render a prompt, expanding ``{{voice}}`` and any supplied placeholders."""
    values = {"voice": _raw("_voice").strip(), **values}

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise PromptError(f"prompt {name!r} needs a value for {{{{{key}}}}}")
        return str(values[key])

    return _PLACEHOLDER.sub(substitute, _raw(name)).strip()
