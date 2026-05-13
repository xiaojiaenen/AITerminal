"""AI Terminal — 智能终端管家。"""

__version__ = "0.2.0"

from ai_terminal.app import AITerminalTUI
from ai_terminal.config import ClusterInventory, Config, HostConfig

__all__ = ["AITerminalTUI", "Config", "HostConfig", "ClusterInventory"]
