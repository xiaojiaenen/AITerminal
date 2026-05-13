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
from ai_terminal.skill import SkillRunner, register_skill_tools


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
        skill_runner: SkillRunner | None = None,
    ):
        self.config = config
        self.policy = policy or SafetyPolicy(config.safety)
        self.audit = audit or AuditLogger(config.get("audit.log_dir", "~/.ai-terminal/audit"))
        self.skill_runner = skill_runner or SkillRunner()

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

        # 注册技能工具
        register_skill_tools(self.registry, self.skill_runner)

        # LLM 网关
        self._llm: LLMGateway | None = None
        self._agent: Agent | None = None
        self._session_id: str | None = None  # 持久会话 ID，保留对话历史
        self._round_count = 0  # 对话轮数计数
        self._review_interval = 5  # 每 N 轮触发经验审查

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
            default_max_steps=30,
        )
        return self._agent

    async def chat(self, user_input: str) -> str:
        """与 AI 对话。"""
        agent = self._build_agent()
        session = agent.create_or_get_session(session_id=self._session_id)
        if self._session_id is None:
            self._session_id = session.session_id
        result = await agent.run(user_input, session=session)
        if hasattr(result, "content"):
            return result.content
        return str(result)

    async def chat_stream(self, user_input: str):
        """与 AI 对话（流式输出）。历史上下文自动保留。

        Yields dict: {"type": "text"|"tool_start"|"tool_end", "data": ...}
        """
        agent = self._build_agent()
        session = agent.create_or_get_session(session_id=self._session_id)
        if self._session_id is None:
            self._session_id = session.session_id
        async for event in agent.stream_events(user_input, session=session):
            if event.type == "text_delta":
                content = event.data.get("content", "")
                if content:
                    yield {"type": "text", "data": content}
            elif event.type == "reasoning_delta":
                pass
            elif event.type == "tool_start":
                yield {
                    "type": "tool_start",
                    "data": {
                        "tool_name": event.data.get("tool_name", ""),
                        "args": event.data.get("args", ""),
                    },
                }
            elif event.type == "tool_end":
                output = event.data.get("output", "")
                yield {
                    "type": "tool_end",
                    "data": {
                        "tool_name": event.data.get("tool_name", ""),
                        "output": output,
                    },
                }
            elif event.type == "run_end":
                break

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

    def clear_session(self) -> None:
        """清除会话上下文，开始新对话。"""
        self._session_id = None
        self._round_count = 0
        if self._agent is not None:
            # 创建新会话替换旧会话
            self._session_id = self._agent.create_session().session_id

    def get_context_info(self) -> dict:
        """获取当前会话上下文信息。"""
        if self._agent is None or self._session_id is None:
            return {"messages": 0, "estimated_tokens": 0, "rounds": 0}

        session = self._agent._sessions.get(self._session_id)
        if session is None:
            return {"messages": 0, "estimated_tokens": 0, "rounds": 0}

        messages = session.context.get_messages()
        msg_count = len(messages)
        # 粗略估算：每字符约 0.3 token（中英文混合）
        total_chars = sum(len(m.content or "") for m in messages)
        estimated_tokens = int(total_chars * 0.3)

        return {
            "messages": msg_count,
            "estimated_tokens": estimated_tokens,
            "rounds": self._round_count,
        }

    def on_round_complete(self) -> bool:
        """每轮对话完成后调用。返回 True 表示应触发经验审查。"""
        self._round_count += 1
        return self._round_count > 0 and self._round_count % self._review_interval == 0

    async def review_experience(self) -> list[dict]:
        """审查最近对话，提取值得沉淀的经验。返回新生成的经验列表。"""
        if self._agent is None or self._session_id is None:
            return []

        session = self._agent._sessions.get(self._session_id)
        if session is None:
            return []

        messages = session.context.get_messages()
        if len(messages) < 4:  # system + 至少一轮对话
            return []

        # 取最近几轮对话（一轮通常包含 user + assistant）
        recent = messages[-20:]  # 最多取最近 20 条消息

        # 构建审查 prompt
        conversation_text = []
        for m in recent:
            role = m.role
            content = (m.content or "")[:500]
            if content.strip():
                conversation_text.append(f"[{role}] {content}")

        if not conversation_text:
            return []

        review_prompt = f"""你是一个运维经验审查专家。请审查以下 AI Terminal 终端对话记录，判断是否有值得沉淀的运维经验。

有价值的经验包括：
1. 解决了一个具体的运维问题（错误排查、配置修复等）
2. 发现了一个重要的操作技巧或最佳实践
3. 踩到了某个坑并找到了解决方案

不值得沉淀的内容：
1. 简单的查看/查询操作
2. 一般的聊天对话
3. 没有实际结论的探索

对话记录：
---
{chr(10).join(conversation_text[-30:])}
---

请用 JSON 格式回复，如果没有值得沉淀的经验请返回空数组：
```json
[
  {{
    "title": "经验的简短标题",
    "problem": "遇到的问题",
    "root_cause": "根因分析",
    "solution": "解决方案（可执行的命令）",
    "tags": ["标签1", "标签2"]
  }}
]
```

如果没有任何值得沉淀的经验，返回：```json
[]
```"""

        try:
            from wuwei.llm.types import Message as LLMMessage

            llm = self._llm or LLMGateway({
                "provider": self.config.llm.get("provider", "openai"),
                "api_key": self.config.llm.get("api_key") or __import__("os").environ.get("OPENAI_API_KEY", ""),
                "model": self.config.llm.get("model", "gpt-4o"),
                "temperature": 0.1,
                "max_tokens": 2048,
            })

            result = await llm.generate(
                messages=[LLMMessage(role="user", content=review_prompt)],
                tools=None,
            )

            content = ""
            if hasattr(result, "content"):
                content = result.content
            elif isinstance(result, dict):
                content = result.get("content", "")
            else:
                content = str(result)

            # 提取 JSON 数组
            experiences = self._parse_experience_json(content)
            return experiences

        except Exception:
            return []

    def _parse_experience_json(self, content: str) -> list[dict]:
        """从 LLM 回复中解析经验 JSON。"""
        import json as _json
        import re as _re

        # 尝试匹配 ```json ... ``` 代码块
        match = _re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if match:
            json_str = match.group(1).strip()
        else:
            # 尝试匹配直接的 JSON 数组
            match = _re.search(r"\[[\s\S]*\]", content)
            if match:
                json_str = match.group(0)
            else:
                return []

        try:
            data = _json.loads(json_str)
            if isinstance(data, list):
                return data
        except (_json.JSONDecodeError, TypeError):
            pass

        return []

    async def close(self) -> None:
        """清理资源。"""
        await self.remote.close()
