"""Message splitting logic for platform message length limits."""

from __future__ import annotations


class MessageSplitter:
    """Splits long messages into platform-safe chunks.

    Splitting strategy:
    1. Try to split on paragraph boundaries (double newline)
    2. Fall back to sentence boundaries (period + space)
    3. Fall back to word boundaries (space)
    4. Last resort: hard split at max_length

    Each part gets a prefix like "[1/3] " to indicate ordering.
    """

    _PART_PREFIX_TEMPLATE = "[{current}/{total}] "
    _MAX_PART_PREFIX_LEN = 8  # Reserve space for up to "[99/99] "

    def __init__(self, max_length: int = 1600) -> None:
        self._max_length = max_length

    def split(self, text: str) -> list[str]:
        """Split text into parts, each no longer than max_length.

        Returns a single-element list if no split is needed.
        """
        if len(text) <= self._max_length:
            return [text]

        effective_max = self._max_length - self._MAX_PART_PREFIX_LEN
        raw_parts = self._do_split(text, effective_max)
        total = len(raw_parts)
        return [f"[{i + 1}/{total}] {part}" for i, part in enumerate(raw_parts)]

    def _do_split(self, text: str, max_len: int) -> list[str]:
        """Recursively split text into chunks of at most max_len."""
        if len(text) <= max_len:
            return [text]

        # Try paragraph boundary
        split_pos = self._find_split_point(text, max_len, "\n\n")
        if split_pos == -1:
            # Try sentence boundary
            split_pos = self._find_split_point(text, max_len, ". ")
            if split_pos != -1:
                split_pos += 1  # Include the period
        if split_pos == -1:
            # Try word boundary
            split_pos = self._find_split_point(text, max_len, " ")
        if split_pos == -1:
            # Hard split
            split_pos = max_len

        first = text[:split_pos].rstrip()
        rest = text[split_pos:].lstrip()
        if not rest:
            return [first]
        return [first, *self._do_split(rest, max_len)]

    @staticmethod
    def _find_split_point(text: str, max_len: int, delimiter: str) -> int:
        """Find the last occurrence of delimiter within max_len characters."""
        pos = text.rfind(delimiter, 0, max_len)
        return pos if pos > 0 else -1
