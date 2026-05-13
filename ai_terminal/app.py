"""AI Terminal 主应用 — 交互式 CLI 入口。"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from ai_terminal.config import Config
from ai_terminal.safety.policy import SafetyPolicy, RiskLevel
from ai_terminal.safety.audit import AuditLogger
from ai_terminal.tools.shell_tools import ShellExecutor


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


# 系统提示词
SYSTEM_PROMPT = """你是 AI Terminal 智能终端管家。你可以：

1. **直接执行命令** — 用户用 `!` 前缀直接执行 shell 命令
2. **AI 对话** — 用户用自然语言描述需求，你生成并执行命令
3. **混合模式** — 用户用 `>` 前缀，你生成命令但需用户确认后执行

安全规则：
- SAFE 级别（只读）自动执行
- LOW 级别（可逆写入）自动执行
- HIGH 级别（破坏性）需用户确认
- CRITICAL 级别（不可逆）需二次确认
- 优先推荐安全替代方案

回复风格：
- 简洁直接，不过度解释
- 命令执行结果用代码块展示
- 出错时给出修复建议
"""


class AITerminal:
    """AI Terminal 主应用。"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.policy = SafetyPolicy(self.config.safety)
        self.audit = AuditLogger(self.config.get("audit.log_dir", "~/.ai-terminal/audit"))
        self.shell = ShellExecutor(
            timeout=self.config.get("safety.command_timeout", 30),
        )
        self._running = False

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
    /quit        退出程序

  安全说明：
    只读命令自动执行，破坏性命令需确认
    所有操作记录审计日志
"""
        print(help_text)

    async def execute_direct(self, command: str) -> None:
        """直接执行模式。"""
        # 安全检查
        decision = self.policy.check(command)

        if decision.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            print(f"\n⚠️  风险等级: {decision.risk_level.value}")
            print(f"   {decision.reason}")
            if decision.alternative:
                print(f"   建议: {decision.alternative}")

            try:
                confirm = input("\n继续执行？(y/N): ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("已取消。")
                    self.audit.log_execution(
                        command=command,
                        risk_level=decision.risk_level,
                        action="denied",
                    )
                    return
            except (EOFError, KeyboardInterrupt):
                print("\n已取消。")
                return

        # 执行
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

    async def execute_hybrid(self, description: str) -> None:
        """混合模式 — AI 生成命令，用户确认后执行。"""
        # 这里简化实现，实际应该调用 LLM 生成命令
        print(f"\n🤖 AI 分析: {description}")
        print("   （LLM 集成后会自动生成命令）")

        try:
            command = input("\n请输入要执行的命令: ").strip()
            if not command:
                print("已取消。")
                return
            await self.execute_direct(command)
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")

    async def handle_ai_chat(self, user_input: str) -> None:
        """AI 对话模式。"""
        print(f"\n🤖 AI 对话: {user_input}")
        print("   （LLM 集成后会自动处理）")
        print("   当前仅支持直接执行（!）和混合模式（>）")

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
                    print(f"   [{action:10s}] [{risk:8s}] {cmd_str}")
            return True

        if cmd == "/stats":
            stats = self.audit.get_stats()
            print(f"\n📊 审计统计")
            print(f"   总命令数: {stats.get('total_commands', 0)}")
            print(f"   按操作: {stats.get('by_action', {})}")
            print(f"   按风险: {stats.get('by_risk_level', {})}")
            return True

        if cmd == "/config":
            print("\n⚙️  当前配置:")
            for key in ["general", "safety", "llm", "cluster"]:
                print(f"   {key}: {self.config.get(key, {})}")
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


def main() -> None:
    """CLI 入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="AI Terminal 智能终端管家")
    parser.add_argument("-c", "--config", help="配置文件路径")
    parser.add_argument("-t", "--timeout", type=int, help="命令超时时间（秒）")
    args = parser.parse_args()

    config = Config(args.config) if args.config else Config()
    if args.timeout:
        config.set("safety.command_timeout", args.timeout)

    app = AITerminal(config)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\n👋 再见！")
        sys.exit(0)


if __name__ == "__main__":
    main()
