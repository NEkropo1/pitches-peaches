"""Kokoro — the default. Offline, Apache-2.0, 82M params, cross-platform.

Best quality per install of the offline options, which is why it is the
default. It is an optional extra because the model weights are a large download
and most people run this without audio at all.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .base import BackendUnavailable, Result
from .normalize import estimate_duration, normalize_for_speech, strip_pause_markers

SAMPLE_RATE = 24_000
INSTALL_HINT = 'uv tool install "pitches-peaches[audio]"'


class KokoroBackend:
    name = "kokoro"

    def available(self) -> bool:
        return all(
            importlib.util.find_spec(mod) is not None
            for mod in ("kokoro", "soundfile", "numpy")
        )

    def synthesize(self, text: str, out: Path, voice: str, rate: int) -> Result:
        if not self.available():
            raise BackendUnavailable(
                "kokoro is not installed. Install it with:\n  " + INSTALL_HINT
            )

        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline

        # Kokoro has no pause command, so pauses become real silence.
        spoken = normalize_for_speech(text, pauses="keep")
        pipeline = KPipeline(lang_code=voice[:1] if voice else "a")

        chunks: list[object] = []
        for segment, gap_ms in _segments(spoken):
            if segment.strip():
                for _, _, audio in pipeline(segment, voice=voice, speed=_speed(rate)):
                    chunks.append(audio)
            if gap_ms:
                chunks.append(np.zeros(int(SAMPLE_RATE * gap_ms / 1000), dtype="float32"))

        if not chunks:
            raise BackendUnavailable("nothing to synthesize — the script was empty")

        audio = np.concatenate([np.asarray(c, dtype="float32") for c in chunks])
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out), audio, SAMPLE_RATE)

        return Result(
            path=out,
            seconds=len(audio) / SAMPLE_RATE,
            words=len(strip_pause_markers(spoken).split()),
            backend=self.name,
            voice=voice,
            rate=rate,
        )


def _speed(rate: int) -> float:
    """Kokoro takes a speed multiplier; 178 wpm is its natural pace at 1.0."""
    return max(0.5, min(2.0, rate / 178))


def _segments(text: str) -> list[tuple[str, int]]:
    """Split on pause markers into (text, silence-after-ms) pairs."""
    import re

    parts = re.split(r"\{\{\s*pause\s*:\s*(\d{1,5})\s*\}\}", text)
    out: list[tuple[str, int]] = []
    for index in range(0, len(parts), 2):
        chunk = parts[index]
        gap = int(parts[index + 1]) if index + 1 < len(parts) else 0
        out.append((chunk, gap))
    return out


def duration_estimate(text: str, rate: int) -> float:
    return estimate_duration(text, rate)
