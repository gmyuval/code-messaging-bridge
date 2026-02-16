"""Claude Code CLI invocation and result schemas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClaudeInvocation:
    """Typed request for invoking the Claude Code CLI."""

    prompt: str
    session_id: str | None = None
    working_directory: str = "."
    max_turns: int = 10
    allowed_tools: list[str] = field(
        default_factory=lambda: ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]
    )


@dataclass(frozen=True)
class ClaudeResult:
    """Typed result from a Claude Code CLI invocation."""

    success: bool
    output: str
    session_id: str | None = None
    error_message: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
