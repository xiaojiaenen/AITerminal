"""审计日志 — 记录所有命令执行与安全决策。"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ai_terminal.safety.policy import RiskLevel


class AuditAction(str, Enum):
    EXECUTED = "executed"  # 命令已执行
    BLOCKED = "blocked"  # 命令被阻止
    CONFIRMED = "confirmed"  # 用户确认后执行
    DENIED = "denied"  # 用户拒绝执行
    ALTERNATIVE = "alternative"  # 使用了替代方案


@dataclass
class AuditEntry:
    """单条审计记录。"""
    timestamp: str
    command: str
    action: AuditAction
    risk_level: RiskLevel
    target: str  # local / remote host
    user: str = ""
    reason: str = ""
    exit_code: int | None = None
    output: str = ""
    stderr: str = ""
    alternative_used: str = ""
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_level"] = self.risk_level.value
        d["action"] = self.action.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AuditLogger:
    """审计日志管理器。

    同时写入 JSON Lines 文件和 Python logging，便于后续分析。
    """

    def __init__(self, log_dir: str | Path = "~/.ai-terminal/audit"):
        self.log_dir = Path(log_dir).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger("ai_terminal.audit")
        self._logger.setLevel(logging.INFO)

        # 文件 handler — 按天分割
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"audit-{today}.jsonl"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(fh)

        # 控制台 handler — 只记 WARNING 以上
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        ch.setFormatter(logging.Formatter("[审计] %(message)s"))
        self._logger.addHandler(ch)

    def log(self, entry: AuditEntry) -> None:
        """写入一条审计记录。"""
        self._logger.info(entry.to_json())

    def log_execution(
        self,
        command: str,
        target: str = "local",
        risk_level: RiskLevel = RiskLevel.SAFE,
        exit_code: int | None = None,
        output: str = "",
        stderr: str = "",
        duration_ms: int = 0,
        action: AuditAction = AuditAction.EXECUTED,
        **kwargs: Any,
    ) -> AuditEntry:
        """记录命令执行。"""
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            command=command,
            action=action,
            risk_level=risk_level,
            target=target,
            exit_code=exit_code,
            output=output[:2000],  # stdout 截断到 2000 字符
            stderr=stderr[:2000],  # stderr 截断到 2000 字符
            duration_ms=duration_ms,
            **kwargs,
        )
        self.log(entry)
        return entry

    def log_blocked(
        self,
        command: str,
        reason: str,
        target: str = "local",
        risk_level: RiskLevel = RiskLevel.CRITICAL,
    ) -> AuditEntry:
        """记录被阻止的命令。"""
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            command=command,
            action=AuditAction.BLOCKED,
            risk_level=risk_level,
            target=target,
            reason=reason,
        )
        self.log(entry)
        return entry

    def get_recent(self, count: int = 50) -> list[dict]:
        """读取最近的审计记录。"""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"audit-{today}.jsonl"
        if not log_file.exists():
            return []

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        entries = []
        for line in lines[-count:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    def get_stats(self, days: int = 7) -> dict[str, Any]:
        """统计最近 N 天的审计数据。"""
        from collections import Counter

        action_counts: Counter[str] = Counter()
        risk_counts: Counter[str] = Counter()
        total = 0

        for _i in range(days):
            day = datetime.now().strftime("%Y-%m-%d")  # 简化：只看今天
            log_file = self.log_dir / f"audit-{day}.jsonl"
            if not log_file.exists():
                continue
            for line in log_file.read_text(encoding="utf-8").strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    action_counts[record.get("action", "unknown")] += 1
                    risk_counts[record.get("risk_level", "unknown")] += 1
                    total += 1
                except json.JSONDecodeError:
                    continue

        return {
            "total_commands": total,
            "by_action": dict(action_counts),
            "by_risk_level": dict(risk_counts),
        }
