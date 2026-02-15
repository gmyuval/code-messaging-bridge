"""Tests for message splitting logic."""

from __future__ import annotations

from code_messaging_bridge.services.messaging.message_splitter import MessageSplitter


def test_short_message_not_split() -> None:
    """Messages under the limit should not be split."""
    splitter = MessageSplitter(max_length=100)
    result = splitter.split("Hello world")
    assert result == ["Hello world"]


def test_exact_limit_not_split() -> None:
    """Messages exactly at the limit should not be split."""
    splitter = MessageSplitter(max_length=10)
    result = splitter.split("0123456789")
    assert result == ["0123456789"]


def test_empty_string_not_split() -> None:
    """Empty string should return single empty element."""
    splitter = MessageSplitter(max_length=100)
    result = splitter.split("")
    assert result == [""]


def test_split_on_paragraph_boundary() -> None:
    """Long messages should split on paragraph boundaries (double newline)."""
    splitter = MessageSplitter(max_length=50)
    text = "Short paragraph here.\n\nAnother paragraph here plus extra."
    result = splitter.split(text)
    assert len(result) == 2
    assert "[1/2]" in result[0]
    assert "[2/2]" in result[1]
    assert "Short paragraph" in result[0]
    assert "Another paragraph" in result[1]


def test_split_on_sentence_boundary() -> None:
    """Should fall back to sentence boundary when no paragraph break fits."""
    splitter = MessageSplitter(max_length=50)
    text = "First sentence is long enough to exceed the limit. Second sentence also exceeds it."
    result = splitter.split(text)
    assert len(result) >= 2
    # Each part should have a prefix
    for part in result:
        assert part.startswith("[")


def test_split_on_word_boundary() -> None:
    """Should fall back to word boundary when no sentence break fits."""
    splitter = MessageSplitter(max_length=30)
    text = "one two three four five six seven eight nine ten"
    result = splitter.split(text)
    assert len(result) >= 2
    # No word should be broken in the middle
    for part in result:
        # Remove prefix like "[1/3] "
        content = part.split("] ", 1)[1] if "] " in part else part
        assert not content.startswith(" ")


def test_hard_split_no_spaces() -> None:
    """Should hard-split when there are no word boundaries."""
    splitter = MessageSplitter(max_length=20)
    text = "a" * 50
    result = splitter.split(text)
    assert len(result) >= 3
    # Reconstruct original (minus prefixes)
    reconstructed = ""
    for part in result:
        content = part.split("] ", 1)[1] if "] " in part else part
        reconstructed += content
    assert reconstructed == text


def test_split_preserves_all_content() -> None:
    """Splitting should preserve all content from the original message."""
    splitter = MessageSplitter(max_length=50)
    text = "Word " * 30  # 150 chars
    result = splitter.split(text)
    # Reconstruct content without prefixes
    reconstructed = " ".join(part.split("] ", 1)[1] if "] " in part else part for part in result)
    assert text.strip() in reconstructed.replace("  ", " ").strip()


def test_part_indicators_correct() -> None:
    """Part indicators should show correct numbering."""
    splitter = MessageSplitter(max_length=30)
    text = "Hello world. " * 10
    result = splitter.split(text)
    total = len(result)
    for i, part in enumerate(result):
        expected_prefix = f"[{i + 1}/{total}]"
        assert part.startswith(expected_prefix)


def test_default_max_length_is_1600() -> None:
    """Default max_length should be 1600 (WhatsApp limit)."""
    splitter = MessageSplitter()
    assert splitter._max_length == 1600


def test_unicode_messages() -> None:
    """Splitting should handle Unicode characters correctly."""
    splitter = MessageSplitter(max_length=30)
    text = "Hello 🌍! " * 10
    result = splitter.split(text)
    assert len(result) >= 2
