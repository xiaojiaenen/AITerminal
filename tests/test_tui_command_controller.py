"""Tests for command workflow controller."""

import pytest

from ai_terminal.safety.policy import RiskLevel
from ai_terminal.services.terminal_service import CommandDecision
from ai_terminal.tui.controllers.command import CommandController


class FakeLog:
    def __init__(self):
        self.items = []

    def write(self, value):
        self.items.append(str(value))


class FakeService:
    def __init__(self):
        self.executed = []

    def decide(self, command):
        return CommandDecision(
            command=command,
            allowed=True,
            risk_level=RiskLevel.HIGH,
            reason="needs confirmation",
            require_confirmation=True,
        )

    async def execute(self, command, *, confirmed=False):
        self.executed.append((command, confirmed))
        return {"exit_code": 0, "stdout": "", "stderr": "", "duration_ms": 1}


@pytest.mark.asyncio
async def test_command_controller_does_not_execute_cancelled_risky_command():
    service = FakeService()
    log = FakeLog()
    refreshed = []
    events = []

    async def cancel(_decision):
        return None

    controller = CommandController(
        service=service,
        command_log=log,
        set_status=lambda _status: None,
        refresh_data=lambda: refreshed.append(True),
        confirm_command=cancel,
        on_event=events.append,
    )

    await controller.maybe_execute("rm file.txt")

    assert service.executed == []
    assert any("已取消" in item for item in log.items)
    assert events[-1].status.value == "cancelled"
