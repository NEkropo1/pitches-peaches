"""The run directory: resume, dependency errors, and the gate."""

import json

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
    payload = json.loads((tmp_path / "run.json").read_text())
    assert "stages" in payload and "recon" in payload["stages"]


# -- configuration precedence ------------------------------------------------


def test_config_defaults(tmp_path):
    cfg = Config.load(tmp_path)
    assert cfg.model == "claude-opus-5"
    assert cfg.effort == "high"
    assert cfg.audio is False


def test_config_file_beats_default(tmp_path):
    (tmp_path / "peaches.toml").write_text('model = "claude-sonnet-5"\nrate = 165\n')
    cfg = Config.load(tmp_path)
    assert cfg.model == "claude-sonnet-5"
    assert cfg.rate == 165


def test_env_beats_config_file(tmp_path, monkeypatch):
    (tmp_path / "peaches.toml").write_text('model = "claude-sonnet-5"\n')
    monkeypatch.setenv("PEACHES_MODEL", "claude-opus-5")
    assert Config.load(tmp_path).model == "claude-opus-5"


def test_flag_beats_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PEACHES_MODEL", "claude-opus-5")
    assert Config.load(tmp_path, model="claude-haiku-4-5").model == "claude-haiku-4-5"


def test_none_overrides_are_ignored(tmp_path):
    (tmp_path / "peaches.toml").write_text('model = "claude-sonnet-5"\n')
    assert Config.load(tmp_path, model=None).model == "claude-sonnet-5"


def test_bools_and_ints_coerce_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PEACHES_AUDIO", "true")
    monkeypatch.setenv("PEACHES_MAX_TECHNOLOGIES", "2")
    cfg = Config.load(tmp_path)
    assert cfg.audio is True
    assert cfg.max_technologies == 2


def test_unknown_config_keys_are_ignored(tmp_path):
    (tmp_path / "peaches.toml").write_text('model = "x"\nnonsense = 1\n')
    assert Config.load(tmp_path).model == "x"
