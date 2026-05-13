"""Tests for sanitized config display data."""

from ai_terminal.config import Config
from ai_terminal.services.terminal_service import TerminalService


def test_config_view_masks_sensitive_values():
    config = Config()
    config.set("llm.api_key", "sk-test-1234567890")
    config.set("cluster.inventory_file", "~/.ai-terminal/inventory.yaml")
    service = TerminalService(config)

    rows = service.config_view()
    api_rows = [row for row in rows if row["key"] == "api_key"]
    path_rows = [row for row in rows if row["key"] == "inventory_file"]

    assert api_rows
    assert "sk-t" in api_rows[0]["value"]
    assert path_rows
    assert "inventory.yaml" in path_rows[0]["value"]


def test_execute_requires_confirmation_for_high_risk_command():
    service = TerminalService(Config())

    result = __import__("asyncio").run(service.execute("docker rm temp"))

    assert result["blocked"] is True
    assert result["needs_confirmation"] is True
