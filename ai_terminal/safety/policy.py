"""安全策略引擎 — 命令分级与决策。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RiskLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Decision:
    """安全决策结果。"""

    allowed: bool
    risk_level: RiskLevel
    reason: str
    require_confirmation: bool = False
    alternative: str | None = None
    rollback_command: str | None = None


# SAFE — 只读，没有任何副作用
_SAFE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^ls\b"),
    re.compile(r"^cat\b"),
    re.compile(r"^head\b"),
    re.compile(r"^tail\b"),
    re.compile(r"^less\b"),
    re.compile(r"^more\b"),
    re.compile(r"^file\b"),
    re.compile(r"^stat\b"),
    re.compile(r"^wc\b"),
    re.compile(r"^du\b"),
    re.compile(r"^df\b"),
    re.compile(r"^find\b(?!.*-delete)(?!.*-exec\s+rm)"),
    re.compile(r"^grep\b"),
    re.compile(r"^rg\b"),
    re.compile(r"^ag\b"),
    re.compile(r"^awk\b(?!.*>)"),
    re.compile(r"^sed\b(?!.*-i)"),
    re.compile(r"^ps\b"),
    re.compile(r"^top\b"),
    re.compile(r"^htop\b"),
    re.compile(r"^free\b"),
    re.compile(r"^uptime\b"),
    re.compile(r"^whoami\b"),
    re.compile(r"^id\b"),
    re.compile(r"^hostname\b"),
    re.compile(r"^uname\b"),
    re.compile(r"^ip\b"),
    re.compile(r"^ifconfig\b"),
    re.compile(r"^netstat\b"),
    re.compile(r"^ss\b"),
    re.compile(r"^lsof\b"),
    re.compile(r"^mount\b"),
    re.compile(r"^lsblk\b"),
    re.compile(r"^lscpu\b"),
    re.compile(r"^ping\b"),
    re.compile(r"^traceroute\b"),
    re.compile(r"^nslookup\b"),
    re.compile(r"^dig\b"),
    re.compile(r"^curl\b(?!.*-X\s*(POST|PUT|DELETE|PATCH))"),
    re.compile(r"^wget\b(?!.*-O\s*/)"),
    re.compile(r"^docker ps\b"),
    re.compile(r"^docker images\b"),
    re.compile(r"^docker logs\b"),
    re.compile(r"^docker inspect\b"),
    re.compile(r"^docker stats\b"),
    re.compile(r"^docker top\b"),
    re.compile(r"^git (status|log|diff|show|branch|remote)\b"),
    re.compile(r"^systemctl status\b"),
    re.compile(r"^systemctl is-active\b"),
    re.compile(r"^systemctl list-units\b"),
    re.compile(r"^journalctl\b"),
    re.compile(r"^env\b"),
    re.compile(r"^echo\b"),
    re.compile(r"^date\b"),
    re.compile(r"^which\b"),
    re.compile(r"^whereis\b"),
    re.compile(r"^type\b"),
    re.compile(r"^history\b"),
]

# LOW — 写入操作，但可逆或影响范围小
_LOW_PATTERNS: list[re.Pattern] = [
    re.compile(r"^touch\b"),
    re.compile(r"^mkdir\b"),
    re.compile(r"^cp\b"),
    re.compile(r"^mv\b"),
    re.compile(r"^ln\b"),
    re.compile(r"^install\b"),
    re.compile(r"^echo\b.*>>"),
    re.compile(r"^tee\b.*-a"),
    re.compile(r"^sed\s+-i\b"),
    re.compile(r"^tar\b.*-x"),
    re.compile(r"^unzip\b"),
    re.compile(r"^docker run\b"),
    re.compile(r"^docker start\b"),
    re.compile(r"^docker stop\b"),
    re.compile(r"^docker compose\b(.*up|.*down|.*restart)"),
    re.compile(r"^git (add|commit|push|pull|fetch|checkout|branch|merge|stash)\b"),
    re.compile(r"^pip(3?)\s+install\b"),
    re.compile(r"^npm\s+install\b"),
    re.compile(r"^apt\s+install\b"),
    re.compile(r"^yum\s+install\b"),
    re.compile(r"^brew\s+install\b"),
    re.compile(r"^systemctl (start|restart|reload)\b"),
    re.compile(r"^chmod\b(?!.*777)"),
]

# HIGH — 破坏性操作，有备份路径但需要确认
_HIGH_PATTERNS: list[re.Pattern] = [
    re.compile(r"^rm\b"),
    re.compile(r"^rmdir\b"),
    re.compile(r"^shred\b"),
    re.compile(r"^find\b.*-delete"),
    re.compile(r"^find\b.*-exec\s+rm"),
    re.compile(r"^echo\b.*>[^>]"),
    re.compile(r"^tee\b(?!.*-a)"),
    re.compile(r"^docker rm\b"),
    re.compile(r"^docker kill\b"),
    re.compile(r"^docker rmi\b"),
    re.compile(r"^docker compose\b.*rm"),
    re.compile(r"^git reset\b.*--hard"),
    re.compile(r"^git clean\b.*-f"),
    re.compile(r"^git push\b.*--force"),
    re.compile(r"^git branch\b.*-D"),
    re.compile(r"^systemctl (stop|disable|mask)\b"),
    re.compile(r"^iptables\b"),
    re.compile(r"^ufw\b"),
    re.compile(r"^userdel\b"),
    re.compile(r"^groupdel\b"),
    re.compile(r"^crontab\b.*-r"),
    re.compile(r"^mysql\b.*-e.*DELETE\b"),
    re.compile(r"^mysql\b.*-e.*DROP\b"),
    re.compile(r"^redis-cli\b.*FLUSH"),
    re.compile(r"^chmod\s+.*777\b"),
]

# CRITICAL — 不可逆，可能造成系统级破坏
_CRITICAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"^rm\s+(-rf?|--recursive)\s+/"),
    re.compile(r"^rm\s+(-rf?|--recursive)\s+~"),
    re.compile(r"^rm\s+(-rf?|--recursive)\s+\*"),
    re.compile(r"^mkfs\b"),
    re.compile(r"^dd\b.*of=/dev/"),
    re.compile(r"^fdisk\b"),
    re.compile(r"^parted\b"),
    re.compile(r"^shutdown\b"),
    re.compile(r"^reboot\b"),
    re.compile(r"^halt\b"),
    re.compile(r"^poweroff\b"),
    re.compile(r"^init\s+[06]"),
    re.compile(r"^DROP\s+DATABASE\b", re.IGNORECASE),
    re.compile(r"^TRUNCATE\b", re.IGNORECASE),
    re.compile(r"^docker system prune\b.*-a"),
    re.compile(r"^docker volume rm\b"),
    re.compile(r"^>\s*/dev/sd"),
    re.compile(r"^chmod\s+(-R\s+)?777\s+/"),
]

# 自动生成替代方案的规则
_ALTERNATIVES: dict[str, tuple[str, str]] = {
    "rm ": (
        "mv {target} ~/.ai-terminal/trash/  # 7 天后自动清理",
        "mv ~/.ai-terminal/trash/{basename} {target}",
    ),
    "rm -rf": (
        "mv {target} ~/.ai-terminal/trash/  # 7 天后自动清理",
        "mv ~/.ai-terminal/trash/{basename} {target}",
    ),
    "docker rm": (
        "docker stop {container}  # 先停止，不删除",
        "docker start {container}",
    ),
    "git reset --hard": (
        "git stash  # 暂存修改，可恢复",
        "git stash pop",
    ),
    "git push --force": (
        "git push --force-with-lease  # 更安全的强制推送",
        None,
    ),
}


class SafetyPolicy:
    """安全策略引擎。"""

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.allow_remote = config.get("allow_remote", True)
        self.allow_batch = config.get("allow_batch", True)
        self.whitelist: set[str] = set(config.get("whitelist", []))
        self.blacklist: set[str] = set(config.get("blacklist", []))
        self.max_batch_size = config.get("max_batch_size", 5)
        self.command_timeout = config.get("command_timeout", 30)
        self.trash_dir = config.get("trash_dir", "~/.ai-terminal/trash")

        # 自定义规则
        self._custom_rules: list[tuple[re.Pattern, RiskLevel]] = []
        for rule in config.get("custom_rules", []):
            self._custom_rules.append((
                re.compile(rule["pattern"]),
                RiskLevel(rule["level"]),
            ))

    def classify(self, command: str) -> RiskLevel:
        """判断命令的风险等级。"""
        cmd = command.strip()

        # 自定义规则优先
        for pattern, level in self._custom_rules:
            if pattern.search(cmd):
                return level

        # 黑名单直接 CRITICAL
        if cmd in self.whitelist:
            return RiskLevel.SAFE

        # 按优先级匹配
        for pattern in _CRITICAL_PATTERNS:
            if pattern.search(cmd):
                return RiskLevel.CRITICAL

        for pattern in _HIGH_PATTERNS:
            if pattern.search(cmd):
                return RiskLevel.HIGH

        for pattern in _LOW_PATTERNS:
            if pattern.search(cmd):
                return RiskLevel.LOW

        for pattern in _SAFE_PATTERNS:
            if pattern.search(cmd):
                return RiskLevel.SAFE

        # 未知命令默认 HIGH
        return RiskLevel.HIGH

    def check(self, command: str, target: str = "local") -> Decision:
        """检查命令是否允许执行。"""
        cmd = command.strip()

        # 白名单直接放行
        if cmd in self.whitelist:
            return Decision(
                allowed=True,
                risk_level=RiskLevel.SAFE,
                reason="白名单放行",
            )

        # 黑名单直接拒绝
        if cmd in self.blacklist:
            return Decision(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                reason="黑名单禁止",
            )

        risk = self.classify(cmd)

        if risk == RiskLevel.SAFE:
            return Decision(
                allowed=True,
                risk_level=risk,
                reason="只读操作，自动放行",
            )

        if risk == RiskLevel.LOW:
            return Decision(
                allowed=True,
                risk_level=risk,
                reason="可逆操作，自动放行",
            )

        if risk == RiskLevel.HIGH:
            alternative, rollback = self._suggest_alternative(cmd)
            return Decision(
                allowed=True,
                risk_level=risk,
                reason="破坏性操作，需要确认",
                require_confirmation=True,
                alternative=alternative,
                rollback_command=rollback,
            )

        # CRITICAL
        return Decision(
            allowed=True,
            risk_level=risk,
            reason="极高风险操作，需要二次确认",
            require_confirmation=True,
        )

    def _suggest_alternative(self, command: str) -> tuple[str | None, str | None]:
        """根据命令生成替代方案。"""
        for key, (alt, rollback) in _ALTERNATIVES.items():
            if key in command:
                # 尝试提取目标路径
                target = self._extract_target(command, key)
                alt_text = alt.format(target=target, basename="") if target else alt
                rollback_text = rollback.format(target=target, basename="") if rollback else None
                return alt_text, rollback_text
        return None, None

    def _extract_target(self, command: str, prefix: str) -> str | None:
        """从命令中提取目标路径。"""
        try:
            idx = command.index(prefix)
            rest = command[idx + len(prefix):].strip()
            # 跳过 flags
            parts = rest.split()
            for part in parts:
                if not part.startswith("-"):
                    return part
        except ValueError:
            pass
        return None
