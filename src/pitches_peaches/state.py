"""The run directory and its state machine.

Every stage writes a typed artifact into one directory and records that it ran
in ``run.json``. A stage that depends on another refuses to start when the
artifact is missing, and names the command that produces it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_FILE = "run.json"

#: artifact filename -> the command that produces it
PRODUCERS: dict[str, str] = {
    "recon.json": "peaches recon <url|file>",
    "profile.json": "peaches profile <cv path>",
    "match.json": "peaches match",
    "playbook.json": "peaches playbook",
}


class StageError(RuntimeError):
    """A stage cannot run. The message names the fix."""


class MissingDependency(StageError):
    def __init__(self, artifact: str, workdir: Path) -> None:
        producer = PRODUCERS.get(artifact, f"the stage that writes {artifact}")
        super().__init__(
            f"{artifact} is missing from {workdir}. Run:  {producer}"
        )
        self.artifact = artifact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RunState:
    """``run.json``, loaded.

    Deliberately a thin wrapper over a dict: this file is meant to be readable
    and hand-editable by the person whose interview it is.
    """

    workdir: Path
    data: dict[str, Any] = field(default_factory=dict)

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def load(cls, workdir: Path) -> RunState:
        path = Path(workdir) / STATE_FILE
        if not path.exists():
            raise StageError(
                f"no {STATE_FILE} in {workdir}. Run:  peaches init"
            )
        return cls(Path(workdir), json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def load_or_create(cls, workdir: Path) -> RunState:
        workdir = Path(workdir)
        if (workdir / STATE_FILE).exists():
            return cls.load(workdir)
        state = cls(workdir, {"created": _now(), "stages": {}})
        state.save()
        return state

    def save(self) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / STATE_FILE).write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    # -- stages ------------------------------------------------------------

    @property
    def stages(self) -> dict[str, Any]:
        return self.data.setdefault("stages", {})

    def record(self, stage: str, **info: Any) -> None:
        self.stages[stage] = {"at": _now(), **info}
        self.save()

    def ran(self, stage: str) -> bool:
        return stage in self.stages

    # -- artifacts ---------------------------------------------------------

    def artifact_path(self, name: str) -> Path:
        return self.workdir / name

    def has(self, name: str) -> bool:
        return self.artifact_path(name).exists()

    def require(self, *names: str) -> None:
        """Refuse to continue unless every named artifact is on disk."""
        for name in names:
            if not self.has(name):
                raise MissingDependency(name, self.workdir)

    def read_json(self, name: str) -> dict[str, Any]:
        self.require(name)
        return json.loads(self.artifact_path(name).read_text(encoding="utf-8"))

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.artifact_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json")
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.artifact_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")
        return path

    # -- the gate ----------------------------------------------------------

    def record_decision(self, decision: str, recommendation: str) -> None:
        self.data["decision"] = {
            "decision": decision,
            "recommendation": recommendation,
            "at": _now(),
        }
        self.save()

    @property
    def decision(self) -> str | None:
        got = self.data.get("decision")
        return got.get("decision") if got else None

    def require_gate_passed(self, force: bool = False) -> None:
        """Downstream stages stop on a declined gate unless --force."""
        if force:
            return
        decision = self.decision
        if decision is None:
            raise StageError("the gate has not been run. Run:  peaches gate")
        if decision != "proceed":
            raise StageError(
                "you decided not to proceed with this application "
                f"(decision: {decision}). Pass --force to build the playbook anyway."
            )
