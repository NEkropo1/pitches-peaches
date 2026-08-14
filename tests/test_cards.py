"""The card renders three ways from one object, with no model call."""

import json
import re
from pathlib import Path

import pytest

from pitches_peaches.cards import BANNER, html_card, markdown, terminal_lines
from pitches_peaches.models import Match

FIXTURE = Path(__file__).parent / "fixtures" / "match.json"


@pytest.fixture
def match() -> Match:
    return Match.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_fixture_is_a_valid_match(match):
    assert match.overall == 74
    assert len(match.dimensions) == 4


# -- the banner is not optional ---------------------------------------------


def test_every_surface_carries_the_banner(match):
    # The terminal surface wraps it, so compare on collapsed whitespace.
    terminal = re.sub(r"\s+", " ", "\n".join(terminal_lines(match)))
    assert BANNER in terminal
    assert BANNER in markdown(match)
    assert BANNER in html_card(match)


def test_terminal_card_is_width_bounded(match):
    """It gets screenshotted and pasted, so it must not depend on the terminal."""
    match.dimensions[0].reasoning = "word " * 120
    match.gaps[0].detail = "detail " * 80
    for line in terminal_lines(match, role="A very long role title", company="Co"):
        assert len(line) <= 92, f"line ran past the fixed width: {line[:60]!r}"


def test_banner_says_it_never_applies_to_anything(match):
    assert "does not apply to anything" in BANNER
    assert "built from what you provided about yourself" in BANNER


# -- all three surfaces show the same numbers -------------------------------


def test_all_surfaces_agree_on_the_scores(match):
    surfaces = [
        "\n".join(terminal_lines(match)),
        markdown(match),
        html_card(match),
    ]
    for surface in surfaces:
        assert "74" in surface
        for dim in match.dimensions:
            assert str(dim.score) in surface


def test_dimensions_render_in_a_fixed_order(match):
    text = "\n".join(terminal_lines(match))
    positions = [
        text.index(label)
        for label in ("TECHNICAL", "OWNERSHIP", "DELIVERY", "BUSINESS CONTEXT")
    ]
    assert positions == sorted(positions)


def test_every_fit_point_shows_its_quote(match):
    for surface in (markdown(match), html_card(match), "\n".join(terminal_lines(match))):
        for point in match.fit_points:
            assert point.quote in surface


def test_provisional_is_shown_when_probes_were_skipped(match):
    match.provisional = True
    assert "provisional" in markdown(match).lower()
    assert "provisional" in html_card(match).lower()
    assert "provisional" in "\n".join(terminal_lines(match)).lower()


# -- the HTML has to be openable from a plane -------------------------------


def test_html_is_self_contained(match):
    page = html_card(match)
    assert "<style>" in page  # inline CSS, not a link
    assert "<script" not in page.lower()
    assert not re.search(r'(src|href)=["\']https?://', page), "external resource found"
    assert "cdn" not in page.lower()


def test_html_escapes_content_rather_than_trusting_it(match):
    match.gaps[0].headline = 'No <script>alert("x")</script> background.'
    page = html_card(match)
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_html_is_well_formed_enough_to_parse(match):
    from html.parser import HTMLParser

    class Strict(HTMLParser):
        def error(self, message):  # pragma: no cover
            raise AssertionError(message)

    Strict().feed(html_card(match))


def test_markdown_has_one_h1_and_the_expected_sections(match):
    text = markdown(match)
    assert len(re.findall(r"^# ", text, re.M)) == 1
    for heading in ("Why you fit", "Gaps", "What to prepare"):
        assert heading in text


def test_diagrams_are_not_redrawn_when_they_already_exist(tmp_path):
    """Re-running render to finish an interrupted one must not re-pay for mermaid."""
    from pitches_peaches.stages import render
    from pitches_peaches.state import RunState

    class _LLM:
        calls = 0

        def parse(self, *a, **kw):
            type(self).calls += 1
            raise AssertionError("drew diagrams that were already on disk")

    state = RunState.load_or_create(tmp_path)
    state.write_text("04-diagrams.md", "# Diagrams\n")

    said: list[str] = []
    render._write_diagrams(state, _LLM(), {}, None, said.append)

    assert _LLM.calls == 0
    assert "reusing" in said[0]
