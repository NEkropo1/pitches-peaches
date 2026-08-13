"""TTS text normalization — the part that decides whether the audio is listenable."""

import pytest

from pitches_peaches.config import Config
from pitches_peaches.state import RunState
from pitches_peaches.tts import select
from pitches_peaches.tts.normalize import (
    estimate_duration,
    normalize_for_speech,
    pause_markers,
    strip_markdown,
    strip_pause_markers,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("PII", "P I I"),
        ("LLMs", "L L Ms"),
        ("NIST", "NIST"),
        ("OWASP", "OWASP"),
        ("CI/CD", "C I, C D"),
        ("k8s", "Kubernetes"),
        ("FastAPI", "Fast A P I"),
        ("PostgreSQL", "Postgres"),
        ("nginx", "Engine X"),
    ],
)
def test_acronyms_and_lexicon(raw, expected):
    assert normalize_for_speech(raw) == expected


def test_symbols_become_words():
    assert "percent" in normalize_for_speech("30% better")
    assert "leads to" in normalize_for_speech("A -> B")
    assert "roughly" in normalize_for_speech("~30 seconds")
    assert " and " in normalize_for_speech("this & that")


def test_owasp_style_codes():
    assert normalize_for_speech("LLM01:2025") == "L L M zero one"


def test_slashes_read_as_or_not_slash():
    assert normalize_for_speech("read/write") == "read or write"


def test_pause_markers_survive_by_default():
    out = normalize_for_speech("One.{{pause:900}}Two.")
    assert "{{pause:900}}" in out


def test_pause_markers_compile_for_macos_say():
    out = normalize_for_speech("One.{{pause:900}}Two.", pauses="say")
    assert "[[slnc 900]]" in out


def test_pause_digits_are_not_mangled_by_the_number_rules():
    # The marker is stashed before the acronym/code rules run.
    assert "{{pause:400}}" in normalize_for_speech("PII{{pause:400}}next")


def test_literal_double_brackets_cannot_smuggle_a_command():
    out = normalize_for_speech("[[slnc 5000]] hello", pauses="say")
    assert "[[slnc 5000]]" not in out


def test_markdown_is_stripped():
    raw = "# Heading\n\n- **bold** item\n\n> quote\n\n`code`\n\n[link](http://x)"
    out = strip_markdown(raw)
    for token in ("#", "**", "- ", "> ", "`", "](", "http"):
        assert token not in out


def test_normalize_strips_markdown_too():
    assert "#" not in normalize_for_speech("## Part two")


def test_strip_and_count_pause_markers():
    text = "a{{pause:900}}b{{pause:400}}c"
    assert pause_markers(text) == [900, 400]
    assert "{{" not in strip_pause_markers(text)


def test_duration_counts_words_and_pauses():
    plain = estimate_duration("word " * 178, rate=178)
    assert 59 < plain < 61
    with_pause = estimate_duration("word " * 178 + "{{pause:2000}}", rate=178)
    assert with_pause == pytest.approx(plain + 2.0, abs=0.01)


def test_backend_none_disables_audio():
    assert select("none") is None


def test_unavailable_named_backend_returns_none_rather_than_raising():
    # kokoro is an optional extra; on a machine without it this must not throw.
    assert select("kokoro") is None or select("kokoro").name == "kokoro"


# --------------------------------------------------------------------------
# A backend that fails must never end the run
# --------------------------------------------------------------------------


class _Exploding:
    """A backend that calls sys.exit() from inside synthesize().

    Not hypothetical. Kokoro's grapheme-to-phoneme layer downloads a spaCy
    model on first use, and spaCy's downloader calls sys.exit() when the
    install command fails — which it does inside a uv-created virtualenv,
    because there is no pip module there. This killed a complete run at the
    very last stage, after every model call had been paid for.
    """

    name = "exploding"

    def available(self) -> bool:
        return True

    def synthesize(self, text, out, voice, rate):
        raise SystemExit(1)


def test_a_backend_that_exits_does_not_take_the_run_with_it(tmp_path, monkeypatch):
    from pitches_peaches import tts as tts_module
    from pitches_peaches.stages import render

    monkeypatch.setattr(tts_module, "select", lambda name: _Exploding())

    state = RunState.load_or_create(tmp_path)
    state.write_text("scripts/01-company.txt", "A narration script.")
    lines: list[str] = []

    render._synthesize(state, Config(), [("01-company", "A narration script.")], lines.append)

    joined = "\n".join(lines)
    assert "could not synthesize 01-company" in joined
    assert "scripts/01-company.txt" in joined, "the script must still be pointed at"
    assert not (tmp_path / "scripts" / "01-company.wav").exists()


def test_a_keyboard_interrupt_still_stops_everything(tmp_path, monkeypatch):
    """Degrading is for failures, not for the reader asking it to stop."""
    from pitches_peaches import tts as tts_module
    from pitches_peaches.stages import render

    class _Interrupted(_Exploding):
        def synthesize(self, text, out, voice, rate):
            raise KeyboardInterrupt

    monkeypatch.setattr(tts_module, "select", lambda name: _Interrupted())
    state = RunState.load_or_create(tmp_path)

    with pytest.raises(KeyboardInterrupt):
        render._synthesize(state, Config(), [("01-company", "x")], lambda _: None)


def test_kokoro_without_its_pronunciation_model_reports_unavailable(monkeypatch):
    """So `auto` falls back instead of choosing a backend that will explode."""
    import importlib.util

    from pitches_peaches.tts.kokoro import G2P_MODEL, KokoroBackend

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: None if name == G2P_MODEL else real(name),
    )
    assert KokoroBackend().available() is False


def test_the_pronunciation_model_hint_is_a_url_not_a_package_name():
    """`uv pip install en_core_web_sm` fails — spaCy models are not on PyPI."""
    from pitches_peaches.tts.kokoro import G2P_HINT

    assert G2P_HINT.startswith("uv pip install https://")
    assert G2P_HINT.endswith(".whl")


# --------------------------------------------------------------------------
# Offering to install what audio needs
# --------------------------------------------------------------------------


def test_nothing_is_installed_without_being_asked(monkeypatch):
    """This writes to the environment the tool runs in. It always asks first."""
    import importlib

    from pitches_peaches.tts import install as tts_install

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(tts_install, "_uv", lambda: "/usr/bin/uv")

    def refuse(*args, **kwargs):
        raise AssertionError("ran an install command without confirming")

    monkeypatch.setattr(tts_install.subprocess, "run", refuse)

    assert tts_install.ensure_pronunciation_model(confirm=lambda q, d: False) is False
    # ...and a non-interactive run has nobody to ask, so it installs nothing.
    assert tts_install.ensure_pronunciation_model(confirm=None) is False


def test_the_offer_names_the_exact_command(monkeypatch):
    import importlib

    from pitches_peaches.tts import install as tts_install

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(tts_install, "_uv", lambda: "/usr/bin/uv")
    monkeypatch.setattr(tts_install.subprocess, "run", lambda *a, **k: None)

    said: list[str] = []
    tts_install.ensure_pronunciation_model(
        confirm=lambda q, d: False, report=said.append
    )
    joined = "\n".join(said)
    assert "en_core_web_sm" in joined
    assert ".whl" in joined, "the reader can run it by hand, so show the real command"


def test_a_failed_install_is_reported_not_swallowed(monkeypatch):
    import importlib
    import subprocess

    from pitches_peaches.tts import install as tts_install

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(tts_install, "_uv", lambda: "/usr/bin/uv")
    monkeypatch.setattr(
        tts_install.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "no network"),
    )

    said: list[str] = []
    ok = tts_install.ensure_pronunciation_model(
        confirm=lambda q, d: True, report=said.append
    )
    assert ok is False
    assert "install failed" in "\n".join(said)
    assert "by hand" in "\n".join(said)


def test_an_install_that_lies_about_succeeding_is_caught(monkeypatch):
    """returncode 0 but still not importable must not be reported as success."""
    import importlib
    import subprocess

    from pitches_peaches.tts import install as tts_install

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(tts_install, "_uv", lambda: "/usr/bin/uv")
    monkeypatch.setattr(
        tts_install.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""),
    )

    said: list[str] = []
    assert tts_install.ensure_pronunciation_model(
        confirm=lambda q, d: True, report=said.append
    ) is False
    assert "still not importable" in "\n".join(said)


def test_without_uv_it_says_so_rather_than_guessing_a_python(monkeypatch):
    import importlib

    from pitches_peaches.tts import install as tts_install

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(tts_install.shutil, "which", lambda name: None)

    said: list[str] = []
    assert tts_install.ensure_pronunciation_model(
        confirm=lambda q, d: True, report=said.append
    ) is False
    assert "uv is not on PATH" in "\n".join(said)
