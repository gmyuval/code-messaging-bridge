"""Format Claude Code output for WhatsApp delivery."""

from __future__ import annotations

import re


class ResponseFormatter:
    """Converts Claude CLI output into WhatsApp-friendly text.

    - Converts markdown links to plain text with URL
    - Removes markdown images
    - Truncates extremely long responses
    """

    _MAX_RESPONSE_LENGTH = 10000

    def format(self, text: str) -> str:
        """Format Claude output for WhatsApp delivery."""
        if not text:
            return "Claude returned an empty response."

        # Remove markdown images ![alt](url) → "Image: alt" (must run before link regex)
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"Image: \1", text)

        # Convert markdown links [text](url) → "text (url)"
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)

        # Truncate if too long
        if len(text) > self._MAX_RESPONSE_LENGTH:
            text = text[: self._MAX_RESPONSE_LENGTH] + "\n\n[Response truncated]"

        return text.strip()
