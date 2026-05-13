"""安全审批 Hook — 在工具执行前进行安全检查。"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from wuwei.runtime.hooks import RuntimeHook
from ai_terminal.safety.policy import SafetyPolicy, RiskLevel, Decision
from ai_terminal.safety.audit import AuditLogger, AuditAction


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
        """默认确认方式 — 在终端中提示用户。"""
        print(f"\n⚠️  安全检查: {decision.reason}")
        print(f"   风险等级: {decision.risk_level.value}")
        if decision.alternative:
            print(f"   建议替代: {decision.alternative}")
        if decision.rollback_command:
            print(f"   回滚命令: {decision.rollback_command}")

        try:
            response = input("\n是否继续执行？(y/N): ").strip().lower()
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    async def before_tool(
        self,
        session: str,
        tool_call: Any,
        *,
        step: int = 0,
        task: Any = None,
    ) -> tuple[bool, str | None]:
        """工具执行前的安全检查。

        返回 (should_continue, modified_args)。
        - should_continue=False 表示阻止执行
        - modified_args 可以替换工具参数
        """
        # 提取命令
        command = self._extract_command(tool_call)
        if not command:
            return True, None

        # 安全检查
        decision = self.policy.check(command)

        # SAFE 级别直接放行
        if decision.risk_level == RiskLevel.SAFE and self.auto_approve_safe:
            self.audit.log_execution(
                command=command,
                risk_level=decision.risk_level,
                action=AuditAction.EXECUTED,
            )
            return True, None

        # LOW 级别自动放行但记录
        if decision.risk_level == RiskLevel.LOW:
            self.audit.log_execution(
                command=command,
                risk_level=decision.risk_level,
                action=AuditAction.EXECUTED,
            )
            return True, None

        # HIGH / CRITICAL 需要确认
        if decision.require_confirmation:
            approved = await self.confirm_callback(decision)

            if approved:
                self.audit.log_execution(
                    command=command,
                    risk_level=decision.risk_level,
                    action=AuditAction.CONFIRMED,
                )
                return True, None
            else:
                self.audit.log_execution(
                    command=command,
                    risk_level=decision.risk_level,
                    action=AuditAction.DENIED,
                )
                return False, None

        # 不需要确认的放行
        self.audit.log_execution(
            command=command,
            risk_level=decision.risk_level,
            action=AuditAction.EXECUTED,
        )
        return True, None

    def _extract_command(self, tool_call: Any) -> str | None:
        """从 tool_call 中提取命令字符串。"""
        # 处理不同的 tool_call 格式
        if hasattr(tool_call, "function"):
            # OpenAI 格式
            import json
            try:
                args = json.loads(tool_call.function.arguments)
                return args.get("command", "")
            except (json.JSONDecodeError, AttributeError):
                pass

        if isinstance(tool_call, dict):
            # 字典格式
            if "arguments" in tool_call:
                args = tool_call["arguments"]
                if isinstance(args, str):
                    import json
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        return args
                if isinstance(args, dict):
                    return args.get("command", "")
            if "command" in tool_call:
                return tool_call["command"]

        if isinstance(tool_call, str):
            return tool_call

        return None

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
