"""Offer to install what audio needs, when it turns out not to be there.

Audio is the one part of this tool whose dependencies cannot be expressed as
ordinary package metadata. ``pitches-peaches[audio]`` brings kokoro, but kokoro
reaches for a spaCy pronunciation model at synthesis time and fetches it with a
downloader that shells out to ``pip`` — which a uv-created virtualenv does not
have. So the extra installs cleanly, reports itself installed, and then fails
the first time you ask it to speak.

Rather than leave that to a README nobody rereads, the run offers to fix it at
the moment it matters. Two rules, both of which are the same rule the model
calls follow:

- **Never install anything without asking.** This writes to the environment the
  tool is running in. It is offered once, at the point of use, with the exact
  command shown, and a no is remembered for the rest of the run.
- **Never pretend it worked.** A failed install prints the command so it can be
  run by hand, and the run continues to completion with the narration scripts
  on disk, because audio has never been the reason to have run any of this.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from typing import Callable

from .kokoro import G2P_MODEL, G2P_WHEEL

Reporter = Callable[[str], None]
#: ``(question, default) -> bool``. ``None`` means nobody is there to answer.
Confirm = Callable[[str, bool], bool]


def _uv() -> str | None:
    """uv, if we can find it. It is how this tool is installed in the first place."""
    return shutil.which("uv")


def command_for_g2p() -> list[str] | None:
    """The argv that installs the pronunciation model, or None if we cannot."""
    uv = _uv()
    if uv is None:
        return None
    return [uv, "pip", "install", "--python", sys.executable, G2P_WHEEL]


def ensure_pronunciation_model(
    *,
    confirm: Confirm | None,
    report: Reporter = lambda _: None,
) -> bool:
    """Install kokoro's spaCy model if the reader agrees. True if it is there now.

    Deliberately narrow: this installs *one known wheel* whose URL is a constant
    in this repository, never something read from a response or a config file.
    """
    if importlib.util.find_spec(G2P_MODEL) is not None:
        return True

    argv = command_for_g2p()
    if argv is None:
        report("  uv is not on PATH, so this cannot be installed automatically.")
        return False

    if confirm is None:
        return False  # nobody to ask, so nothing is installed

    report("")
    report(f"Kokoro needs the {G2P_MODEL} pronunciation model, which its own")
    report("installer cannot fetch inside a uv environment. It is a ~12 MB download:")
    report(f"  {' '.join(argv)}")
    if not confirm(f"Install {G2P_MODEL} now?", True):
        return False

    report(f"  installing {G2P_MODEL}")
    try:
        finished = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        report(f"  install failed: {exc}")
        return False

    if finished.returncode != 0:
        detail = (finished.stderr or finished.stdout or "").strip().splitlines()
        report(f"  install failed: {detail[-1] if detail else 'unknown error'}")
        report("  run it by hand with the command above, then re-run render.")
        return False

    # importlib caches what it could not find a moment ago.
    importlib.invalidate_caches()
    if importlib.util.find_spec(G2P_MODEL) is None:
        report("  the install reported success but the model is still not importable.")
        return False

    report(f"  {G2P_MODEL} installed")
    return True
