"""Tests for Claude response formatter."""

from __future__ import annotations

from code_messaging_bridge.services.claude.response_formatter import ResponseFormatter


def test_format_plain_text() -> None:
    """Plain text should pass through unchanged."""
    formatter = ResponseFormatter()
    assert formatter.format("Hello world") == "Hello world"


def test_format_empty_string() -> None:
    """Empty string should return fallback message."""
    formatter = ResponseFormatter()
    assert "empty response" in formatter.format("")


def test_format_markdown_link() -> None:
    """Markdown links should be converted to plain text with URL."""
    formatter = ResponseFormatter()
    result = formatter.format("Check [this page](https://example.com) out")
    assert result == "Check this page (https://example.com) out"


def test_format_multiple_markdown_links() -> None:
    """Multiple markdown links should all be converted."""
    formatter = ResponseFormatter()
    result = formatter.format("[one](http://1.com) and [two](http://2.com)")
    assert "one (http://1.com)" in result
    assert "two (http://2.com)" in result


def test_format_markdown_image() -> None:
    """Markdown images should be converted to plain text."""
    formatter = ResponseFormatter()
    result = formatter.format("See ![diagram](https://img.png) here")
    assert result == "See Image: diagram here"


def test_format_truncates_long_response() -> None:
    """Very long responses should be truncated."""
    formatter = ResponseFormatter()
    long_text = "x" * 20000
    result = formatter.format(long_text)
    assert len(result) < 20000
    assert "[Response truncated]" in result


def test_format_preserves_whitespace_formatting() -> None:
    """Basic whitespace formatting should be preserved."""
    formatter = ResponseFormatter()
    text = "Line 1\n\nLine 2\n- bullet"
    assert formatter.format(text) == text


def test_format_strips_surrounding_whitespace() -> None:
    """Leading/trailing whitespace should be stripped."""
    formatter = ResponseFormatter()
    assert formatter.format("  hello  ") == "hello"
