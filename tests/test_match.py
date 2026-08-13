"""The match stage asks first and scores once.

The shape under test is the whole point of the stage: work out what to ask in
one small call, put those questions to the reader, and generate the card a
single time with the answers already in it. The card is the longest generation
in the stage, so scoring twice and discarding the first result is the most
expensive thing this pipeline can do by accident — these tests are what stop it
coming back.
"""

from __future__ import annotations

import pytest

from pitches_peaches.config import Config
from pitches_peaches.models import Match, MatchDraft, Probe, ProbeSet, Profile
from pitches_peaches.stages import match as stage
from pitches_peaches.state import RunState

CV_LINE = "Ran Kafka in production for four years, including a partition rebalance incident."

PROFILE = Profile(
    name="A Candidate",
    skills=[{"name": "Kafka", "cv_line": CV_LINE, "depth": "core"}],
    projects=[{"name": "Ingest", "what_you_did": CV_LINE}],
)


def _draft(**over) -> MatchDraft:
    base = dict(
        overall=74,
        dimensions=[
            {"name": n, "score": 70, "reasoning": "because"}
            for n in ("technical", "ownership", "delivery", "business_context")
        ],
        fit_points=[{"statement": "s", "quote": CV_LINE, "claim": "Kafka"}],
        gaps=[{"headline": "h", "detail": "d"}],
        prepare=["lead with the migration"],
        probes=[],
    )
    return MatchDraft.model_validate({**base, **over})


class StubLLM:
    """Records every call, and returns whatever the test queued for that schema."""

    def __init__(self, *, probes: list[dict] | None = None, draft: MatchDraft | None = None):
        self.config = Config()
        self._probes = probes or []
        self._draft = draft or _draft()
        self.calls: list[str] = []
        self.systems: list[str] = []

    def parse(self, schema, *, system, content, effort=None, max_tokens=None):
        self.calls.append(schema.__name__)
        self.systems.append(system)
        if schema is ProbeSet:
            return ProbeSet(probes=[Probe.model_validate(p) for p in self._probes])
        return self._draft


@pytest.fixture
def state(tmp_path) -> RunState:
    state = RunState.load_or_create(tmp_path)
    state.write_json("recon.json", {"company": "Acme", "role_title": "Backend Engineer"})
    state.write_json("profile.json", PROFILE)
    state.write_text("cv-source.txt", CV_LINE)
    return state


ONE_PROBE = [{"question": "Have you run Kafka?", "why": "the only must-have you omit"}]


def test_the_card_is_generated_exactly_once(state):
    """The regression this stage was restructured to fix."""
    llm = StubLLM(probes=ONE_PROBE)
    stage.run(state, llm, interactive=True, ask=lambda q: "yes, four years")

    assert llm.calls == ["ProbeSet", "MatchDraft"], (
        "expected one cheap probe call then one card; a second MatchDraft means "
        "the discarded-first-draft regression is back"
    )


def test_answers_reach_the_only_scoring_call(state):
    """Answering after the card exists would be pointless — it must land before."""
    llm = StubLLM(probes=ONE_PROBE)
    stage.run(state, llm, interactive=True, ask=lambda q: "yes, four years")

    scoring_prompt = llm.systems[llm.calls.index("MatchDraft")]
    assert "yes, four years" in scoring_prompt
    assert "already been asked" in scoring_prompt  # the collected branch


def test_non_interactive_skips_the_probe_call_entirely(state):
    llm = StubLLM(draft=_draft(probes=[{"question": "q", "why": "w"}]))
    match = stage.run(state, llm, interactive=False)

    assert llm.calls == ["MatchDraft"], "a non-interactive run must not pay for probes"
    assert "Keep it under eight questions" in llm.systems[0]  # the wanted branch
    assert match.provisional is True
    assert [p.question for p in match.probes] == ["q"]


def test_answers_are_saved_before_the_scoring_call(state):
    """A provider error must not be what loses six hand-typed paragraphs."""

    class Boom(StubLLM):
        def parse(self, schema, **kw):
            if schema is not ProbeSet:
                raise RuntimeError("provider exploded")
            return super().parse(schema, **kw)

    with pytest.raises(RuntimeError):
        stage.run(state, Boom(probes=ONE_PROBE), interactive=True, ask=lambda q: "four years")

    saved = state.read_json("profile.json")["extra_notes"]
    assert any("four years" in note for note in saved)


def test_stop_ends_the_loop_without_discarding_earlier_answers(state):
    probes = [
        {"question": "first?", "why": "w"},
        {"question": "second?", "why": "w"},
        {"question": "third?", "why": "w"},
    ]
    answers = iter(["kept", "stop", "never asked"])
    llm = StubLLM(probes=probes)
    stage.run(state, llm, interactive=True, ask=lambda q: next(answers))

    assert state.stages["match"]["probes_answered"] == 1
    assert state.stages["match"]["probes_asked"] == 3
    assert "kept" in llm.systems[-1]


def test_skipped_questions_still_count_as_asked(state):
    """Answer nothing and the card is still final — you were asked, and declined."""
    llm = StubLLM(probes=ONE_PROBE)
    match = stage.run(state, llm, interactive=True, ask=lambda q: "")

    assert llm.calls == ["ProbeSet", "MatchDraft"]
    assert state.stages["match"]["probes_answered"] == 0
    assert match.provisional is False


def test_no_probes_worth_asking_costs_nothing_extra(state):
    llm = StubLLM(probes=[])
    match = stage.run(state, llm, interactive=True, ask=lambda q: pytest.fail("asked anyway"))

    assert llm.calls == ["ProbeSet", "MatchDraft"]
    assert match.probes == []


def test_the_probe_cap_is_ours_to_enforce(state):
    """The prompt asks for at most eight. Code does not trust it to remember."""
    llm = StubLLM(probes=[{"question": f"q{i}", "why": "w"} for i in range(20)])
    asked: list[str] = []
    stage.run(state, llm, interactive=True, ask=lambda q: asked.append(q) or "")

    assert len(asked) == stage.MAX_PROBES


def test_quote_verification_still_runs_on_the_single_draft(state):
    """The one deterministic check on our own output survives the restructure."""
    llm = StubLLM(
        probes=[],
        draft=_draft(fit_points=[{"statement": "s", "quote": "never written", "claim": "c"}]),
    )
    match = stage.run(state, llm, interactive=True, ask=lambda q: "")

    assert match.fit_points == []
    assert state.stages["match"]["quotes_dropped"] == 1


def test_the_match_is_a_valid_card(state):
    match = stage.run(state, StubLLM(probes=ONE_PROBE), interactive=True, ask=lambda q: "yes")
    assert isinstance(match, Match)
    assert state.has("02-fit.md")
    assert Match.model_validate(state.read_json("match.json"))
