"""The CV cache never spends money quietly, and never lies about what it has.

Two failures are possible here and both are worse than an extra prompt:
spending on a parse nobody approved, and scoring someone against a CV they
have since rewritten. Every test below is one of those two.
"""

from __future__ import annotations

import pytest

from pitches_peaches import cvs
from pitches_peaches.config import Config
from pitches_peaches.models import Profile
from pitches_peaches.workspace import Workspace, WorkspaceError

CV_TEXT = "# CV\nRan Kafka in production for four years."


class StubLLM:
    """Counts parses. The count is the assertion in most of these tests."""

    def __init__(self):
        self.config = Config()
        self.parses = 0

    def parse(self, schema, *, system, content, effort=None, max_tokens=None):
        self.parses += 1
        return Profile(
            name="A Candidate",
            skills=[{"name": "Kafka", "cv_line": "Ran Kafka in production", "depth": "core"}],
            projects=[{"name": "Ingest", "what_you_did": "Ran Kafka in production"}],
        )


@pytest.fixture
def cv(tmp_path):
    ws = Workspace.create(tmp_path)
    (ws.cvs_dir / "backend-senior.md").write_text(CV_TEXT, encoding="utf-8")
    return ws.cv("backend-senior")


def yes(question, default):
    return True


def no(question, default):
    return False


def test_the_second_application_does_not_pay_to_parse_again(cv):
    """The saving the cache exists for."""
    llm = StubLLM()
    cvs.ensure_parsed(cv, llm, confirm=yes)
    cvs.ensure_parsed(cv, llm, confirm=yes)
    cvs.ensure_parsed(cv, llm, confirm=yes)
    assert llm.parses == 1


def test_a_first_parse_is_asked_for_and_names_the_cost(cv):
    asked = []
    cvs.ensure_parsed(cv, StubLLM(), confirm=lambda q, d: asked.append(q) or True)
    assert len(asked) == 1
    assert "model call" in asked[0]


def test_declining_the_first_parse_spends_nothing_and_names_the_fix(cv):
    llm = StubLLM()
    with pytest.raises(WorkspaceError, match="peaches cv parse backend-senior"):
        cvs.ensure_parsed(cv, llm, confirm=no)
    assert llm.parses == 0


def test_a_named_cv_parses_without_asking_when_nobody_is_there(cv):
    """--non-interactive: you named the CV, so parsing it is what you asked for."""
    llm = StubLLM()
    cvs.ensure_parsed(cv, llm, confirm=None)
    assert llm.parses == 1


def test_an_edited_cv_is_never_scored_against_silently(cv):
    llm = StubLLM()
    cvs.ensure_parsed(cv, llm, confirm=yes)
    cv.path.write_text(CV_TEXT + "\nAlso Postgres.", encoding="utf-8")

    asked = []
    cvs.ensure_parsed(cv, llm, confirm=lambda q, d: asked.append(q) or True)
    assert "has changed" in asked[0]
    assert llm.parses == 2


def test_declining_the_reparse_uses_the_older_one_rather_than_failing(cv):
    llm = StubLLM()
    cvs.ensure_parsed(cv, llm, confirm=yes)
    cv.path.write_text(CV_TEXT + "\nAlso Postgres.", encoding="utf-8")

    cvs.ensure_parsed(cv, llm, confirm=no)
    assert llm.parses == 1


def test_a_stale_cv_refuses_non_interactively_rather_than_guessing(cv):
    """Re-parsing spends unapproved money; using the old parse scores the wrong CV."""
    llm = StubLLM()
    cvs.ensure_parsed(cv, llm, confirm=yes)
    cv.path.write_text(CV_TEXT + "\nAlso Postgres.", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="--reparse"):
        cvs.ensure_parsed(cv, llm, confirm=None)
    assert llm.parses == 1


@pytest.mark.parametrize("reparse,expected", [(True, 2), (False, 1)])
def test_the_stale_prompt_can_be_pre_answered_for_scripts(cv, reparse, expected):
    llm = StubLLM()
    cvs.ensure_parsed(cv, llm, confirm=yes)
    cv.path.write_text(CV_TEXT + "\nAlso Postgres.", encoding="utf-8")

    cvs.ensure_parsed(cv, llm, confirm=None, reparse=reparse)
    assert llm.parses == expected


# --------------------------------------------------------------------------
# The answer bank
# --------------------------------------------------------------------------

ANSWER = "Q: Have you run Kafka?\nA: Four years, including a rebalance incident."


def test_promoted_answers_reach_every_later_application(cv):
    llm = StubLLM()
    cvs.save_extra(cv, [ANSWER])

    profile, source = cvs.resolved(cv, llm, confirm=yes)
    assert ANSWER in profile.extra_notes
    assert "rebalance incident" in source, "and it is quotable, or the point is lost"


def test_re_parsing_an_edited_cv_does_not_discard_the_bank(cv):
    """The bank lives outside the parse precisely so an edit cannot drop it."""
    llm = StubLLM()
    cvs.ensure_parsed(cv, llm, confirm=yes)
    cvs.save_extra(cv, [ANSWER])
    cv.path.write_text(CV_TEXT + "\nAlso Postgres.", encoding="utf-8")

    profile, _ = cvs.resolved(cv, llm, confirm=None, reparse=True)
    assert ANSWER in profile.extra_notes


def test_the_bank_does_not_accumulate_duplicates(cv):
    cvs.save_extra(cv, [ANSWER])
    cvs.save_extra(cv, [ANSWER, "Q: Another?\nA: Yes."])
    assert cvs.load_extra(cv) == [ANSWER, "Q: Another?\nA: Yes."]


def test_probe_answers_are_distinguishable_from_other_notes():
    """What the promotion prompt offers, and what it must leave alone."""
    profile = Profile(
        skills=[],
        projects=[],
        extra_notes=["notes I pasted with --notes", ANSWER],
    )
    assert cvs.answers_in(profile) == [ANSWER]
