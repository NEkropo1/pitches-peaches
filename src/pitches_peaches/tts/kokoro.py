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

#: Kokoro's grapheme-to-phoneme layer (misaki) needs this spaCy model, and it
#: is not a package dependency of anything — misaki fetches it on first use.
G2P_MODEL = "en_core_web_sm"
G2P_VERSION = "3.8.0"

#: The wheel URL, not ``uv pip install en_core_web_sm`` — spaCy models are not
#: published to PyPI, so the bare name fails with "no versions of
#: en-core-web-sm". Not ``python -m spacy download`` either: that is the path
#: that breaks here in the first place, because it shells out to a pip a
#: uv-created virtualenv does not have. A URL is ugly and will need bumping
#: when spaCy's major version moves, but it is the one that works.
G2P_WHEEL = (
    f"https://github.com/explosion/spacy-models/releases/"
    f"download/{G2P_MODEL}-{G2P_VERSION}/{G2P_MODEL}-{G2P_VERSION}-py3-none-any.whl"
)
G2P_HINT = f"uv pip install {G2P_WHEEL}"


class KokoroBackend:
    name = "kokoro"

    def available(self) -> bool:
        """Whether synthesis will actually work — not merely whether it imports.

        The spaCy model is checked here because of what happens when it is
        absent: misaki asks spaCy to download it, spaCy shells out to
        ``sys.executable -m pip``, and inside a uv-created venv there is no pip
        module, so the downloader calls ``sys.exit()``. That is a ``SystemExit``
        raised from the middle of synthesis, and the run it kills has already
        paid for every document it was about to narrate.

        Reporting unavailable instead lets ``auto`` fall back to a backend that
        works, and lets the caller print an install line — which is what this
        project does everywhere else something is missing.
        """
        return all(
            importlib.util.find_spec(mod) is not None
            for mod in ("kokoro", "soundfile", "numpy", G2P_MODEL)
        )

    def synthesize(self, text: str, out: Path, voice: str, rate: int) -> Result:
        if not self.available():
            missing_g2p = importlib.util.find_spec(G2P_MODEL) is None and all(
                importlib.util.find_spec(mod) is not None
                for mod in ("kokoro", "soundfile", "numpy")
            )
            if missing_g2p:
                raise BackendUnavailable(
                    f"kokoro is installed but its {G2P_MODEL} pronunciation "
                    "model is not. Install it with:\n  " + G2P_HINT
                )
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
