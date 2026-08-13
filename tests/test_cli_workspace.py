"""The workspace through the CLI, without an API key.

Everything here stops before a model call — which is most of what matters,
because the point of the layer is deciding *where* work goes and *whether* it
has to be paid for again.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from pitches_peaches.cli import app
from pitches_peaches.workspace import Workspace

runner = CliRunner()

POSTING = "https://boards.greenhouse.io/acme/jobs/4012345"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    return Workspace.at(tmp_path)


def _add_cv(ws, name="backend-senior", text="# CV\nKafka in production."):
    path = ws.cvs_dir / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------

def test_init_scaffolds_a_workspace(ws):
    assert ws.cvs_dir.is_dir()
    assert ws.applications_dir.is_dir()
    assert (ws.root / "peaches.toml").exists()


def test_the_gitignore_keeps_cvs_and_dossiers_out_of_a_repository(ws):
    ignored = (ws.root / ".gitignore").read_text(encoding="utf-8")
    assert "cvs/" in ignored
    assert "applications/" in ignored
    assert ".env" in ignored


def test_dash_c_still_scaffolds_one_directory(tmp_path, monkeypatch):
    """The original contract, unchanged."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "one-run"
    result = runner.invoke(app, ["init", "-C", str(target)])
    assert result.exit_code == 0
    assert (target / "run.json").exists()
    assert not (target / "applications").exists()


# --------------------------------------------------------------------------
# CVs
# --------------------------------------------------------------------------

def test_adding_a_cv_costs_nothing(ws, tmp_path):
    source = tmp_path / "elsewhere.md"
    source.write_text("# CV", encoding="utf-8")

    result = runner.invoke(app, ["cv", "add", str(source)])
    assert result.exit_code == 0
    assert (ws.cvs_dir / "elsewhere.md").exists()
    assert not ws.parsed_dir.exists(), "adding a CV must not spend a model call"
    assert "on first use" in result.output


def test_cv_add_can_rename(ws, tmp_path):
    source = tmp_path / "CV_final_FINAL_v3.md"
    source.write_text("# CV", encoding="utf-8")
    runner.invoke(app, ["cv", "add", str(source), "--name", "backend-senior"])
    assert (ws.cvs_dir / "backend-senior.md").exists()


def test_cv_ls_says_which_are_parsed(ws):
    _add_cv(ws)
    result = runner.invoke(app, ["cv", "ls"])
    assert "backend-senior" in result.output
    assert "not parsed yet" in result.output


def test_cv_ls_with_nothing_names_the_command(ws):
    result = runner.invoke(app, ["cv", "ls"])
    assert "peaches cv add" in result.output


def test_a_missing_cv_file_is_reported_not_copied(ws):
    result = runner.invoke(app, ["cv", "add", "/nope/cv.pdf"])
    assert result.exit_code == 1
    assert "no CV at" in result.output


# --------------------------------------------------------------------------
# The board
# --------------------------------------------------------------------------

def test_ls_on_an_empty_workspace_says_what_to_do(ws):
    result = runner.invoke(app, ["ls"])
    assert "no applications yet" in result.output


def test_ls_shows_ids_labels_and_the_cvs_used(ws):
    application = ws.new_application(POSTING)
    (application.path / "recon.json").write_text(
        json.dumps({"company": "Acme", "role_title": "Backend Engineer"}),
        encoding="utf-8",
    )
    (application.by_cv / "backend-senior").mkdir(parents=True)

    result = runner.invoke(app, ["ls"])
    assert "01" in result.output
    assert "Acme" in result.output
    assert "backend-senior" in result.output


def test_ls_outside_a_workspace_names_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["ls"])
    assert result.exit_code == 1
    assert "peaches init" in result.output


# --------------------------------------------------------------------------
# Picking a CV
# --------------------------------------------------------------------------

def test_no_cv_at_all_names_the_command_before_spending_anything(ws):
    result = runner.invoke(app, ["run", POSTING])
    assert result.exit_code == 1
    assert "peaches cv add" in result.output


def test_several_cvs_non_interactively_refuses_rather_than_guessing(ws):
    _add_cv(ws, "backend-senior")
    _add_cv(ws, "platform-lead")

    result = runner.invoke(app, ["run", POSTING, "--non-interactive"])
    assert result.exit_code == 1
    assert "--cv" in result.output
    assert "backend-senior" in result.output and "platform-lead" in result.output


def test_an_unknown_cv_name_lists_the_real_ones(ws):
    _add_cv(ws, "backend-senior")
    result = runner.invoke(app, ["run", POSTING, "--cv", "nope"])
    assert result.exit_code == 1
    assert "backend-senior" in result.output


# --------------------------------------------------------------------------
# Where work lands
# --------------------------------------------------------------------------

def _skip_credential_check(monkeypatch):
    """Get past the key check to test what happens after it, without a key."""
    monkeypatch.setattr("pitches_peaches.cli._check_credential", lambda _: None)


def test_a_run_names_the_application_from_the_posting(ws, monkeypatch):
    """The directory is claimed by string work; nothing here is a model call."""
    _skip_credential_check(monkeypatch)
    _add_cv(ws)
    runner.invoke(app, ["run", POSTING])

    applications = ws.applications()
    assert [a.path.name for a in applications] == ["01-acme"]
    assert applications[0].target == POSTING


def test_the_same_posting_twice_resumes_rather_than_duplicating(ws, monkeypatch):
    _skip_credential_check(monkeypatch)
    _add_cv(ws)
    runner.invoke(app, ["run", POSTING])
    runner.invoke(app, ["run", POSTING + "/"])
    assert len(ws.applications()) == 1


def test_a_second_cv_lands_beside_the_first_under_one_application(ws, monkeypatch):
    _skip_credential_check(monkeypatch)
    _add_cv(ws, "backend-senior")
    runner.invoke(app, ["run", POSTING, "--cv", "backend-senior"])
    _add_cv(ws, "platform-lead")
    runner.invoke(app, ["run", POSTING, "--cv", "platform-lead"])

    application = ws.application(1)
    assert sorted(application.cvs()) == ["backend-senior", "platform-lead"]
    assert len(ws.applications()) == 1, "one posting, one research bill"


def test_a_stage_on_an_application_that_never_started_names_the_fix(ws):
    _add_cv(ws)
    ws.new_application(POSTING)
    result = runner.invoke(app, ["match", "--app", "1"])
    assert result.exit_code == 1
    assert "peaches run --app 1" in result.output


def test_an_unknown_application_id_says_so(ws):
    _add_cv(ws)
    result = runner.invoke(app, ["match", "--app", "42"])
    assert result.exit_code == 1
    assert "peaches ls" in result.output


def test_resume_with_nothing_to_resume_names_the_command(ws):
    _add_cv(ws)
    result = runner.invoke(app, ["resume"])
    assert result.exit_code == 1
    assert "no applications yet" in result.output


def test_dash_c_never_looks_for_a_workspace(ws, tmp_path):
    """Even standing inside one: -C names a run directory and that is all."""
    _add_cv(ws)
    elsewhere = tmp_path / "one-run"
    runner.invoke(app, ["init", "-C", str(elsewhere)])
    result = runner.invoke(app, ["match", "-C", str(elsewhere)])

    assert result.exit_code == 1
    assert "peaches recon" in result.output  # the old single-directory error
    assert not (elsewhere / "by-cv").exists()


def test_a_run_with_no_key_does_not_burn_an_application_id(ws):
    """Ids are never reused, so one must not be spent on a run that cannot start."""
    _add_cv(ws)
    result = runner.invoke(app, ["run", POSTING])

    assert result.exit_code == 1
    assert "API_KEY" in result.output, "the error still names what to set"
    assert ws.applications() == [], "nothing was created"
    assert ws.next_id() == 1, "and no id was consumed"


def test_the_key_error_names_the_workspace_env_file(ws):
    _add_cv(ws)
    result = runner.invoke(app, ["run", POSTING])
    assert str(ws.root) in result.output
