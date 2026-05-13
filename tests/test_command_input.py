"""Tests for the command input widget."""

import pytest

from ai_terminal.tui.app import AITerminalTUI


@pytest.mark.asyncio
async def test_command_input_history_navigation():
    app = AITerminalTUI()
    async with app.run_test(size=(120, 36)):
        widget = app.query_one("#command-input")
        widget.push_history("git status")
        widget.push_history("docker ps")
        widget.action_history_up()
        assert widget.value == "docker ps"
        widget.action_history_up()
        assert widget.value == "git status"
        widget.action_history_down()
        assert widget.value == "docker ps"


@pytest.mark.asyncio
async def test_command_input_completion_cycles():
    app = AITerminalTUI()
    async with app.run_test(size=(120, 36)):
        widget = app.query_one("#command-input")
        widget.value = "/h"
        widget.action_complete_value()
        assert widget.value in {"/help", "/history", "/hosts"}
