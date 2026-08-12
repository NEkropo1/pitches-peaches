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
    (tmp_path / "peaches.toml").write_text('model = "mine"\n', encoding="utf-8")
    result = runner.invoke(app, ["init", "-C", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "peaches.toml").read_text(encoding="utf-8") == 'model = "mine"\n'


def test_generated_config_documents_every_knob(tmp_path):
    from dataclasses import fields

    from pitches_peaches.config import Config

    runner.invoke(app, ["init", "-C", str(tmp_path)])
    text = (tmp_path / "peaches.toml").read_text(encoding="utf-8")
    for field in fields(Config):
        assert field.name in text, f"{field.name} is undocumented in peaches.toml"
        assert f"PEACHES_{field.name.upper()}" in text


def test_generated_gitignore_covers_the_env_file(tmp_path):
    runner.invoke(app, ["init", "-C", str(tmp_path)])
    assert ".env" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_generated_example_cv_is_valid_json_and_self_documenting(tmp_path):
    import json

    runner.invoke(app, ["init", "-C", str(tmp_path)])
    data = json.loads((tmp_path / "cv.example.json").read_text(encoding="utf-8"))
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


def test_the_fix_command_survives_a_long_workdir(tmp_path, monkeypatch):
    """A CI tmp path once pushed "peaches recon" over the wrap column.

    The command is the one thing in the message a person copies, so it has to
    arrive whole no matter how long the path in front of it is.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    deep = tmp_path.joinpath(*["a-directory-with-a-long-name"] * 4)
    deep.mkdir(parents=True)
    runner.invoke(app, ["init", "-C", str(deep)])
    result = runner.invoke(app, ["match", "-C", str(deep)])
    assert result.exit_code == 1
    assert "Run: peaches recon <url|file>" in result.output


def test_match_names_profile_once_recon_exists(workdir):
    (workdir / "recon.json").write_text("{}", encoding="utf-8")
    result = runner.invoke(app, ["match", "-C", str(workdir)])
    assert "profile.json" in result.output
    assert "peaches profile" in result.output


def test_missing_key_is_reported_when_dependencies_are_satisfied(workdir):
    for name in ("recon.json", "profile.json", "match.json"):
        (workdir / name).write_text("{}", encoding="utf-8")
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


# -- the honesty notice must not drift from the code ------------------------

from pathlib import Path  # noqa: E402

import pitches_peaches  # noqa: E402

ROOT = Path(__file__).parent.parent


def test_version_command_prints_both_lists():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert pitches_peaches.__version__ in result.output
    assert pitches_peaches.VERIFIED_PROVIDER in result.output
    assert pitches_peaches.VERIFIED_MODEL in result.output
    flat = " ".join(result.output.split())  # rich wraps
    for path in pitches_peaches.VERIFIED_PATHS + pitches_peaches.UNVERIFIED_PATHS:
        assert " ".join(path.split()) in flat, f"version output omits {path!r}"


@pytest.mark.parametrize("doc", ["README.md", "skill/SKILL.md"])
def test_docs_name_the_same_verified_combination_as_the_code(doc):
    """If someone bumps VERIFIED_MODEL, these fail until the docs follow."""
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert pitches_peaches.VERIFIED_MODEL in text, (
        f"{doc} does not mention the verified model "
        f"({pitches_peaches.VERIFIED_MODEL}); it will mislead people."
    )
    assert pitches_peaches.VERIFIED_PROVIDER in text


def test_readme_states_the_version_it_is_making_claims_about():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"v{pitches_peaches.__version__}" in text


def _key_phrase(path: str) -> str:
    """The distinctive part of an UNVERIFIED_PATHS entry, minus any aside."""
    return path.split("(")[0].strip().rstrip(",").lower()


def _prose(markdown: str) -> str:
    """Markdown with emphasis removed, so a phrase can be matched across it.

    The README bolds parts of these phrases — "the **Anthropic and Gemini
    providers**" — which breaks a naive substring match on the prose.
    """
    import re

    return " ".join(re.sub(r"[*`_]", "", markdown).split()).lower()


@pytest.mark.parametrize("path", pitches_peaches.UNVERIFIED_PATHS)
def test_readme_names_every_unproven_path(path):
    """Derived from the code, never hardcoded.

    The hardcoded version of this kept passing after the interactive probe
    loop had actually been exercised, because the README still contained the
    word "interactive" — in the phrase "non-interactive". Deriving the list
    means dropping an entry from UNVERIFIED_PATHS forces the README to change.
    """
    text = _prose((ROOT / "README.md").read_text(encoding="utf-8"))
    assert _key_phrase(path) in text, f"README does not flag {path!r} as unproven"


def test_verified_and_unverified_paths_do_not_overlap():
    """Nothing may be claimed as both proven and unproven."""
    verified = " ".join(pitches_peaches.VERIFIED_PATHS).lower()
    for path in pitches_peaches.UNVERIFIED_PATHS:
        assert _key_phrase(path) not in verified, (
            f"{path!r} appears in both VERIFIED_PATHS and UNVERIFIED_PATHS"
        )


def test_metrics_request_count_matches_the_configuration_it_states():
    """The contradiction a reader caught: 12 requests described as a no-audio run.

    METRICS.md documents one run. If it says that run had no audio, it must
    also say 9 requests — the 12-request figure belongs to an audio run.
    """
    text = (ROOT / "METRICS.md").read_text(encoding="utf-8")
    header = text[: text.index("## Requests per stage")]
    assert "**no audio**" in header, "METRICS.md no longer states the audio setting"
    assert "| Model requests | **9** |" in text, (
        "METRICS.md states a no-audio run but not the 9-request count that "
        "implies; audio adds three narration calls"
    )


def test_running_on_an_unverified_combination_warns(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    runner.invoke(app, ["init", "-C", str(tmp_path)])
    for name in ("recon.json", "match.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    result = runner.invoke(app, ["render", "-C", str(tmp_path)])
    output = " ".join(result.output.split())
    assert "has only been run end to end" in output
    assert pitches_peaches.VERIFIED_MODEL in output


def test_the_verified_combination_does_not_warn(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    runner.invoke(app, ["init", "-C", str(tmp_path)])
    for name in ("recon.json", "match.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    result = runner.invoke(
        app,
        ["render", "-C", str(tmp_path), "--provider", pitches_peaches.VERIFIED_PROVIDER,
         "--model", pitches_peaches.VERIFIED_MODEL],
    )
    assert "has only been run end to end" not in " ".join(result.output.split())


# -- the audio question ------------------------------------------------------


def _llm_for_audio(tmp_path):
    from pitches_peaches.config import Config
    from pitches_peaches.llm import LLM
    from pitches_peaches.providers import select

    return LLM(Config.load(tmp_path), select("openai"), "m")


@pytest.mark.parametrize("flag", [True, False])
def test_an_explicit_audio_flag_is_never_second_guessed(tmp_path, flag, monkeypatch):
    from pitches_peaches.cli import _want_audio

    def no_prompts(*args, **kwargs):  # a prompt here would hang a scripted run
        raise AssertionError("asked despite an explicit flag")

    monkeypatch.setattr("typer.confirm", no_prompts)
    assert _want_audio(flag, _llm_for_audio(tmp_path), interactive=True) is flag


def test_non_interactive_never_asks(tmp_path, monkeypatch):
    from pitches_peaches.cli import _want_audio

    monkeypatch.setattr(
        "typer.confirm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked"))
    )
    # None means "fall through to the config default", not "prompt"
    assert _want_audio(None, _llm_for_audio(tmp_path), interactive=False) is None


@pytest.mark.parametrize("answer", [True, False])
def test_interactive_run_asks_and_takes_the_answer(tmp_path, monkeypatch, answer):
    from pitches_peaches.cli import _want_audio

    asked = {}

    def fake_confirm(question, default=None, **kwargs):
        asked["question"] = question
        asked["default"] = default
        return answer

    monkeypatch.setattr("typer.confirm", fake_confirm)
    assert _want_audio(None, _llm_for_audio(tmp_path), interactive=True) is answer
    assert "audio" in asked["question"].lower()
    assert asked["default"] is False, "audio must be opt-in, so enter means no"


def test_ctrl_c_at_the_audio_prompt_means_no(tmp_path, monkeypatch):
    from pitches_peaches.cli import _want_audio

    monkeypatch.setattr(
        "typer.confirm", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt)
    )
    assert _want_audio(None, _llm_for_audio(tmp_path), interactive=True) is False


def test_metrics_doc_exists_and_is_linked_from_the_readme():
    """A cost claim in the README must point at the evidence behind it."""
    assert (ROOT / "METRICS.md").exists()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "METRICS.md" in readme


def test_metrics_doc_names_the_verified_combination():
    text = (ROOT / "METRICS.md").read_text(encoding="utf-8")
    assert pitches_peaches.VERIFIED_PROVIDER in text
    assert pitches_peaches.VERIFIED_MODEL in text


def test_readme_no_longer_carries_the_pre_measurement_cost_guess():
    """The old $2.50-$4.50 figure was inferred from list prices, never measured."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "$2.50" not in readme and "$4.50" not in readme


def test_no_text_file_is_read_in_the_locale_encoding():
    """Windows defaults to cp1252, which cannot read our own em dashes.

    Every dossier, prompt and doc here is UTF-8, so every read must say so.
    """
    bare = ".read_text" + "()"  # split so this line is not its own offender
    offenders = [
        f"{path.relative_to(ROOT)}:{number}"
        for directory in ("src", "tests")
        for path in (ROOT / directory).rglob("*.py")
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        )
        if bare in line
    ]
    assert not offenders, f"{bare} without encoding=: {offenders}"


def test_the_version_is_defined_in_exactly_one_place():
    """pyproject reads __version__, so the two can never disagree.

    They did once: a bump to pyproject alone left the CLI reporting the old
    number while PyPI served the new one.
    """
    import re

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in pyproject
    assert 'attr = "pitches_peaches.__version__"' in pyproject
    assert not re.search(r'^version = "', pyproject, re.M), (
        "pyproject declares a literal version as well as a dynamic one"
    )


def test_the_publish_guard_reads_the_same_place_the_build_does():
    """The tag/version guard must not grep a line that no longer exists."""
    from conftest import repo_only

    repo_only(".github/workflows/publish.yml")
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert "src/pitches_peaches/__init__.py" in workflow, (
        "the publish guard reads the version from somewhere other than the "
        "single source, so it will silently compare against an empty string"
    )
