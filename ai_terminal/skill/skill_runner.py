"""Skill orchestration built on wuwei skill providers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wuwei.skill.fs_provider import FileSystemSkillProvider
from wuwei.skill.skill import Skill, SkillManager, SkillProvider


class IncidentSkillProvider(SkillProvider):
    """Expose generated incident skills as wuwei SKILL.md folders."""

    def __init__(self, skill_dir: str | Path):
        self.root_dir = Path(skill_dir).expanduser().resolve()
        self._provider = FileSystemSkillProvider(str(self.root_dir))

    def list_skills(self) -> list[Skill]:
        return self._provider.list_skills()

    def load_skill_instruction(self, skill_name: str) -> str | None:
        return self._provider.load_skill_instruction(skill_name)

    def refresh(self) -> None:
        self._provider.refresh()


class SkillRunner:
    """Aggregate project, user, and incident skills through wuwei."""

    def __init__(
        self,
        skill_dirs: list[str] | None = None,
        incident_skill_dir: str | Path = "~/.ai-terminal/incidents/skills",
    ):
        self.incident_skill_dir = Path(incident_skill_dir).expanduser().resolve()
        self.incident_skill_dir.mkdir(parents=True, exist_ok=True)

        providers: list[SkillProvider] = [IncidentSkillProvider(self.incident_skill_dir)]
        for skill_dir in skill_dirs or []:
            path = Path(skill_dir).expanduser().resolve()
            if path.is_dir():
                providers.append(FileSystemSkillProvider(str(path)))

        self._manager = SkillManager(providers)

    def refresh(self) -> None:
        self._manager.refresh()

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "scripts_count": len(skill.scripts),
                "path": skill.path,
                "references_count": len(skill.references),
            }
            for skill in self._manager.list_skills()
        ]

    def get_skill(self, name: str) -> dict[str, Any] | None:
        try:
            skill = self._manager.get_skill(name)
        except ValueError:
            return None
        return {
            "name": skill.name,
            "description": skill.description,
            "instruction": skill.instruction[:4000],
            "scripts": skill.scripts,
            "path": skill.path,
            "references": skill.references,
        }

    def search_skills(self, query: str) -> list[dict[str, Any]]:
        query_lower = query.lower().strip()
        if not query_lower:
            return self.list_skills()
        results: list[dict[str, Any]] = []
        for skill in self._manager.list_skills():
            haystack = " ".join(
                [
                    skill.name,
                    skill.description,
                    skill.instruction,
                    " ".join(skill.scripts),
                    " ".join(skill.references),
                ]
            ).lower()
            if query_lower in haystack:
                results.append(
                    {
                        "name": skill.name,
                        "description": skill.description,
                        "scripts_count": len(skill.scripts),
                        "path": skill.path,
                    }
                )
        return results

    def get_skill_instruction(self, name: str) -> str | None:
        try:
            return self._manager.load_skill_instruction(name)
        except ValueError:
            return None


def register_skill_tools(registry: Any, skill_runner: SkillRunner) -> None:
    @registry.tool(
        name="list_skills",
        description="列出所有可用技能。",
    )
    async def list_skills() -> dict:
        return {"skills": skill_runner.list_skills()}

    @registry.tool(
        name="search_skills",
        description="搜索技能。",
    )
    async def search_skills(query: str) -> dict:
        results = skill_runner.search_skills(query)
        return {"query": query, "results": results, "count": len(results)}

    @registry.tool(
        name="get_skill",
        description="获取指定技能详情。",
    )
    async def get_skill(name: str) -> dict:
        skill = skill_runner.get_skill(name)
        if skill:
            return {"found": True, "skill": skill}
        return {"found": False, "error": f"技能 '{name}' 不存在。"}
