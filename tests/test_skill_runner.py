"""Tests for wuwei-based skill loading."""

from __future__ import annotations

from pathlib import Path

from ai_terminal.runtime.incident import Incident
from ai_terminal.skill.skill_runner import SkillRunner


def test_skill_runner_loads_skill_directory(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills" / "deploy"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text(
        """---
name: deploy
description: Deploy service safely
when_to_use:
  - release time
user_invocable: true
---

# Deploy

Use this skill to deploy the service.
""",
        encoding="utf-8",
    )

    runner = SkillRunner(
        skill_dirs=[str(tmp_path / "skills")],
        incident_skill_dir=tmp_path / "incidents",
    )

    skills = runner.list_skills()
    assert any(skill["name"] == "deploy" for skill in skills)
    skill = runner.get_skill("deploy")
    assert skill is not None
    assert "Deploy" in skill["instruction"]


def test_generate_skill_writes_skill_md(tmp_path: Path) -> None:
    from ai_terminal.runtime.incident import IncidentRecorder

    recorder = IncidentRecorder(store_path=tmp_path)
    incident = Incident(
        id="202605130001",
        timestamp="2026-05-13T14:50:00",
        command="apt install nginx",
        error_output="bash: apt: command not found",
        exit_code=127,
        root_cause="command not found",
        solution="apt/yum/brew install apt",
        tags=["install"],
        resolved=True,
    )

    path = recorder.generate_skill(incident)
    assert path.endswith("SKILL.md")
    assert Path(path).exists()
    assert Path(path).name == "SKILL.md"
