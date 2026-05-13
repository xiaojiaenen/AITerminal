"""Chat workflow controller."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from rich.markup import escape
from rich.syntax import Syntax
from textual.containers import VerticalScroll
from textual.widgets import Markdown, RichLog, Static

from ai_terminal.services.terminal_service import (
    CommandDecision,
    TerminalService,
    extract_command_from_args,
    format_tool_output,
)
from ai_terminal.tui.formatters import task_event_markup
from ai_terminal.tui.tasks import TaskEvent, TaskStatus


class ChatController:
    """Stream AI events into the chat log and tool timeline."""

    def __init__(
        self,
        service: TerminalService,
        chat_log: VerticalScroll,
        tool_log: RichLog,
        set_status: Callable[[str], None],
        on_event: Callable[[TaskEvent], None] | None = None,
        confirm_command: Callable[[CommandDecision], Any] | None = None,
        markdown_factory: Callable[[str, str], Any] | None = None,
        scroll_to_end: Callable[[], None] | None = None,
        refresh_data: Callable[[], None] | None = None,
    ):
        self.service = service
        self.chat_log = chat_log
        self.tool_log = tool_log
        self.set_status = set_status
        self.confirm_command = confirm_command
        self.on_event = on_event or (lambda _event: None)
        self.markdown_factory = markdown_factory or self._default_markdown_factory
        self.scroll_to_end = scroll_to_end or (lambda: None)
        self.refresh_data = refresh_data or (lambda: None)

    async def run(self, text: str) -> None:
        user_message = f"[bold cyan]你[/bold cyan] {escape(text)}"
        self.chat_log.mount(Static(user_message, classes="chat-user"))
        assistant_md = self.markdown_factory("", "chat-assistant")
        self.chat_log.mount(assistant_md)
        self.scroll_to_end()
        self.set_status("AI 正在思考...")

        answer = ""
        try:
            async for event in self.service.chat_stream(text):
                event_type = event["type"]
                if event_type == "text":
                    answer += event["data"]
                    assistant_md.update(answer)
                    self.scroll_to_end()
                elif event_type == "tool_start":
                    tool_name = event["data"].get("tool_name", "")
                    cmd = extract_command_from_args(tool_name, event["data"].get("args", ""))
                    self._write_tool_event(TaskEvent.tool_started(tool_name, cmd))
                    self.scroll_to_end()
                elif event_type == "tool_end":
                    tool_name = event["data"].get("tool_name", "")
                    raw_output = event["data"].get("output", "")
                    output = format_tool_output(tool_name, raw_output)
                    self._write_tool_event(TaskEvent.tool_finished(tool_name, output))
                    if tool_name == "check_safety":
                        cancelled = await self._handle_safety_confirmation(raw_output, assistant_md)
                        if cancelled:
                            break
                    self.scroll_to_end()

        except Exception as exc:
            assistant_md.update(f"**AI 调用失败:** `{escape(str(exc))}`")
            self.scroll_to_end()
        finally:
            self.set_status("就绪")

    def _write_tool_event(self, event: TaskEvent) -> None:
        self.on_event(event)
        self.tool_log.write(task_event_markup(event))

    def _default_markdown_factory(self, text: str, classes: str) -> Markdown:
        return Markdown(text, classes=classes)

    async def _handle_safety_confirmation(
        self,
        raw_output: str | dict[str, Any],
        assistant_md: Any,
    ) -> bool:
        if self.confirm_command is None:
            return False

        try:
            payload = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
        except (json.JSONDecodeError, TypeError):
            return False

        if not isinstance(payload, dict) or not payload.get("require_confirmation"):
            return False

        command = str(payload.get("command", "")).strip()
        if not command:
            return False

        decision = CommandDecision(
            command=command,
            allowed=bool(payload.get("allowed", True)),
            risk_level=self.service.policy.classify(command),
            reason=str(payload.get("reason", "")),
            require_confirmation=True,
            alternative=payload.get("alternative"),
            rollback_command=payload.get("rollback_command"),
        )
        resolved = await self.confirm_command(decision)
        if resolved is None:
            self._write_tool_event(TaskEvent(
                title="命令已取消",
                status=TaskStatus.CANCELLED,
                command=command,
            ))
            assistant_md.update(
                f"**已取消，未执行。**\n\n命令 `{escape(command)}` 没有运行。"
            )
            self.scroll_to_end()
            return True

        self._write_tool_event(TaskEvent.command_started(resolved))
        self.set_status("命令执行中...")
        result = await self.service.execute(resolved, confirmed=True)
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""

        if stdout:
            syntax = Syntax(stdout.rstrip(), "powershell", theme="monokai", word_wrap=True)
            self.tool_log.write(syntax)
        if stderr:
            self.tool_log.write(f"[red]{stderr.rstrip()}[/red]")

        self._write_tool_event(TaskEvent.command_finished(resolved, result))
        self.refresh_data()
        return False
