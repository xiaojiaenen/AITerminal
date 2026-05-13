"""Bottom command input widget with history and completion."""

from __future__ import annotations

import sys
from collections.abc import Iterable

from textual.binding import Binding
from textual.widgets import Input

COMMON_COMMANDS = [
    "git status",
    "git diff",
    "git log",
    "docker ps",
    "docker logs",
    "ls",
    "pwd",
    "cat",
    "grep",
    "find",
    "df -h",
    "top",
    "ps aux",
    "whoami",
]


class CommandInput(Input):
    """Input bar for AI prompts, direct commands, and slash commands."""

    BINDINGS = [
        Binding("ctrl+l", "clear_value", "清空输入", show=False),
        Binding("up", "history_up", "上一条", show=False),
        Binding("down", "history_down", "下一条", show=False),
        Binding("tab", "complete_value", "补全", show=False),
    ]

    def __init__(self) -> None:
        super().__init__(
            placeholder="自然语言提问，! 执行命令，> 生成命令，/ 打开页面",
            id="command-input",
        )
        self._history: list[str] = []
        self._history_index: int | None = None
        self._completion_options: list[str] = []
        self._completion_index = 0
        self._simulated_value = ""

    def push_history(self, value: str) -> None:
        value = value.strip()
        if not value:
            return
        if self._history and self._history[-1] == value:
            return
        self._history.append(value)
        self._history = self._history[-200:]
        self._history_index = None

    def set_completion_options(self, options: Iterable[str]) -> None:
        self._completion_options = [opt for opt in options if opt]
        self._completion_index = 0

    def action_clear_value(self) -> None:
        self.value = ""
        self._simulated_value = ""
        self._history_index = None
        self._completion_index = 0

    def action_history_up(self) -> None:
        if not self._history:
            return
        if self._history_index is None:
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self._set_value(self._history[self._history_index])

    def action_history_down(self) -> None:
        if not self._history:
            return
        if self._history_index is None:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._set_value(self._history[self._history_index])
        else:
            self._history_index = None
            self._set_value("")

    def action_complete_value(self) -> None:
        current = self.value.strip()
        if not current:
            return
        if not self._completion_options:
            self._completion_options = self._default_completion_options(current)
            self._completion_index = 0
        if not self._completion_options:
            return
        choice = self._completion_options[self._completion_index % len(self._completion_options)]
        self._completion_index += 1
        self._set_value(choice)

    def watch_value(self, value: str) -> None:
        self._simulated_value = value
        if not value.strip():
            self._completion_options = []
            self._completion_index = 0
            return
        self._completion_options = self._default_completion_options(value.strip())
        self._completion_index = 0

    def _set_value(self, value: str) -> None:
        self._simulated_value = value
        self.value = value
        if self.is_mounted:
            self.cursor_position = len(self.value)

    def _default_completion_options(self, current: str) -> list[str]:
        options: list[str] = []
        if current.startswith("/"):
            options.extend([
                "/help",
                "/chat",
                "/hosts",
                "/history",
                "/skills",
                "/incidents",
                "/config",
                "/quit",
                "/exit",
            ])
        else:
            options.extend(COMMON_COMMANDS)
            if sys.platform == "win32":
                options.extend(["dir", "ipconfig", "tasklist", "Get-ChildItem", "Get-Process"])
        return [opt for opt in options if opt.startswith(current)]
