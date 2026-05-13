"""Integration tests for AI chat safety confirmation in the TUI."""

from __future__ import annotations

import json

import pytest

from ai_terminal.safety.policy import RiskLevel
from ai_terminal.services.terminal_service import CommandDecision, TerminalService
from ai_terminal.tui.app import AITerminalTUI
from ai_terminal.tui.widgets import RiskModal


@pytest.mark.asyncio
async def test_ai_chat_flow_triggers_confirmation_callback():
    service = TerminalService()
    app = AITerminalTUI(service)
    confirmations: list[str] = []

    async def fake_chat_stream(_text: str):
        yield {
            "type": "tool_start",
            "data": {
                "tool_name": "check_safety",
                "args": {"command": "shutdown /s /t 60"},
            },
        }
        yield {
            "type": "tool_end",
            "data": {
                "tool_name": "check_safety",
                "output": json.dumps(
                    {
                        "command": "shutdown /s /t 60",
                        "allowed": True,
                        "risk_level": "critical",
                        "require_confirmation": True,
                        "reason": "极高风险操作，需要二次确认",
                        "alternative": None,
                        "rollback_command": None,
                    },
                    ensure_ascii=False,
                ),
            },
        }

    async def fake_confirm(decision: CommandDecision) -> str | None:
        confirmations.append(decision.command)
        return None

    service.chat_stream = fake_chat_stream  # type: ignore[method-assign]
    app._confirm_command = fake_confirm  # type: ignore[method-assign]

    async with app.run_test(size=(120, 36)) as pilot:
        app.run_chat_flow("关机")
        await pilot.pause()
        await pilot.pause()

    assert confirmations == ["shutdown /s /t 60"]
    assert service.policy.classify("shutdown /s /t 60") == RiskLevel.CRITICAL


@pytest.mark.asyncio
async def test_ai_chat_flow_pushes_risk_modal():
    service = TerminalService()
    app = AITerminalTUI(service)

    async def fake_chat_stream(_text: str):
        yield {
            "type": "tool_start",
            "data": {
                "tool_name": "check_safety",
                "args": {"command": "shutdown /s /t 60"},
            },
        }
        yield {
            "type": "tool_end",
            "data": {
                "tool_name": "check_safety",
                "output": json.dumps(
                    {
                        "command": "shutdown /s /t 60",
                        "allowed": True,
                        "risk_level": "critical",
                        "require_confirmation": True,
                        "reason": "极高风险操作，需要二次确认",
                        "alternative": None,
                        "rollback_command": None,
                    },
                    ensure_ascii=False,
                ),
            },
        }

    service.chat_stream = fake_chat_stream  # type: ignore[method-assign]

    async with app.run_test(size=(120, 36)) as pilot:
        app.run_chat_flow("关机")
        await pilot.pause()
        await pilot.pause()
        assert any(isinstance(screen, RiskModal) for screen in app.screen_stack)
        await pilot.press("n")
        await pilot.pause()
