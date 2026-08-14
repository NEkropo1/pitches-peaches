"""Two algorithmic passes over a parsed CV. No model call in this file.

Both exist because of the same observation: a parsed CV repeats itself, and the
repetition is not free. It costs input tokens on every stage that reads the
profile, and in one case it states something that is not true.

**consolidate** — correctness. A figure that appears under more than one
project was attributed by a model that could not tell which one it belonged to.
Extracting a real CV produced exactly this: all five metrics from one project
also landed on a neighbouring one. Quote verification cannot catch it, because
the figure genuinely is in the CV — it is only the attachment that is invented,
and nothing checks attachment.

The fix is to stop claiming what is not known. A figure claimed under several
projects is hoisted out of all of them and kept as something the person did,
with the projects it was claimed under recorded beside it. "You cut API times
by 90%" is true and useful; "you cut API times by 90% *on the browser*" is a
sentence someone might have to defend in a room, and it may be wrong.

**compact** — size. Skills are extracted one per technology, each carrying the
CV line it came from, and CVs list technologies in dense rows: one line yields
a dozen skills, and the profile then carries that line a dozen times. Grouping
by line says the same thing in a third of the bytes. This one only changes what
prompts are shown; ``profile.json`` on disk stays a faithful record of the
parse, because a stored artifact that has been rearranged for a prompt is a
stored artifact nobody can check against the CV.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import Achievement, Profile


def consolidate(profile: Profile) -> Profile:
    """Move figures claimed under several projects into ``achievements``.

    A figure under exactly one project is left where it is: single attribution
    may still be wrong, but nothing here can tell, and moving everything would
    throw away the attributions that are right.
    """
    counted = Counter(
        figure for project in profile.projects for figure in project.numbers
    )
    contested = {figure for figure, seen in counted.items() if seen > 1}
    if not contested:
        return profile

    hoisted: list[Achievement] = []
    for figure in contested:
        claimed_under = [
            project.name for project in profile.projects if figure in project.numbers
        ]
        hoisted.append(Achievement(figure=figure, claimed_under=claimed_under))

    for project in profile.projects:
        project.numbers = [n for n in project.numbers if n not in contested]

    # Stable order, so the same parse produces the same file twice.
    hoisted.sort(key=lambda a: a.figure)
    profile.achievements.extend(hoisted)
    return profile


def compact(profile: Profile) -> dict[str, Any]:
    """A prompt-shaped view: skills grouped under the line they came from.

    Same information, a third of the bytes on a real CV. Returned as a plain
    dict rather than a ``Profile`` because it is deliberately not the schema —
    nothing should be tempted to write it to disk.
    """
    data = profile.model_dump(mode="json")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for skill in data.pop("skills", []):
        entry = {"name": skill["name"]}
        if skill.get("years"):
            entry["years"] = skill["years"]
        if skill.get("depth") and skill["depth"] != "working":
            entry["depth"] = skill["depth"]
        grouped.setdefault(skill.get("cv_line", ""), []).append(entry)

    data["skills_by_cv_line"] = [
        {"cv_line": line, "skills": skills} for line, skills in grouped.items()
    ]
    return data
