"""Tests for chat streaming presentation."""

import json

import pytest

from ai_terminal.safety.policy import RiskLevel
from ai_terminal.services.terminal_service import CommandDecision
from ai_terminal.tui.controllers.chat import ChatController


class FakeLog:
    def __init__(self):
        self.items = []

    def write(self, value):
        self.items.append(str(value))

    def mount(self, value):
        self.items.append(value)
        return value


class FakeMarkdown:
    def __init__(self, text, classes):
        self.text = text
        self.classes = classes

    def update(self, text):
        self.text = text


class FakeService:
    def __init__(self):
        self.executed = []
        self.policy = self

    async def chat_stream(self, _text):
        for delta in ["当前", "目录", ": D:", "\\code", "\n完成"]:
            yield {"type": "text", "data": delta}
        yield {
            "type": "tool_start",
            "data": {"tool_name": "run_command", "args": {"command": "pwd"}},
        }
        yield {
            "type": "tool_end",
            "data": {"tool_name": "run_command", "output": '{"exit_code": 0}'},
        }

    async def execute(self, command, *, confirmed=False):
        self.executed.append((command, confirmed))
        return {"exit_code": 0, "stdout": "", "stderr": "", "duration_ms": 1}

    def classify(self, _command):
        return RiskLevel.CRITICAL


class FakeSafetyService(FakeService):
    async def chat_stream(self, _text):
        yield {
            "type": "tool_start",
            "data": {
                "tool_name": "check_safety",
                "args": {"command": "shutdown /s /t 0"},
            },
        }
        yield {
            "type": "tool_end",
            "data": {
                "tool_name": "check_safety",
                "output": json.dumps({
                    "command": "shutdown /s /t 0",
                    "allowed": True,
                    "risk_level": "critical",
                    "require_confirmation": True,
                    "reason": "极高风险操作，需要二次确认",
                    "alternative": None,
                    "rollback_command": None,
                }, ensure_ascii=False),
            },
        }


class FakeSafetyThenTextService(FakeSafetyService):
    async def chat_stream(self, _text):
        async for event in super().chat_stream(_text):
            yield event
        yield {"type": "text", "data": "这段取消后不应该出现"}


@pytest.mark.asyncio
async def test_chat_controller_writes_stream_without_prefix_duplication():
    chat_log = FakeLog()
    tool_log = FakeLog()
    statuses = []
    events = []
    controller = ChatController(
        FakeService(),
        chat_log,
        tool_log,
        statuses.append,
        events.append,
        markdown_factory=FakeMarkdown,
    )

    await controller.run("pwd")

    rendered = "\n".join(str(getattr(item, "text", item)) for item in chat_log.items)
    assert "当前\n当前目录" not in rendered
    assert any(getattr(item, "text", "") == "当前目录: D:\\code\n完成" for item in chat_log.items)
    assert statuses[-1] == "就绪"
    assert [event.status.value for event in events] == ["running", "success"]


@pytest.mark.asyncio
async def test_chat_controller_executes_confirmed_safety_checked_command():
    chat_log = FakeLog()
    tool_log = FakeLog()
    service = FakeSafetyService()
    confirmations = []

    async def confirm(decision: CommandDecision):
        confirmations.append(decision.command)
        return decision.command

    controller = ChatController(
        service,
        chat_log,
        tool_log,
        lambda _status: None,
        confirm_command=confirm,
        markdown_factory=FakeMarkdown,
    )

    await controller.run("关机")

    assert confirmations == ["shutdown /s /t 0"]
    assert service.executed == [("shutdown /s /t 0", True)]


@pytest.mark.asyncio
async def test_chat_controller_stops_after_cancelled_safety_confirmation():
    chat_log = FakeLog()
    tool_log = FakeLog()
    service = FakeSafetyThenTextService()

    async def cancel(_decision: CommandDecision):
        return None

    controller = ChatController(
        service,
        chat_log,
        tool_log,
        lambda _status: None,
        confirm_command=cancel,
        markdown_factory=FakeMarkdown,
    )

    await controller.run("关机")

    assistant_items = [item for item in chat_log.items if isinstance(item, FakeMarkdown)]
    assert assistant_items[-1].text.startswith("**已取消，未执行。**")
    assert "不应该出现" not in assistant_items[-1].text
    assert service.executed == []
