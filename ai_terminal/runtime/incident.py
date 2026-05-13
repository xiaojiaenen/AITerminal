"""经验自动沉淀 — 从失败中学习，生成可复用 Skill。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class Incident:
    """一条经验记录。"""
    id: str
    timestamp: str
    command: str
    error_output: str
    exit_code: int
    root_cause: str = ""
    solution: str = ""
    tags: list[str] = field(default_factory=list)
    resolved: bool = False
    skill_generated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        """生成 Markdown 格式的 Skill 文档。"""
        tags_str = ", ".join(self.tags) if self.tags else "general"
        return f"""# {self.root_cause or self.command[:50]}

**标签**: {tags_str}
**触发命令**: `{self.command}`
**错误码**: {self.exit_code}

## 问题描述

{self.error_output[:500]}

## 根因分析

{self.root_cause or "待分析"}

## 解决方案

```bash
{self.solution}
```

## 自动生成时间

{self.timestamp}
"""


class IncidentRecorder:
    """经验记录器。"""

    # 常见错误模式 → 根因 + 解决方案
    KNOWN_PATTERNS: list[tuple[str, str, str, list[str]]] = [
        (
            r"Permission denied",
            "权限不足",
            "chmod +x {file} 或 sudo 执行",
            ["permission", "linux"],
        ),
        (
            r"No such file or directory",
            "文件或目录不存在",
            "检查路径是否正确，ls 确认",
            ["filesystem"],
        ),
        (
            r"command not found",
            "命令未安装",
            "apt/yum/brew install {cmd}",
            ["install", "dependency"],
        ),
        (
            r"port already in use|Address already in use",
            "端口被占用",
            "lsof -i :{port} 找到占用进程并 kill",
            ["network", "port"],
        ),
        (
            r"Out of memory|Cannot allocate memory",
            "内存不足",
            "检查内存使用，增加 swap 或释放内存",
            ["memory", "resource"],
        ),
        (
            r"No space left on device",
            "磁盘空间不足",
            "df -h 检查，清理日志或临时文件",
            ["disk", "resource"],
        ),
        (
            r"Connection refused",
            "连接被拒绝",
            "检查目标服务是否启动，端口是否正确",
            ["network", "service"],
        ),
        (
            r"Connection timed out",
            "连接超时",
            "检查网络连通性，防火墙规则",
            ["network", "firewall"],
        ),
        (
            r"ModuleNotFoundError|ImportError",
            "Python 模块缺失",
            "pip install {module}",
            ["python", "dependency"],
        ),
        (
            r"docker.*not found|Cannot connect to the Docker daemon",
            "Docker 未运行",
            "systemctl start docker 或检查 Docker 安装",
            ["docker"],
        ),
        (
            r"fatal: not a git repository",
            "不在 Git 仓库中",
            "cd 到正确的项目目录或 git init",
            ["git"],
        ),
        (
            r"error: failed to push some refs",
            "推送被拒绝",
            "git pull --rebase 后再 push",
            ["git", "push"],
        ),
        (
            r"ECONNREFUSED|EADDRINUSE",
            "Node.js 端口或连接问题",
            "检查端口占用或服务状态",
            ["node", "network"],
        ),
    ]

    def __init__(self, store_path: str | Path = "~/.ai-terminal/incidents"):
        self.store_path = Path(store_path).expanduser()
        self.store_path.mkdir(parents=True, exist_ok=True)
        self._incidents: list[Incident] = []
        self._load()

    def _load(self) -> None:
        """加载已有记录。"""
        incidents_file = self.store_path / "incidents.jsonl"
        if not incidents_file.exists():
            return
        for line in incidents_file.read_text(encoding="utf-8").strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    self._incidents.append(Incident(**data))
                except (json.JSONDecodeError, TypeError):
                    continue

    def _save(self, incident: Incident) -> None:
        """追加保存记录。"""
        incidents_file = self.store_path / "incidents.jsonl"
        with open(incidents_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(incident.to_dict(), ensure_ascii=False) + "\n")

    def _generate_id(self) -> str:
        return datetime.now().strftime("%Y%m%d%H%M%S") + str(len(self._incidents))

    def record(
        self,
        command: str,
        exit_code: int,
        error_output: str,
        tags: list[str] | None = None,
    ) -> Incident | None:
        """记录一次失败。如果匹配已知模式则自动填充根因和方案。"""
        if exit_code == 0:
            return None  # 成功的命令不记录

        # 过滤：太短的错误信息不值得记录（如单纯的 "error"）
        stripped_error = error_output.strip()
        if len(stripped_error) < 10:
            return None

        # 过滤：过于简单的命令不值得沉淀经验
        trivial_commands = {"cls", "clear", "echo", "pwd", "cd", "whoami", "date", "time"}
        cmd_root = command.strip().split()[0] if command.strip() else ""
        if cmd_root.lower() in trivial_commands and not stripped_error:
            return None

        # 检测已知模式
        root_cause = ""
        solution = ""
        auto_tags = list(tags or [])

        for pattern, cause, sol, pattern_tags in self.KNOWN_PATTERNS:
            if re.search(pattern, error_output, re.IGNORECASE):
                root_cause = cause
                solution = sol
                auto_tags.extend(pattern_tags)
                # 尝试提取具体信息填充方案
                solution = self._fill_solution(solution, command, error_output)
                break

        # 过滤：没有匹配已知模式且错误信息不包含实质性内容
        if not root_cause:
            # 只保留有关键异常字样的错误
            has_substance = any(
                kw in stripped_error.lower()
                for kw in (
                    "error", "fail", "exception", "denied",
                    "not found", "cannot", "无法", "错误",
                )
            )
            if not has_substance:
                return None

        incident = Incident(
            id=self._generate_id(),
            timestamp=datetime.now().isoformat(),
            command=command,
            error_output=stripped_error[:2000],
            exit_code=exit_code,
            root_cause=root_cause,
            solution=solution,
            tags=list(set(auto_tags)),
            resolved=bool(solution),
        )

        self._incidents.append(incident)
        self._save(incident)
        return incident

    def _fill_solution(self, solution: str, command: str, error: str) -> str:
        """尝试用实际信息填充解决方案模板。"""
        # 提取文件名
        file_match = re.search(r"(/[\w./-]+)", command)
        if file_match and "{file}" in solution:
            solution = solution.replace("{file}", file_match.group(1))

        # 提取命令名
        cmd_parts = command.split()
        if cmd_parts and "{cmd}" in solution:
            solution = solution.replace("{cmd}", cmd_parts[0])

        # 提取端口
        port_match = re.search(r":(\d+)", command)
        if port_match and "{port}" in solution:
            solution = solution.replace("{port}", port_match.group(1))

        # 提取 Python 模块
        module_match = re.search(r"No module named '(\w+)'", error)
        if module_match and "{module}" in solution:
            solution = solution.replace("{module}", module_match.group(1))

        return solution

    def get_unresolved(self) -> list[Incident]:
        """获取未解决的经验记录。"""
        return [i for i in self._incidents if not i.resolved]

    def get_recent(self, count: int = 20) -> list[Incident]:
        """获取最近的经验记录。"""
        return self._incidents[-count:]

    def mark_resolved(self, incident_id: str, solution: str) -> bool:
        """标记为已解决。"""
        for incident in self._incidents:
            if incident.id == incident_id:
                incident.resolved = True
                incident.solution = solution
                self._save_all()
                return True
        return False

    def _create_incident(
        self,
        command: str = "",
        error_output: str = "",
        root_cause: str = "",
        solution: str = "",
        tags: list[str] | None = None,
    ) -> Incident | None:
        """直接创建一条经验记录（由 LLM 审查生成）。跳过自动诊断。"""
        if not solution and not root_cause:
            return None  # 没有实质内容不记录

        incident = Incident(
            id=self._generate_id(),
            timestamp=datetime.now().isoformat(),
            command=command[:500],
            error_output=error_output[:2000],
            exit_code=-1,  # LLM 审查生成，非实际失败
            root_cause=root_cause,
            solution=solution,
            tags=list(set(tags or [])),
            resolved=bool(solution),
        )
        self._incidents.append(incident)
        self._save(incident)
        return incident

    def _save_all(self) -> None:
        """重新保存所有记录。"""
        incidents_file = self.store_path / "incidents.jsonl"
        with open(incidents_file, "w", encoding="utf-8") as f:
            for incident in self._incidents:
                f.write(json.dumps(incident.to_dict(), ensure_ascii=False) + "\n")

    def generate_skill(self, incident: Incident) -> str:
        """从经验记录生成 Skill 文档。"""
        skill_dir = self.store_path / "skills"
        skill_dir.mkdir(exist_ok=True)

        filename = f"{incident.id}_{incident.root_cause[:30].replace(' ', '_')}.md"
        skill_file = skill_dir / filename

        content = incident.to_markdown()
        skill_file.write_text(content, encoding="utf-8")

        incident.skill_generated = True
        self._save_all()

        return str(skill_file)

    def generate_all_skills(self) -> list[str]:
        """为所有已解决但未生成 Skill 的记录生成 Skill。"""
        paths = []
        for incident in self._incidents:
            if incident.resolved and not incident.skill_generated:
                path = self.generate_skill(incident)
                paths.append(path)
        return paths

    def search(self, query: str) -> list[Incident]:
        """搜索经验记录。"""
        query_lower = query.lower()
        results = []
        for incident in self._incidents:
            if (
                query_lower in incident.command.lower()
                or query_lower in incident.error_output.lower()
                or query_lower in incident.root_cause.lower()
                or query_lower in incident.solution.lower()
                or any(query_lower in tag for tag in incident.tags)
            ):
                results.append(incident)
        return results

    def get_stats(self) -> dict[str, Any]:
        """统计信息。"""
        total = len(self._incidents)
        resolved = sum(1 for i in self._incidents if i.resolved)
        skill_gen = sum(1 for i in self._incidents if i.skill_generated)

        tag_counts: dict[str, int] = {}
        for incident in self._incidents:
            for tag in incident.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return {
            "total": total,
            "resolved": resolved,
            "unresolved": total - resolved,
            "skills_generated": skill_gen,
            "top_tags": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:10]),
        }


def register_incident_tools(registry: Any, recorder: IncidentRecorder) -> None:
    """注册经验记录相关工具。"""

    @registry.tool(
        name="record_incident",
        description="记录一次命令执行失败，自动分析根因并生成解决方案。",
    )
    async def record_incident(
        command: str,
        exit_code: int,
        error_output: str,
        tags: list[str] | None = None,
    ) -> dict:
        incident = recorder.record(command, exit_code, error_output, tags)
        if incident is None:
            return {"recorded": False, "reason": "命令执行成功，无需记录"}
        return {
            "recorded": True,
            "incident": incident.to_dict(),
        }

    @registry.tool(
        name="search_incidents",
        description="搜索历史经验记录，查找类似问题的解决方案。",
    )
    async def search_incidents(query: str) -> dict:
        results = recorder.search(query)
        return {
            "count": len(results),
            "incidents": [i.to_dict() for i in results[:10]],
        }

    @registry.tool(
        name="get_incident_stats",
        description="获取经验记录统计信息。",
    )
    async def get_incident_stats() -> dict:
        return recorder.get_stats()
