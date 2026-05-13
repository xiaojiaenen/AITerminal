"""Risk approval modal."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from ai_terminal.services.terminal_service import CommandDecision


class RiskModal(ModalScreen[str]):
    """Ask the user to approve, edit, or replace a risky command."""

    BINDINGS = [
        Binding("y", "approve", "执行"),
        Binding("a", "alternative", "替代"),
        Binding("e", "edit", "编辑"),
        Binding("n,escape", "cancel", "取消"),
    ]

    def __init__(self, decision: CommandDecision):
        super().__init__()
        self.decision = decision

    def compose(self) -> ComposeResult:
        risk = self.decision.risk_level.value.upper()
        yield Container(
            Static(f"需要确认: {risk}", id="risk-title"),
            Static(self.decision.command, id="risk-command"),
            Static(self.decision.reason, id="risk-reason"),
            Static(self.decision.alternative or "暂无替代方案", id="risk-alt"),
            Static(self.decision.rollback_command or "暂无回滚命令", id="risk-rollback"),
            Horizontal(
                Button("执行", id="approve", variant="error"),
                Button(
                    "替代方案",
                    id="alternative",
                    variant="warning",
                    disabled=not self.decision.alternative,
                ),
                Button("编辑", id="edit", variant="primary"),
                Button("取消", id="cancel"),
                id="risk-actions",
            ),
            id="risk-dialog",
        )

    def action_approve(self) -> None:
        self.dismiss("approve")

    def action_alternative(self) -> None:
        self.dismiss("alternative")

    def action_edit(self) -> None:
        self.dismiss("edit")

    def action_cancel(self) -> None:
        self.dismiss("cancel")

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(str(event.button.id))
