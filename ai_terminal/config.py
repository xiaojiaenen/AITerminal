"""配置管理 — 加载和管理 AI Terminal 配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# 默认配置
_DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "default_target": "local",
        "language": "zh-CN",
        "history_file": "~/.ai-terminal/history",
        "max_history": 1000,
    },
    "safety": {
        "enabled": True,
        "trash_dir": "~/.ai-terminal/trash",
        "trash_retention_days": 7,
        "require_confirmation": True,
        "max_batch_size": 5,
        "command_timeout": 30,
        "whitelist": [],
        "blacklist": [],
        "custom_rules": [],
    },
    "audit": {
        "enabled": True,
        "log_dir": "~/.ai-terminal/audit",
    },
    "llm": {
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.1,
        "max_tokens": 4096,
    },
    "cluster": {
        "inventory_file": "~/.ai-terminal/inventory.yaml",
        "connection_timeout": 10,
        "command_timeout": 60,
    },
    "knowledge": {
        "enabled": True,
        "store_path": "~/.ai-terminal/knowledge",
    },
    "skills": {
        "dirs": ["~/.ai-terminal/skills", "skills"],
        "incident_dir": "~/.ai-terminal/incidents/skills",
    },
}


@dataclass
class HostConfig:
    """单台主机配置。"""
    name: str
    hostname: str
    port: int = 22
    user: str = "root"
    key_file: str = ""
    password: str = ""  # 建议用 key_file
    tags: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HostConfig:
        return cls(
            name=d.get("name", d.get("hostname", "")),
            hostname=d["hostname"],
            port=d.get("port", 22),
            user=d.get("user", "root"),
            key_file=d.get("key_file", ""),
            password=d.get("password", ""),
            tags=d.get("tags", []),
            env=d.get("env", {}),
        )


@dataclass
class ClusterInventory:
    """集群主机清单。"""
    hosts: list[HostConfig] = field(default_factory=list)
    groups: dict[str, list[str]] = field(default_factory=dict)  # group_name -> [host_names]

    @classmethod
    def load(cls, path: str | Path) -> ClusterInventory:
        """从 YAML 文件加载主机清单。"""
        p = Path(path).expanduser()
        if not p.exists():
            return cls()

        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        hosts = [HostConfig.from_dict(h) for h in (data.get("hosts") or [])]
        groups = data.get("groups") or {}

        return cls(hosts=hosts, groups=groups)

    def get_hosts(self, target: str = "all") -> list[HostConfig]:
        """获取目标主机列表。支持 'all'、组名、主机名。"""
        if target == "all":
            return self.hosts

        # 按组名查
        if target in self.groups:
            names = set(self.groups[target])
            return [h for h in self.hosts if h.name in names]

        # 按主机名或标签查
        for host in self.hosts:
            if host.name == target or host.hostname == target:
                return [host]
            if target in host.tags:
                return [host]

        return []


class Config:
    """AI Terminal 全局配置。"""

    def __init__(self, config_path: str | Path | None = None):
        self._data: dict[str, Any] = {}
        self._config_path: Path | None = None

        # 加载默认配置
        self._merge(_DEFAULT_CONFIG)

        # 加载配置文件
        if config_path:
            self.load_file(config_path)
        else:
            # 尝试默认路径
            for p in self._default_paths():
                if p.exists():
                    self.load_file(p)
                    break

        # 环境变量覆盖
        self._apply_env()

    def _default_paths(self) -> list[Path]:
        return [
            Path("~/.ai-terminal/config.yaml").expanduser(),
            Path("~/.ai-terminal/config.yml").expanduser(),
            Path("ai-terminal.yaml"),
            Path("ai-terminal.yml"),
        ]

    def _merge(self, data: dict[str, Any], base: dict | None = None) -> None:
        """深度合并配置。"""
        target = base if base is not None else self._data
        for key, value in data.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._merge(value, target[key])
            else:
                target[key] = value

    def load_file(self, path: str | Path) -> None:
        """从 YAML 文件加载配置。"""
        p = Path(path).expanduser()
        self._config_path = p
        if not p.exists():
            return

        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self._merge(data)

    def _apply_env(self) -> None:
        """从环境变量覆盖配置。支持 AI_TERMINAL_ 前缀。"""
        prefix = "AI_TERMINAL_"
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue
            parts = key[len(prefix):].lower().split("_")
            target = self._data
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        """点号分隔获取配置值。如 'safety.trash_dir'。"""
        parts = key.split(".")
        target = self._data
        for part in parts:
            if isinstance(target, dict) and part in target:
                target = target[part]
            else:
                return default
        return target

    def set(self, key: str, value: Any) -> None:
        """点号分隔设置配置值。"""
        parts = key.split(".")
        target = self._data
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    @property
    def safety(self) -> dict[str, Any]:
        return self._data.get("safety", {})

    @property
    def llm(self) -> dict[str, Any]:
        return self._data.get("llm", {})

    @property
    def cluster(self) -> dict[str, Any]:
        return self._data.get("cluster", {})

    @property
    def general(self) -> dict[str, Any]:
        return self._data.get("general", {})

    def load_inventory(self) -> ClusterInventory:
        """加载集群主机清单。"""
        inventory_file = self.get("cluster.inventory_file", "~/.ai-terminal/inventory.yaml")
        return ClusterInventory.load(inventory_file)

    def save(self, path: str | Path | None = None) -> None:
        """保存当前配置到文件。"""
        p = Path(path) if path else self._config_path
        if not p:
            p = Path("~/.ai-terminal/config.yaml").expanduser()

        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, allow_unicode=True, default_flow_style=False)
