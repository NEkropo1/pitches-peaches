"""End-to-end tests against a live provider API.

Skipped unless you opt in — these cost real money:

    pytest --e2e -k smoke                  # one cheap parse call
    pytest --e2e                           # the full pipeline
    pytest --e2e --provider openai         # the same suite, on OpenAI
    pytest --e2e --provider gemini
    pytest --e2e --provider openai --e2e-model gpt-5.4-mini

They assert on *structure and invariants*, never on the model's wording. A test
that asserts the dossier contains a particular sentence is a test of the model,
not of this code, and it will fail for the wrong reasons forever.

What they actually pin down:

- every stage writes the artifact the next stage requires
- every artifact still validates against its schema after a real round trip
- the labelling rule holds on real output (verified claims carry a source)
- every surviving quote is really in the source text
- the band matches the score, and the gate decision is recorded
- fit.html has no external references, so it opens on a plane

Because it asserts only on structure, the same suite is the conformance test
for a new provider: if `--provider yours` passes, your backend is wired
correctly. Point it at your own CV with PEACHES_E2E_CV=/path/to/cv.pdf.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pitches_peaches.config import Config
from pitches_peaches.llm import LLM
from pitches_peaches.models import (
    DIMENSION_NAMES,
    Gate,
    Match,
    Playbook,
    Profile,
    Recon,
    band_for,
)
from pitches_peaches.quotes import quote_appears
from pitches_peaches.state import RunState

pytestmark = pytest.mark.e2e

FIXTURES = Path(__file__).parent / "fixtures"
POSTING = FIXTURES / "posting.txt"
CV = Path(os.environ.get("PEACHES_E2E_CV") or FIXTURES / "cv.json")


@pytest.fixture(scope="module")
def workdir(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("e2e-run")
    RunState.load_or_create(path)
    return path


@pytest.fixture(scope="module")
def provider_name(pytestconfig) -> str:
    from conftest import e2e_provider

    return e2e_provider(pytestconfig)


@pytest.fixture(scope="module")
def llm(workdir: Path, provider_name: str, pytestconfig) -> LLM:
    # Keep the live suite affordable by default; override with PEACHES_EFFORT.
    config = Config.load(
        workdir,
        provider=provider_name,
        model=pytestconfig.getoption("--e2e-model"),
        effort=os.environ.get("PEACHES_EFFORT", "medium"),
    )
    built = LLM.from_config(config, workdir=workdir)
    print(f"\n[e2e] provider: {built.describe()}")
    return built


# -- the cheap one -----------------------------------------------------------


def test_smoke_structured_output_round_trips(llm: LLM):
    """One small parse call. Proves the key, the model id, and the schema path.

    Run this first against any new provider — it is the cheapest thing that
    fails when a credential, model id, or structured-output binding is wrong.
    """
    from pitches_peaches.models import Profile as Schema

    result = llm.parse(
        Schema,
        system=(
            "Extract the structured profile. Invent nothing that is not in the CV."
        ),
        content="Jo Bloggs. 4 years commercial Python. Built a Flask API on Postgres.",
        effort="low",
    )
    assert isinstance(result, Schema)
    assert result.skills, "no skills extracted from an obviously skill-bearing CV"
    assert any("python" in s.name.lower() for s in result.skills)
    for skill in result.skills:
        assert skill.cv_line.strip(), "a skill came back with no source line"


# -- the full pipeline -------------------------------------------------------


@pytest.mark.slow
def test_full_pipeline(workdir: Path, llm: LLM):
    from pitches_peaches.stages import gate as gate_stage
    from pitches_peaches.stages import match as match_stage
    from pitches_peaches.stages import playbook as playbook_stage
    from pitches_peaches.stages import profile as profile_stage
    from pitches_peaches.stages import recon as recon_stage
    from pitches_peaches.stages import render as render_stage

    state = RunState.load(workdir)
    log: list[str] = []

    # --- recon ------------------------------------------------------------
    recon = recon_stage.run(state, llm, str(POSTING), report=log.append)
    assert isinstance(recon, Recon)
    assert state.has("recon.json") and state.has("01-company.md")
    assert recon.claims, "recon found nothing to claim about the company"
    assert recon.requirements, "recon read no requirements out of the posting"

    for claim in recon.claims:
        if claim.confidence == "verified":
            assert claim.source, f"verified claim with no source: {claim.statement}"
        assert claim.why_it_matters.strip()

    assert recon.charitable_read.strip() and recon.uncharitable_read.strip()
    assert recon.charitable_read != recon.uncharitable_read

    # Grounding is the least portable of the three call shapes — check the
    # provider's web search actually ran and its citations were extracted.
    notes = (workdir / "recon-notes.md").read_text()
    assert len(notes) > 800, "research produced almost nothing"
    assert state.stages["recon"]["sources"], (
        "no sources were extracted — the provider's grounding result walker "
        "is probably reading the wrong field"
    )

    dossier = (workdir / "01-company.md").read_text()
    assert len(dossier) > 1500, "the dossier is suspiciously short"
    assert dossier.lstrip().startswith("#")

    # --- profile ----------------------------------------------------------
    profile = profile_stage.run(state, llm, str(CV), report=log.append)
    assert isinstance(profile, Profile)
    assert profile.skills and profile.projects
    for skill in profile.skills:
        assert skill.cv_line.strip(), f"skill {skill.name} has no CV line"

    # --- match ------------------------------------------------------------
    match = match_stage.run(state, llm, interactive=False, report=log.append)
    assert isinstance(match, Match)
    assert match.provisional is True, "non-interactive runs must say so"
    assert {d.name for d in match.dimensions} == set(DIMENSION_NAMES)
    assert match.band == band_for(match.overall)
    assert match.fit_points, "every fit point was dropped by quote verification"
    assert match.gaps

    source = (workdir / "cv-source.txt").read_text() + json.dumps(
        json.loads((workdir / "profile.json").read_text())
    )
    for point in match.fit_points:
        assert quote_appears(point.quote, source), (
            f"a quote survived verification but is not in the source: {point.quote!r}"
        )

    # --- gate -------------------------------------------------------------
    gate, decision = gate_stage.run(
        state, llm, interactive=False, assume="proceed", report=log.append
    )
    assert isinstance(gate, Gate)
    assert gate.recommendation in {"apply", "apply_with_caveats", "do_not_apply"}
    assert gate.spread_read.strip() and gate.reason.strip()
    assert decision == "proceed"
    assert RunState.load(workdir).decision == "proceed"

    # --- playbook ---------------------------------------------------------
    playbook = playbook_stage.run(state, llm, report=log.append)
    assert isinstance(playbook, Playbook)
    assert playbook.technologies, "no technical core was produced"
    assert len(playbook.technologies) <= llm.config.max_technologies
    for tech in playbook.technologies:
        assert tech.questions
        assert len(tech.questions) <= llm.config.max_questions_per_tech
        for question in tech.questions:
            # The depth target is the whole point of this stage.
            assert len(question.answer) > 600, (
                f"shallow answer for {tech.technology}: {question.question!r}"
            )
            assert question.why_this_one.strip()

    # --- render -----------------------------------------------------------
    render_stage.run(state, llm, audio=False, report=log.append)
    for name in ("00-README.md", "02-fit.md", "03-playbook.md", "fit.html"):
        assert state.has(name), f"render did not write {name}"

    page = (workdir / "fit.html").read_text()
    assert "<style>" in page
    assert "https://" not in page.split("<footer>")[0], "fit.html references the network"

    diagrams = list((workdir / "diagrams").glob("*.mermaid"))
    assert diagrams, "no standalone .mermaid files were written"
    for diagram in diagrams:
        assert diagram.read_text().strip().startswith("flowchart")

    # --- the state machine survived the whole thing -----------------------
    final = RunState.load(workdir)
    for stage in ("recon", "profile", "match", "gate", "playbook", "render"):
        assert final.ran(stage), f"{stage} was not recorded in run.json"


@pytest.mark.slow
def test_declined_gate_blocks_the_playbook(workdir: Path, llm: LLM):
    """The ethical spine, exercised: a declined gate must actually stop things."""
    from pitches_peaches.stages import playbook as playbook_stage
    from pitches_peaches.state import StageError

    state = RunState.load(workdir)
    if not state.has("match.json"):
        pytest.skip("depends on the full-pipeline test having run first")

    state.record_decision("declined", "do_not_apply")
    with pytest.raises(StageError) as err:
        playbook_stage.run(state, llm)
    assert "--force" in str(err.value)

    state.record_decision("proceed", "apply")  # leave the run dir as we found it
