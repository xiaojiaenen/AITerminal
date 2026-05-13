"""Task event model for the TUI workbench."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    INFO = "info"


@dataclass(slots=True)
class TaskEvent:
    """One visible event in a command/tool/task timeline."""

    title: str
    status: TaskStatus = TaskStatus.INFO
    detail: str = ""
    command: str = ""
    duration_ms: int | None = None
    exit_code: int | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def command_started(cls, command: str) -> TaskEvent:
        return cls(title="执行命令", status=TaskStatus.RUNNING, command=command)

    @classmethod
    def command_finished(cls, command: str, result: dict[str, Any]) -> TaskEvent:
        exit_code = result.get("exit_code")
        return cls(
            title="命令完成" if exit_code == 0 else "命令失败",
            status=TaskStatus.SUCCESS if exit_code == 0 else TaskStatus.FAILED,
            command=command,
            duration_ms=result.get("duration_ms"),
            exit_code=exit_code,
        )

    @classmethod
    def tool_started(cls, name: str, command: str = "") -> TaskEvent:
        return cls(title=f"工具开始: {name}", status=TaskStatus.RUNNING, command=command)

    @classmethod
    def tool_finished(cls, name: str, detail: str = "") -> TaskEvent:
        return cls(title=f"工具完成: {name}", status=TaskStatus.SUCCESS, detail=detail)
