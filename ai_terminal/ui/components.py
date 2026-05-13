"""Rich UI 组件 — 美化终端输出（跨平台）。"""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone as _timezone
from pathlib import Path
from typing import Any

# Windows 下强制 UTF-8，避免 Rich emoji 输出报错
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.syntax import Syntax
from rich.columns import Columns
from rich.markdown import Markdown
from rich.tree import Tree
from rich.markup import escape
from rich.rule import Rule
from rich.align import Align
from rich.layout import Layout
from rich import box
from rich.live import Live
from rich.spinner import Spinner

from ai_terminal.safety.policy import RiskLevel


def _is_windows() -> bool:
    return sys.platform == "win32"


def _supports_emoji() -> bool:
    if _is_windows():
        wt_session = __import__("os").environ.get("WT_SESSION")
        ps_version = __import__("os").environ.get("PSModulePath")
        return bool(wt_session or ps_version)
    return True


# 图标
_EMOJI_OK = "✓" if not _supports_emoji() else "✅"
_EMOJI_FAIL = "✗" if not _supports_emoji() else "❌"
_EMOJI_WARN = "!" if not _supports_emoji() else "⚠️"
_EMOJI_CRIT = "!!" if not _supports_emoji() else "🚨"
_EMOJI_INFO = "i" if not _supports_emoji() else "ℹ️"
_EMOJI_ROBOT = "(AI)" if not _supports_emoji() else "🤖"
_EMOJI_LIGHT = "*" if not _supports_emoji() else "💡"
_EMOJI_SYNC = "~" if not _supports_emoji() else "🔄"
_EMOJI_WRENCH = "#" if not _supports_emoji() else "🔧"
_EMOJI_CHART = "=" if not _supports_emoji() else "📊"
_EMOJI_GLOBE = "@" if not _supports_emoji() else "🌐"
_EMOJI_BYE = "bye" if not _supports_emoji() else "👋"
_EMOJI_GEAR = "(cfg)" if not _supports_emoji() else "⚙️"
_EMOJI_SHIELD = "(safe)" if not _supports_emoji() else "🛡️"
_EMOJI_CLOCK = "t" if not _supports_emoji() else "⏱"
_EMOJI_BOLT = ">" if not _supports_emoji() else "⚡"
_EMOJI_STAR = "*" if not _supports_emoji() else "⭐"
_EMOJI_BOOK = "(doc)" if not _supports_emoji() else "📖"
_EMOJI_TARGET = "(>>)" if not _supports_emoji() else "🎯"
_EMOJI_SEARCH = "(?)" if not _supports_emoji() else "🔍"

console = Console()

# 统一配色
C_PRIMARY = "cyan"
C_SUCCESS = "green"
C_DANGER = "red"
C_WARNING = "yellow"
C_MUTED = "dim"
C_ACCENT = "bright_cyan"
C_HIGHLIGHT = "bold white"


def _to_local_time(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is not None:
            dt = dt.astimezone(None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ts


def _get_system_info() -> dict[str, str]:
    info: dict[str, str] = {}
    info["os"] = f"{platform.system()} {platform.release()}"
    info["arch"] = platform.machine()
    info["python"] = platform.python_version()
    info["hostname"] = platform.node()
    info["shell"] = "PowerShell" if _is_windows() else os.environ.get("SHELL", "bash")
    info["cwd"] = os.getcwd()
    return info


def _get_git_branch() -> str | None:
    """获取当前 git 分支名。"""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=2
        )
        branch = result.stdout.strip()
        return branch if branch else None
    except Exception:
        return None


def _format_duration(ms: int) -> str:
    """格式化耗时。"""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        return f"{ms / 60000:.1f}m"


# ═══════════════════════════════════════════════════════════════
# Banner / 启动画面
# ═══════════════════════════════════════════════════════════════

def print_banner() -> None:
    """打印启动横幅。"""
    info = _get_system_info()

    # Logo
    logo = Text()
    logo.append("   ╭─", style=f"bold {C_PRIMARY}")
    logo.append(" AI Terminal ", style=f"bold {C_HIGHLIGHT}")
    logo.append("─────────────────────╮\n", style=f"bold {C_PRIMARY}")
    logo.append("   │ ", style=f"bold {C_PRIMARY}")
    logo.append(f"{_EMOJI_ROBOT}  自然语言 → 安全执行 → 智能运维", style="")
    logo.append(" │\n", style=f"bold {C_PRIMARY}")
    logo.append("   ╰", style=f"bold {C_PRIMARY}")
    logo.append("──────────────────────────────────────────╯", style=f"bold {C_PRIMARY}")

    # 系统信息行
    info_line = Text()
    info_line.append(f"{_EMOJI_BOLT} ", style=C_WARNING)
    info_line.append(f"{info['hostname']}", style=f"bold {C_HIGHLIGHT}")
    info_line.append(f"  {_EMOJI_GEAR} ", style=C_MUTED)
    info_line.append(f"{info['os']}", style=C_ACCENT)
    info_line.append(f"  {_EMOJI_STAR} ", style=C_MUTED)
    info_line.append(f"Python {info['python']}", style=C_ACCENT)
    info_line.append(f"  📁 ", style=C_MUTED)
    info_line.append(f"{info['cwd']}", style=C_ACCENT)

    # 模式说明
    modes = Table(show_header=False, box=None, padding=(0, 2))
    modes.add_column("k", style=f"bold {C_PRIMARY}", width=8)
    modes.add_column("d", style=C_MUTED, width=18)
    modes.add_column("e", style=C_ACCENT)
    modes.add_row(" 输入", "AI 对话", '"查看磁盘使用率"')
    modes.add_row(f" !命令", "直接执行", "!dir / !git status")
    modes.add_row(f" >描述", "混合模式", "> 清理临时文件")
    modes.add_row(f" /命令", "系统功能", "/help /status /skills")

    console.print()
    console.print(logo)
    console.print()
    console.print(Panel(info_line, border_style=C_MUTED, padding=(0, 2)))
    console.print()
    console.print(
        Panel(modes, title=f"{_EMOJI_TARGET} 输入模式", border_style=C_PRIMARY, padding=(1, 2))
    )
    console.print()


# ═══════════════════════════════════════════════════════════════
# 帮助
# ═══════════════════════════════════════════════════════════════

def print_help() -> None:
    """打印帮助信息。"""
    console.print()

    # 输入模式
    input_table = Table(
        title=f"{_EMOJI_TARGET} 输入模式",
        box=box.ROUNDED,
        show_header=True,
        header_style=f"bold {C_PRIMARY}",
    )
    input_table.add_column("前缀", style=f"bold {C_PRIMARY}", width=8)
    input_table.add_column("模式", width=12)
    input_table.add_column("说明")
    input_table.add_column("示例", style=C_ACCENT)
    input_table.add_row("无", "AI 对话", "自然语言描述需求，AI 生成命令并执行", '"列出大文件"')
    input_table.add_row("!", "直接执行", "跳过 AI，直接运行命令", "!dir")
    input_table.add_row(">", "混合模式", "AI 生成命令，确认后执行", "> 清理日志")
    console.print(input_table)

    # 快捷命令
    cmd_table = Table(
        title=f"{_EMOJI_WRENCH} 快捷命令",
        box=box.ROUNDED,
        show_header=True,
        header_style=f"bold {C_PRIMARY}",
    )
    cmd_table.add_column("命令", style=f"bold {C_PRIMARY}", width=14)
    cmd_table.add_column("功能")
    cmd_table.add_column("命令", style=f"bold {C_PRIMARY}", width=14)
    cmd_table.add_column("功能")
    cmds = [
        ("/help", "显示帮助"),
        ("/status", "系统状态"),
        ("/new", "新对话"),
        ("/history", "执行历史"),
        ("/stats", "审计统计"),
        ("/config", "当前配置"),
        ("/incidents", "经验记录"),
        ("/hosts", "主机清单"),
        ("/skills", "技能列表"),
        ("/skill <n>", "技能详情"),
        ("/quit", "退出"),
        ("Ctrl+C", "停止当前对话"),
    ]
    for i in range(0, len(cmds), 2):
        row = list(cmds[i]) + list(cmds[i + 1] if i + 1 < len(cmds) else ("", ""))
        cmd_table.add_row(*row)
    console.print(cmd_table)

    # 安全说明
    console.print()
    console.print(Panel(
        f"{_EMOJI_OK} 只读命令自动执行  ·  "
        f"{_EMOJI_WARN} 破坏性命令需确认  ·  "
        f"{_EMOJI_SYNC} 所有操作记录审计  ·  "
        f"{_EMOJI_LIGHT} 错误自动诊断",
        title=f"{_EMOJI_SHIELD} 安全策略",
        border_style=C_SUCCESS,
        padding=(1, 2),
    ))
    console.print()


# ═══════════════════════════════════════════════════════════════
# 风险警告
# ═══════════════════════════════════════════════════════════════

def print_risk_warning(
    risk_level: RiskLevel,
    reason: str,
    alternative: str | None = None,
    rollback: str | None = None,
) -> None:
    colors = {
        RiskLevel.SAFE: C_SUCCESS,
        RiskLevel.LOW: C_ACCENT,
        RiskLevel.HIGH: C_WARNING,
        RiskLevel.CRITICAL: C_DANGER,
    }
    icons = {
        RiskLevel.SAFE: _EMOJI_OK,
        RiskLevel.LOW: _EMOJI_INFO,
        RiskLevel.HIGH: _EMOJI_WARN,
        RiskLevel.CRITICAL: _EMOJI_CRIT,
    }
    labels = {
        RiskLevel.SAFE: "安全",
        RiskLevel.LOW: "低风险",
        RiskLevel.HIGH: "高风险",
        RiskLevel.CRITICAL: "危险",
    }

    color = colors.get(risk_level, "white")
    icon = icons.get(risk_level, "?")
    label = labels.get(risk_level, risk_level.value)

    content = Text()
    content.append(f"{icon}  {label}\n", style=f"bold {color}")
    content.append(f"{reason}\n", style=C_MUTED)
    if alternative:
        content.append(f"{_EMOJI_LIGHT} 建议: ", style=C_MUTED)
        content.append(f"{alternative}\n", style=C_SUCCESS)
    if rollback:
        content.append(f"{_EMOJI_SYNC} 回滚: ", style=C_MUTED)
        content.append(rollback, style=C_MUTED)

    border_color = C_DANGER if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else C_WARNING
    console.print()
    console.print(Panel(content, title="安全检查", border_style=border_color))


# ═══════════════════════════════════════════════════════════════
# 命令执行结果
# ═══════════════════════════════════════════════════════════════

def print_command_result(
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    duration_ms: int,
    host: str = "local",
) -> None:
    """打印命令执行结果 — 颜色编码面板。"""
    ok = exit_code == 0
    status_icon = _EMOJI_OK if ok else _EMOJI_FAIL
    status_text = "成功" if ok else "失败"
    border_color = C_SUCCESS if ok else C_DANGER
    title_style = f"bold {border_color}"

    # 标题：状态 + 命令 + 耗时
    host_label = f"[{host}] " if host != "local" else ""
    duration_str = _format_duration(duration_ms)
    title = f"{status_icon} {status_text}  {host_label}{_EMOJI_CLOCK} {duration_str}"

    # 构建内容
    content = Text()
    content.append(f"$ {command}\n\n", style=f"bold {C_PRIMARY}")

    if stdout:
        stripped = stdout.rstrip()
        line_count = stripped.count("\n") + 1
        if line_count <= 20:
            content.append(stripped, style="")
        else:
            head_lines = stripped.split("\n")[:15]
            content.append("\n".join(head_lines), style="")
            content.append(
                f"\n\n... 共 {line_count} 行，已截断显示前 15 行",
                style=C_MUTED,
            )

    if stderr:
        if stdout:
            content.append("\n")
        content.append(stderr.rstrip()[:500], style=C_DANGER)

    console.print()
    console.print(Panel(content, title=title, title_align="left", border_style=border_color))


# ═══════════════════════════════════════════════════════════════
# 远程执行结果
# ═══════════════════════════════════════════════════════════════

def print_remote_results(results: list[dict]) -> None:
    table = Table(
        title=f"{_EMOJI_GLOBE} 远程执行结果",
        box=box.ROUNDED,
        show_header=True,
        header_style=f"bold {C_PRIMARY}",
    )
    table.add_column("主机", style="bold")
    table.add_column("状态", justify="center")
    table.add_column("退出码", justify="center")
    table.add_column("耗时", justify="right")
    table.add_column("输出", max_width=50)

    for r in results:
        host = r.get("host", "?")
        success = r.get("success", False)
        exit_code = r.get("exit_code", -1)
        duration = r.get("duration_ms", 0)
        stdout = r.get("stdout", "").strip()[:100]
        stderr = r.get("stderr", "").strip()[:100]
        error = r.get("error", "")

        status = (
            f"[{C_SUCCESS}]{_EMOJI_OK} 成功[/{C_SUCCESS}]"
            if success
            else f"[{C_DANGER}]{_EMOJI_FAIL} 失败[/{C_DANGER}]"
        )
        duration_str = _format_duration(duration)
        output = stdout if success else (stderr or error)

        table.add_row(host, status, str(exit_code), duration_str, output)

    console.print(table)

    success_count = sum(1 for r in results if r.get("success"))
    total = len(results)
    if success_count == total:
        console.print(f"[{C_SUCCESS}]{_EMOJI_OK} 全部成功 ({total}/{total})[/{C_SUCCESS}]")
    else:
        console.print(
            f"[{C_WARNING}]{_EMOJI_WARN} {success_count}/{total} 成功[/{C_WARNING}]"
        )


# ═══════════════════════════════════════════════════════════════
# 经验记录
# ═══════════════════════════════════════════════════════════════

def print_incident(incident: dict) -> None:
    root_cause = incident.get("root_cause", "")
    solution = incident.get("solution", "")
    command = incident.get("command", "")

    content = Text()
    content.append("触发命令: ", style="bold")
    content.append(f"`{command}`\n", style=C_ACCENT)
    if root_cause:
        content.append("根因: ", style="bold")
        content.append(f"{root_cause}\n", style=C_DANGER)
    if solution:
        content.append("方案: ", style="bold")
        content.append(solution, style=C_SUCCESS)

    tags = incident.get("tags", [])
    if tags:
        content.append("\n标签: ", style="bold")
        content.append(", ".join(tags), style=C_MUTED)

    border = C_SUCCESS if incident.get("resolved") else C_DANGER
    console.print(Panel(
        content,
        title=f"{_EMOJI_BOOK} 经验 {incident.get('id', '')}",
        border_style=border,
    ))


def print_incident_stats(stats: dict) -> None:
    table = Table(title=f"{_EMOJI_CHART} 经验统计", box=box.SIMPLE)
    table.add_column("指标", style="bold")
    table.add_column("数值", justify="right")

    total = stats.get("total", 0)
    resolved = stats.get("resolved", 0)
    unresolved = stats.get("unresolved", 0)
    skills = stats.get("skills_generated", 0)

    table.add_row("总记录", str(total))
    table.add_row(f"[{C_SUCCESS}]已解决[/{C_SUCCESS}]", str(resolved))
    table.add_row(f"[{C_DANGER}]未解决[/{C_DANGER}]", str(unresolved))
    table.add_row(f"[{C_PRIMARY}]已生成 Skill[/{C_PRIMARY}]", str(skills))

    console.print(table)

    top_tags = stats.get("top_tags", {})
    if top_tags:
        console.print("\n[bold]高频标签:[/bold]")
        for tag, count in list(top_tags.items())[:5]:
            console.print(f"  [{C_PRIMARY}]{tag}[/{C_PRIMARY}]: {count}")


# ═══════════════════════════════════════════════════════════════
# 主机清单
# ═══════════════════════════════════════════════════════════════

def print_hosts(hosts: list[dict], groups: dict[str, list[str]]) -> None:
    table = Table(
        title=f"{_EMOJI_GLOBE} 主机清单",
        box=box.ROUNDED,
        show_header=True,
        header_style=f"bold {C_PRIMARY}",
    )
    table.add_column("名称", style="bold")
    table.add_column("地址")
    table.add_column("端口", justify="center")
    table.add_column("用户")
    table.add_column("标签")

    for h in hosts:
        tags = ", ".join(h.get("tags", []))
        table.add_row(
            h.get("name", ""),
            h.get("hostname", ""),
            str(h.get("port", 22)),
            h.get("user", "root"),
            tags,
        )

    console.print(table)

    if groups:
        console.print("\n[bold]分组:[/bold]")
        for group, members in groups.items():
            console.print(f"  [{C_PRIMARY}]{group}[/{C_PRIMARY}]: {', '.join(members)}")


# ═══════════════════════════════════════════════════════════════
# 历史记录
# ═══════════════════════════════════════════════════════════════

def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def print_history(entries: list[dict]) -> None:
    if not entries:
        console.print(f"\n[{C_MUTED}]暂无执行历史。[/{C_MUTED}]")
        return

    console.print(f"\n[bold]最近 {len(entries)} 条记录[/bold]")
    console.print(f"[{C_MUTED}]输入 /history <编号> 查看完整输出[/{C_MUTED}]\n")

    action_styles = {
        "executed": C_SUCCESS,
        "confirmed": C_WARNING,
        "denied": C_DANGER,
        "blocked": f"{C_DANGER} bold",
    }
    action_labels = {
        "executed": "执行",
        "confirmed": "确认",
        "denied": "拒绝",
        "blocked": "阻止",
    }

    for i, e in enumerate(reversed(entries), 1):
        action = e.get("action", "?")
        color = action_styles.get(action, "white")
        label = action_labels.get(action, action)
        exit_code = e.get("exit_code")
        output = e.get("output", "")
        cmd = e.get("command", "")[:80]
        time_str = _to_local_time(e.get("timestamp", ""))[11:19]

        # 状态图标
        if exit_code == 0:
            status = f"[{C_SUCCESS}]{_EMOJI_OK}[/{C_SUCCESS}]"
        elif exit_code is not None:
            status = f"[{C_DANGER}]{_EMOJI_FAIL}[/{C_DANGER}]"
        else:
            status = f"[{C_MUTED}]-[/{C_MUTED}]"

        line = (
            f" {status} [{i:>2}] "
            f"[{color}]{label}[/{color}]  "
            f"[{C_MUTED}]{time_str}[/{C_MUTED}]  "
            f"[{C_PRIMARY}]{escape(cmd)}[/{C_PRIMARY}]"
        )

        if output:
            preview = _truncate(output, 120).replace("\n", " \\ ")
            line += f"\n       [{C_MUTED}]{escape(preview)}[/{C_MUTED}]"

        console.print(line)
        if i < len(entries):
            console.print(f"  [{C_MUTED}]│[/{C_MUTED}]")

    console.print()


def print_history_detail(entry: dict) -> None:
    console.print()
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    table.add_column("k", style=f"bold {C_MUTED}")
    table.add_column("v")

    table.add_row("命令", f"[{C_PRIMARY}]{escape(entry.get('command', ''))}[/{C_PRIMARY}]")
    table.add_row("时间", _to_local_time(entry.get("timestamp", "")))
    table.add_row("风险", entry.get("risk_level", "?"))
    table.add_row("目标", entry.get("target", "local"))
    table.add_row("退出码", str(entry.get("exit_code", "-")))
    table.add_row("耗时", f"{entry.get('duration_ms', '-')}ms")
    console.print(table)

    output = entry.get("output", "")
    if output:
        if len(output) > 2000:
            console.print(f"\n[bold]输出[/bold] [{C_MUTED}]已截断[/{C_MUTED}]:")
            console.print(Syntax(output[:2000], "bash", theme="monokai"))
            console.print(f"[{C_MUTED}]... {len(output) - 2000} 字符未显示[/{C_MUTED}]")
        else:
            console.print(f"\n[bold]输出:[/bold]")
            console.print(Syntax(output, "bash", theme="monokai"))
    else:
        console.print(f"\n[{C_MUTED}]无输出[/{C_MUTED}]")

    stderr = entry.get("stderr", "")
    if stderr:
        console.print(f"\n[bold {C_DANGER}]错误输出:[/bold {C_DANGER}]")
        console.print(f"[{C_DANGER}]{stderr[:2000]}[/{C_DANGER}]")

    console.print()


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

def print_config(config_data: dict) -> None:
    tree = Tree(f"{_EMOJI_GEAR} 配置")
    for section, values in config_data.items():
        branch = tree.add(f"[bold {C_PRIMARY}]{section}[/bold {C_PRIMARY}]")
        if isinstance(values, dict):
            for k, v in values.items():
                branch.add(f"{k}: [{C_ACCENT}]{v}[/{C_ACCENT}]")
        else:
            branch.add(f"[{C_ACCENT}]{values}[/{C_ACCENT}]")
    console.print()
    console.print(tree)
    console.print()


# ═══════════════════════════════════════════════════════════════
# 辅助：状态栏、进度、分割线
# ═══════════════════════════════════════════════════════════════

def create_spinner(text: str = "思考中...") -> Spinner:
    """创建加载旋转器。"""
    return Spinner("dots", text=f"[{C_MUTED}]{text}[/{C_MUTED}]", style=f"bold {C_PRIMARY}")


def print_section(title: str) -> None:
    """打印带标题的分割线。"""
    console.print()
    console.print(Rule(title=f"[bold {C_PRIMARY}]{title}[/bold {C_PRIMARY}]", style=C_MUTED))


def print_status_line(metrics: dict[str, str]) -> None:
    """打印一行状态概览。"""
    parts = []
    for key, val in metrics.items():
        parts.append(f"[{C_MUTED}]{key}:[/{C_MUTED}] [{C_ACCENT}]{val}[/{C_ACCENT}]")
    console.print("  ".join(parts))


def print_success(msg: str) -> None:
    console.print(f"[{C_SUCCESS}]{_EMOJI_OK} {msg}[/{C_SUCCESS}]")


def print_error(msg: str) -> None:
    console.print(f"[{C_DANGER}]{_EMOJI_FAIL} {msg}[/{C_DANGER}]")


def print_warning(msg: str) -> None:
    console.print(f"[{C_WARNING}]{_EMOJI_WARN} {msg}[/{C_WARNING}]")


def print_info(msg: str) -> None:
    console.print(f"[{C_MUTED}]{_EMOJI_INFO} {msg}[/{C_MUTED}]")
