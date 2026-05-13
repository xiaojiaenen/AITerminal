"""Backward-compatible application entrypoints.

The interactive implementation now lives in ``ai_terminal.tui.app``.
This module remains as a stable import path for scripts, packaging,
and older callers that still import ``ai_terminal.app``.
"""

from ai_terminal.tui.app import AITerminalTUI, main

__all__ = ["AITerminalTUI", "main"]
