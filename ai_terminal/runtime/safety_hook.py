"""安全审批 Hook — 在工具执行前进行安全检查。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from wuwei.runtime.hitl import ToolApprovalRejected
from wuwei.runtime.hooks import RuntimeHook

from ai_terminal.safety.audit import AuditAction, AuditLogger
from ai_terminal.safety.policy import Decision, RiskLevel, SafetyPolicy


class SafetyApprovalHook(RuntimeHook):
    """安全审批 Hook。

    在工具执行前检查命令风险等级，高风险命令需要用户确认。
    集成审计日志记录所有决策。
    """

    def __init__(
        self,
        policy: SafetyPolicy | None = None,
        audit: AuditLogger | None = None,
        confirm_callback: Callable | None = None,
        auto_approve_safe: bool = True,
    ):
        self.policy = policy or SafetyPolicy()
        self.audit = audit or AuditLogger()
        self.confirm_callback = confirm_callback or self._default_confirm
        self.auto_approve_safe = auto_approve_safe
        self._pending_decisions: dict[str, Decision] = {}

    async def _default_confirm(self, decision: Decision) -> bool:
        """默认拒绝高风险 AI 工具调用，避免在 TUI 中出现阻塞式输入。"""
        return False

    async def before_tool(
        self,
        session: Any,
        tool_call: Any,
        *,
        step: int = 0,
        task: Any = None,
        tool: Any = None,
    ) -> None:
        """工具执行前的安全检查。"""
        if tool is not None and not tool.execution.side_effect:
            return

        # 提取命令
        command = self._extract_command(tool_call)
        if not command:
            return

        # 安全检查
        decision = self.policy.check(command)
        tool_call_id = getattr(tool_call, "id", command)
        self._pending_decisions[tool_call_id] = decision

        if not decision.allowed:
            self.audit.log_blocked(command, decision.reason, risk_level=decision.risk_level)
            self._pending_decisions.pop(tool_call_id, None)
            raise ToolApprovalRejected(decision.reason)

        # SAFE 级别直接放行
        if decision.risk_level == RiskLevel.SAFE and self.auto_approve_safe:
            return

        # LOW 级别自动放行但记录
        if decision.risk_level == RiskLevel.LOW:
            return

        # HIGH / CRITICAL 需要确认
        if decision.require_confirmation:
            approved = await self.confirm_callback(decision)

            if not approved:
                self.audit.log_execution(
                    command=command,
                    risk_level=decision.risk_level,
                    action=AuditAction.DENIED,
                    reason="AI 工具调用需要人工确认，已阻止执行",
                )
                self._pending_decisions.pop(tool_call_id, None)
                raise ToolApprovalRejected(
                    "High-risk AI tool calls require human confirmation. "
                    "Use direct mode (!) or hybrid mode (>) to approve execution."
                )

    async def after_tool(
        self,
        session: Any,
        tool_call: Any,
        tool_message: Any,
        *,
        step: int = 0,
        task: Any = None,
        tool: Any = None,
    ) -> None:
        """在工具执行后补充审计记录。"""
        command = self._extract_command(tool_call)
        if not command:
            return

        tool_call_id = getattr(tool_call, "id", command)
        decision = self._pending_decisions.pop(tool_call_id, self.policy.check(command))
        payload = self._parse_tool_output(tool_message)
        target = self._extract_target(tool_call)

        self.audit.log_execution(
            command=command,
            target=target,
            risk_level=decision.risk_level,
            exit_code=payload["exit_code"],
            output=payload["stdout"],
            stderr=payload["stderr"],
            duration_ms=payload["duration_ms"],
            action=AuditAction.CONFIRMED if decision.require_confirmation else AuditAction.EXECUTED,
        )

    def _extract_command(self, tool_call: Any) -> str | None:
        """从 tool_call 中提取命令字符串。"""
        # 处理不同的 tool_call 格式
        if hasattr(tool_call, "function"):
            # OpenAI 格式
            try:
                args = self._normalize_arguments(tool_call.function.arguments)
                return self._extract_command_from_args(tool_call.function.name, args)
            except AttributeError:
                pass

        if isinstance(tool_call, dict):
            # 字典格式
            if "arguments" in tool_call:
                args = tool_call["arguments"]
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        return args
                if isinstance(args, dict):
                    return self._extract_command_from_args(tool_call.get("name", ""), args)
            if "command" in tool_call:
                return tool_call["command"]

        if isinstance(tool_call, str):
            return tool_call

        return None

    def _extract_command_from_args(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name in {"run_command", "check_safety", "remote_run"}:
            return str(args.get("command", ""))
        if tool_name in {"run_pipeline", "run_batch"}:
            commands = args.get("commands", [])
            if isinstance(commands, list):
                return " | ".join(str(command) for command in commands)
            return str(commands)
        return str(args.get("command", ""))

    def _extract_target(self, tool_call: Any) -> str:
        arguments = {}
        if hasattr(tool_call, "function"):
            try:
                arguments = self._normalize_arguments(tool_call.function.arguments)
            except AttributeError:
                arguments = {}
        elif isinstance(tool_call, dict):
            arguments = tool_call.get("arguments", {}) or {}

        if not isinstance(arguments, dict):
            return "local"

        return str(arguments.get("target") or arguments.get("host") or "local")

    def _normalize_arguments(self, arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _parse_tool_output(self, tool_message: Any) -> dict[str, Any]:
        content = getattr(tool_message, "content", tool_message)
        try:
            payload = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError):
            payload = {}

        if not isinstance(payload, dict):
            payload = {}

        if "results" in payload and isinstance(payload["results"], list):
            failures = [
                result for result in payload["results"]
                if not result.get("success", False) and result.get("exit_code", 0) != 0
            ]
            return {
                "exit_code": 0 if not failures else 1,
                "stdout": json.dumps(payload, ensure_ascii=False),
                "stderr": "",
                "duration_ms": 0,
            }

        return {
            "exit_code": payload.get("exit_code"),
            "stdout": payload.get("stdout", ""),
            "stderr": payload.get("stderr", ""),
            "duration_ms": payload.get("duration_ms", 0),
        }

    def get_suggestion(self, command: str) -> dict[str, Any]:
        """获取命令的安全建议（不执行检查）。"""
        decision = self.policy.check(command)
        return {
            "command": command,
            "risk_level": decision.risk_level.value,
            "allowed": decision.allowed,
            "require_confirmation": decision.require_confirmation,
            "reason": decision.reason,
            "alternative": decision.alternative,
            "rollback_command": decision.rollback_command,
        }
