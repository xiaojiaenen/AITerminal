"""AI Terminal — 智能终端管家。"""

__version__ = "0.1.0"

from ai_terminal.app import AITerminal
from ai_terminal.config import Config, HostConfig, ClusterInventory

__all__ = ["AITerminal", "Config", "HostConfig", "ClusterInventory"]
