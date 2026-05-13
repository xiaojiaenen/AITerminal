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
    print_history_detail,
    print_config,
    _EMOJI_OK,
    _EMOJI_FAIL,
    _EMOJI_WARN,
    _EMOJI_ROBOT,
    _EMOJI_LIGHT,
    _EMOJI_GLOBE,
    _EMOJI_BYE,
    _EMOJI_CHART,
    _EMOJI_WRENCH,
)
from ai_terminal.ui.prompt import get_prompt
from ai_terminal.skill import SkillRunner


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


def _format_tool_output(tool_name: str, output: str) -> str:
    """格式化工具输出，提取关键信息，截断过长文本。"""
    import json as _json

    # 尝试解析 JSON 输出
    try:
        data = _json.loads(output) if isinstance(output, str) else output
    except (_json.JSONDecodeError, TypeError):
        data = None

    if isinstance(data, dict):
        # run_command / remote_run 输出
        if tool_name in ("run_command", "remote_run"):
            stdout = data.get("stdout", "").strip()
            stderr = data.get("stderr", "").strip()
            exit_code = data.get("exit_code", "")
            parts = []
            if exit_code == 0:
                parts.append(f"exit=0")
            else:
                parts.append(f"exit={exit_code}")
            if stdout:
                lines = stdout.split("\n")
                # 取关键行：跳过空行，取前 6 行
                key_lines = [l for l in lines if l.strip()][:6]
                parts.append("\n".join(key_lines))
                if len(lines) > 6:
                    parts.append("[dim]... 输出截断[/dim]")
            if stderr:
                parts.append(f"[red]{stderr[:200]}[/red]")
            return "\n".join(parts) or "(无输出)"

        # check_safety 输出
        if tool_name == "check_safety":
            risk = data.get("risk_level", "?")
            reason = data.get("reason", "")
            return f"风险: {risk} — {reason}"[:300]

        # search_knowledge / search_skills / search_incidents 输出
        if "results" in data or "count" in data:
            results = data.get("results", [])
            count = data.get("count", len(results))
            preview = ""
            if isinstance(results, list) and results:
                first = results[0]
                if isinstance(first, dict):
                    preview = first.get("text", first.get("name", str(first)))[:150]
            return f"{count} 条结果" + (f": {preview}" if preview else "")

        # 其他 dict 输出 — 取第一个有意义的值
        for key in ("summary", "status", "result", "message"):
            if key in data:
                return str(data[key])[:300]
        return _json.dumps(data, ensure_ascii=False)[:300]

    # 纯文本输出
    stripped = str(output).strip()[:300] if not isinstance(output, str) else output.strip()[:300]
    if len(str(output).strip()) > 300:
        stripped += "\n[dim]... 输出截断[/dim]"
    return stripped


def _extract_command_from_args(tool_name: str, args: str | dict) -> str:
    """从工具调用的 args 中提取可显示的命令字符串。"""
    import json as _json

    if isinstance(args, str):
        try:
            args = _json.loads(args)
        except (_json.JSONDecodeError, TypeError):
            return args[:200]

    if not isinstance(args, dict):
        return str(args)[:200]

    # 按工具名匹配关键参数
    cmd_keys = {
        "run_command": "command",
        "check_safety": "command",
        "remote_run": "command",
    }
    list_keys = {
        "run_pipeline": "commands",
        "run_batch": "commands",
    }

    if tool_name in cmd_keys:
        return str(args.get(cmd_keys[tool_name], ""))[:200]
    if tool_name in list_keys:
        cmds = args.get(list_keys[tool_name], [])
        if isinstance(cmds, list):
            return " | ".join(str(c) for c in cmds)[:200]
        return str(cmds)[:200]
    if tool_name == "search_knowledge":
        return f'search: {args.get("query", "")}'[:200]
    if tool_name == "ingest_knowledge":
        return args.get("file_path", "") or args.get("text", "")[:200]

    return tool_name


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
        self.skill_runner = SkillRunner()
        self.prompt = get_prompt()
        self._agent = None  # 延迟初始化
        self._running = False

    def _get_agent(self):
        """延迟初始化 AI Agent。"""
        if self._agent is None:
            from ai_terminal.agent import AITerminalAgent
            self._agent = AITerminalAgent(
                self.config, self.policy, self.audit, self.skill_runner
            )
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
            output=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
        )

        # 失败时自动记录经验
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
            response = await agent.generate_command(
                f"用户需要: {description}"
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
        """AI 对话模式（流式输出 + Markdown 渲染 + 工具调用可见）。"""
        try:
            from rich.markdown import Markdown
            from rich.live import Live
            from rich.panel import Panel
            from rich.columns import Columns

            agent = self._get_agent()
            full_response = ""
            tool_outputs: list[str] = []  # 本轮工具调用输出

            # 构建显示内容
            def build_renderable():
                parts = []
                if full_response:
                    parts.append(Markdown(full_response))
                if tool_outputs:
                    parts.append(
                        Panel(
                            "\n".join(tool_outputs[-8:]),  # 最多显示 8 条
                            title=f"{_EMOJI_WRENCH} 执行命令",
                            border_style="dim",
                        )
                    )
                return parts[0] if len(parts) == 1 else Columns(parts) if parts else ""

            with Live(console=console, refresh_per_second=10, screen=False) as live:
                async for event in agent.chat_stream(user_input):
                    if event["type"] == "text":
                        full_response += event["data"]
                    elif event["type"] == "tool_start":
                        args = event["data"].get("args", "")
                        # 解析 run_command 的 command 参数
                        cmd = _extract_command_from_args(
                            event["data"]["tool_name"], args
                        )
                        tool_outputs.append(f"[bold cyan]$ {cmd}[/bold cyan]")
                    elif event["type"] == "tool_end":
                        output = event["data"].get("output", "")
                        tool_name = event["data"].get("tool_name", "")
                        formatted = _format_tool_output(tool_name, output)
                        tool_outputs.append(f"[dim]{formatted}[/dim]")

                    renderable = build_renderable()
                    if renderable:
                        live.update(renderable)

            console.print()
        except asyncio.CancelledError:
            console.print("\n[yellow]对话已取消。[/yellow]")
        except KeyboardInterrupt:
            console.print("\n[yellow]对话已取消。[/yellow]")
        except Exception as e:
            console.print(f"\n[red]AI 调用失败: {e}[/red]")
            console.print("[dim]提示: 设置 OPENAI_API_KEY 环境变量，或使用 ! 前缀直接执行命令。[/dim]")

    async def _do_experience_review(self, agent) -> None:
        """后台审查最近对话，提取可沉淀的经验。"""
        try:
            console.print(f"\n[dim]{_EMOJI_LIGHT} 正在审查最近对话经验...[/dim]")
            experiences = await agent.review_experience()
            if not experiences:
                console.print("[dim]  未发现需要沉淀的新经验。[/dim]")
                return

            saved = 0
            for exp in experiences:
                title = exp.get("title", "")
                problem = exp.get("problem", "")
                solution = exp.get("solution", "")
                root_cause = exp.get("root_cause", "")
                tags = exp.get("tags", [])

                if not solution:
                    continue

                # 手动创建经验记录
                incident = self.incidents._create_incident(
                    command=problem[:200] if problem else title,
                    error_output=f"{root_cause}\n{problem}" if root_cause else problem,
                    root_cause=root_cause,
                    solution=solution,
                    tags=tags,
                )
                if incident:
                    saved += 1

            if saved > 0:
                console.print(
                    f"[green]{_EMOJI_OK} 已沉淀 {saved} 条新经验。"
                    f"输入 /incidents 查看。[/green]"
                )
        except Exception:
            pass  # 经验审查失败不影响主流程

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
                output=r.stdout,
                stderr=r.stderr,
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

        if cmd == "/new":
            agent = self._get_agent()
            agent.clear_session()
            console.print(f"\n[green]{_EMOJI_OK} 已开始新对话，上下文已清除。[/green]")
            return True

        if cmd == "/status":
            console.print(f"\n[bold]{_EMOJI_CHART} 系统状态[/bold]")
            console.print(f"   工作目录: [cyan]{self.shell.work_dir}[/cyan]")
            console.print(f"   命令超时: [cyan]{self.shell.timeout}s[/cyan]")
            console.print(f"   安全策略: [cyan]{'启用' if self.config.get('safety.enabled', True) else '禁用'}[/cyan]")
            console.print(f"   主机数量: [cyan]{len(self.config.load_inventory().hosts)}[/cyan]")
            # 上下文信息
            agent = self._get_agent()
            ctx = agent.get_context_info()
            console.print(f"   会话轮数: [cyan]{ctx['rounds']}[/cyan]")
            console.print(f"   上下文消息: [cyan]{ctx['messages']} 条[/cyan]")
            console.print(f"   估算 Token: [cyan]~{ctx['estimated_tokens']}[/cyan]")
            return True

        if cmd == "/history":
            entries = self.audit.get_recent(20)
            print_history(entries)
            return True

        if cmd.startswith("/history "):
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                idx = int(parts[1])
                entries = self.audit.get_recent(20)
                if 1 <= idx <= len(entries):
                    print_history_detail(entries[-idx])
                else:
                    console.print(f"[red]无效编号: {idx}，当前最多 20 条[/red]")
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
                console.print("\n[dim]暂无经验记录。[/dim]")
            else:
                console.print(f"\n[bold]🔧 最近 {len(incidents)} 条经验记录:[/bold]")
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

        if cmd == "/skills":
            skills = self.skill_runner.list_skills()
            if not skills:
                console.print("\n[dim]暂无可用技能。[/dim]")
                console.print("[dim]  经验记录解决后可生成技能 (/incidents)[/dim]")
            else:
                console.print(f"\n[bold]{_EMOJI_WRENCH} 可用技能 ({len(skills)}):[/bold]")
                for s in skills:
                    scripts_info = f" ({s['scripts_count']} 条命令)" if s['scripts_count'] else ""
                    console.print(f"  [bold cyan]{s['name']}[/bold cyan]{scripts_info}")
                    console.print(f"    [dim]{s['description'][:100]}[/dim]")
            return True

        if cmd.startswith("/skill "):
            name = cmd[7:].strip()
            if not name:
                console.print("[red]用法: /skill <技能名>[/red]")
                return True
            skill = self.skill_runner.get_skill(name)
            if not skill:
                console.print(f"[red]未找到技能: {name}[/red]")
                console.print("[dim]  使用 /skills 查看可用技能[/dim]")
                return True
            from rich.panel import Panel
            from rich.markdown import Markdown
            console.print()
            console.print(Panel(
                Markdown(skill["instruction"]),
                title=f"{_EMOJI_WRENCH} 技能: {name}",
                border_style="cyan",
            ))
            if skill["scripts"]:
                console.print(f"\n[bold]可执行命令:[/bold]")
                for sc in skill["scripts"]:
                    console.print(f"  [green]$[/green] {sc}")
                console.print(f"\n[dim]输入 [bold]!{skill['scripts'][0]}[/bold] 直接执行[/dim]")
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

            try:
                if mode == MODE_DIRECT:
                    await self.execute_direct(content)
                elif mode == MODE_HYBRID:
                    await self.execute_hybrid(content)
                else:
                    await self.handle_ai_chat(content)
                    # 每轮 AI 对话后检查是否需要经验审查
                    agent = self._get_agent()
                    if agent.on_round_complete():
                        await self._do_experience_review(agent)
            except KeyboardInterrupt:
                console.print("\n[yellow]操作已取消。按 Ctrl+C 再次可退出程序。[/yellow]")
                continue

        await self.remote.close()


def main() -> None:
    """CLI 入口。"""
    import argparse
    import warnings

    # Windows 下强制 UTF-8 输出，避免中文乱码
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # 抑制 asyncio 子进程清理时的 ResourceWarning（Windows 常见）
    warnings.filterwarnings("ignore", message=".*Event loop is closed.*")
    warnings.filterwarnings("ignore", category=ResourceWarning)

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
        mode, content = detect_mode(args.command)
        asyncio.run(app.execute_direct(content))
    else:
        try:
            asyncio.run(app.run())
        except KeyboardInterrupt:
            console.print(f"\n[bold cyan]{_EMOJI_BYE} 再见！[/bold cyan]")
        finally:
            # 确保子进程传输被正确关闭，避免 __del__ 报错
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.stop()
            except RuntimeError:
                pass


if __name__ == "__main__":
    main()
