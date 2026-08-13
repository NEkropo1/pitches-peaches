"""The run directory: resume, dependency errors, and the gate."""

import json
import os

import pytest

from pitches_peaches.config import Config
from pitches_peaches.state import MissingDependency, RunState, StageError


def test_load_without_init_names_the_fix(tmp_path):
    with pytest.raises(StageError) as err:
        RunState.load(tmp_path)
    assert "peaches init" in str(err.value)


def test_load_or_create_is_idempotent(tmp_path):
    first = RunState.load_or_create(tmp_path)
    first.record("recon", url="https://example.com/job")
    second = RunState.load_or_create(tmp_path)
    assert second.ran("recon")
    assert second.stages["recon"]["url"] == "https://example.com/job"


def test_missing_dependency_names_the_producing_command(tmp_path):
    state = RunState.load_or_create(tmp_path)
    with pytest.raises(MissingDependency) as err:
        state.require("recon.json")
    assert "peaches recon" in str(err.value)

    with pytest.raises(MissingDependency) as err:
        state.require("profile.json")
    assert "peaches profile" in str(err.value)


def test_match_depends_on_both_upstream_artifacts(tmp_path):
    state = RunState.load_or_create(tmp_path)
    state.write_json("recon.json", {"company": "Example"})
    with pytest.raises(MissingDependency) as err:
        state.require("recon.json", "profile.json")
    assert err.value.artifact == "profile.json"


def test_artifacts_round_trip(tmp_path):
    state = RunState.load_or_create(tmp_path)
    state.write_json("recon.json", {"company": "Example", "claims": []})
    assert state.read_json("recon.json")["company"] == "Example"


def test_write_json_accepts_a_pydantic_model(tmp_path):
    from pitches_peaches.models import Claim

    state = RunState.load_or_create(tmp_path)
    claim = Claim(
        statement="s", confidence="inferred", source=None, why_it_matters="w"
    )
    state.write_json("claim.json", claim)
    assert state.read_json("claim.json")["confidence"] == "inferred"


def test_gate_must_run_before_downstream_stages(tmp_path):
    state = RunState.load_or_create(tmp_path)
    with pytest.raises(StageError) as err:
        state.require_gate_passed()
    assert "peaches gate" in str(err.value)


def test_declined_gate_blocks_downstream_but_force_overrides(tmp_path):
    state = RunState.load_or_create(tmp_path)
    state.record_decision("declined", "do_not_apply")
    with pytest.raises(StageError) as err:
        state.require_gate_passed()
    assert "--force" in str(err.value)
    state.require_gate_passed(force=True)  # does not raise


def test_proceed_decision_lets_downstream_run(tmp_path):
    state = RunState.load_or_create(tmp_path)
    state.record_decision("proceed", "apply_with_caveats")
    state.require_gate_passed()
    assert state.decision == "proceed"


def test_state_file_is_readable_json(tmp_path):
    state = RunState.load_or_create(tmp_path)
    state.record("recon")
    payload = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert "stages" in payload and "recon" in payload["stages"]


# -- configuration precedence ------------------------------------------------


def test_config_defaults(tmp_path):
    cfg = Config.load(tmp_path)
    assert cfg.provider == "auto"  # agnostic: whichever key you have
    assert cfg.model == "auto"  # resolved to the provider's default in LLM.model
    assert cfg.effort == "high"
    assert cfg.audio is False


def test_config_file_beats_default(tmp_path):
    (tmp_path / "peaches.toml").write_text(
        'model = "claude-sonnet-5"\nrate = 165\n', encoding="utf-8"
    )
    cfg = Config.load(tmp_path)
    assert cfg.model == "claude-sonnet-5"
    assert cfg.rate == 165


def test_env_beats_config_file(tmp_path, monkeypatch):
    (tmp_path / "peaches.toml").write_text('model = "claude-sonnet-5"\n', encoding="utf-8")
    monkeypatch.setenv("PEACHES_MODEL", "claude-opus-5")
    assert Config.load(tmp_path).model == "claude-opus-5"


def test_flag_beats_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PEACHES_MODEL", "claude-opus-5")
    assert Config.load(tmp_path, model="claude-haiku-4-5").model == "claude-haiku-4-5"


def test_none_overrides_are_ignored(tmp_path):
    (tmp_path / "peaches.toml").write_text('model = "claude-sonnet-5"\n', encoding="utf-8")
    assert Config.load(tmp_path, model=None).model == "claude-sonnet-5"


def test_bools_and_ints_coerce_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PEACHES_AUDIO", "true")
    monkeypatch.setenv("PEACHES_MAX_TECHNOLOGIES", "2")
    cfg = Config.load(tmp_path)
    assert cfg.audio is True
    assert cfg.max_technologies == 2


def test_unknown_config_keys_are_ignored(tmp_path):
    (tmp_path / "peaches.toml").write_text('model = "x"\nnonsense = 1\n', encoding="utf-8")
    assert Config.load(tmp_path).model == "x"


# -- .env parsing: the shape of a real, hand-edited file ---------------------


def _dotenv(tmp_path, body: str):
    (tmp_path / ".env").write_text(body, encoding="utf-8")
    return tmp_path


def test_dotenv_strips_an_inline_comment(tmp_path, monkeypatch):
    """A template with trailing comments is exactly what people uncomment.

    Swallowing the comment turns a model id into a 57-character string that
    fails much later, somewhere much less obvious.
    """
    from pitches_peaches.config import load_dotenv

    monkeypatch.delenv("PEACHES_MODEL", raising=False)
    monkeypatch.delenv("PEACHES_EFFORT", raising=False)
    _dotenv(
        tmp_path,
        "PEACHES_MODEL=auto                  # `auto` = this provider's default:\n"
        "PEACHES_EFFORT=high                 # low|medium|high|xhigh|max\n",
    )
    load_dotenv(tmp_path)
    assert os.environ["PEACHES_MODEL"] == "auto"
    assert os.environ["PEACHES_EFFORT"] == "high"


def test_dotenv_keeps_a_hash_that_is_part_of_the_value(tmp_path, monkeypatch):
    from pitches_peaches.config import load_dotenv

    monkeypatch.delenv("SECRET", raising=False)
    _dotenv(tmp_path, 'SECRET="abc#def"\n')
    load_dotenv(tmp_path)
    assert os.environ["SECRET"] == "abc#def"


def test_dotenv_keeps_a_hash_with_no_leading_space(tmp_path, monkeypatch):
    from pitches_peaches.config import load_dotenv

    monkeypatch.delenv("SECRET", raising=False)
    _dotenv(tmp_path, "SECRET=abc#def\n")
    load_dotenv(tmp_path)
    assert os.environ["SECRET"] == "abc#def"


def test_dotenv_strips_quotes_and_whitespace(tmp_path, monkeypatch):
    from pitches_peaches.config import load_dotenv

    for name in ("A", "B", "C"):
        monkeypatch.delenv(name, raising=False)
    _dotenv(tmp_path, "A='single'\nB=\"double\"\nC=   spaced   \n")
    load_dotenv(tmp_path)
    assert os.environ["A"] == "single"
    assert os.environ["B"] == "double"
    assert os.environ["C"] == "spaced"


def test_dotenv_tolerates_a_pasted_export_line(tmp_path, monkeypatch):
    from pitches_peaches.config import load_dotenv

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _dotenv(tmp_path, "export OPENAI_API_KEY=sk-proj-abc\n")
    load_dotenv(tmp_path)
    assert os.environ["OPENAI_API_KEY"] == "sk-proj-abc"


def test_dotenv_does_not_override_the_shell(tmp_path, monkeypatch):
    from pitches_peaches.config import load_dotenv

    monkeypatch.setenv("OPENAI_API_KEY", "from-shell")
    _dotenv(tmp_path, "OPENAI_API_KEY=from-file\n")
    load_dotenv(tmp_path)
    assert os.environ["OPENAI_API_KEY"] == "from-shell"


def test_sample_env_has_no_trailing_comments_on_settable_lines():
    """The template must be safe to uncomment, line by line."""
    import re
    from pathlib import Path

    sample = Path(__file__).parent.parent / ".env.sample"
    for number, line in enumerate(sample.read_text(encoding="utf-8").splitlines(), 1):
        body = line.lstrip("# ").strip()
        if not re.match(r"^[A-Z][A-Z0-9_]*=", body):
            continue
        assert not re.search(r"\s#", body), (
            f".env.sample:{number} has a trailing comment on a settable line, "
            f"which becomes part of the value when uncommented: {line!r}"
        )


# -- artifacts are documents, not chat replies -------------------------------


@pytest.mark.parametrize(
    "tail",
    [
        "If you want, I can turn these notes into a cheat sheet.",
        "If you'd like, I can expand this into a one-pager.",
        "Would you like me to draft the follow-up email?",
        "Let me know if you need anything else.",
        "Shall I also cover the system design round?",
        "I can also generate a one-page summary.",
        "Hope this helps!",
    ],
)
def test_trailing_offers_of_help_are_stripped(tail):
    from pitches_peaches.state import strip_assistant_residue

    body = "## Open questions\n\n- What is the team size?"
    assert strip_assistant_residue(f"{body}\n\n{tail}") == body


def test_real_content_that_merely_contains_the_phrase_survives():
    """The lead-in alone is not a trigger — this is ordinary prose in a gaps section."""
    from pitches_peaches.state import strip_assistant_residue

    text = (
        "## Gaps\n\n"
        "If you want Kafka on your CV, they run it in production and will ask "
        "about it in the systems round."
    )
    assert strip_assistant_residue(text) == text.rstrip()


def test_a_long_final_paragraph_is_never_truncated():
    """An offer is short. A long closing section is content, whatever it opens with."""
    from pitches_peaches.state import strip_assistant_residue

    long_close = "Let me know if " + "this genuinely matters. " * 20
    text = f"## Close\n\n{long_close}"
    assert strip_assistant_residue(text) == text.rstrip()


def test_a_single_paragraph_document_is_left_alone():
    from pitches_peaches.state import strip_assistant_residue

    text = "Shall I is a phrase, and this document is one paragraph."
    assert strip_assistant_residue(text) == text


def test_documents_without_residue_are_untouched():
    from pitches_peaches.state import strip_assistant_residue

    text = "# Dossier\n\nYou are walking into a three-person company."
    assert strip_assistant_residue(text) == text


def test_write_text_strips_residue_on_the_way_to_disk(tmp_path):
    state = RunState.load_or_create(tmp_path)
    state.write_text(
        "01-company.md",
        "# Semgrep\n\nReal content.\n\nIf you want, I can turn this into a deck.",
    )
    written = (tmp_path / "01-company.md").read_text(encoding="utf-8")
    assert "If you want" not in written
    assert written == "# Semgrep\n\nReal content.\n"


def test_the_shipped_prompts_forbid_offering_further_help():
    from pitches_peaches.prompts import render

    voice = render("recon_research")
    assert "writing a file, not a chat reply" in voice


# --------------------------------------------------------------------------
# Shared artifacts — one posting, several CVs
# --------------------------------------------------------------------------


def _paired(tmp_path):
    """Two run directories under one application, as a workspace lays them out."""
    application = tmp_path / "01-acme"
    first = RunState.load_or_create(application / "by-cv" / "backend", shared=application)
    second = RunState.load_or_create(application / "by-cv" / "platform", shared=application)
    return application, first, second


def test_recon_is_written_once_and_read_by_every_cv(tmp_path):
    """Recon is three requests and ~22 searches; a second CV must not re-run it."""
    application, first, second = _paired(tmp_path)

    first.write_json("recon.json", {"company": "Acme"})
    assert (application / "recon.json").exists()
    assert not (first.workdir / "recon.json").exists()
    assert second.has("recon.json")
    assert second.read_json("recon.json") == {"company": "Acme"}


def test_the_cv_dependent_artifacts_stay_apart(tmp_path):
    application, first, second = _paired(tmp_path)

    first.write_json("match.json", {"overall": 88})
    assert not second.has("match.json")
    assert (first.workdir / "match.json").exists()


def test_the_company_dossier_is_shared_too(tmp_path):
    application, first, second = _paired(tmp_path)
    first.write_text("01-company.md", "# Acme\n")
    assert (application / "01-company.md").exists()
    assert second.has("01-company.md")


def test_a_run_without_a_shared_directory_is_unchanged(tmp_path):
    """What -C gives you: one directory holding everything, exactly as before."""
    state = RunState.load_or_create(tmp_path)
    state.write_json("recon.json", {"company": "Acme"})
    assert (tmp_path / "recon.json").exists()


def test_a_shared_stage_can_be_recorded_without_pretending_it_ran(tmp_path):
    application, first, second = _paired(tmp_path)
    first.record("recon", company="Acme", sources=["https://acme.com"])

    second.adopt("recon", first.stages["recon"])
    assert second.ran("recon")
    assert second.stages["recon"]["shared"] is True
    assert second.stages["recon"]["company"] == "Acme"
