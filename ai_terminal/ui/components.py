"""Rich UI 组件 — 美化终端输出（跨平台）。"""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.syntax import Syntax
from rich.columns import Columns
from rich.markdown import Markdown
from rich.tree import Tree
from rich import box

from ai_terminal.safety.policy import RiskLevel


def _is_windows() -> bool:
    return sys.platform == "win32"


# 检测终端是否支持 emoji
def _supports_emoji() -> bool:
    """检测终端是否支持 emoji。"""
    if _is_windows():
        # Windows Terminal 和 PowerShell 7+ 支持 emoji
        wt_session = __import__("os").environ.get("WT_SESSION")
        ps_version = __import__("os").environ.get("PSModulePath")
        return bool(wt_session or ps_version)
    return True  # Linux/macOS 通常支持


# 根据终端能力选择图标
_EMOJI_OK = "✅" if _supports_emoji() else "[OK]"
_EMOJI_FAIL = "❌" if _supports_emoji() else "[FAIL]"
_EMOJI_WARN = "⚠️" if _supports_emoji() else "[!]"
_EMOJI_CRIT = "🚨" if _supports_emoji() else "[!!]"
_EMOJI_INFO = "ℹ️" if _supports_emoji() else "[i]"
_EMOJI_ROBOT = "🤖" if _supports_emoji() else "[AI]"
_EMOJI_LIGHT = "💡" if _supports_emoji() else "[*]"
_EMOJI_SYNC = "🔄" if _supports_emoji() else "[~]"
_EMOJI_WRENCH = "🔧" if _supports_emoji() else "[#]"
_EMOJI_CHART = "📊" if _supports_emoji() else "[=]"
_EMOJI_GLOBE = "🌐" if _supports_emoji() else "[@]"
_EMOJI_BYE = "👋" if _supports_emoji() else "bye"
_EMOJI_GEAR = "⚙️" if _supports_emoji() else "[cfg]"
_EMOJI_SHIELD = "🛡️" if _supports_emoji() else "[safe]"
_EMOJI_CLOCK = "⏱" if _supports_emoji() else "t"


console = Console()


def print_banner() -> None:
    """打印启动横幅。"""
    banner = Text()
    banner.append("╔══════════════════════════════════════════════════╗\n", style="cyan")
    banner.append("║           ", style="cyan")
    banner.append("AI Terminal 智能终端管家", style="bold white")
    banner.append("            ║\n", style="cyan")
    banner.append("╠══════════════════════════════════════════════════╣\n", style="cyan")
    banner.append("║  ", style="cyan")
    banner.append("自然语言", style="green")
    banner.append(" → ", style="dim")
    banner.append("安全执行", style="yellow")
    banner.append(" → ", style="dim")
    banner.append("智能运维", style="red")
    banner.append("              ║\n", style="cyan")
    banner.append("╠══════════════════════════════════════════════════╣\n", style="cyan")
    banner.append("║  输入模式：                                      ║\n", style="cyan")
    banner.append("║    ", style="cyan")
    banner.append("无前缀", style="bold")
    banner.append("  AI 对话   ", style="dim")
    banner.append('"看看磁盘使用率"', style="white")
    banner.append("       ║\n", style="cyan")
    banner.append("║    ", style="cyan")
    banner.append("!      ", style="bold")
    banner.append(" 直接执行   ", style="dim")
    banner.append("!docker ps", style="white")
    banner.append("               ║\n", style="cyan")
    banner.append("║    ", style="cyan")
    banner.append(">      ", style="bold")
    banner.append(" 混合模式   ", style="dim")
    banner.append("> 清理日志", style="white")
    banner.append("               ║\n", style="cyan")
    banner.append("║    ", style="cyan")
    banner.append("/help", style="bold")
    banner.append("  帮助信息                            ║\n", style="cyan")
    banner.append("║    ", style="cyan")
    banner.append("/quit", style="bold")
    banner.append("  退出                                ║\n", style="cyan")
    banner.append("╚══════════════════════════════════════════════════╝", style="cyan")
    console.print(banner)


def print_help() -> None:
    """打印帮助信息。"""
    table = Table(
        title="AI Terminal 命令",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("命令", style="bold")
    table.add_column("说明")

    table.add_row("<文本>", "AI 对话模式 — 描述需求，AI 生成命令")
    table.add_row("!<命令>", "直接执行模式 — 跳过 AI，直接运行")
    table.add_row("><描述>", "混合模式 — AI 生成命令，确认后执行")
    table.add_row("", "")
    table.add_row("/help", "显示此帮助")
    table.add_row("/status", "显示系统状态")
    table.add_row("/history", "显示执行历史")
    table.add_row("/stats", "显示审计统计")
    table.add_row("/config", "显示当前配置")
    table.add_row("/incidents", "查看踩坑记录")
    table.add_row("/hosts", "查看主机清单")
    table.add_row("/quit", "退出程序")

    console.print(table)

    console.print()
    safety_panel = Panel(
        "[bold]安全说明[/bold]\n"
        "  * 只读命令自动执行，破坏性命令需确认\n"
        "  * 所有操作记录审计日志\n"
        "  * 失败命令自动记录并分析根因\n"
        "  * 推荐安全替代方案",
        title=f"{_EMOJI_SHIELD} 安全策略",
        border_style="green",
    )
    console.print(safety_panel)


def print_risk_warning(risk_level: RiskLevel, reason: str, alternative: str | None = None, rollback: str | None = None) -> None:
    """打印风险警告。"""
    colors = {
        RiskLevel.SAFE: "green",
        RiskLevel.LOW: "blue",
        RiskLevel.HIGH: "yellow",
        RiskLevel.CRITICAL: "red bold",
    }
    icons = {
        RiskLevel.SAFE: _EMOJI_OK,
        RiskLevel.LOW: _EMOJI_INFO,
        RiskLevel.HIGH: _EMOJI_WARN,
        RiskLevel.CRITICAL: _EMOJI_CRIT,
    }

    color = colors.get(risk_level, "white")
    icon = icons.get(risk_level, "❓")

    content = f"[{color}]{icon} 风险等级: {risk_level.value.upper()}[/{color}]\n"
    content += f"   {reason}\n"
    if alternative:
        content += f"   {_EMOJI_LIGHT} 建议: [green]{alternative}[/green]\n"
    if rollback:
        content += f"   {_EMOJI_SYNC} 回滚: [dim]{rollback}[/dim]"

    border_color = "red" if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "yellow"
    panel = Panel(content, title="安全检查", border_style=border_color)
    console.print(panel)


def print_command_result(
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    duration_ms: int,
    host: str = "local",
) -> None:
    """打印命令执行结果。"""
    # 命令头
    if host != "local":
        console.print(f"\n[bold cyan]$ [{host}][/bold cyan] {command}")
    else:
        console.print(f"\n[bold green]$[/bold green] {command}")

    # stdout
    if stdout:
        # 尝试语法高亮
        if any(cmd in command for cmd in ["ls", "cat", "grep", "git", "docker"]):
            console.print(Syntax(stdout.rstrip(), "bash", theme="monokai"))
        else:
            console.print(stdout.rstrip())

    # stderr
    if stderr:
        console.print(f"[red]{stderr.rstrip()}[/red]")

    # 状态栏
    status_color = "green" if exit_code == 0 else "red"
    status_icon = _EMOJI_OK if exit_code == 0 else _EMOJI_FAIL
    duration_str = f"{duration_ms}ms" if duration_ms < 1000 else f"{duration_ms / 1000:.1f}s"
    console.print(f"[dim]{status_icon} exit={exit_code}  {_EMOJI_CLOCK} {duration_str}[/dim]")


def print_remote_results(results: list[dict]) -> None:
    """打印远程执行结果。"""
    table = Table(
        title="远程执行结果",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
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

        status = f"[green]{_EMOJI_OK} 成功[/green]" if success else f"[red]{_EMOJI_FAIL} 失败[/red]"
        duration_str = f"{duration}ms" if duration < 1000 else f"{duration / 1000:.1f}s"
        output = stdout if success else (stderr or error)

        table.add_row(host, status, str(exit_code), duration_str, output)

    console.print(table)

    success_count = sum(1 for r in results if r.get("success"))
    total = len(results)
    if success_count == total:
        console.print(f"[green]{_EMOJI_OK} 全部成功 ({total}/{total})[/green]")
    else:
        console.print(f"[yellow]{_EMOJI_WARN} {success_count}/{total} 成功[/yellow]")


def print_incident(incident: dict) -> None:
    """打印踩坑记录。"""
    root_cause = incident.get("root_cause", "")
    solution = incident.get("solution", "")
    command = incident.get("command", "")

    content = f"[bold]触发命令[/bold]: `{command}`\n"
    if root_cause:
        content += f"[bold]根因[/bold]: [red]{root_cause}[/red]\n"
    if solution:
        content += f"[bold]方案[/bold]: [green]{solution}[/green]"

    tags = incident.get("tags", [])
    if tags:
        content += f"\n[bold]标签[/bold]: {', '.join(tags)}"

    border = "green" if incident.get("resolved") else "red"
    console.print(Panel(content, title=f"{_EMOJI_WRENCH} 踩坑记录 {incident.get('id', '')}", border_style=border))


def print_incident_stats(stats: dict) -> None:
    """打印踩坑统计。"""
    table = Table(title="踩坑统计", box=box.SIMPLE)
    table.add_column("指标", style="bold")
    table.add_column("数值", justify="right")

    table.add_row("总记录", str(stats.get("total", 0)))
    table.add_row("[green]已解决[/green]", str(stats.get("resolved", 0)))
    table.add_row("[red]未解决[/red]", str(stats.get("unresolved", 0)))
    table.add_row("已生成 Skill", str(stats.get("skills_generated", 0)))

    console.print(table)

    top_tags = stats.get("top_tags", {})
    if top_tags:
        console.print("\n[bold]高频标签:[/bold]")
        for tag, count in list(top_tags.items())[:5]:
            console.print(f"  {tag}: {count}")


def print_hosts(hosts: list[dict], groups: dict[str, list[str]]) -> None:
    """打印主机清单。"""
    table = Table(
        title="主机清单",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
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
            console.print(f"  [cyan]{group}[/cyan]: {', '.join(members)}")


def print_history(entries: list[dict]) -> None:
    """打印执行历史。"""
    if not entries:
        console.print("[dim]暂无执行历史。[/dim]")
        return

    table = Table(
        title=f"最近 {len(entries)} 条记录",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("时间", style="dim")
    table.add_column("操作", justify="center")
    table.add_column("风险", justify="center")
    table.add_column("目标", justify="center")
    table.add_column("命令", max_width=40)

    action_colors = {
        "executed": "green",
        "confirmed": "yellow",
        "denied": "red",
        "blocked": "red bold",
    }

    for e in entries:
        action = e.get("action", "?")
        color = action_colors.get(action, "white")
        table.add_row(
            e.get("timestamp", "")[:19],
            f"[{color}]{action}[/{color}]",
            e.get("risk_level", "?"),
            e.get("target", "local"),
            e.get("command", "")[:50],
        )

    console.print(table)


def print_config(config_data: dict) -> None:
    """打印配置信息。"""
    tree = Tree(f"{_EMOJI_GEAR} 配置")
    for section, values in config_data.items():
        branch = tree.add(f"[bold]{section}[/bold]")
        if isinstance(values, dict):
            for k, v in values.items():
                branch.add(f"{k}: [cyan]{v}[/cyan]")
        else:
            branch.add(f"[cyan]{values}[/cyan]")
    console.print(tree)
