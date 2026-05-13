"""Application services shared by the Textual UI."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_terminal.agent import AITerminalAgent
from ai_terminal.cluster.remote import RemoteExecutor
from ai_terminal.config import Config
from ai_terminal.runtime.incident import IncidentRecorder
from ai_terminal.safety.audit import AuditAction, AuditLogger
from ai_terminal.safety.policy import RiskLevel, SafetyPolicy
from ai_terminal.skill import SkillRunner
from ai_terminal.tools.shell_tools import ShellExecutor

MODE_AI = "ai"
MODE_DIRECT = "direct"
MODE_HYBRID = "hybrid"


@dataclass(slots=True)
class CommandDecision:
    """A command plus its safety decision."""

    command: str
    allowed: bool
    risk_level: RiskLevel
    reason: str
    require_confirmation: bool
    alternative: str | None = None
    rollback_command: str | None = None


def detect_mode(user_input: str) -> tuple[str, str]:
    """Return the input mode and stripped content."""
    stripped = user_input.strip()
    if stripped.startswith("!"):
        return MODE_DIRECT, stripped[1:].strip()
    if stripped.startswith(">"):
        return MODE_HYBRID, stripped[1:].strip()
    return MODE_AI, stripped


def extract_command_from_args(tool_name: str, args: str | dict) -> str:
    """Extract a readable command or query from tool args."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, TypeError):
            return args[:200]

    if not isinstance(args, dict):
        return str(args)[:200]

    cmd_keys = {
        "run_command": "command",
        "check_safety": "command",
        "remote_run": "command",
    }
    list_keys = {
        "run_pipeline": "commands",
        "run_batch": "commands",
    }

    if tool_name in cmd_keys:
        return str(args.get(cmd_keys[tool_name], ""))[:200]
    if tool_name in list_keys:
        cmds = args.get(list_keys[tool_name], [])
        if isinstance(cmds, list):
            return " | ".join(str(c) for c in cmds)[:200]
        return str(cmds)[:200]
    if tool_name == "search_knowledge":
        return f'search: {args.get("query", "")}'[:200]
    if tool_name == "ingest_knowledge":
        return args.get("file_path", "") or args.get("text", "")[:200]

    return tool_name


def format_tool_output(tool_name: str, output: str) -> str:
    """Create a compact tool result summary for timeline display."""
    try:
        data = json.loads(output) if isinstance(output, str) else output
    except (json.JSONDecodeError, TypeError):
        data = None

    if isinstance(data, dict):
        if tool_name in ("run_command", "remote_run"):
            stdout = data.get("stdout", "").strip()
            stderr = data.get("stderr", "").strip()
            exit_code = data.get("exit_code", "")
            parts = [f"exit={exit_code}"]
            if stdout:
                lines = [line for line in stdout.splitlines() if line.strip()]
                parts.append("\n".join(lines[:6]))
                if len(lines) > 6:
                    parts.append("... output truncated")
            if stderr:
                parts.append(stderr[:240])
            return "\n".join(parts)

        if tool_name == "check_safety":
            risk = data.get("risk_level", "?")
            reason = data.get("reason", "")
            return f"risk: {risk} - {reason}"[:300]

        if "results" in data or "count" in data:
            results = data.get("results", [])
            count = data.get("count", len(results))
            preview = ""
            if isinstance(results, list) and results:
                first = results[0]
                if isinstance(first, dict):
                    preview = first.get("text", first.get("name", str(first)))[:150]
            return f"{count} results" + (f": {preview}" if preview else "")

        for key in ("summary", "status", "result", "message"):
            if key in data:
                return str(data[key])[:300]
        return json.dumps(data, ensure_ascii=False)[:300]

    text = str(output).strip()
    if len(text) > 300:
        return text[:300] + "\n... output truncated"
    return text


class TerminalService:
    """Thin orchestration layer for TUI screens."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.policy = SafetyPolicy(self.config.safety)
        self.audit = AuditLogger(self.config.get("audit.log_dir", "~/.ai-terminal/audit"))
        self.shell = ShellExecutor(timeout=self.config.get("safety.command_timeout", 30))
        self.remote = RemoteExecutor(timeout=self.config.get("cluster.command_timeout", 60))
        self.incidents = IncidentRecorder()
        self.skill_runner = SkillRunner(
            skill_dirs=self.config.get("skills.dirs", []),
            incident_skill_dir=self.config.get(
                "skills.incident_dir",
                "~/.ai-terminal/incidents/skills",
            ),
        )
        self._agent: AITerminalAgent | None = None

    @property
    def agent(self) -> AITerminalAgent:
        if self._agent is None:
            self._agent = AITerminalAgent(
                self.config,
                self.policy,
                self.audit,
                self.skill_runner,
                self.incidents,
            )
        return self._agent

    def decide(self, command: str) -> CommandDecision:
        decision = self.policy.check(command)
        return CommandDecision(
            command=command,
            allowed=decision.allowed,
            risk_level=decision.risk_level,
            reason=decision.reason,
            require_confirmation=decision.require_confirmation,
            alternative=decision.alternative,
            rollback_command=decision.rollback_command,
        )

    async def execute(self, command: str, *, confirmed: bool = False) -> dict[str, Any]:
        decision = self.policy.check(command)

        if not decision.allowed:
            self.audit.log_blocked(command, decision.reason, risk_level=decision.risk_level)
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": decision.reason,
                "duration_ms": 0,
                "success": False,
                "blocked": True,
            }

        if decision.require_confirmation and not confirmed:
            self.audit.log_execution(
                command=command,
                risk_level=decision.risk_level,
                action=AuditAction.DENIED,
                reason="命令需要人工确认后才能执行",
            )
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": "命令需要人工确认后才能执行",
                "duration_ms": 0,
                "success": False,
                "blocked": True,
                "needs_confirmation": True,
            }

        result = await self.shell.run(command)
        self.audit.log_execution(
            command=command,
            risk_level=decision.risk_level,
            exit_code=result.exit_code,
            output=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
            action=AuditAction.CONFIRMED if confirmed else AuditAction.EXECUTED,
        )

        if not result.success:
            self.incidents.record(
                command=command,
                exit_code=result.exit_code,
                error_output=result.stderr or result.stdout,
            )

        return result.to_dict()

    async def generate_commands(self, description: str) -> list[str]:
        response = await self.agent.generate_command(description)
        return [line.strip().strip("`") for line in response.splitlines() if line.strip()]

    async def chat_stream(self, text: str) -> AsyncIterator[dict[str, Any]]:
        async for event in self.agent.chat_stream(text):
            yield event

    def clear_session(self) -> None:
        if self._agent is not None:
            self._agent.clear_session()

    def context_info(self) -> dict[str, Any]:
        if self._agent is None:
            return {"messages": 0, "estimated_tokens": 0, "rounds": 0}
        return self._agent.get_context_info()

    def audit_entries(self, count: int = 50) -> list[dict[str, Any]]:
        return self.audit.get_recent(count)

    def audit_stats(self) -> dict[str, Any]:
        return self.audit.get_stats()

    def hosts(self) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        inventory = self.config.load_inventory()
        return (
            [
                {
                    "name": h.name,
                    "hostname": h.hostname,
                    "port": h.port,
                    "user": h.user,
                    "tags": h.tags,
                }
                for h in inventory.hosts
            ],
            inventory.groups,
        )

    def skills(self) -> list[dict[str, Any]]:
        return self.skill_runner.list_skills()

    def skill_detail(self, name: str) -> dict[str, Any] | None:
        return self.skill_runner.get_skill(name)

    def incident_entries(self, count: int = 50) -> list[dict[str, Any]]:
        return [incident.to_dict() for incident in self.incidents.get_recent(count)]

    def incident_stats(self) -> dict[str, Any]:
        return self.incidents.get_stats()

    def config_sections(self) -> dict[str, Any]:
        return {
            key: self.config.get(key, {})
            for key in ("general", "safety", "audit", "llm", "cluster", "knowledge", "skills")
        }

    def config_view(self) -> list[dict[str, str]]:
        """Return sanitized, read-only config rows for the TUI."""
        rows: list[dict[str, str]] = []
        for section, values in self.config_sections().items():
            if not isinstance(values, dict):
                rows.append({
                    "section": section,
                    "key": "-",
                    "value": self._mask_config_value(section, "-", values),
                    "source": "配置",
                })
                continue

            for key, value in values.items():
                rows.append({
                    "section": section,
                    "key": key,
                    "value": self._mask_config_value(section, key, value),
                    "source": "只读",
                })
        return rows

    def _mask_config_value(self, section: str, key: str, value: Any) -> str:
        key_lower = key.lower()
        sensitive_tokens = ("api_key", "apikey", "token", "secret", "password")
        if any(token in key_lower for token in sensitive_tokens):
            text = str(value or "")
            if not text:
                return "(未设置)"
            return f"{text[:4]}...{text[-4:]}" if len(text) > 8 else "********"
        if key_lower.endswith("_file") or key_lower.endswith("_dir") or "path" in key_lower:
            path = Path(str(value)).expanduser()
            return str(path)
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value) if value else "[]"
        if isinstance(value, dict):
            return "{...}" if value else "{}"
        return str(value)

    async def close(self) -> None:
        await self.remote.close()
        if self._agent is not None:
            await self._agent.close()
