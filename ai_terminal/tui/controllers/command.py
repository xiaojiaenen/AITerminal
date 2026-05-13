"""Command execution workflow controller."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from rich.syntax import Syntax
from textual.widgets import RichLog

from ai_terminal.services.terminal_service import CommandDecision, TerminalService
from ai_terminal.tui.formatters import task_event_markup
from ai_terminal.tui.tasks import TaskEvent, TaskStatus


class CommandController:
    """Run direct commands and generated commands."""

    def __init__(
        self,
        service: TerminalService,
        command_log: RichLog,
        set_status: Callable[[str], None],
        refresh_data: Callable[[], None],
        confirm_command: Callable[[CommandDecision], Awaitable[str | None]],
        on_event: Callable[[TaskEvent], None] | None = None,
    ):
        self.service = service
        self.command_log = command_log
        self.set_status = set_status
        self.refresh_data = refresh_data
        self.confirm_command = confirm_command
        self.on_event = on_event or (lambda _event: None)

    async def run_direct(self, command: str) -> None:
        await self.maybe_execute(command)

    async def run_hybrid(self, description: str) -> None:
        self.command_log.write(f"[bold yellow]生成命令[/bold yellow] {description}")
        self.set_status("正在生成命令...")
        try:
            commands = await self.service.generate_commands(description)
            if not commands:
                self.command_log.write("[red]没有生成可执行命令。[/red]")
                return
            for command in commands:
                self.command_log.write(f"[cyan]$ {command}[/cyan]")
                await self.maybe_execute(command)
        except Exception as exc:
            self.command_log.write(f"[red]命令生成失败:[/red] {exc}")
        finally:
            self.set_status("就绪")

    async def maybe_execute(self, command: str) -> None:
        decision = self.service.decide(command)
        if not decision.allowed:
            self._write_event(TaskEvent(
                title="命令已阻止",
                status=TaskStatus.BLOCKED,
                command=command,
                detail=decision.reason,
            ))
            await self.service.execute(command)
            self.refresh_data()
            return

        confirmed = False
        if decision.require_confirmation:
            resolved = await self.confirm_command(decision)
            if resolved is None:
                self._write_event(TaskEvent(
                    title="命令已取消",
                    status=TaskStatus.CANCELLED,
                    command=command,
                ))
                return
            command = resolved
            confirmed = True

        await self.execute_now(command, confirmed=confirmed)

    async def execute_now(self, command: str, *, confirmed: bool = False) -> None:
        self._write_event(TaskEvent.command_started(command))
        self.set_status("命令执行中...")
        result = await self.service.execute(command, confirmed=confirmed)
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""

        if stdout:
            syntax = Syntax(stdout.rstrip(), "powershell", theme="monokai", word_wrap=True)
            self.command_log.write(syntax)
        if stderr:
            self.command_log.write(f"[red]{stderr.rstrip()}[/red]")

        self._write_event(TaskEvent.command_finished(command, result))
        self.refresh_data()
        self.set_status("就绪")

    def _write_event(self, event: TaskEvent) -> None:
        self.on_event(event)
        self.command_log.write(task_event_markup(event))
