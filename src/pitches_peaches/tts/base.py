"""The TTS backend contract.

Three lines of interface, so a user with an API key can drop in their own
backend without forking the project. See "Better voiceovers" in the README for
a worked ElevenLabs example.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class Result:
    path: Path
    seconds: float
    words: int
    backend: str
    voice: str
    rate: int


@runtime_checkable
class TTSBackend(Protocol):
    name: str

    def available(self) -> bool:
        """True when this backend can actually synthesize on this machine."""

    def synthesize(self, text: str, out: Path, voice: str, rate: int) -> Result:
        """Write audio for ``text`` to ``out`` and describe what was written."""


class BackendUnavailable(RuntimeError):
    """Raised with the exact install command that would fix it."""
