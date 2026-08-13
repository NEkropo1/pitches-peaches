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


# --------------------------------------------------------------------------
# How long have you been doing this
# --------------------------------------------------------------------------

DISPUTE = {
    "lines": ["8+ years designing distributed systems", "Jan 2020 - Jan 2022"],
    "note": "These two lines say different things — pick the one you want to lead with.",
}


def _disputed() -> Profile:
    return Profile(
        skills=[], projects=[], years_total="8+ years",
        inconsistencies=[DISPUTE],
    )


def test_a_years_dispute_is_recognised():
    assert cvs.years_dispute(_disputed()) is not None


def test_an_unrelated_inconsistency_is_not_mistaken_for_one(cv):
    profile = Profile(
        skills=[], projects=[],
        inconsistencies=[{"lines": ["Kafka", "no Kafka"], "note": "Two lines disagree about the stack."}],
    )
    assert cvs.years_dispute(profile) is None


def test_whatever_they_type_is_taken_as_true(cv):
    profile = cvs.settle_years(cv, _disputed(), ask=lambda q: "8.5")
    assert profile.years_total == "8.5 years"


@pytest.mark.parametrize(
    "typed,expected",
    [("8.5", "8.5 years"), ("1", "1 year"), ("8,5", "8.5 years"), ("20", "20 years")],
)
def test_a_bare_number_becomes_a_readable_figure(cv, typed, expected):
    assert cvs.settle_years(cv, _disputed(), ask=lambda q: typed).years_total == expected


def test_a_sentence_is_kept_exactly_as_typed(cv):
    said = "8 commercial, longer if you count the unpaid years"
    assert cvs.settle_years(cv, _disputed(), ask=lambda q: said).years_total == said


def test_pressing_enter_keeps_what_the_cv_says(cv):
    assert cvs.settle_years(cv, _disputed(), ask=lambda q: "").years_total == "8+ years"


def test_nobody_to_ask_changes_nothing(cv):
    assert cvs.settle_years(cv, _disputed(), ask=None).years_total == "8+ years"


def test_it_is_asked_once_per_cv_not_once_per_application(cv):
    cvs.settle_years(cv, _disputed(), ask=lambda q: "8.5")

    def refuse(question):
        raise AssertionError("asked again on a later application")

    assert cvs.settle_years(cv, _disputed(), ask=refuse).years_total == "8.5 years"


def test_a_settled_figure_survives_re_parsing_an_edited_cv(cv):
    """The answer is about them, not about the file, so an edit must not lose it."""
    cvs.settle_years(cv, _disputed(), ask=lambda q: "8.5")
    fresh = _disputed()  # as a re-parse would return it
    assert cvs.settle_years(cv, fresh, ask=None).years_total == "8.5 years"


def test_settling_years_does_not_clobber_the_answer_bank(cv):
    cvs.save_extra(cv, [ANSWER])
    cvs.settle_years(cv, _disputed(), ask=lambda q: "8.5")
    assert cvs.load_extra(cv) == [ANSWER]
