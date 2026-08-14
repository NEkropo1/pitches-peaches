"""macOS `say` — zero install, auto-selected on Darwin when kokoro is absent.

Quality is bounded by which voices the OS has. The default-quality voices are
clear but plainly synthetic; the Enhanced and Premium voices are a large step
up and free — see "Better voiceovers" in the README.

Output is compressed by ``encode``, so a narration lands as .mp3 or .m4a rather
than the AIFF `say` emits. A forty-minute playbook is 108 MB uncompressed and
about 19 MB as speech-rate MP3, which is the difference between an artifact you
can keep and one you delete.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from . import encode
from .base import BackendUnavailable, Result
from .normalize import estimate_duration, normalize_for_speech, strip_pause_markers

DEFAULT_VOICE = "Samantha"


class SayBackend:
    name = "say"

    def available(self) -> bool:
        return sys.platform == "darwin" and shutil.which("say") is not None

    def synthesize(self, text: str, out: Path, voice: str, rate: int) -> Result:
        if not self.available():
            raise BackendUnavailable("`say` is macOS-only and was not found")

        # `say` understands [[slnc N]]; normalize_for_speech emits it for us.
        spoken = normalize_for_speech(text, pauses="say")
        # A kokoro voice id means nothing to `say` — fall back rather than fail.
        if not voice or "_" in voice or voice.islower():
            voice = DEFAULT_VOICE

        stem = out.with_suffix("")
        stem.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "speech.aiff"
            subprocess.run(
                # No --data-format. LEF32 is little-endian float, AIFF is
                # big-endian by definition, and macOS rejects the pair with
                # "Opening output file failed: fmt?" after writing a zero-byte
                # file. `say -o out.aiff` on its own picks a format that works,
                # and afinfo reads the duration back off it either way.
                ["say", "-v", voice, "-r", str(rate), "-o", str(raw)],
                input=spoken.encode("utf-8"),
                check=True,
            )
            try:
                out = encode.compress(raw, stem)
            except encode.EncodeError:
                out = stem.with_suffix(".aiff")  # a converter failed; keep the audio
            if out == raw:  # nothing better than AIFF is available here
                out = stem.with_suffix(".aiff")
            if not out.exists():
                shutil.copyfile(raw, out)

        return Result(
            path=out,
            seconds=encode.duration(out) or _measure(out) or estimate_duration(spoken, rate),
            words=len(strip_pause_markers(spoken).split()),
            backend=self.name,
            voice=voice,
            rate=rate,
        )


def _measure(path: Path) -> float | None:
    """Read the duration back off the file. Measured beats estimated."""
    if shutil.which("afinfo"):
        try:
            output = subprocess.run(
                ["afinfo", str(path)], capture_output=True, text=True, check=True
            ).stdout
            for line in output.splitlines():
                if "estimated duration" in line:
                    return float(line.split(":")[1].strip().split()[0])
        except (subprocess.CalledProcessError, ValueError, IndexError):
            pass
    try:
        with wave.open(str(path)) as handle:
            return handle.getnframes() / handle.getframerate()
    except Exception:
        return None


def list_voices() -> list[str]:
    if shutil.which("say") is None:
        return []
    output = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return [line.split()[0] for line in output.splitlines() if line.strip()]
