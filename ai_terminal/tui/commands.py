"""Slash command routing for the TUI."""

from __future__ import annotations

TAB_ROUTES = {
    "/chat": "chat",
    "/hosts": "hosts",
    "/history": "history",
    "/skills": "skills",
    "/incidents": "incidents",
    "/config": "config",
    "/status": "config",
}

QUIT_COMMANDS = {"/quit", "/exit", "/q"}
HELP_COMMANDS = {"/help", "/?"}


def normalize_slash_command(text: str) -> str:
    return text.lower().strip()
