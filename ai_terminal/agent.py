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


import sys as _sys

if _sys.platform == "win32":
    SYSTEM_PROMPT = """你是 AI Terminal 智能终端管家。你的职责：

1. 理解用户的自然语言需求，生成并执行终端命令
2. 确保操作安全：只读命令自动执行，破坏性命令需确认
3. 提供运维建议和故障排查

重要：当前系统是 Windows，请使用 Windows 命令或 PowerShell 命令。
- 查看文件: dir / Get-ChildItem
- 查看文件内容: type / Get-Content
- 创建目录: mkdir / New-Item
- 复制文件: copy / Copy-Item
- 删除文件: del / Remove-Item
- 网络: ipconfig / Test-Connection
- 进程: tasklist / Get-Process

回复要求：
- 简洁直接，先执行后解释
- 命令执行结果用代码块展示
- 出错时给出修复建议
"""
else:
    SYSTEM_PROMPT = """你是 AI Terminal 智能终端管家。你的职责：

1. 理解用户的自然语言需求，生成并执行终端命令
2. 确保操作安全：只读命令自动执行，破坏性命令需确认
3. 提供运维建议和故障排查

回复要求：
- 简洁直接，先执行后解释
- 命令执行结果用代码块展示
- 出错时给出修复建议
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
            default_system_prompt=SYSTEM_PROMPT,
            default_max_steps=10,
        )
        return self._agent

    async def chat(self, user_input: str) -> str:
        """与 AI 对话。"""
        agent = self._build_agent()
        result = await agent.run(user_input)
        if hasattr(result, "content"):
            return result.content
        return str(result)

    async def generate_command(self, description: str) -> str:
        """让 AI 生成命令但不执行（用于混合模式）。"""
        from wuwei.agent.agent import Agent as WuAgent
        llm_config = self.config.llm
        api_key = llm_config.get("api_key") or __import__("os").environ.get("OPENAI_API_KEY", "")
        gw_config = {
            "provider": llm_config.get("provider", "openai"),
            "api_key": api_key,
            "model": llm_config.get("model", "gpt-4o"),
            "temperature": llm_config.get("temperature", 0.1),
            "max_tokens": llm_config.get("max_tokens", 4096),
        }
        if llm_config.get("base_url"):
            gw_config["base_url"] = llm_config["base_url"]

        llm = LLMGateway(gw_config)

        if _sys.platform == "win32":
            cmd_prompt = "你是一个终端命令专家。当前系统是 Windows。用户会描述需求，你只输出要执行的 Windows/PowerShell 命令，每行一条，不要解释，不要 markdown 代码块。"
        else:
            cmd_prompt = "你是一个终端命令专家。当前系统是 Linux/macOS。用户会描述需求，你只输出要执行的 shell 命令，每行一条，不要解释，不要 markdown 代码块。"

        agent = WuAgent(
            llm=llm,
            tools=None,
            default_system_prompt=cmd_prompt,
            default_max_steps=1,
        )
        result = await agent.run(description)
        if hasattr(result, "content"):
            return result.content
        return str(result)

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
