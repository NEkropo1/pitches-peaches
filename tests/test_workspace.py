"""The layout, the handles, and the ids.

Naming is pure string work on purpose — no network, no model, no waiting for
recon — so all of it is testable offline, which is most of what is here.
"""

from __future__ import annotations

import json

import pytest

from pitches_peaches.workspace import (
    SHARED_ARTIFACTS,
    Workspace,
    WorkspaceError,
    slug_for,
    slugify,
)


# --------------------------------------------------------------------------
# Handles
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url,expected",
    [
        # The company is in the path on an ATS host; the trailing id is noise.
        ("https://boards.greenhouse.io/acme/jobs/4012345", "acme"),
        ("https://job-boards.greenhouse.io/acme/jobs/4012345", "acme"),
        ("https://jobs.lever.co/acme/1a2b3c4d-5e6f-7890-abcd-ef1234567890", "acme"),
        # The company is in the host when the host belongs to the company.
        ("https://careers.acme.com/en/jobs/staff-platform-engineer",
         "acme-staff-platform-engineer"),
        ("https://www.acme.io/careers/senior-backend-engineer",
         "acme-senior-backend-engineer"),
        # The title is the longest hyphenated segment, minus its trailing id.
        ("https://linkedin.com/jobs/view/senior-backend-engineer-at-acme-4012345678",
         "senior-backend-engineer-at-acme"),
        # Workable-style opaque tokens are ids, not names.
        ("https://apply.workable.com/acme/j/AB12CD34/", "acme"),
    ],
)
def test_urls_get_a_readable_handle(url, expected):
    assert slug_for(url) == expected


def test_every_greenhouse_url_would_have_collided_on_a_naive_prefix():
    """The reason the handle is not simply the first twenty characters."""
    a = slug_for("https://boards.greenhouse.io/acme/jobs/1")
    b = slug_for("https://boards.greenhouse.io/globex/jobs/2")
    assert a != b
    assert (a, b) == ("acme", "globex")


def test_a_file_target_uses_its_stem():
    assert slug_for("~/postings/semgrep-backend.txt") == "semgrep-backend"


@pytest.mark.parametrize(
    "target",
    ["https://x.io/?token=abc", "!!!", "https://", "   "],
)
def test_the_fallback_chain_always_produces_something(target):
    """A bad handle is cosmetic — the id prefix keeps directories distinct."""
    handle = slug_for(target)
    assert handle
    assert handle == slugify(handle)


def test_handles_are_bounded_and_cut_on_a_word_boundary():
    handle = slug_for(
        "https://careers.acme.com/jobs/"
        "extremely-senior-distinguished-principal-staff-backend-platform-engineer"
    )
    assert len(handle) <= 40
    assert not handle.endswith("-")
    assert "engine" not in handle.split("-")[-1] or handle.split("-")[-1] == "engineer"


def test_cyrillic_is_transliterated_not_deleted():
    """Otherwise every DOU posting lands in NN-untitled alongside all the others."""
    assert slugify("Київ Софт") == "kyiv-soft"
    assert slugify("Розробник") == "rozrobnyk"
    assert slug_for("https://jobs.dou.ua/companies/acme/vacancies/12345") == "acme"


def test_accented_latin_still_folds():
    assert slugify("Zürich Söftware") == "zurich-software"


# --------------------------------------------------------------------------
# Ids
# --------------------------------------------------------------------------

@pytest.fixture
def ws(tmp_path) -> Workspace:
    return Workspace.create(tmp_path)


def test_ids_increment(ws):
    first = ws.new_application("https://boards.greenhouse.io/acme/jobs/1")
    second = ws.new_application("https://boards.greenhouse.io/globex/jobs/2")
    assert (first.id, second.id) == (1, 2)
    assert first.path.name == "01-acme"
    assert second.path.name == "02-globex"


def test_a_deleted_id_is_never_handed_out_again(ws):
    """An old path in a README or in shell history must not change meaning."""
    ws.new_application("https://boards.greenhouse.io/acme/jobs/1")
    second = ws.new_application("https://boards.greenhouse.io/globex/jobs/2")

    import shutil

    shutil.rmtree(second.path)
    third = ws.new_application("https://boards.greenhouse.io/initech/jobs/3")
    assert third.id == 3


def test_the_counter_is_floored_by_what_is_on_disk(ws):
    """Hand-editing it is the reader's business; landing on an existing id is not."""
    ws.new_application("https://boards.greenhouse.io/acme/jobs/1")
    ws.new_application("https://boards.greenhouse.io/globex/jobs/2")
    (ws.applications_dir / ".next_id").write_text("1\n", encoding="utf-8")

    assert ws.next_id() == 3
    assert ws.new_application("https://x.com/jobs/three").id == 3


def test_same_company_twice_needs_no_collision_handling(ws):
    """Two applications to one company both slug to `acme`; the prefix separates them."""
    first = ws.new_application("https://boards.greenhouse.io/acme/jobs/1")
    second = ws.new_application("https://boards.greenhouse.io/acme/jobs/2")
    assert first.path != second.path
    assert (first.path.name, second.path.name) == ("01-acme", "02-acme")


# --------------------------------------------------------------------------
# The board
# --------------------------------------------------------------------------

def test_applications_are_discovered_by_scanning_not_from_an_index(ws):
    ws.new_application("https://boards.greenhouse.io/acme/jobs/1")
    # A directory created by hand, with no application.json, still shows up.
    (ws.applications_dir / "07-by-hand").mkdir()

    found = {app.id: app.handle for app in ws.applications()}
    assert found == {1: "acme", 7: "by-hand"}


def test_the_label_comes_from_recon_when_it_exists_and_costs_nothing(ws):
    app = ws.new_application("https://boards.greenhouse.io/acme/jobs/1")
    assert app.display() == "acme"  # the handle, until recon has run

    (app.path / "recon.json").write_text(
        json.dumps({"company": "Acme", "role_title": "Senior Backend Engineer"}),
        encoding="utf-8",
    )
    assert ws.application(1).display() == "Acme · Senior Backend Engineer"


def test_a_corrupt_recon_falls_back_to_the_handle(ws):
    app = ws.new_application("https://boards.greenhouse.io/acme/jobs/1")
    (app.path / "recon.json").write_text("{not json", encoding="utf-8")
    assert ws.application(1).display() == "acme"


def test_the_same_posting_is_recognised_despite_a_trailing_slash(ws):
    ws.new_application("https://boards.greenhouse.io/acme/jobs/1")
    found = ws.find_by_target("https://boards.greenhouse.io/acme/jobs/1/")
    assert found is not None and found.id == 1


def test_an_unknown_application_names_the_command_that_lists_them(ws):
    with pytest.raises(WorkspaceError, match="peaches ls"):
        ws.application(9)


# --------------------------------------------------------------------------
# CVs
# --------------------------------------------------------------------------

def test_cvs_are_named_by_filename_stem(ws):
    (ws.cvs_dir / "backend-senior.pdf").write_bytes(b"%PDF-1.4")
    (ws.cvs_dir / "platform-lead.md").write_text("# CV", encoding="utf-8")
    assert [cv.name for cv in ws.cvs()] == ["backend-senior", "platform-lead"]


def test_unsupported_and_hidden_files_are_not_cvs(ws):
    (ws.cvs_dir / "notes.docx").write_text("x", encoding="utf-8")
    (ws.cvs_dir / ".DS_Store").write_text("x", encoding="utf-8")
    assert ws.cvs() == []


def test_two_files_with_one_stem_is_an_error_that_says_what_to_do(ws):
    (ws.cvs_dir / "cv.md").write_text("x", encoding="utf-8")
    (ws.cvs_dir / "cv.pdf").write_bytes(b"x")
    with pytest.raises(WorkspaceError, match="Rename one"):
        ws.cvs()


def test_an_unknown_cv_lists_the_ones_that_exist(ws):
    (ws.cvs_dir / "backend-senior.md").write_text("x", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="backend-senior"):
        ws.cv("nope")


def test_a_cv_is_stale_once_the_file_changes(ws):
    path = ws.cvs_dir / "backend-senior.md"
    path.write_text("# CV\nKafka", encoding="utf-8")
    cv = ws.cv("backend-senior")
    assert cv.state() == "unparsed"

    from pitches_peaches.models import Profile

    profile = Profile(skills=[], projects=[])
    cv.write_cache(profile, "# CV\nKafka")
    assert cv.state() == "ready"

    path.write_text("# CV\nKafka and Postgres", encoding="utf-8")
    assert cv.state() == "stale"


def test_a_corrupt_cache_reads_as_unparsed_rather_than_exploding(ws):
    (ws.cvs_dir / "cv.md").write_text("x", encoding="utf-8")
    cv = ws.cv("cv")
    cv.parsed_dir.mkdir(parents=True, exist_ok=True)
    cv.parsed_path.write_text("{truncated", encoding="utf-8")
    assert cv.state() == "unparsed"


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------

def test_discovery_walks_up_from_a_run_directory(ws):
    app = ws.new_application("https://boards.greenhouse.io/acme/jobs/1")
    deep = app.by_cv / "backend-senior" / "diagrams"
    deep.mkdir(parents=True)
    found = Workspace.discover(deep)
    assert found is not None and found.root == ws.root


def test_discovery_returns_none_outside_a_workspace(tmp_path):
    lonely = tmp_path / "somewhere" / "else"
    lonely.mkdir(parents=True)
    assert Workspace.discover(lonely) is None


def test_recon_is_the_thing_that_is_shared():
    """If this set grows, something CV-dependent may have been shared by mistake."""
    assert SHARED_ARTIFACTS == {"recon.json", "recon-notes.md", "01-company.md"}
