"""CLI behaviour that does not need an API key.

These assert on the error a user actually sees when they run the stages out of
order — the most common way to meet this tool.
"""

import pytest
from typer.testing import CliRunner

from pitches_peaches.cli import app

runner = CliRunner()


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner.invoke(app, ["init", "-C", str(tmp_path)])
    return tmp_path


def test_init_scaffolds_the_run_directory(tmp_path):
    result = runner.invoke(app, ["init", "-C", str(tmp_path)])
    assert result.exit_code == 0
    for name in ("peaches.toml", "cv.example.json", ".gitignore", "run.json"):
        assert (tmp_path / name).exists(), name


def test_init_is_idempotent(tmp_path):
    runner.invoke(app, ["init", "-C", str(tmp_path)])
    (tmp_path / "peaches.toml").write_text('model = "mine"\n')
    result = runner.invoke(app, ["init", "-C", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "peaches.toml").read_text() == 'model = "mine"\n'


def test_generated_config_documents_every_knob(tmp_path):
    from dataclasses import fields

    from pitches_peaches.config import Config

    runner.invoke(app, ["init", "-C", str(tmp_path)])
    text = (tmp_path / "peaches.toml").read_text()
    for field in fields(Config):
        assert field.name in text, f"{field.name} is undocumented in peaches.toml"
        assert f"PEACHES_{field.name.upper()}" in text


def test_generated_gitignore_covers_the_env_file(tmp_path):
    runner.invoke(app, ["init", "-C", str(tmp_path)])
    assert ".env" in (tmp_path / ".gitignore").read_text()


def test_generated_example_cv_is_valid_json_and_self_documenting(tmp_path):
    import json

    runner.invoke(app, ["init", "-C", str(tmp_path)])
    data = json.loads((tmp_path / "cv.example.json").read_text())
    assert "_comment" in data
    assert data["projects"] and "_comment" in data["projects"][0]


# -- running stages out of order --------------------------------------------


@pytest.mark.parametrize(
    "command,missing,producer",
    [
        (["match"], "recon.json", "peaches recon"),
        (["gate"], "recon.json", "peaches recon"),
        (["playbook"], "recon.json", "peaches recon"),
        (["render"], "recon.json", "peaches recon"),
    ],
)
def test_missing_dependency_is_reported_before_the_missing_key(
    workdir, command, missing, producer
):
    result = runner.invoke(app, [*command, "-C", str(workdir)])
    assert result.exit_code == 1
    assert missing in result.output
    assert producer in result.output
    assert "ANTHROPIC_API_KEY" not in result.output


def test_match_names_profile_once_recon_exists(workdir):
    (workdir / "recon.json").write_text("{}")
    result = runner.invoke(app, ["match", "-C", str(workdir)])
    assert "profile.json" in result.output
    assert "peaches profile" in result.output


def test_missing_key_is_reported_when_dependencies_are_satisfied(workdir):
    for name in ("recon.json", "profile.json", "match.json"):
        (workdir / name).write_text("{}")
    result = runner.invoke(app, ["match", "-C", str(workdir)])
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_stage_in_an_uninitialised_directory_says_run_init(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["match", "-C", str(tmp_path)])
    assert result.exit_code == 1
    assert "peaches init" in result.output


def test_version_prints_the_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "pitches-peaches" in result.output


def test_help_leads_with_the_constraint():
    import re

    result = runner.invoke(app, ["--help"])
    # Rich wraps and pads the help text, so compare on collapsed whitespace.
    assert "never applies to anything" in re.sub(r"\s+", " ", result.output)
