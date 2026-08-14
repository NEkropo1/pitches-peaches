"""TTS backends, behind one small Protocol.

Selection: whatever ``tts_backend`` names, or ``auto`` — kokoro if installed,
then macOS ``say``, then nothing. If nothing is available the scripts are still
written to disk and the caller is told exactly what to install.
"""

from __future__ import annotations

import importlib.util
import sys

from .base import BackendUnavailable, Result, TTSBackend
from .kokoro import G2P_HINT, G2P_MODEL, INSTALL_HINT, KokoroBackend
from .normalize import estimate_duration, normalize_for_speech
from .say import SayBackend

__all__ = [
    "BackendUnavailable",
    "Result",
    "TTSBackend",
    "estimate_duration",
    "install_hint",
    "kokoro_is_only_missing_its_model",
    "normalize_for_speech",
    "select",
]

_BACKENDS: dict[str, type] = {"kokoro": KokoroBackend, "say": SayBackend}


def select(name: str = "auto") -> TTSBackend | None:
    """Return a usable backend, or None. ``none`` disables audio entirely."""
    if name == "none":
        return None
    if name in _BACKENDS:
        backend = _BACKENDS[name]()
        return backend if backend.available() else None

    for candidate in (KokoroBackend(), SayBackend()):
        if candidate.available():
            return candidate
    return None


def kokoro_is_only_missing_its_model() -> bool:
    """Kokoro is installed and the one thing it still needs is fixable.

    The condition worth acting on, kept in one place: everything heavy is
    already on disk and a single ~12 MB wheel stands between the reader and the
    audio they asked for.
    """
    if importlib.util.find_spec("kokoro") is None:
        return False
    return importlib.util.find_spec(G2P_MODEL) is None


def install_hint() -> str:
    """What to install, phrased for the machine we are actually on.

    Kokoro half-installed is the common case rather than an exotic one: the
    extra pulls the model but not the spaCy pronunciation model misaki wants,
    and misaki's own attempt to fetch it fails inside a uv venv. So when kokoro
    is present and only that model is missing, say precisely that instead of
    telling someone to install what they already have.
    """
    if importlib.util.find_spec("kokoro") is not None and (
        importlib.util.find_spec(G2P_MODEL) is None
    ):
        lines = [f"kokoro needs its pronunciation model:  {G2P_HINT}"]
    else:
        lines = [f"kokoro (free, offline, best quality):  {INSTALL_HINT}"]
    if sys.platform == "darwin":
        lines.append("or use the built-in macOS voices:      --tts-backend say")
    return "\n  ".join(lines)
