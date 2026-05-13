"""Tests for runtime tool registration and safety gating."""

from __future__ import annotations

import json

import pytest
from wuwei.llm.types import FunctionCall, ToolCall
from wuwei.runtime.hitl import ToolApprovalRejected

from ai_terminal.agent import AITerminalAgent
from ai_terminal.config import Config
from ai_terminal.runtime.safety_hook import SafetyApprovalHook


class _FakeFunction:
    def __init__(self, name: str, arguments: dict[str, object]) -> None:
        self.name = name
        self.arguments = json.dumps(arguments, ensure_ascii=False)


class _FakeToolCall:
    def __init__(self, name: str, arguments: dict[str, object]) -> None:
        self.id = "call-1"
        self.function = _FakeFunction(name, arguments)


@pytest.mark.asyncio
async def test_safety_hook_rejects_high_risk_tool_call() -> None:
    hook = SafetyApprovalHook()
    tool_call = _FakeToolCall("run_command", {"command": "docker rm temp"})

    with pytest.raises(ToolApprovalRejected):
        await hook.before_tool(session=None, tool_call=tool_call, step=0)


@pytest.mark.asyncio
async def test_safety_hook_allows_non_side_effect_safety_check() -> None:
    hook = SafetyApprovalHook()
    tool_call = _FakeToolCall("check_safety", {"command": "shutdown /s /t 60"})

    class _ToolExecution:
        side_effect = False

    class _Tool:
        execution = _ToolExecution()

    await hook.before_tool(session=None, tool_call=tool_call, step=0, tool=_Tool())


@pytest.mark.asyncio
async def test_safety_hook_accepts_wuwei_dict_arguments() -> None:
    hook = SafetyApprovalHook()
    tool_call = ToolCall(
        id="call-1",
        type="function",
        function=FunctionCall(name="run_command", arguments={"command": "dir"}),
    )

    class _ToolExecution:
        side_effect = True

    class _Tool:
        execution = _ToolExecution()

    await hook.before_tool(session=None, tool_call=tool_call, step=0, tool=_Tool())


def test_agent_registers_knowledge_and_incident_tools() -> None:
    agent = AITerminalAgent(Config())
    tool_names = {tool.name for tool in agent.registry.list_tools()}

    assert "search_knowledge" in tool_names
    assert "record_incident" in tool_names
