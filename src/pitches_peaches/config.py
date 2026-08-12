"""Configuration: flag > env > config file > default.

One provider API key is the only value a user ever has to supply, and the only
one never written to a config file. Everything else has a default, and the
provider default is ``auto`` — whichever key you happen to have set.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

try:  # 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

ENV_PREFIX = "PEACHES_"
CONFIG_FILE = "peaches.toml"

DEFAULT_PROVIDER = "auto"
#: "auto" means "this provider's default model", resolved in llm.LLM.model.
DEFAULT_MODEL = "auto"
DEFAULT_EFFORT = "high"

CONFIG_TEMPLATE = """\
# peaches.toml — every knob PitchesPeaches has.
# Precedence: CLI flag > environment variable > this file > built-in default.
# API keys are never written here. Put them in .env or your shell.

provider = "auto"                # PEACHES_PROVIDER — auto|anthropic|openai|gemini
#                                # auto = whichever provider key you have set
model = "auto"                   # PEACHES_MODEL — "auto" = this provider's default
effort = "high"                  # PEACHES_EFFORT — low|medium|high|xhigh|max
parse_effort = "medium"          # PEACHES_PARSE_EFFORT — effort for the parsing stages
max_technologies = 3             # PEACHES_MAX_TECHNOLOGIES — cap on playbook tech blocks
max_questions_per_tech = 3       # PEACHES_MAX_QUESTIONS_PER_TECH — cap on questions each
audio = false                    # PEACHES_AUDIO — synthesize narration on `peaches render`
tts_backend = "auto"             # PEACHES_TTS_BACKEND — auto|kokoro|say|none
voice = "af_heart"               # PEACHES_VOICE — kokoro voice id, or a macOS `say` voice
rate = 178                       # PEACHES_RATE — words per minute; ~150 slow, ~180 brisk
"""

GITIGNORE_TEMPLATE = """\
.env
*.wav
*.mp3
*.aiff
__pycache__/
"""

_BOOLS = {"1": True, "true": True, "yes": True, "on": True,
          "0": False, "false": False, "no": False, "off": False}


@dataclass
class Config:
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    parse_effort: str = "medium"
    max_technologies: int = 3
    max_questions_per_tech: int = 3
    audio: bool = False
    tts_backend: str = "auto"
    voice: str = "af_heart"
    rate: int = 178

    @classmethod
    def load(cls, workdir: Path, **overrides: Any) -> Config:
        """Build a config from file, then env, then explicit CLI overrides."""
        values: dict[str, Any] = {}

        path = Path(workdir) / CONFIG_FILE
        if path.exists():
            values.update(tomllib.loads(path.read_text(encoding="utf-8")))

        known = {f.name: f.type for f in fields(cls)}
        for name in known:
            raw = os.environ.get(ENV_PREFIX + name.upper())
            if raw is not None:
                values[name] = raw

        values.update({k: v for k, v in overrides.items() if v is not None})

        coerced: dict[str, Any] = {}
        for name, value in values.items():
            if name not in known:
                continue  # unknown keys in the toml are ignored, not fatal
            coerced[name] = _coerce(name, value, getattr(cls, name, None))
        return cls(**coerced)


def _coerce(name: str, value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        return _BOOLS.get(str(value).strip().lower(), default)
    if isinstance(default, int):
        return int(value)
    return str(value)


def load_dotenv(workdir: Path) -> None:
    """Read ``.env`` from the workdir into the environment, without overriding it.

    Deliberately tiny. The only things that belong there are provider keys —
    ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY — which is also why an
    already-exported shell variable always wins over the file.
    """
    path = Path(workdir) / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):  # people paste shell lines in here
            key = key[len("export ") :].strip()
        os.environ.setdefault(key, _env_value(value))


def _env_value(raw: str) -> str:
    """Parse one ``.env`` right-hand side.

    Strips an inline ``# comment``, because a config template with trailing
    comments is exactly what people uncomment — and a silently swallowed
    comment turns a model id into a 57-character string that fails much later,
    somewhere much less obvious.

    A quoted value is taken verbatim, so a ``#`` inside quotes survives.
    """
    value = raw.strip()
    for quote in ("'", '"'):
        if len(value) >= 2 and value.startswith(quote):
            end = value.find(quote, 1)
            if end != -1:
                return value[1:end]
    # Unquoted: a comment starts at the first '#' that follows whitespace.
    cut = re.search(r"\s#", value)
    if cut:
        value = value[: cut.start()]
    return value.strip()


def any_key_present() -> bool:
    """True when any provider has a usable credential."""
    from .providers import all_providers

    return any(p.available() for p in all_providers())
