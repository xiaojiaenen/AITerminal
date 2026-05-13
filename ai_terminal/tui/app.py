"""Textual full-screen interface for AI Terminal."""

from __future__ import annotations

import argparse

from rich.syntax import Syntax
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Markdown,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from ai_terminal.config import Config
from ai_terminal.services.terminal_service import CommandDecision, TerminalService, detect_mode
from ai_terminal.tui.commands import (
    HELP_COMMANDS,
    QUIT_COMMANDS,
    TAB_ROUTES,
    normalize_slash_command,
)
from ai_terminal.tui.controllers import ChatController, CommandController
from ai_terminal.tui.formatters import (
    config_rows,
    history_rows,
    host_rows,
    incident_rows,
    skill_rows,
)
from ai_terminal.tui.palette import CommandPalette, PaletteEntry
from ai_terminal.tui.tasks import TaskEvent
from ai_terminal.tui.widgets import CommandInput, RiskModal


class AITerminalTUI(App):
    """Full-screen AI Terminal workbench."""

    CSS_PATH = "theme.tcss"
    TITLE = "AI Terminal"
    SUB_TITLE = "智能终端工作台"

    BINDINGS = [
        Binding("ctrl+p", "open_palette", "命令面板"),
        Binding("ctrl+c", "quit", "退出", priority=True),
        Binding("ctrl+n", "new_session", "新会话"),
        Binding("ctrl+l", "clear_log", "清空"),
        Binding("f1", "show_help", "帮助"),
        Binding("f5", "refresh_current", "刷新"),
        Binding("ctrl+h", "focus_tab('history')", "历史"),
        Binding("ctrl+k", "focus_tab('hosts')", "主机"),
        Binding("ctrl+s", "focus_tab('skills')", "技能"),
    ]

    def __init__(self, service: TerminalService | None = None):
        super().__init__()
        self.service = service or TerminalService()
        self._history_entries: list[dict] = []
        self._task_events: list[TaskEvent] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="app-shell"):
            yield Static("", id="context-line")
            with TabbedContent(id="tabs"):
                with TabPane("Chat", id="chat"), Horizontal(classes="split-pane"):
                    yield VerticalScroll(id="chat-log")
                    yield RichLog(id="tool-timeline", wrap=True, markup=True, highlight=True)
                with TabPane("Hosts", id="hosts"):
                    yield DataTable(id="hosts-table")
                with TabPane("History", id="history"), Horizontal(classes="split-pane"):
                    yield DataTable(id="history-table")
                    yield RichLog(id="history-detail", wrap=True, markup=True, highlight=True)
                with TabPane("Skills", id="skills"), Horizontal(classes="split-pane"):
                    yield DataTable(id="skills-table")
                    yield RichLog(id="skill-detail", wrap=True, markup=True)
                with TabPane("Incidents", id="incidents"):
                    yield DataTable(id="incidents-table")
                with TabPane("Config", id="config"):
                    yield DataTable(id="config-table")
            yield CommandInput()
        yield Static("", id="status-line")
        yield Footer()

    async def on_mount(self) -> None:
        self._setup_tables()
        self._welcome()
        self.refresh_data()
        self.query_one(CommandInput).focus()

    async def on_unmount(self) -> None:
        await self.service.close()

    def _setup_tables(self) -> None:
        hosts = self.query_one("#hosts-table", DataTable)
        hosts.add_columns("名称", "地址", "端口", "用户", "标签")

        history = self.query_one("#history-table", DataTable)
        history.add_columns("时间", "状态", "风险", "命令", "耗时")

        skills = self.query_one("#skills-table", DataTable)
        skills.add_columns("技能", "脚本", "描述")

        incidents = self.query_one("#incidents-table", DataTable)
        incidents.add_columns("时间", "状态", "根因", "命令")

        config = self.query_one("#config-table", DataTable)
        config.add_columns("分组", "键", "值", "状态")

    def _welcome(self) -> None:
        log = self.query_one("#chat-log", VerticalScroll)
        log.mount(Markdown("# AI Terminal\n\n直接输入需求，或使用 `!git status` 执行命令。"))
        log.mount(Markdown("`Ctrl+H` 历史  `Ctrl+K` 主机  `Ctrl+S` 技能  `F1` 帮助"))
        self._set_status("就绪")

    def _set_status(self, message: str) -> None:
        ctx = self.service.context_info()
        safe = "on" if self.service.config.get("safety.enabled", True) else "off"
        model = self.service.config.get("llm.model", "-")
        self._update_base_static(
            "#status-line",
            f" {message}   safe:{safe}   model:{model}   rounds:{ctx.get('rounds', 0)}",
        )
        self._update_base_static(
            "#context-line",
            f"local  |  safe:{safe}  |  model:{model}  |  messages:{ctx.get('messages', 0)}",
        )

    def _update_base_static(self, selector: str, message: str) -> None:
        """Update status widgets on the base screen even when a modal is active."""
        try:
            base_screen = self.screen_stack[0]
            base_screen.query_one(selector, Static).update(message)
        except (IndexError, NoMatches):
            pass

    def action_focus_tab(self, tab_id: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab_id
        self.refresh_data()
        self.query_one(CommandInput).focus()

    def action_new_session(self) -> None:
        self.service.clear_session()
        self.query_one("#chat-log", VerticalScroll).remove_children()
        self._welcome()

    def action_clear_log(self) -> None:
        active = self.query_one("#tabs", TabbedContent).active
        if active == "chat":
            self.query_one("#chat-log", VerticalScroll).remove_children()
            self.query_one("#tool-timeline", RichLog).clear()

    def action_show_help(self) -> None:
        log = self.query_one("#chat-log", VerticalScroll)
        self.action_focus_tab("chat")
        log.mount(Markdown(
            "## 快捷键\n\n"
            "- `Ctrl+N` 新会话\n"
            "- `Ctrl+L` 清空当前日志\n"
            "- `Ctrl+H` 历史\n"
            "- `Ctrl+K` 主机\n"
            "- `Ctrl+S` 技能\n"
            "- `F5` 刷新\n\n"
            "## 输入\n\n"
            "- 普通文本: AI 对话\n"
            "- `!命令`: 直接执行\n"
            "- `>描述`: 生成命令并确认\n"
            "- `/hosts` `/history` `/skills` `/config`: 切换页面"
        ))

    def action_refresh_current(self) -> None:
        self.refresh_data()

    async def action_open_palette(self) -> None:
        entry = await self.push_screen_wait(CommandPalette(self._palette_entries()))
        if entry is None:
            self.query_one(CommandInput).focus()
            return
        await self._run_palette_entry(entry)

    def _palette_entries(self) -> list[PaletteEntry]:
        entries = [
            PaletteEntry("page", "Chat", "回到对话页面", "tab:chat"),
            PaletteEntry("page", "Hosts", "查看主机清单", "tab:hosts"),
            PaletteEntry("page", "History", "查看执行历史", "tab:history"),
            PaletteEntry("page", "Skills", "查看 wuwei 技能", "tab:skills"),
            PaletteEntry("page", "Incidents", "查看失败经验", "tab:incidents"),
            PaletteEntry("page", "Config", "查看只读配置", "tab:config"),
            PaletteEntry("action", "New Session", "清空当前对话上下文", "action:new"),
            PaletteEntry("action", "Clear Current Log", "清空当前日志视图", "action:clear"),
            PaletteEntry("action", "Refresh", "刷新当前数据", "action:refresh"),
        ]
        hosts, _groups = self.service.hosts()
        for host in hosts:
            name = host.get("name", "")
            detail = f"{host.get('user', 'root')}@{host.get('hostname', '')}:{host.get('port', 22)}"
            entries.append(PaletteEntry("host", name, detail, f"host:{name}"))
        for skill in self.service.skills():
            name = skill.get("name", "")
            entries.append(
                PaletteEntry("skill", name, skill.get("description", ""), f"skill:{name}")
            )
        for item in reversed(self.service.audit_entries(20)):
            command = item.get("command", "")
            if command:
                entries.append(PaletteEntry("history", command[:80], "填入历史命令", f"!{command}"))
        return entries

    async def _run_palette_entry(self, entry: PaletteEntry) -> None:
        command_input = self.query_one(CommandInput)
        if entry.value.startswith("tab:"):
            self.action_focus_tab(entry.value.split(":", 1)[1])
        elif entry.value == "action:new":
            self.action_new_session()
        elif entry.value == "action:clear":
            self.action_clear_log()
        elif entry.value == "action:refresh":
            self.action_refresh_current()
        elif entry.value.startswith("host:"):
            command_input.value = f"连接主机 {entry.title}，查看状态"
        elif entry.value.startswith("skill:"):
            command_input.value = f"使用技能 {entry.title} 帮我处理："
        elif entry.value:
            command_input.value = entry.value
        command_input.focus()
        if command_input.value:
            command_input.cursor_position = len(command_input.value)

    @on(Input.Submitted, "#command-input")
    async def on_command_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        text = event.value.strip()
        command_input = self.query_one(CommandInput)
        command_input.value = ""
        if not text:
            return
        command_input.push_history(text)
        command_input.set_completion_options([])
        if text.startswith("/"):
            await self._handle_slash(text)
            return

        mode, content = detect_mode(text)
        if not content:
            return
        if mode == "direct":
            self.run_command_flow(content)
        elif mode == "hybrid":
            self.run_hybrid_flow(content)
        else:
            self.run_chat_flow(content)

    async def _handle_slash(self, text: str) -> None:
        command = normalize_slash_command(text)
        if command in QUIT_COMMANDS:
            self.exit()
            return
        if command == "/new":
            self.action_new_session()
            return
        if command in HELP_COMMANDS:
            self.action_show_help()
            return
        if command in TAB_ROUTES:
            self.action_focus_tab(TAB_ROUTES[command])
            return
        self.query_one("#chat-log", VerticalScroll).mount(Markdown(f"**未知命令:** `{text}`"))

    @work(exclusive=False)
    async def run_chat_flow(self, text: str) -> None:
        self.action_focus_tab("chat")
        controller = ChatController(
            service=self.service,
            chat_log=self.query_one("#chat-log", VerticalScroll),
            tool_log=self.query_one("#tool-timeline", RichLog),
            set_status=self._set_status,
            confirm_command=self._confirm_command,
            on_event=self._record_task_event,
            scroll_to_end=self._scroll_chat_end,
            refresh_data=self.refresh_data,
        )
        await controller.run(text)

    def _scroll_chat_end(self) -> None:
        self.query_one("#chat-log", VerticalScroll).scroll_end(animate=False, force=True)

    @work(exclusive=False)
    async def run_hybrid_flow(self, description: str) -> None:
        await self._command_controller().run_hybrid(description)

    @work(exclusive=False)
    async def run_command_flow(self, command: str) -> None:
        await self._command_controller().run_direct(command)

    def _command_controller(self) -> CommandController:
        return CommandController(
            service=self.service,
            command_log=self.query_one("#tool-timeline", RichLog),
            set_status=self._set_status,
            refresh_data=self.refresh_data,
            confirm_command=self._confirm_command,
            on_event=self._record_task_event,
        )

    def _record_task_event(self, event: TaskEvent) -> None:
        self._task_events.append(event)
        self._task_events = self._task_events[-200:]

    async def _confirm_command(self, decision: CommandDecision) -> str | None:
        result = await self.push_screen_wait(RiskModal(decision))
        if result == "cancel" or result is None:
            return None
        if result == "edit":
            self.query_one(CommandInput).value = f"!{decision.command}"
            self.query_one(CommandInput).focus()
            return None
        if result == "alternative" and decision.alternative:
            return decision.alternative.split("#", 1)[0].strip()
        return decision.command

    def refresh_data(self) -> None:
        self._refresh_hosts()
        self._refresh_history()
        self._refresh_skills()
        self._refresh_incidents()
        self._refresh_config()

    def _refresh_hosts(self) -> None:
        table = self.query_one("#hosts-table", DataTable)
        table.clear()
        hosts, _groups = self.service.hosts()
        for row in host_rows(hosts):
            table.add_row(*row)

    def _refresh_history(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.clear()
        self._history_entries = list(reversed(self.service.audit_entries(100)))
        for row in history_rows(list(reversed(self._history_entries))):
            table.add_row(*row)
        detail = self.query_one("#history-detail", RichLog)
        detail.clear()
        detail.write("[dim]选择一条历史记录查看详情[/dim]")

    @on(DataTable.RowSelected, "#history-table")
    def on_history_selected(self, event: DataTable.RowSelected) -> None:
        if event.cursor_row is None or event.cursor_row >= len(self._history_entries):
            return
        entry = self._history_entries[event.cursor_row]
        detail = self.query_one("#history-detail", RichLog)
        detail.clear()
        detail.write(f"[bold]命令[/bold]\n[cyan]{entry.get('command', '')}[/cyan]")
        detail.write(f"[bold]时间[/bold] {entry.get('timestamp', '-')}")
        detail.write(f"[bold]风险[/bold] {entry.get('risk_level', '-')}")
        detail.write(f"[bold]动作[/bold] {entry.get('action', '-')}")
        detail.write(f"[bold]退出码[/bold] {entry.get('exit_code', '-')}")
        detail.write(f"[bold]耗时[/bold] {entry.get('duration_ms', 0)}ms")
        output = entry.get("output") or ""
        stderr = entry.get("stderr") or ""
        if output:
            detail.write("[bold]输出[/bold]")
            detail.write(Syntax(output, "powershell", theme="monokai", word_wrap=True))
        if stderr:
            detail.write("[bold red]错误[/bold red]")
            detail.write(f"[red]{stderr}[/red]")

    def _refresh_skills(self) -> None:
        table = self.query_one("#skills-table", DataTable)
        table.clear()
        for row in skill_rows(self.service.skills()):
            table.add_row(*row)

    @on(DataTable.RowSelected, "#skills-table")
    def on_skill_selected(self, event: DataTable.RowSelected) -> None:
        row = event.data_table.get_row(event.row_key)
        if not row:
            return
        detail = self.service.skill_detail(str(row[0]))
        log = self.query_one("#skill-detail", RichLog)
        log.clear()
        if detail:
            log.write(Markdown(detail.get("instruction", "")))
            scripts = detail.get("scripts") or []
            if scripts:
                log.write("[bold]可执行命令[/bold]")
                for script in scripts:
                    log.write(f"[cyan]$ {script}[/cyan]")

    def _refresh_incidents(self) -> None:
        table = self.query_one("#incidents-table", DataTable)
        table.clear()
        for row in incident_rows(self.service.incident_entries(100)):
            table.add_row(*row)

    def _refresh_config(self) -> None:
        table = self.query_one("#config-table", DataTable)
        table.clear()
        for row in config_rows(self.service.config_view()):
            table.add_row(*row)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AI Terminal TUI")
    parser.add_argument("-c", "--config", help="配置文件路径")
    args = parser.parse_args(argv)
    config = Config(args.config) if args.config else Config()
    AITerminalTUI(TerminalService(config)).run()


if __name__ == "__main__":
    main()
