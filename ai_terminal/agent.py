"""AI Agent 集成 — 基于 wuwei 框架的智能对话。"""

from __future__ import annotations

import json
from typing import Any, Callable

from wuwei.agent.agent import Agent
from wuwei.llm.gateway import LLMGateway
from wuwei.tools.registry import ToolRegistry

from ai_terminal.config import Config
from ai_terminal.safety.policy import SafetyPolicy, RiskLevel
from ai_terminal.safety.audit import AuditLogger, AuditAction
from ai_terminal.tools.shell_tools import ShellExecutor, register_shell_tools
from ai_terminal.cluster.remote import RemoteExecutor, register_cluster_tools


SYSTEM_PROMPT = """你是 AI Terminal 智能终端管家。你的职责：

1. 理解用户的自然语言需求，生成并执行终端命令
2. 确保操作安全：只读命令自动执行，破坏性命令需确认
3. 提供运维建议和故障排查

安全规则：
- 只读命令（ls、cat、grep 等）自动执行
- 可逆写入（mkdir、cp、git commit 等）自动执行
- 破坏性命令（rm、docker rm 等）推荐安全替代方案
- 不可逆命令（rm -rf /、DROP DATABASE 等）必须二次确认

回复要求：
- 简洁直接，先执行后解释
- 命令执行结果用代码块展示
- 出错时给出修复建议
- 涉及多台服务器时汇总展示结果
"""


class AITerminalAgent:
    """AI Terminal 智能 Agent。"""

    def __init__(
        self,
        config: Config,
        policy: SafetyPolicy | None = None,
        audit: AuditLogger | None = None,
    ):
        self.config = config
        self.policy = policy or SafetyPolicy(config.safety)
        self.audit = audit or AuditLogger(config.get("audit.log_dir", "~/.ai-terminal/audit"))

        # 执行器
        self.shell = ShellExecutor(
            timeout=config.get("safety.command_timeout", 30),
        )
        self.remote = RemoteExecutor(
            timeout=config.get("cluster.command_timeout", 60),
        )

        # 工具注册
        self.registry = ToolRegistry()
        register_shell_tools(self.registry, self.shell)
        self._inventory = config.load_inventory()
        register_cluster_tools(self.registry, self.remote, self._inventory)

        # 注册安全检查工具
        self._register_safety_tools()

        # LLM 网关
        self._llm: LLMGateway | None = None
        self._agent: Agent | None = None

    def _register_safety_tools(self) -> None:
        """注册安全相关工具。"""

        @self.registry.tool(
            name="check_safety",
            description="检查命令的安全等级和风险，返回是否需要确认。在执行任何不确定的命令前调用。",
        )
        async def check_safety(command: str) -> dict:
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

    def _build_agent(self) -> Agent:
        """构建 wuwei Agent。"""
        if self._agent is not None:
            return self._agent

        llm_config = self.config.llm

        # api_key: 优先用配置文件，其次用环境变量
        api_key = llm_config.get("api_key") or __import__("os").environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "未配置 LLM API Key。请在 config.yaml 中设置 llm.api_key，"
                "或设置环境变量 OPENAI_API_KEY"
            )

        # LLMGateway 需要 config dict，支持 api_key / base_url
        gw_config = {
            "provider": llm_config.get("provider", "openai"),
            "api_key": api_key,
            "model": llm_config.get("model", "gpt-4o"),
            "temperature": llm_config.get("temperature", 0.1),
            "max_tokens": llm_config.get("max_tokens", 4096),
        }
        if llm_config.get("base_url"):
            gw_config["base_url"] = llm_config["base_url"]

        self._llm = LLMGateway(gw_config)

        self._agent = Agent(
            llm=self._llm,
            tools=self.registry,
            system_prompt=SYSTEM_PROMPT,
            max_steps=10,
        )
        return self._agent

    async def chat(self, user_input: str) -> str:
        """与 AI 对话。"""
        agent = self._build_agent()
        result = await agent.run(user_input)
        return result

    async def execute_with_approval(self, command: str) -> dict:
        """执行命令（带安全审批）。"""
        decision = self.policy.check(command)

        # 记录审计
        if decision.risk_level in (RiskLevel.SAFE, RiskLevel.LOW):
            result = await self.shell.run(command)
            self.audit.log_execution(
                command=command,
                risk_level=decision.risk_level,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
            )
            return result.to_dict()

        # 高风险命令需要外部确认
        return {
            "needs_confirmation": True,
            "risk_level": decision.risk_level.value,
            "reason": decision.reason,
            "alternative": decision.alternative,
            "rollback_command": decision.rollback_command,
        }

    async def execute_confirmed(self, command: str) -> dict:
        """用户确认后执行命令。"""
        decision = self.policy.check(command)
        result = await self.shell.run(command)
        self.audit.log_execution(
            command=command,
            risk_level=decision.risk_level,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            action=AuditAction.CONFIRMED,
        )
        return result.to_dict()

    async def close(self) -> None:
        """清理资源。"""
        await self.remote.close()
