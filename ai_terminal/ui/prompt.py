"""交互式输入 — prompt_toolkit 增强（跨平台）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import (
    WordCompleter,
    PathCompleter,
    NestedCompleter,
    Completer,
    Completion,
    merge_completers,
)
from prompt_toolkit.document import Document
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
    "/help", "/new", "/status", "/history", "/stats", "/config",
    "/incidents", "/hosts", "/skills", "/quit", "/exit",
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


class ContextCompleter(Completer):
    """上下文感知补全器 — 根据输入前缀智能切换补全策略。"""

    def __init__(
        self,
        slash_completer: Completer,
        command_completer: Completer,
        path_completer: Completer,
    ):
        self.slash_completer = slash_completer
        self.command_completer = command_completer
        self.path_completer = path_completer

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor.lstrip()

        # / 开头 → 斜杠命令补全
        if text.startswith("/"):
            yield from self.slash_completer.get_completions(document, complete_event)
            return

        # ! 开头 → 只补全命令（去掉 ! 前缀后匹配）
        if text.startswith("!"):
            # 创建一个去掉 ! 前缀的虚拟文档
            stripped = text[1:]
            virtual_doc = Document(
                text=stripped + document.text_after_cursor,
                cursor_position=document.cursor_position - 1,
            )
            for comp in self.command_completer.get_completions(virtual_doc, complete_event):
                yield Completion(
                    text=comp.text,
                    start_position=comp.start_position,
                    display=comp.display,
                    display_meta=comp.display_meta,
                    style=comp.style,
                )
            return

        # > 开头 → AI 混合模式，只补全路径
        if text.startswith(">"):
            yield from self.path_completer.get_completions(document, complete_event)
            return

        # 普通输入 → AI 对话模式，只补全路径
        yield from self.path_completer.get_completions(document, complete_event)


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

        # 分层补全器
        slash_completer = WordCompleter(
            SLASH_COMMANDS,
            ignore_case=True,
            sentence=True,  # 支持多词输入
        )
        command_completer = WordCompleter(
            _get_common_commands(),
            ignore_case=True,
            sentence=True,
        )
        path_completer = PathCompleter(
            expanduser=True,
        )

        self._completer = ContextCompleter(
            slash_completer=slash_completer,
            command_completer=command_completer,
            path_completer=path_completer,
        )

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
                complete_while_typing=True,  # 输入时实时补全
                complete_in_thread=True,  # 补全在后台线程，不阻塞输入
                reserve_space_for_menu=4,  # 底部预留 4 行显示下拉菜单
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
            "ai": ("❯ ", "bold cyan"),
            "direct": ("$ ", "bold green"),
            "hybrid": ("> ", "bold yellow"),
        }
        prompt_text, style_name = mode_styles.get(mode, ("❯ ", "bold cyan"))

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
