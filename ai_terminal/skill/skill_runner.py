"""技能执行器 — 基于 wuwei Skill 系统，支持加载和执行运维技能。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from wuwei.skill.skill import Skill, SkillProvider, SkillManager
from wuwei.skill.fs_provider import FileSystemSkillProvider


class IncidentSkillProvider(SkillProvider):
    """将经验记录生成的 .md 文件包装为 SkillProvider。"""

    def __init__(self, skill_dir: str | Path):
        self.root_dir = Path(skill_dir).expanduser()
        self._cache: dict[str, Skill] | None = None

    def list_skills(self) -> list[Skill]:
        return list(self._ensure_cache().values())

    def load_skill_instruction(self, skill_name: str) -> str | None:
        skill = self._ensure_cache().get(skill_name)
        return skill.instruction if skill else None

    def refresh(self) -> None:
        self._cache = None

    def _ensure_cache(self) -> dict[str, Skill]:
        if self._cache is None:
            self._cache = self._build_index()
        return self._cache

    def _build_index(self) -> dict[str, Skill]:
        skills: dict[str, Skill] = {}
        if not self.root_dir.is_dir():
            return skills
        for path in sorted(self.root_dir.rglob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            skill = self._parse_incident_md(content, path)
            if skill:
                skills[skill.name] = skill
        return skills

    def _parse_incident_md(self, content: str, path: Path) -> Skill | None:
        """从经验 Markdown 解析技能。提取标题、描述、方案命令。"""
        lines = content.strip().split("\n")
        if not lines:
            return None

        # 标题（跳过 # 前缀）
        title = lines[0].lstrip("#").strip()[:80]

        # 提取标签
        tags = []
        tag_match = re.search(r"\*\*标签\*\*:\s*(.+)", content)
        if tag_match:
            tags = [t.strip() for t in tag_match.group(1).split(",") if t.strip()]

        # 提取根因
        root_cause = ""
        rc_match = re.search(r"## 根因分析\s*\n+(.+?)(?:\n##|\n\*\*|$)", content, re.DOTALL)
        if rc_match:
            root_cause = rc_match.group(1).strip()[:200]

        # 提取解决方案命令
        solutions = []
        sol_match = re.search(r"## 解决方案\s*\n+(.+?)(?:\n##|\n\*\*|$)", content, re.DOTALL)
        if sol_match:
            sol_text = sol_match.group(1).strip()
            # 提取代码块中的命令
            code_blocks = re.findall(r"```(?:bash|shell)?\s*\n(.+?)```", sol_text, re.DOTALL)
            for block in code_blocks:
                for line in block.strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        solutions.append(line)

        # 提取触发命令
        cmd_match = re.search(r"\*\*触发命令\*\*:\s*`(.+?)`", content)
        trigger_cmd = cmd_match.group(1) if cmd_match else ""

        description = f"{root_cause}" if root_cause else f"技能: {title}"
        if tags:
            description += f" [{', '.join(tags)}]"

        # 名称用文件名（去掉 .md 和时间戳前缀）
        name = path.stem
        # 去掉 Incident 前缀如 20250101_xxx_
        name = re.sub(r"^\d+_", "", name)[:50]

        instruction = content  # 完整 markdown 作为指令

        return Skill(
            name=name,
            description=description,
            instruction=instruction,
            path=str(path),
            scripts=solutions or ([trigger_cmd] if trigger_cmd else []),
        )


class SkillRunner:
    """技能执行器 — 管理技能并执行。"""

    def __init__(
        self,
        skill_dirs: list[str] | None = None,
        incident_skill_dir: str | Path = "~/.ai-terminal/incidents/skills",
    ):
        self._providers: list[SkillProvider] = []

        # 从经验记录生成的技能
        self.incident_skill_dir = Path(incident_skill_dir).expanduser()
        self.incident_skill_dir.mkdir(parents=True, exist_ok=True)
        self._incident_provider = IncidentSkillProvider(self.incident_skill_dir)
        self._providers.append(self._incident_provider)

        # 用户自定义技能目录
        for d in (skill_dirs or []):
            p = Path(d).expanduser()
            if p.is_dir():
                self._providers.append(FileSystemSkillProvider(str(p)))

        self._manager = SkillManager(self._providers)

    def refresh(self) -> None:
        """刷新技能索引。"""
        self._manager.refresh()

    def list_skills(self) -> list[dict]:
        """列出所有可用技能。"""
        skills = self._manager.list_skills()
        return [
            {
                "name": s.name,
                "description": s.description,
                "scripts_count": len(s.scripts),
                "path": s.path,
            }
            for s in skills
        ]

    def get_skill(self, name: str) -> dict | None:
        """获取技能详情。"""
        try:
            skill = self._manager.get_skill(name)
            return {
                "name": skill.name,
                "description": skill.description,
                "instruction": skill.instruction[:2000],
                "scripts": skill.scripts,
                "path": skill.path,
                "references": skill.references,
            }
        except ValueError:
            return None

    def search_skills(self, query: str) -> list[dict]:
        """搜索技能。"""
        query_lower = query.lower()
        results = []
        for s in self._manager.list_skills():
            if (
                query_lower in s.name.lower()
                or query_lower in s.description.lower()
                or any(query_lower in script.lower() for script in s.scripts)
            ):
                results.append({
                    "name": s.name,
                    "description": s.description,
                    "scripts": s.scripts[:5],
                })
        return results

    def get_skill_instruction(self, name: str) -> str | None:
        """获取技能的完整指令，用于注入 AI 对话上下文。"""
        try:
            return self._manager.load_skill_instruction(name)
        except ValueError:
            return None


def register_skill_tools(registry: Any, skill_runner: SkillRunner) -> None:
    """注册技能相关工具到 ToolRegistry。"""

    @registry.tool(
        name="list_skills",
        description="列出所有可用的运维技能。返回技能名称和描述。",
    )
    async def list_skills() -> dict:
        return {"skills": skill_runner.list_skills()}

    @registry.tool(
        name="search_skills",
        description="搜索与问题相关的运维技能。输入关键词，返回匹配的技能及其解决方案命令。",
    )
    async def search_skills(query: str) -> dict:
        results = skill_runner.search_skills(query)
        return {"query": query, "results": results, "count": len(results)}

    @registry.tool(
        name="get_skill",
        description="获取指定技能的完整指令，包括解决方案命令。用于在执行前了解技能详情。",
    )
    async def get_skill(name: str) -> dict:
        skill = skill_runner.get_skill(name)
        if skill:
            return {"found": True, "skill": skill}
        return {"found": False, "error": f"技能 '{name}' 不存在。使用 list_skills 查看可用技能。"}
