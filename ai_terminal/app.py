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
        self._agent = None  # 延迟初始化
        self._running = False

    def _get_agent(self):
        """延迟初始化 AI Agent。"""
        if self._agent is None:
            from ai_terminal.agent import AITerminalAgent
            self._agent = AITerminalAgent(self.config, self.policy, self.audit)
        return self._agent

    def print_banner(self) -> None:
        """打印启动横幅。"""
        banner = """
╔══════════════════════════════════════════════╗
║           AI Terminal 智能终端管家            ║
║──────────────────────────────────────────────║
║  自然语言 → 安全执行 → 智能运维              ║
║                                              ║
║  输入模式：                                   ║
║    无前缀  AI 对话   "看看磁盘使用率"         ║
║    !      直接执行   !docker ps               ║
║    >      混合模式   > 清理日志               ║
║    /help  帮助信息                            ║
║    /quit  退出                                ║
╚══════════════════════════════════════════════╝
"""
        print(banner)

    def print_help(self) -> None:
        """打印帮助信息。"""
        help_text = """
AI Terminal 命令：

  输入模式：
    <文本>       AI 对话模式 — 描述需求，AI 生成命令
    !<命令>      直接执行模式 — 跳过 AI，直接运行
    ><描述>      混合模式 — AI 生成命令，确认后执行

  快捷命令：
    /help        显示此帮助
    /status      显示系统状态
    /history     显示执行历史
    /stats       显示审计统计
    /config      显示当前配置
    /incidents   查看踩坑记录
    /hosts       查看主机清单
    /quit        退出程序

  安全说明：
    只读命令自动执行，破坏性命令需确认
    所有操作记录审计日志
    失败命令自动记录并分析根因
"""
        print(help_text)

    async def execute_direct(self, command: str) -> None:
        """直接执行模式。"""
        decision = self.policy.check(command)

        if decision.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            print(f"\n⚠️  风险等级: {decision.risk_level.value}")
            print(f"   {decision.reason}")
            if decision.alternative:
                print(f"   建议: {decision.alternative}")
            if decision.rollback_command:
                print(f"   回滚: {decision.rollback_command}")

            try:
                confirm = input("\n继续执行？(y/N): ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("已取消。")
                    self.audit.log_execution(
                        command=command,
                        risk_level=decision.risk_level,
                        action=AuditAction.DENIED,
                    )
                    return
            except (EOFError, KeyboardInterrupt):
                print("\n已取消。")
                return

        print(f"\n$ {command}")
        result = await self.shell.run(command)

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"\033[31m{result.stderr}\033[0m", end="")

        if result.timed_out:
            print(f"\n⏰ 命令超时 ({self.shell.timeout}s)")

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
                print(f"\n💡 自动诊断: {incident.root_cause}")
                if incident.solution:
                    print(f"   建议方案: {incident.solution}")

    async def execute_hybrid(self, description: str) -> None:
        """混合模式 — AI 生成命令，用户确认后执行。"""
        try:
            agent = self._get_agent()
            response = await agent.chat(
                f"用户需要: {description}\n"
                "请只输出要执行的 shell 命令，不要解释。如果需要多条命令，每行一条。"
            )
            # 提取命令（取第一行非空内容）
            commands = [line.strip() for line in response.strip().split("\n") if line.strip()]
            if not commands:
                print("AI 未能生成命令。")
                return

            print(f"\n🤖 AI 建议执行:")
            for cmd in commands:
                print(f"   $ {cmd}")

            try:
                confirm = input("\n确认执行？(y/N/edit): ").strip().lower()
                if confirm == "y":
                    for cmd in commands:
                        await self.execute_direct(cmd)
                elif confirm == "edit":
                    edited = input("请输入修改后的命令: ").strip()
                    if edited:
                        await self.execute_direct(edited)
                else:
                    print("已取消。")
            except (EOFError, KeyboardInterrupt):
                print("\n已取消。")

        except Exception as e:
            print(f"\nAI 调用失败: {e}")
            print("请使用 ! 前缀直接执行命令。")

    async def handle_ai_chat(self, user_input: str) -> None:
        """AI 对话模式。"""
        try:
            agent = self._get_agent()
            response = await agent.chat(user_input)
            print(f"\n{response}")
        except Exception as e:
            print(f"\nAI 调用失败: {e}")
            print("提示: 设置 OPENAI_API_KEY 环境变量，或使用 ! 前缀直接执行命令。")

    async def execute_remote(self, command: str, target: str = "all") -> None:
        """远程执行命令。"""
        inventory = self.config.load_inventory()
        hosts = inventory.get_hosts(target)

        if not hosts:
            print(f"\n❌ 未找到目标主机: {target}")
            print("   使用 /hosts 查看主机清单")
            return

        print(f"\n🌐 在 {len(hosts)} 台主机上执行: {command}")
        results = await self.remote.run_on_hosts(hosts, command)

        for r in results:
            status = "✅" if r.success else "❌"
            print(f"\n  {status} [{r.host}]")
            if r.stdout:
                for line in r.stdout.strip().split("\n")[:20]:
                    print(f"     {line}")
            if r.stderr:
                print(f"     \033[31m{r.stderr[:200]}\033[0m")
            if r.error:
                print(f"     \033[31m错误: {r.error}\033[0m")

        success_count = sum(1 for r in results if r.success)
        print(f"\n  汇总: {success_count}/{len(results)} 成功")

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
            print("\n👋 再见！")
            return False

        if cmd == "/help":
            self.print_help()
            return True

        if cmd == "/status":
            print("\n📊 系统状态")
            print(f"   工作目录: {self.shell.work_dir}")
            print(f"   命令超时: {self.shell.timeout}s")
            print(f"   安全策略: {'启用' if self.config.get('safety.enabled', True) else '禁用'}")
            print(f"   主机数量: {len(self.config.load_inventory().hosts)}")
            return True

        if cmd == "/history":
            entries = self.audit.get_recent(20)
            if not entries:
                print("\n暂无执行历史。")
            else:
                print(f"\n📜 最近 {len(entries)} 条记录:")
                for e in entries:
                    action = e.get("action", "?")
                    cmd_str = e.get("command", "")[:50]
                    risk = e.get("risk_level", "?")
                    target = e.get("target", "local")
                    print(f"   [{action:10s}] [{risk:8s}] [{target:6s}] {cmd_str}")
            return True

        if cmd == "/stats":
            stats = self.audit.get_stats()
            print(f"\n📊 审计统计")
            print(f"   总命令数: {stats.get('total_commands', 0)}")
            print(f"   按操作: {stats.get('by_action', {})}")
            print(f"   按风险: {stats.get('by_risk_level', {})}")

            inc_stats = self.incidents.get_stats()
            print(f"\n📊 踩坑统计")
            print(f"   总记录: {inc_stats.get('total', 0)}")
            print(f"   已解决: {inc_stats.get('resolved', 0)}")
            print(f"   未解决: {inc_stats.get('unresolved', 0)}")
            print(f"   已生成 Skill: {inc_stats.get('skills_generated', 0)}")
            return True

        if cmd == "/config":
            print("\n⚙️  当前配置:")
            for key in ["general", "safety", "llm", "cluster"]:
                print(f"   {key}: {self.config.get(key, {})}")
            return True

        if cmd == "/incidents":
            incidents = self.incidents.get_recent(10)
            if not incidents:
                print("\n暂无踩坑记录。")
            else:
                print(f"\n🔧 最近 {len(incidents)} 条踩坑记录:")
                for inc in incidents:
                    status = "✅" if inc.resolved else "❌"
                    print(f"   {status} [{inc.id}] {inc.root_cause or inc.command[:40]}")
                    if inc.solution:
                        print(f"      方案: {inc.solution[:60]}")
            return True

        if cmd == "/hosts":
            inventory = self.config.load_inventory()
            if not inventory.hosts:
                print("\n未配置主机。编辑 ~/.ai-terminal/inventory.yaml 添加主机。")
            else:
                print(f"\n🖥️  主机清单 ({len(inventory.hosts)} 台):")
                for h in inventory.hosts:
                    tags = f" [{', '.join(h.tags)}]" if h.tags else ""
                    print(f"   {h.name:15s} {h.hostname}:{h.port} ({h.user}){tags}")
                if inventory.groups:
                    print(f"\n   分组: {list(inventory.groups.keys())}")
            return True

        print(f"未知命令: {cmd}，输入 /help 查看帮助")
        return True

    async def run(self) -> None:
        """主运行循环。"""
        self.print_banner()

        self._running = True
        while self._running:
            try:
                user_input = input("\n❯ ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 再见！")
                break

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
        # 单次执行模式
        asyncio.run(app.execute_direct(args.command))
    else:
        try:
            asyncio.run(app.run())
        except KeyboardInterrupt:
            print("\n👋 再见！")
            sys.exit(0)


if __name__ == "__main__":
    main()
