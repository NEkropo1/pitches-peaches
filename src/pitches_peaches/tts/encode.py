"""Compress spoken audio, using only what macOS already has.

Vendored from voxsmith (github.com/NEkropo1 — same author, MIT), which was the
extracted and better-developed version of this project's synthesis path. Only
the encoder chain is taken: voxsmith's own text normalization is tuned for
security briefings, and the one in ``normalize.py`` is tuned for CVs and job
postings, which is the vocabulary that turns up here.

Speech at 24 kHz mono is enormously compressible, and uncompressed it is
unusable in practice: one real playbook narration came out at 108 MB, past
GitHub's per-file limit, which is why the checked-in example ships a single
short narration instead of the set.

Three rungs, and the middle one matters most:

``mp3``   needs ``lame`` (``brew install lame``). Plays anywhere.
``m4a``   needs only ``afconvert``, which **ships with macOS**. ~4x smaller
          than AIFF, no install, and the reason this is worth doing at all.
``aiff``  what ``say`` emits. Always available, always large.

Nothing here is required. A missing encoder means a bigger file, never a
failed run — audio is the last and most optional thing this tool does.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_BITRATE = 64
#: Speech carries no useful content above ~11 kHz, so this is not a compromise.
SAMPLE_RATE = 22_050


class EncodeError(RuntimeError):
    """A converter was present but failed."""


def available_format() -> str:
    """The smallest format this machine can actually write."""
    if shutil.which("lame") and shutil.which("afconvert"):
        return "mp3"
    if shutil.which("afconvert"):
        return "m4a"
    return "aiff"


def _run(argv: list[str], what: str) -> None:
    finished = subprocess.run(argv, capture_output=True, text=True)
    if finished.returncode != 0:
        detail = (finished.stderr or finished.stdout or "").strip().splitlines()
        raise EncodeError(f"{what} failed: {detail[-1] if detail else 'unknown error'}")


def _to_wav(src: Path, dest: Path, sample_rate: int = SAMPLE_RATE) -> None:
    """Downmix to mono 16-bit PCM — plenty for speech, and what lame wants."""
    _run(
        ["afconvert", str(src), "-o", str(dest), "-f", "WAVE",
         "-d", f"LEI16@{sample_rate}", "--mix", "-c", "1"],
        "afconvert",
    )


def _to_m4a(src: Path, dest: Path, bitrate: int = DEFAULT_BITRATE) -> None:
    _run(
        ["afconvert", str(src), "-o", str(dest), "-f", "m4af", "-d", "aac",
         "-b", str(bitrate * 1000), "--mix"],
        "afconvert",
    )


def _to_mp3(src: Path, dest: Path, bitrate: int = DEFAULT_BITRATE) -> None:
    """AIFF in, MP3 out. lame wants PCM, so this goes through a temporary WAV."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        _to_wav(src, wav)
        _run(
            ["lame", "--quiet", "-m", "m", "-b", str(bitrate), "-q", "2",
             str(wav), str(dest)],
            "lame",
        )


def compress(src: Path, stem: Path, fmt: str | None = None) -> Path:
    """Encode ``src`` beside ``stem`` in the best format available.

    Returns the path actually written, which is ``src`` itself when nothing
    better than AIFF can be produced.
    """
    fmt = fmt or available_format()
    if fmt == "aiff":
        return src

    dest = stem.with_suffix(f".{fmt}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "mp3":
        _to_mp3(src, dest)
    else:
        _to_m4a(src, dest)
    return dest


def duration(path: Path) -> float | None:
    """True duration read back off the encoded file, if afinfo can."""
    if not shutil.which("afinfo"):
        return None
    finished = subprocess.run(["afinfo", str(path)], capture_output=True, text=True)
    for line in finished.stdout.splitlines():
        if "estimated duration" in line.lower():
            try:
                return float(line.split(":")[1].strip().split()[0])
            except (IndexError, ValueError):
                return None
    return None
