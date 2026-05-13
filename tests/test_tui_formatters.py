"""Tests for TUI presentation helpers."""

from ai_terminal.tui.formatters import (
    history_rows,
    host_rows,
    incident_rows,
    skill_rows,
    task_event_markup,
)
from ai_terminal.tui.tasks import TaskEvent


def test_host_rows_empty_state():
    assert host_rows([])[0][0] == "暂无主机"


def test_history_rows_formats_success():
    rows = history_rows([
        {
            "timestamp": "2026-05-13T14:50:00",
            "exit_code": 0,
            "risk_level": "safe",
            "command": "git status",
            "duration_ms": 12,
        }
    ])
    assert rows == [("14:50:00", "ok", "safe", "git status", "12ms")]


def test_skill_rows_empty_state():
    assert skill_rows([])[0][0] == "暂无技能"


def test_incident_rows_formats_open_incident():
    rows = incident_rows([
        {
            "timestamp": "2026-05-13T14:50:00",
            "resolved": False,
            "root_cause": "权限不足",
            "command": "cat secret.txt",
        }
    ])
    assert rows == [("2026-05-13 14:50:00", "open", "权限不足", "cat secret.txt")]


def test_task_event_markup_formats_finished_command():
    markup = task_event_markup(TaskEvent.command_finished(
        "git status",
        {"exit_code": 0, "duration_ms": 12},
    ))

    assert "命令完成" in markup
    assert "git status" in markup
    assert "exit=0" in markup
    assert "12ms" in markup
