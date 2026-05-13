"""交互式输入 — prompt_toolkit 增强。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, PathCompleter, merge_completers
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style

try:
    from pygments.lexers import BashLexer
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


# 自定义样式
TERMINAL_STYLE = Style.from_dict({
    "prompt": "bold cyan",
    "command": "bold green",
    "mode-ai": "bold white",
    "mode-direct": "bold green",
    "mode-hybrid": "bold yellow",
})

# 快捷命令补全
SLASH_COMMANDS = [
    "/help", "/status", "/history", "/stats", "/config",
    "/incidents", "/hosts", "/quit", "/exit",
]

# 常用命令补全
COMMON_COMMANDS = [
    "ls", "cd", "pwd", "mkdir", "rm", "cp", "mv", "cat", "head", "tail",
    "grep", "find", "chmod", "chown", "ps", "top", "kill", "df", "du",
    "free", "uptime", "whoami", "hostname", "uname", "ping", "curl", "wget",
    "git status", "git log", "git diff", "git add", "git commit", "git push",
    "git pull", "git branch", "git checkout", "git merge", "git stash",
    "docker ps", "docker images", "docker logs", "docker exec", "docker run",
    "docker stop", "docker rm", "docker build", "docker compose up",
    "docker compose down", "docker compose logs",
    "systemctl status", "systemctl start", "systemctl stop", "systemctl restart",
    "journalctl", "apt install", "apt update", "apt upgrade",
    "pip install", "pip list", "npm install", "npm run",
]


class TerminalPrompt:
    """交互式终端输入。"""

    def __init__(self, history_file: str = "~/.ai-terminal/history"):
        self._history_path = Path(history_file).expanduser()
        self._history_path.parent.mkdir(parents=True, exist_ok=True)

        # 补全器
        slash_completer = WordCompleter(SLASH_COMMANDS, ignore_case=True)
        command_completer = WordCompleter(COMMON_COMMANDS, ignore_case=True)
        path_completer = PathCompleter()

        self._completer = merge_completers([
            slash_completer,
            command_completer,
            path_completer,
        ])

        # 会话
        self._session: PromptSession | None = None

    def _get_session(self) -> PromptSession:
        """获取或创建 prompt_toolkit 会话。"""
        if self._session is None:
            history = FileHistory(str(self._history_path))
            self._session = PromptSession(
                history=history,
                auto_suggest=AutoSuggestFromHistory(),
                completer=self._completer,
                style=TERMINAL_STYLE,
            )
        return self._session

    def get_input(self, mode: str = "ai") -> str | None:
        """获取用户输入。

        Args:
            mode: 当前输入模式 ("ai", "direct", "hybrid")

        Returns:
            用户输入字符串，或 None（Ctrl+C/Ctrl+D）
        """
        mode_styles = {
            "ai": ("❯ ", "prompt"),
            "direct": ("$ ", "command"),
            "hybrid": ("🤖 ", "mode-hybrid"),
        }
        prompt_text, style_name = mode_styles.get(mode, ("❯ ", "prompt"))

        try:
            session = self._get_session()
            return session.prompt(
                [(style_name, prompt_text)],
                lexer=PygmentsLexer(BashLexer) if HAS_PYGMENTS else None,
            )
        except (EOFError, KeyboardInterrupt):
            return None


# 全局实例
_prompt: TerminalPrompt | None = None


def get_prompt() -> TerminalPrompt:
    """获取全局 TerminalPrompt 实例。"""
    global _prompt
    if _prompt is None:
        _prompt = TerminalPrompt()
    return _prompt
