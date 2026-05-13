"""安全策略引擎 — 命令分级与决策（跨平台）。"""

from __future__ import annotations

import re
import sys
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


# ── 跨平台命令别名映射 ──────────────────────────────────────────────

def _is_windows() -> bool:
    return sys.platform == "win32"


# ── SAFE — 只读，没有任何副作用 ──────────────────────────────────────

# Linux/macOS SAFE 命令
_SAFE_UNIX: list[re.Pattern] = [
    re.compile(r"^ls\b"),
    re.compile(r"^pwd\b"),
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

# Windows SAFE 命令
_SAFE_WINDOWS: list[re.Pattern] = [
    re.compile(r"^dir\b", re.IGNORECASE),
    re.compile(r"^ls\b", re.IGNORECASE),
    re.compile(r"^pwd\b", re.IGNORECASE),
    re.compile(r"^type\b", re.IGNORECASE),
    re.compile(r"^cat\b", re.IGNORECASE),
    re.compile(r"^echo\b", re.IGNORECASE),
    re.compile(r"^whoami\b", re.IGNORECASE),
    re.compile(r"^hostname\b", re.IGNORECASE),
    re.compile(r"^ver\b", re.IGNORECASE),
    re.compile(r"^systeminfo\b", re.IGNORECASE),
    re.compile(r"^tasklist\b", re.IGNORECASE),
    re.compile(r"^ipconfig\b", re.IGNORECASE),
    re.compile(r"^ping\b", re.IGNORECASE),
    re.compile(r"^tracert\b", re.IGNORECASE),
    re.compile(r"^nslookup\b", re.IGNORECASE),
    re.compile(r"^netstat\b", re.IGNORECASE),
    re.compile(r"^net\s+user\b", re.IGNORECASE),
    re.compile(r"^net\s+localgroup\b", re.IGNORECASE),
    re.compile(r"^net\s+share\b", re.IGNORECASE),
    re.compile(r"^net\s+use\b", re.IGNORECASE),
    re.compile(r"^where\b", re.IGNORECASE),
    re.compile(r"^date\b", re.IGNORECASE),
    re.compile(r"^time\b", re.IGNORECASE),
    re.compile(r"^chcp\b", re.IGNORECASE),
    re.compile(r"^set\b", re.IGNORECASE),
    re.compile(r"^tree\b", re.IGNORECASE),
    re.compile(r"^vol\b", re.IGNORECASE),
    re.compile(r"^fsutil\b", re.IGNORECASE),
    re.compile(r"^wmic\b", re.IGNORECASE),
    re.compile(r"^sc\s+query\b", re.IGNORECASE),
    re.compile(r"^curl\b", re.IGNORECASE),
    # PowerShell SAFE 命令
    re.compile(r"^Get-Process\b", re.IGNORECASE),
    re.compile(r"^Get-Service\b", re.IGNORECASE),
    re.compile(r"^Get-ChildItem\b", re.IGNORECASE),
    re.compile(r"^Get-Content\b", re.IGNORECASE),
    re.compile(r"^Get-Location\b", re.IGNORECASE),
    re.compile(r"^Get-Date\b", re.IGNORECASE),
    re.compile(r"^Get-Host\b", re.IGNORECASE),
    re.compile(r"^Get-Help\b", re.IGNORECASE),
    re.compile(r"^Get-Command\b", re.IGNORECASE),
    re.compile(r"^Get-Alias\b", re.IGNORECASE),
    re.compile(r"^Get-EventLog\b", re.IGNORECASE),
    re.compile(r"^Get-WmiObject\b", re.IGNORECASE),
    re.compile(r"^Get-CimInstance\b", re.IGNORECASE),
    re.compile(r"^Select-Object\b", re.IGNORECASE),
    re.compile(r"^Where-Object\b", re.IGNORECASE),
    re.compile(r"^Format-Table\b", re.IGNORECASE),
    re.compile(r"^Format-List\b", re.IGNORECASE),
    re.compile(r"^Measure-Object\b", re.IGNORECASE),
    re.compile(r"^Test-Path\b", re.IGNORECASE),
    re.compile(r"^Resolve-Path\b", re.IGNORECASE),
    # 跨平台通用
    re.compile(r"^docker ps\b"),
    re.compile(r"^docker images\b"),
    re.compile(r"^docker logs\b"),
    re.compile(r"^docker inspect\b"),
    re.compile(r"^docker stats\b"),
    re.compile(r"^docker top\b"),
    re.compile(r"^git (status|log|diff|show|branch|remote)\b"),
]

# macOS 额外 SAFE 命令
_SAFE_MACOS_EXTRA: list[re.Pattern] = [
    re.compile(r"^open\b"),
    re.compile(r"^pbcopy\b"),
    re.compile(r"^pbpaste\b"),
    re.compile(r"^sw_vers\b"),
    re.compile(r"^sysctl\b"),
    re.compile(r"^diskutil\b"),
    re.compile(r"^softwareupdate\b"),
    re.compile(r"^launchctl\b"),
]

# ── LOW — 写入操作，但可逆或影响范围小 ──────────────────────────────

_LOW_UNIX: list[re.Pattern] = [
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

_LOW_WINDOWS: list[re.Pattern] = [
    re.compile(r"^md\b", re.IGNORECASE),
    re.compile(r"^mkdir\b", re.IGNORECASE),
    re.compile(r"^copy\b", re.IGNORECASE),
    re.compile(r"^move\b", re.IGNORECASE),
    re.compile(r"^ren\b", re.IGNORECASE),
    re.compile(r"^rename\b", re.IGNORECASE),
    re.compile(r"^xcopy\b", re.IGNORECASE),
    re.compile(r"^robocopy\b", re.IGNORECASE),
    re.compile(r"^echo\b.*>>", re.IGNORECASE),
    re.compile(r"^mklink\b", re.IGNORECASE),
    re.compile(r"^attrib\b", re.IGNORECASE),
    re.compile(r"^icacls\b", re.IGNORECASE),
    re.compile(r"^takeown\b", re.IGNORECASE),
    re.compile(r"^schtasks\b", re.IGNORECASE),
    re.compile(r"^sc\s+(start|stop|config)\b", re.IGNORECASE),
    re.compile(r"^reg\s+(add|delete)\b", re.IGNORECASE),
    # PowerShell LOW 命令
    re.compile(r"^New-Item\b", re.IGNORECASE),
    re.compile(r"^Copy-Item\b", re.IGNORECASE),
    re.compile(r"^Move-Item\b", re.IGNORECASE),
    re.compile(r"^Rename-Item\b", re.IGNORECASE),
    re.compile(r"^Remove-Item\b", re.IGNORECASE),
    re.compile(r"^Set-Content\b", re.IGNORECASE),
    re.compile(r"^Add-Content\b", re.IGNORECASE),
    re.compile(r"^Start-Service\b", re.IGNORECASE),
    re.compile(r"^Stop-Service\b", re.IGNORECASE),
    re.compile(r"^Restart-Service\b", re.IGNORECASE),
    re.compile(r"^Start-Process\b", re.IGNORECASE),
    re.compile(r"^Invoke-WebRequest\b", re.IGNORECASE),
    re.compile(r"^Invoke-RestMethod\b", re.IGNORECASE),
    re.compile(r"^Install-Package\b", re.IGNORECASE),
    re.compile(r"^Set-Location\b", re.IGNORECASE),
    re.compile(r"^Out-File\b", re.IGNORECASE),
    # 跨平台通用
    re.compile(r"^docker run\b"),
    re.compile(r"^docker start\b"),
    re.compile(r"^docker stop\b"),
    re.compile(r"^docker compose\b(.*up|.*down|.*restart)"),
    re.compile(r"^git (add|commit|push|pull|fetch|checkout|branch|merge|stash)\b"),
    re.compile(r"^pip(3?)\s+install\b", re.IGNORECASE),
    re.compile(r"^npm\s+install\b", re.IGNORECASE),
]

# ── HIGH — 破坏性操作，有备份路径但需要确认 ─────────────────────────

_HIGH_UNIX: list[re.Pattern] = [
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

_HIGH_WINDOWS: list[re.Pattern] = [
    re.compile(r"^del\b", re.IGNORECASE),
    re.compile(r"^erase\b", re.IGNORECASE),
    re.compile(r"^rd\b", re.IGNORECASE),
    re.compile(r"^rmdir\b", re.IGNORECASE),
    re.compile(r"^format\b", re.IGNORECASE),
    re.compile(r"^del\b.*\*", re.IGNORECASE),
    re.compile(r"^echo\b.*>[^>]", re.IGNORECASE),
    re.compile(r"^net\s+(stop|pause)\b", re.IGNORECASE),
    re.compile(r"^sc\s+(delete|stop)\b", re.IGNORECASE),
    re.compile(r"^taskkill\b", re.IGNORECASE),
    re.compile(r"^reg\s+delete\b", re.IGNORECASE),
    re.compile(r"^schtasks\s+/delete\b", re.IGNORECASE),
    re.compile(r"^cipher\s+/w\b", re.IGNORECASE),
    # PowerShell HIGH 命令
    re.compile(r"^Remove-Item\b", re.IGNORECASE),
    re.compile(r"^Remove-ItemProperty\b", re.IGNORECASE),
    re.compile(r"^Clear-Content\b", re.IGNORECASE),
    re.compile(r"^Stop-Process\b", re.IGNORECASE),
    re.compile(r"^Remove-Service\b", re.IGNORECASE),
    re.compile(r"^Unregister-ScheduledTask\b", re.IGNORECASE),
    re.compile(r"^Set-ItemProperty\b", re.IGNORECASE),
    # 跨平台通用
    re.compile(r"^docker rm\b"),
    re.compile(r"^docker kill\b"),
    re.compile(r"^docker rmi\b"),
    re.compile(r"^docker compose\b.*rm"),
    re.compile(r"^git reset\b.*--hard"),
    re.compile(r"^git clean\b.*-f"),
    re.compile(r"^git push\b.*--force"),
    re.compile(r"^git branch\b.*-D"),
    re.compile(r"^mysql\b.*-e.*DELETE\b"),
    re.compile(r"^mysql\b.*-e.*DROP\b"),
    re.compile(r"^redis-cli\b.*FLUSH"),
]

# ── CRITICAL — 不可逆，可能造成系统级破坏 ───────────────────────────

_CRITICAL_UNIX: list[re.Pattern] = [
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

_CRITICAL_WINDOWS: list[re.Pattern] = [
    re.compile(r"^del\s+(/[sfq]\s+)+.*\*", re.IGNORECASE),  # 只有带通配符才是 CRITICAL
    re.compile(r"^del\s+(/[sfq]\s+)+[A-Z]:", re.IGNORECASE),  # 删除驱动器
    re.compile(r"^rd\s+(/[sq]\s+)+[A-Z]:", re.IGNORECASE),  # 删除驱动器
    re.compile(r"^rmdir\s+(/[sq]\s+)+[A-Z]:", re.IGNORECASE),  # 删除驱动器
    re.compile(r"^format\b", re.IGNORECASE),
    re.compile(r"^diskpart\b", re.IGNORECASE),
    re.compile(r"^bcdedit\b", re.IGNORECASE),
    re.compile(r"^shutdown\s+/[sg]\b", re.IGNORECASE),
    re.compile(r"^restart\b", re.IGNORECASE),
    re.compile(r"^Remove-Item\s+.*-Recurse\s+.*-Force", re.IGNORECASE),
    re.compile(r"^Clear-RecycleBin\b", re.IGNORECASE),
    re.compile(r"^Format-Volume\b", re.IGNORECASE),
    re.compile(r"^Stop-Computer\b", re.IGNORECASE),
    re.compile(r"^Restart-Computer\b", re.IGNORECASE),
    re.compile(r"^Reset-ComputerMachinePassword\b", re.IGNORECASE),
    # 跨平台通用
    re.compile(r"^DROP\s+DATABASE\b", re.IGNORECASE),
    re.compile(r"^TRUNCATE\b", re.IGNORECASE),
    re.compile(r"^docker system prune\b.*-a"),
    re.compile(r"^docker volume rm\b"),
]


# ── 替代方案（跨平台） ─────────────────────────────────────────────

_UNIX_ALTERNATIVES: dict[str, tuple[str, str]] = {
    "rm ": (
        "mv {target} ~/.ai-terminal/trash/  # 7 天后自动清理",
        "mv ~/.ai-terminal/trash/{basename} {target}",
    ),
    "rm -rf": (
        "mv {target} ~/.ai-terminal/trash/  # 7 天后自动清理",
        "mv ~/.ai-terminal/trash/{basename} {target}",
    ),
    "docker rm": (
        "docker stop {target}  # 先停止，不删除",
        "docker start {target}",
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

_WINDOWS_ALTERNATIVES: dict[str, tuple[str, str]] = {
    "del ": (
        'Move-Item {target} "$env:TEMP\\.ai-terminal-trash\\"  # 移到回收站',
        'Move-Item "$env:TEMP\\.ai-terminal-trash\\{basename}" {target}',
    ),
    "Remove-Item": (
        'Move-Item {target} "$env:TEMP\\.ai-terminal-trash\\"  # 移到回收站',
        'Move-Item "$env:TEMP\\.ai-terminal-trash\\{basename}" {target}',
    ),
    "rd ": (
        'Move-Item {target} "$env:TEMP\\.ai-terminal-trash\\"  # 移到回收站',
        'Move-Item "$env:TEMP\\.ai-terminal-trash\\{basename}" {target}',
    ),
    "docker rm": (
        "docker stop {target}  # 先停止，不删除",
        "docker start {target}",
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


# ── 获取当前平台的模式列表 ──────────────────────────────────────────

def _get_patterns() -> dict[str, list]:
    """根据当前平台返回对应的模式列表。"""
    if _is_windows():
        return {
            "safe": _SAFE_WINDOWS,
            "low": _LOW_WINDOWS,
            "high": _HIGH_WINDOWS,
            "critical": _CRITICAL_WINDOWS,
            "alternatives": _WINDOWS_ALTERNATIVES,
        }
    else:
        # Linux 和 macOS 共用大部分模式
        safe = _SAFE_UNIX[:]
        if sys.platform == "darwin":
            safe.extend(_SAFE_MACOS_EXTRA)
        return {
            "safe": safe,
            "low": _LOW_UNIX,
            "high": _HIGH_UNIX,
            "critical": _CRITICAL_UNIX,
            "alternatives": _UNIX_ALTERNATIVES,
        }


class SafetyPolicy:
    """安全策略引擎（跨平台）。"""

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.allow_remote = config.get("allow_remote", True)
        self.allow_batch = config.get("allow_batch", True)
        self.whitelist: set[str] = set(config.get("whitelist", []))
        self.blacklist: set[str] = set(config.get("blacklist", []))
        self.max_batch_size = config.get("max_batch_size", 5)
        self.command_timeout = config.get("command_timeout", 30)
        self.trash_dir = config.get("trash_dir", "~/.ai-terminal/trash")

        # 加载平台相关模式
        self._patterns = _get_patterns()

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

        # 白名单直接 SAFE
        if cmd in self.whitelist:
            return RiskLevel.SAFE

        # 按优先级匹配：CRITICAL > HIGH > SAFE > LOW
        # SAFE 在 LOW 之前，因为有些命令同时匹配两者（如 git branch）
        for pattern in self._patterns["critical"]:
            if pattern.search(cmd):
                return RiskLevel.CRITICAL

        for pattern in self._patterns["high"]:
            if pattern.search(cmd):
                return RiskLevel.HIGH

        for pattern in self._patterns["safe"]:
            if pattern.search(cmd):
                return RiskLevel.SAFE

        for pattern in self._patterns["low"]:
            if pattern.search(cmd):
                return RiskLevel.LOW

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
        alternatives = self._patterns["alternatives"]
        for key, (alt, rollback) in alternatives.items():
            if key in command:
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
            parts = rest.split()
            for part in parts:
                if not part.startswith("-"):
                    return part
        except ValueError:
            pass
        return None
