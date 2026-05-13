"""交互式输入 — prompt_toolkit 增强（跨平台）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, PathCompleter, merge_completers
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style

try:
    from prompt_toolkit.lexers import PygmentsLexer
    HAS_LEXER = True
except ImportError:
    HAS_LEXER = False

try:
    from pygments.lexers import BashLexer, BatchLexer, PowerShellLexer
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


def _is_windows() -> bool:
    return sys.platform == "win32"


# 自定义样式
TERMINAL_STYLE = Style.from_dict({
    "prompt": "bold cyan",
    "command": "bold green",
    "mode-ai": "bold white",
    "mode-direct": "bold green",
    "mode-hybrid": "bold yellow",
})

# 快捷命令补全（跨平台通用）
SLASH_COMMANDS = [
    "/help", "/status", "/history", "/stats", "/config",
    "/incidents", "/hosts", "/quit", "/exit",
]

# Linux/macOS 常用命令
_UNIX_COMMANDS = [
    "ls", "ls -la", "ls -lh", "cd", "pwd", "mkdir", "rm", "cp", "mv",
    "cat", "head", "tail", "less", "more", "grep", "find", "wc",
    "chmod", "chown", "ps", "top", "kill", "df", "du", "free",
    "uptime", "whoami", "hostname", "uname", "ping", "curl", "wget",
    "tar", "unzip", "ssh", "scp", "rsync",
    "git status", "git log", "git diff", "git add .", "git commit -m",
    "git push", "git pull", "git branch", "git checkout", "git merge",
    "git stash", "git stash pop", "git reset --hard",
    "docker ps", "docker ps -a", "docker images", "docker logs",
    "docker exec -it", "docker run", "docker stop", "docker rm",
    "docker build", "docker compose up", "docker compose down",
    "docker compose up -d", "docker compose logs",
    "systemctl status", "systemctl start", "systemctl stop",
    "systemctl restart", "systemctl enable", "systemctl disable",
    "journalctl -u", "journalctl -f",
    "apt install", "apt update", "apt upgrade", "apt remove",
    "yum install", "yum update", "yum remove",
    "brew install", "brew update", "brew upgrade",
    "pip install", "pip list", "pip freeze",
    "npm install", "npm run", "npm start", "npm test",
    "vim", "nano", "htop", "tmux", "screen",
]

# Windows 常用命令
_WINDOWS_COMMANDS = [
    "dir", "dir /w", "dir /a", "cd", "cd ..", "cls", "type",
    "copy", "move", "ren", "del", "rd", "mkdir", "rmdir",
    "echo", "set", "path", "where", "whoami", "hostname",
    "ipconfig", "ipconfig /all", "ping", "tracert", "nslookup",
    "netstat -an", "tasklist", "taskkill", "systeminfo",
    "net user", "net localgroup", "net share", "net use",
    "sc query", "sc start", "sc stop",
    "reg query", "reg add", "reg delete",
    "schtasks", "chkdsk", "defrag",
    # PowerShell 命令
    "Get-Process", "Get-Service", "Get-ChildItem", "Get-Content",
    "Get-Location", "Get-Date", "Get-Host", "Get-Help",
    "Get-Command", "Get-Alias", "Get-EventLog",
    "Get-WmiObject", "Get-CimInstance",
    "Select-Object", "Where-Object", "Format-Table", "Format-List",
    "Measure-Object", "Test-Path", "Resolve-Path",
    "New-Item", "Copy-Item", "Move-Item", "Rename-Item", "Remove-Item",
    "Set-Content", "Add-Content", "Clear-Content",
    "Start-Service", "Stop-Service", "Restart-Service",
    "Start-Process", "Stop-Process",
    "Invoke-WebRequest", "Invoke-RestMethod",
    "Install-Package", "Set-Location", "Out-File",
    # 跨平台通用
    "git status", "git log", "git diff", "git add .", "git commit -m",
    "git push", "git pull", "git branch", "git checkout", "git merge",
    "git stash", "git stash pop",
    "docker ps", "docker ps -a", "docker images", "docker logs",
    "docker exec -it", "docker run", "docker stop", "docker rm",
    "docker build", "docker compose up", "docker compose down",
    "pip install", "pip list", "pip freeze",
    "npm install", "npm run", "npm start", "npm test",
]


def _get_lexer():
    """根据平台返回合适的语法高亮 lexer。"""
    if not HAS_LEXER or not HAS_PYGMENTS:
        return None

    if _is_windows():
        return PygmentsLexer(PowerShellLexer)
    else:
        return PygmentsLexer(BashLexer)


def _get_common_commands() -> list[str]:
    """根据平台返回常用命令列表。"""
    if _is_windows():
        return _WINDOWS_COMMANDS
    else:
        return _UNIX_COMMANDS


class TerminalPrompt:
    """交互式终端输入（跨平台）。"""

    def __init__(self, history_file: str = "~/.ai-terminal/history"):
        self._history_path = Path(history_file).expanduser()
        self._history_path.parent.mkdir(parents=True, exist_ok=True)

        # 补全器
        slash_completer = WordCompleter(SLASH_COMMANDS, ignore_case=True)
        command_completer = WordCompleter(_get_common_commands(), ignore_case=True)
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

    async def get_input(self, mode: str = "ai") -> str | None:
        """获取用户输入（异步）。

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
            return await session.prompt_async(
                [(style_name, prompt_text)],
                lexer=_get_lexer(),
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
