"""TTS backends, behind one small Protocol.

Selection: whatever ``tts_backend`` names, or ``auto`` — kokoro if installed,
then macOS ``say``, then nothing. If nothing is available the scripts are still
written to disk and the caller is told exactly what to install.
"""

from __future__ import annotations

import sys

from .base import BackendUnavailable, Result, TTSBackend
from .kokoro import INSTALL_HINT, KokoroBackend
from .normalize import estimate_duration, normalize_for_speech
from .say import SayBackend

__all__ = [
    "BackendUnavailable",
    "Result",
    "TTSBackend",
    "estimate_duration",
    "install_hint",
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


def install_hint() -> str:
    """What to install, phrased for the machine we are actually on."""
    lines = [f"kokoro (free, offline, best quality):  {INSTALL_HINT}"]
    if sys.platform == "darwin":
        lines.append("or use the built-in macOS voices:      --tts-backend say")
    return "\n  ".join(lines)
