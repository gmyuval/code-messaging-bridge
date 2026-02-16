"""Tests for Claude Code CLI runner."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

from code_messaging_bridge.services.claude.runner import ClaudeCodeRunner
from code_messaging_bridge.services.claude.schemas import ClaudeInvocation


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.claude_cli_path = "claude"
    return settings


def test_build_command_basic() -> None:
    """Should build basic CLI command with required flags."""
    runner = ClaudeCodeRunner(_make_settings())
    invocation = ClaudeInvocation(
        prompt="Hello",
        working_directory="/tmp/project",
        max_turns=5,
    )
    cmd = runner._build_command(invocation)
    assert "claude" in cmd
    assert "-p" in cmd
    assert "Hello" in cmd
    assert "--output-format" in cmd
    assert "json" in cmd
    assert "--max-turns" in cmd
    assert "5" in cmd
    assert "--cwd" in cmd
    assert "/tmp/project" in cmd


def test_build_command_with_session_id() -> None:
    """Should include --resume when session_id is provided."""
    runner = ClaudeCodeRunner(_make_settings())
    invocation = ClaudeInvocation(prompt="Hello", session_id="abc-123")
    cmd = runner._build_command(invocation)
    assert "--resume" in cmd
    assert "abc-123" in cmd


def test_build_command_without_session_id() -> None:
    """Should not include --resume when no session_id."""
    runner = ClaudeCodeRunner(_make_settings())
    invocation = ClaudeInvocation(prompt="Hello")
    cmd = runner._build_command(invocation)
    assert "--resume" not in cmd


def test_build_command_with_allowed_tools() -> None:
    """Should include --allowedTools with comma-separated list."""
    runner = ClaudeCodeRunner(_make_settings())
    invocation = ClaudeInvocation(prompt="Hello", allowed_tools=["Read", "Bash"])
    cmd = runner._build_command(invocation)
    assert "--allowedTools" in cmd
    idx = cmd.index("--allowedTools")
    assert cmd[idx + 1] == "Read,Bash"


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_invoke_success(mock_run: MagicMock) -> None:
    """Should parse successful JSON output from Claude CLI."""
    output = json.dumps({
        "type": "result",
        "result": "Here is your answer.",
        "session_id": "sess-456",
        "cost_usd": 0.05,
        "duration_ms": 5000,
        "num_turns": 3,
        "is_error": False,
    })
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=output, stderr=""
    )

    runner = ClaudeCodeRunner(_make_settings())
    result = runner.invoke(ClaudeInvocation(prompt="test"))

    assert result.success is True
    assert result.output == "Here is your answer."
    assert result.session_id == "sess-456"
    assert result.cost_usd == 0.05
    assert result.duration_ms == 5000
    assert result.num_turns == 3


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_invoke_cli_error(mock_run: MagicMock) -> None:
    """Should handle non-zero exit code."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="Some CLI error"
    )

    runner = ClaudeCodeRunner(_make_settings())
    result = runner.invoke(ClaudeInvocation(prompt="test"))

    assert result.success is False
    assert "Some CLI error" in (result.error_message or "")


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_invoke_is_error_flag(mock_run: MagicMock) -> None:
    """Should detect is_error flag in JSON output."""
    output = json.dumps({
        "result": "Something went wrong",
        "is_error": True,
        "session_id": "sess-789",
    })
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=output, stderr=""
    )

    runner = ClaudeCodeRunner(_make_settings())
    result = runner.invoke(ClaudeInvocation(prompt="test"))

    assert result.success is False
    assert result.error_message == "Something went wrong"
    assert result.session_id == "sess-789"


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_invoke_timeout(mock_run: MagicMock) -> None:
    """Should handle subprocess timeout."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=600)

    runner = ClaudeCodeRunner(_make_settings())
    result = runner.invoke(ClaudeInvocation(prompt="test"))

    assert result.success is False
    assert "timed out" in (result.error_message or "")


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_invoke_cli_not_found(mock_run: MagicMock) -> None:
    """Should handle missing Claude CLI binary."""
    mock_run.side_effect = FileNotFoundError()

    runner = ClaudeCodeRunner(_make_settings())
    result = runner.invoke(ClaudeInvocation(prompt="test"))

    assert result.success is False
    assert "not found" in (result.error_message or "")


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_invoke_non_json_output(mock_run: MagicMock) -> None:
    """Should handle plain text output gracefully."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="Just plain text output", stderr=""
    )

    runner = ClaudeCodeRunner(_make_settings())
    result = runner.invoke(ClaudeInvocation(prompt="test"))

    assert result.success is True
    assert result.output == "Just plain text output"
