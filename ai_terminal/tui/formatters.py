"""Presentation helpers for Textual tables and logs."""

from __future__ import annotations

from typing import Any

from rich.markup import escape

from ai_terminal.tui.tasks import TaskEvent, TaskStatus

_TASK_STYLES = {
    TaskStatus.PENDING: ("○", "dim"),
    TaskStatus.RUNNING: ("●", "blue"),
    TaskStatus.SUCCESS: ("✓", "green"),
    TaskStatus.FAILED: ("×", "red"),
    TaskStatus.BLOCKED: ("!", "yellow"),
    TaskStatus.CANCELLED: ("-", "yellow"),
    TaskStatus.INFO: ("·", "dim"),
}


def task_event_markup(event: TaskEvent) -> str:
    """Render a task event as compact Rich markup."""
    icon, style = _TASK_STYLES.get(event.status, ("·", "dim"))
    time = event.timestamp.strftime("%H:%M:%S")
    parts = [f"[{style}]{icon} {escape(event.title)}[/{style}]", f"[dim]{time}[/dim]"]
    if event.command:
        parts.append(f"[cyan]{escape(event.command)}[/cyan]")
    if event.exit_code is not None:
        code_style = "green" if event.exit_code == 0 else "red"
        parts.append(f"[{code_style}]exit={event.exit_code}[/{code_style}]")
    if event.duration_ms is not None:
        parts.append(f"[dim]{event.duration_ms}ms[/dim]")
    if event.detail:
        parts.append(f"\n[dim]{escape(event.detail)}[/dim]")
    return "  ".join(parts)


def host_rows(hosts: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str]]:
    if not hosts:
        return [("暂无主机", "配置 inventory.yaml 后显示", "-", "-", "-")]
    return [
        (
            host.get("name", ""),
            host.get("hostname", ""),
            str(host.get("port", 22)),
            host.get("user", "root"),
            ", ".join(host.get("tags", [])),
        )
        for host in hosts
    ]


def history_rows(entries: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str]]:
    if not entries:
        return [("--", "empty", "-", "暂无执行历史", "-")]

    rows = []
    for entry in reversed(entries):
        ts = str(entry.get("timestamp", ""))[11:19]
        exit_code = entry.get("exit_code", "-")
        status = "ok" if exit_code == 0 else f"exit {exit_code}"
        rows.append(
            (
                ts,
                status,
                entry.get("risk_level", "?"),
                entry.get("command", ""),
                f"{entry.get('duration_ms', 0)}ms",
            )
        )
    return rows


def skill_rows(skills: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    if not skills:
        return [("暂无技能", "0", "经验记录生成 Skill 后会出现在这里")]
    return [
        (
            skill.get("name", ""),
            str(skill.get("scripts_count", 0)),
            skill.get("description", "")[:100],
        )
        for skill in skills
    ]


def incident_rows(incidents: list[dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    if not incidents:
        return [("--", "empty", "暂无经验记录", "失败命令会自动沉淀到这里")]

    rows = []
    for incident in reversed(incidents):
        ts = str(incident.get("timestamp", ""))[0:19].replace("T", " ")
        status = "resolved" if incident.get("resolved") else "open"
        rows.append(
            (
                ts,
                status,
                incident.get("root_cause", ""),
                incident.get("command", "")[:120],
            )
        )
    return rows


def config_rows(rows: list[dict[str, str]]) -> list[tuple[str, str, str, str]]:
    if not rows:
        return [("-", "-", "暂无配置", "只读")]
    return [
        (
            row.get("section", ""),
            row.get("key", ""),
            row.get("value", ""),
            row.get("source", "只读"),
        )
        for row in rows
    ]
