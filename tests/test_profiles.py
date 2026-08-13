"""Two algorithmic passes over a parsed CV.

Both were written against a real extraction. Parsing an actual PDF CV produced
all five metrics from one project bolted onto a neighbouring one, and 74 skills
carrying 21 distinct source lines between them.
"""

from __future__ import annotations

import json

from pitches_peaches.models import Profile
from pitches_peaches.profiles import compact, consolidate


def _profile(projects, skills=None) -> Profile:
    return Profile(
        skills=skills or [{"name": "Python", "cv_line": "Python, Go"}],
        projects=projects,
    )


CONTESTED = "cutting internal API communication times by 90%"


# --------------------------------------------------------------------------
# consolidate
# --------------------------------------------------------------------------

def test_a_figure_claimed_twice_stops_being_claimed_by_either():
    """The real failure: one project's metrics land on its neighbour too."""
    profile = _profile([
        {"name": "Auto-trading platform", "what_you_did": "x", "numbers": [CONTESTED, "10B+ points"]},
        {"name": "Anonymous browser", "what_you_did": "y", "numbers": [CONTESTED, "10B+ points"]},
    ])
    consolidate(profile)

    assert [p.numbers for p in profile.projects] == [[], []]
    assert {a.figure for a in profile.achievements} == {CONTESTED, "10B+ points"}


def test_the_projects_it_was_claimed_under_are_kept():
    """Dropping the attribution entirely would destroy the audit trail."""
    profile = _profile([
        {"name": "Auto-trading platform", "what_you_did": "x", "numbers": [CONTESTED]},
        {"name": "Anonymous browser", "what_you_did": "y", "numbers": [CONTESTED]},
    ])
    consolidate(profile)

    assert profile.achievements[0].claimed_under == [
        "Auto-trading platform",
        "Anonymous browser",
    ]


def test_a_figure_under_one_project_is_left_alone():
    """Single attribution may still be wrong, but nothing here can tell."""
    profile = _profile([
        {"name": "A", "what_you_did": "x", "numbers": ["p99 4.2s to 380ms"]},
        {"name": "B", "what_you_did": "y", "numbers": ["38% infra cut"]},
    ])
    consolidate(profile)

    assert profile.achievements == []
    assert [p.numbers for p in profile.projects] == [["p99 4.2s to 380ms"], ["38% infra cut"]]


def test_a_clean_profile_is_returned_untouched():
    profile = _profile([{"name": "A", "what_you_did": "x", "numbers": []}])
    before = profile.model_dump(mode="json")
    assert consolidate(profile).model_dump(mode="json") == before


def test_consolidating_twice_changes_nothing_the_second_time():
    """It runs after every parse, including a re-parse of a cached CV."""
    profile = _profile([
        {"name": "A", "what_you_did": "x", "numbers": [CONTESTED]},
        {"name": "B", "what_you_did": "y", "numbers": [CONTESTED]},
    ])
    once = consolidate(profile).model_dump(mode="json")
    twice = consolidate(Profile.model_validate(once)).model_dump(mode="json")
    assert once == twice


def test_the_order_is_stable_so_the_same_parse_writes_the_same_file():
    def build():
        return _profile([
            {"name": "A", "what_you_did": "x", "numbers": ["zeta 9x", "alpha 2x"]},
            {"name": "B", "what_you_did": "y", "numbers": ["zeta 9x", "alpha 2x"]},
        ])

    first = [a.figure for a in consolidate(build()).achievements]
    second = [a.figure for a in consolidate(build()).achievements]
    assert first == second == ["alpha 2x", "zeta 9x"]


# --------------------------------------------------------------------------
# compact
# --------------------------------------------------------------------------

DENSE_LINE = (
    "Backend & Systems: Python (FastAPI, Flask, Django, asyncio, multiprocessing), "
    "distributed systems, event-driven architecture"
)


def test_skills_are_grouped_under_the_line_they_came_from():
    profile = _profile(
        [{"name": "A", "what_you_did": "x"}],
        skills=[
            {"name": "Python", "cv_line": DENSE_LINE},
            {"name": "FastAPI", "cv_line": DENSE_LINE},
            {"name": "Flask", "cv_line": DENSE_LINE},
            {"name": "Kafka", "cv_line": "Streaming: Kafka, RabbitMQ"},
        ],
    )
    groups = compact(profile)["skills_by_cv_line"]

    assert len(groups) == 2
    by_line = {g["cv_line"]: [s["name"] for s in g["skills"]] for g in groups}
    assert by_line[DENSE_LINE] == ["Python", "FastAPI", "Flask"]
    assert by_line["Streaming: Kafka, RabbitMQ"] == ["Kafka"]


def test_grouping_is_smaller_than_repeating_the_line():
    """The whole reason it exists: one dense row yields a dozen skills."""
    profile = _profile(
        [{"name": "A", "what_you_did": "x"}],
        skills=[{"name": f"tech{i}", "cv_line": DENSE_LINE} for i in range(12)],
    )
    before = len(json.dumps(profile.model_dump(mode="json")))
    after = len(json.dumps(compact(profile)))
    assert after < before / 2


def test_every_cv_line_survives_so_quotes_are_still_sourceable():
    """A quote the model finds here must still verify against the full profile."""
    profile = _profile(
        [{"name": "A", "what_you_did": "x"}],
        skills=[
            {"name": "Python", "cv_line": DENSE_LINE},
            {"name": "Kafka", "cv_line": "Streaming: Kafka"},
        ],
    )
    rendered = json.dumps(compact(profile))
    for skill in profile.skills:
        assert skill.cv_line in rendered


def test_defaults_are_dropped_but_real_values_are_not():
    profile = _profile(
        [{"name": "A", "what_you_did": "x"}],
        skills=[
            {"name": "Python", "cv_line": "L", "depth": "core", "years": "8"},
            {"name": "Go", "cv_line": "L", "depth": "working"},
        ],
    )
    skills = compact(profile)["skills_by_cv_line"][0]["skills"]

    assert skills[0] == {"name": "Python", "years": "8", "depth": "core"}
    assert skills[1] == {"name": "Go"}, "the default depth is noise in a prompt"


def test_compact_never_returns_something_that_could_be_stored_as_a_profile():
    """It is a prompt view, not the schema. Nothing should write it to disk."""
    profile = _profile([{"name": "A", "what_you_did": "x"}])
    view = compact(profile)
    assert "skills" not in view
    assert "skills_by_cv_line" in view
