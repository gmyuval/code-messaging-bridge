"""Claude Code CLI subprocess wrapper."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from typing import TYPE_CHECKING

from code_messaging_bridge.services.claude.schemas import ClaudeResult

if TYPE_CHECKING:
    from code_messaging_bridge.config import Settings
    from code_messaging_bridge.services.claude.schemas import ClaudeInvocation

logger = logging.getLogger(__name__)


class ClaudeCodeRunner:
    """Invokes the Claude Code CLI as a subprocess and parses its JSON output."""

    _DEFAULT_TIMEOUT = 600  # 10 minutes
    _MAX_RETRIES = 2
    _BASE_BACKOFF = 5  # seconds

    def __init__(self, settings: Settings) -> None:
        self._cli_path = settings.claude_cli_path
        self._timeout = self._DEFAULT_TIMEOUT

    def _build_command(self, invocation: ClaudeInvocation) -> list[str]:
        """Build the CLI command list from an invocation."""
        cmd = [
            self._cli_path,
            "-p",
            invocation.prompt,
            "--output-format",
            "json",
            "--max-turns",
            str(invocation.max_turns),
            "--cwd",
            invocation.working_directory,
        ]
        if invocation.session_id:
            cmd.extend(["--resume", invocation.session_id])
        if invocation.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(invocation.allowed_tools)])
        return cmd

    def invoke(self, invocation: ClaudeInvocation) -> ClaudeResult:
        """Run the Claude CLI and return the parsed result."""
        cmd = self._build_command(invocation)
        logger.info(
            "Running Claude CLI (prompt_len=%d, session_id=%s)",
            len(invocation.prompt),
            invocation.session_id,
        )

        try:
            result = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.error("Claude CLI timed out after %d seconds", self._timeout)
            return ClaudeResult(
                success=False,
                output="",
                error_message=f"Claude CLI timed out after {self._timeout} seconds",
            )
        except FileNotFoundError:
            logger.error("Claude CLI not found at: %s", self._cli_path)
            return ClaudeResult(
                success=False,
                output="",
                error_message=f"Claude CLI not found at: {self._cli_path}",
            )

        if result.returncode != 0:
            logger.warning(
                "Claude CLI exited with code %d: %s",
                result.returncode,
                result.stderr[:200] if result.stderr else "(no stderr)",
            )
            return ClaudeResult(
                success=False,
                output=result.stdout,
                error_message=result.stderr or f"CLI exited with code {result.returncode}",
            )

        return self._parse_output(result.stdout)

    def invoke_with_retry(self, invocation: ClaudeInvocation) -> ClaudeResult:
        """Invoke Claude CLI with automatic retries on transient failures.

        Retries on non-zero exit codes with exponential backoff.
        Does NOT retry on timeout (would take too long) or file-not-found.
        """
        last_result: ClaudeResult | None = None
        for attempt in range(self._MAX_RETRIES + 1):
            result = self.invoke(invocation)

            if result.success:
                return result

            last_result = result

            # Don't retry on timeout or missing CLI
            if result.error_message and (
                "timed out" in result.error_message or "not found" in result.error_message
            ):
                return result

            if attempt < self._MAX_RETRIES:
                backoff = self._BASE_BACKOFF * (2**attempt)
                logger.info("Retrying Claude CLI in %d seconds (attempt %d)", backoff, attempt + 2)
                time.sleep(backoff)

        assert last_result is not None
        return last_result

    @staticmethod
    def _parse_output(stdout: str) -> ClaudeResult:
        """Parse the JSON output from Claude CLI."""
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return ClaudeResult(success=True, output=stdout.strip())

        is_error = data.get("is_error", False)
        return ClaudeResult(
            success=not is_error,
            output=data.get("result", ""),
            session_id=data.get("session_id"),
            error_message=data.get("result") if is_error else None,
            cost_usd=data.get("cost_usd"),
            duration_ms=data.get("duration_ms"),
            num_turns=data.get("num_turns"),
        )
