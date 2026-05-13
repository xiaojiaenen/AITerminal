"""Command palette for quick navigation and selection."""

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static


@dataclass(slots=True)
class PaletteEntry:
    kind: str
    title: str
    detail: str = ""
    value: str = ""

    def matches(self, query: str) -> bool:
        q = query.lower().strip()
        if not q:
            return True
        haystack = " ".join([self.kind, self.title, self.detail, self.value]).lower()
        return q in haystack


class CommandPalette(ModalScreen[PaletteEntry | None]):
    """Searchable quick selector for pages, actions, skills, hosts, and history."""

    BINDINGS = [Binding("escape", "cancel", "取消")]

    def __init__(self, entries: list[PaletteEntry]):
        super().__init__()
        self.entries = entries
        self.filtered: list[PaletteEntry] = entries[:]

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-dialog"):
            yield Static("命令面板", id="palette-title")
            yield Input(placeholder="搜索页面、动作、主机、技能、历史...", id="palette-input")
            yield ListView(id="palette-list")

    def on_mount(self) -> None:
        self.query_one("#palette-input", Input).focus()
        self._refresh_list("")

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Input.Changed, "#palette-input")
    def on_palette_input_changed(self, event: Input.Changed) -> None:
        self._refresh_list(event.value)

    @on(Input.Submitted, "#palette-input")
    def on_palette_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(self.filtered[0] if self.filtered else None)

    @on(ListView.Selected, "#palette-list")
    def on_palette_selected(self, event: ListView.Selected) -> None:
        event.stop()
        if event.index is None or event.index >= len(self.filtered):
            self.dismiss(None)
            return
        self.dismiss(self.filtered[event.index])

    def _refresh_list(self, query: str) -> None:
        self.filtered = [entry for entry in self.entries if entry.matches(query)]
        list_view = self.query_one("#palette-list", ListView)
        list_view.clear()
        if not self.filtered:
            list_view.append(ListItem(Label("没有匹配项")))
            return
        for entry in self.filtered:
            label = f"[{entry.kind.upper()}] {entry.title}"
            if entry.detail:
                label = f"{label}\n{entry.detail}"
            list_view.append(ListItem(Label(label)))
