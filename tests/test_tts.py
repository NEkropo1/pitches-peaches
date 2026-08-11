"""TTS text normalization — the part that decides whether the audio is listenable."""

import pytest

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
