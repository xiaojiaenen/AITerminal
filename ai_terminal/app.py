"""AI Terminal 主应用 — 交互式 CLI 入口。"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from ai_terminal.config import Config
from ai_terminal.safety.policy import SafetyPolicy, RiskLevel
from ai_terminal.safety.audit import AuditLogger, AuditAction
from ai_terminal.tools.shell_tools import ShellExecutor
from ai_terminal.cluster.remote import RemoteExecutor
from ai_terminal.runtime.incident import IncidentRecorder
from ai_terminal.ui.components import (
    console,
    print_banner,
    print_help,
    print_risk_warning,
    print_command_result,
    print_remote_results,
    print_incident,
    print_incident_stats,
    print_hosts,
    print_history,
    print_config,
    _EMOJI_OK,
    _EMOJI_FAIL,
    _EMOJI_WARN,
    _EMOJI_ROBOT,
    _EMOJI_LIGHT,
    _EMOJI_GLOBE,
    _EMOJI_BYE,
    _EMOJI_CHART,
)
from ai_terminal.ui.prompt import get_prompt


# 输入模式
MODE_AI = "ai"  # AI 对话
MODE_DIRECT = "direct"  # ! 直接执行
MODE_HYBRID = "hybrid"  # > 混合模式


def detect_mode(user_input: str) -> tuple[str, str]:
    """检测输入模式，返回 (mode, content)。"""
    stripped = user_input.strip()
    if stripped.startswith("!"):
        return MODE_DIRECT, stripped[1:].strip()
    if stripped.startswith(">"):
        return MODE_HYBRID, stripped[1:].strip()
    return MODE_AI, stripped


class AITerminal:
    """AI Terminal 主应用。"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.policy = SafetyPolicy(self.config.safety)
        self.audit = AuditLogger(self.config.get("audit.log_dir", "~/.ai-terminal/audit"))
        self.shell = ShellExecutor(
            timeout=self.config.get("safety.command_timeout", 30),
        )
        self.remote = RemoteExecutor(
            timeout=self.config.get("cluster.command_timeout", 60),
        )
        self.incidents = IncidentRecorder()
        self.prompt = get_prompt()
        self._agent = None  # 延迟初始化
        self._running = False

    def _get_agent(self):
        """延迟初始化 AI Agent。"""
        if self._agent is None:
            from ai_terminal.agent import AITerminalAgent
            self._agent = AITerminalAgent(self.config, self.policy, self.audit)
        return self._agent

    async def execute_direct(self, command: str) -> None:
        """直接执行模式。"""
        decision = self.policy.check(command)

        if decision.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            print_risk_warning(
                decision.risk_level,
                decision.reason,
                decision.alternative,
                decision.rollback_command,
            )

            try:
                confirm = console.input("\n[bold]继续执行？(y/N):[/bold] ").strip().lower()
                if confirm not in ("y", "yes"):
                    console.print("[yellow]已取消。[/yellow]")
                    self.audit.log_execution(
                        command=command,
                        risk_level=decision.risk_level,
                        action=AuditAction.DENIED,
                    )
                    return
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]已取消。[/yellow]")
                return

        result = await self.shell.run(command)

        print_command_result(
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
        )

        self.audit.log_execution(
            command=command,
            risk_level=decision.risk_level,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
        )

        # 失败时自动记录踩坑
        if not result.success:
            incident = self.incidents.record(
                command=command,
                exit_code=result.exit_code,
                error_output=result.stderr or result.stdout,
            )
            if incident and incident.root_cause:
                console.print(f"\n{_EMOJI_LIGHT} [bold]自动诊断:[/bold] {incident.root_cause}")
                if incident.solution:
                    console.print(f"   [green]建议方案:[/green] {incident.solution}")

    async def execute_hybrid(self, description: str) -> None:
        """混合模式 — AI 生成命令，用户确认后执行。"""
        try:
            agent = self._get_agent()
            response = await agent.chat(
                f"用户需要: {description}\n"
                "请只输出要执行的 shell 命令，不要解释。如果需要多条命令，每行一条。"
            )
            commands = [line.strip() for line in response.strip().split("\n") if line.strip()]
            if not commands:
                console.print("[red]AI 未能生成命令。[/red]")
                return

            console.print(f"\n[bold cyan]{_EMOJI_ROBOT} AI 建议执行:[/bold cyan]")
            for cmd in commands:
                console.print(f"   [green]$[/green] {cmd}")

            try:
                confirm = console.input("\n[bold]确认执行？(y/N/edit):[/bold] ").strip().lower()
                if confirm == "y":
                    for cmd in commands:
                        await self.execute_direct(cmd)
                elif confirm == "edit":
                    edited = console.input("[bold]请输入修改后的命令:[/bold] ").strip()
                    if edited:
                        await self.execute_direct(edited)
                else:
                    console.print("[yellow]已取消。[/yellow]")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]已取消。[/yellow]")

        except Exception as e:
            console.print(f"\n[red]AI 调用失败: {e}[/red]")
            console.print("[dim]请使用 ! 前缀直接执行命令。[/dim]")

    async def handle_ai_chat(self, user_input: str) -> None:
        """AI 对话模式。"""
        try:
            agent = self._get_agent()
            response = await agent.chat(user_input)
            console.print(f"\n{response}")
        except Exception as e:
            console.print(f"\n[red]AI 调用失败: {e}[/red]")
            console.print("[dim]提示: 设置 OPENAI_API_KEY 环境变量，或使用 ! 前缀直接执行命令。[/dim]")

    async def execute_remote(self, command: str, target: str = "all") -> None:
        """远程执行命令。"""
        inventory = self.config.load_inventory()
        hosts = inventory.get_hosts(target)

        if not hosts:
            console.print(f"\n[red]{_EMOJI_FAIL} 未找到目标主机: {target}[/red]")
            console.print("[dim]   使用 /hosts 查看主机清单[/dim]")
            return

        console.print(f"\n[bold cyan]{_EMOJI_GLOBE} 在 {len(hosts)} 台主机上执行:[/bold cyan] {command}")
        results = await self.remote.run_on_hosts(hosts, command)

        results_dicts = [r.to_dict() for r in results]
        print_remote_results(results_dicts)

        for r in results:
            self.audit.log_execution(
                command=command,
                risk_level=RiskLevel.SAFE,
                exit_code=r.exit_code,
                duration_ms=r.duration_ms,
                target=r.host,
            )

    async def handle_command(self, cmd: str) -> bool:
        """处理快捷命令。返回 False 表示退出。"""
        cmd = cmd.strip().lower()

        if cmd in ("/quit", "/exit", "/q"):
            console.print(f"\n[bold cyan]{_EMOJI_BYE} 再见！[/bold cyan]")
            return False

        if cmd == "/help":
            print_help()
            return True

        if cmd == "/status":
            console.print(f"\n[bold]{_EMOJI_CHART} 系统状态[/bold]")
            console.print(f"   工作目录: [cyan]{self.shell.work_dir}[/cyan]")
            console.print(f"   命令超时: [cyan]{self.shell.timeout}s[/cyan]")
            console.print(f"   安全策略: [cyan]{'启用' if self.config.get('safety.enabled', True) else '禁用'}[/cyan]")
            console.print(f"   主机数量: [cyan]{len(self.config.load_inventory().hosts)}[/cyan]")
            return True

        if cmd == "/history":
            entries = self.audit.get_recent(20)
            print_history(entries)
            return True

        if cmd == "/stats":
            stats = self.audit.get_stats()
            console.print(f"\n[bold]📊 审计统计[/bold]")
            console.print(f"   总命令数: [cyan]{stats.get('total_commands', 0)}[/cyan]")
            console.print(f"   按操作: [cyan]{stats.get('by_action', {})}[/cyan]")
            console.print(f"   按风险: [cyan]{stats.get('by_risk_level', {})}[/cyan]")

            inc_stats = self.incidents.get_stats()
            print_incident_stats(inc_stats)
            return True

        if cmd == "/config":
            config_data = {}
            for key in ["general", "safety", "llm", "cluster"]:
                config_data[key] = self.config.get(key, {})
            print_config(config_data)
            return True

        if cmd == "/incidents":
            incidents = self.incidents.get_recent(10)
            if not incidents:
                console.print("\n[dim]暂无踩坑记录。[/dim]")
            else:
                console.print(f"\n[bold]🔧 最近 {len(incidents)} 条踩坑记录:[/bold]")
                for inc in incidents:
                    print_incident(inc.to_dict())
            return True

        if cmd == "/hosts":
            inventory = self.config.load_inventory()
            hosts_data = [
                {
                    "name": h.name,
                    "hostname": h.hostname,
                    "port": h.port,
                    "user": h.user,
                    "tags": h.tags,
                }
                for h in inventory.hosts
            ]
            print_hosts(hosts_data, inventory.groups)
            return True

        console.print(f"[red]未知命令: {cmd}[/red]，输入 [bold]/help[/bold] 查看帮助")
        return True

    async def run(self) -> None:
        """主运行循环。"""
        print_banner()

        current_mode = "ai"
        self._running = True

        while self._running:
            user_input = await self.prompt.get_input(current_mode)

            if user_input is None:
                console.print(f"\n[bold cyan]{_EMOJI_BYE} 再见！[/bold cyan]")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # 快捷命令
            if user_input.startswith("/"):
                if not await self.handle_command(user_input):
                    break
                continue

            # 检测输入模式
            mode, content = detect_mode(user_input)
            if not content:
                continue

            current_mode = mode

            if mode == MODE_DIRECT:
                await self.execute_direct(content)
            elif mode == MODE_HYBRID:
                await self.execute_hybrid(content)
            else:
                await self.handle_ai_chat(content)

        await self.remote.close()


def main() -> None:
    """CLI 入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="AI Terminal 智能终端管家")
    parser.add_argument("-c", "--config", help="配置文件路径")
    parser.add_argument("-t", "--timeout", type=int, help="命令超时时间（秒）")
    parser.add_argument("command", nargs="?", help="直接执行命令后退出")
    args = parser.parse_args()

    config = Config(args.config) if args.config else Config()
    if args.timeout:
        config.set("safety.command_timeout", args.timeout)

    app = AITerminal(config)

    if args.command:
        asyncio.run(app.execute_direct(args.command))
    else:
        try:
            asyncio.run(app.run())
        except KeyboardInterrupt:
            console.print(f"\n[bold cyan]{_EMOJI_BYE} 再见！[/bold cyan]")
            sys.exit(0)


if __name__ == "__main__":
    main()
