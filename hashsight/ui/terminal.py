"""Terminal rendering helpers for HashSight CLI."""
from __future__ import annotations

import os
import re
import sys

GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
RED = "\033[31m"
WHITE = "\033[97m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def colors_enabled() -> bool:
    """Enable ANSI colors only for interactive terminals unless disabled."""
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def paint(text: str, *codes: str, enabled: bool) -> str:
    """Wrap text with ANSI styles when color is enabled."""
    if not enabled or not codes:
        return text
    return "".join(codes) + text + RESET


def certainty_color(certainty: str) -> str:
    """Map certainty percentages to a semantic color."""
    match = re.match(r"^(\d+)%$", certainty)
    if not match:
        return DIM
    value = int(match.group(1))
    if value >= 90:
        return GREEN
    if value >= 70:
        return CYAN
    if value >= 50:
        return YELLOW
    if value > 0:
        return MAGENTA
    return RED


def format_hash_for_table(value: str) -> str:
    """Always return a masked hash preview for table output."""
    preview = value[: min(12, len(value))]
    return f"{preview}... (len={len(value)})"


def _display_len(value: str) -> int:
    """Length of text as displayed in terminal, excluding ANSI codes."""
    return len(_ANSI_RE.sub("", value))


def _pad_cell(value: str, width: int) -> str:
    """Right-pad cell while accounting for ANSI escape sequences."""
    pad = max(0, width - _display_len(value))
    return value + (" " * pad)


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a fixed-width table for terminal output."""
    widths = [_display_len(h) for h in headers]
    for row in rows:
        if not row or all(cell == "" for cell in row):
            continue
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], _display_len(cell))

    def _line(parts: list[str]) -> str:
        if not parts or all(cell == "" for cell in parts):
            return ""
        return " | ".join(_pad_cell(parts[i], widths[i]) for i in range(len(parts)))

    divider = "-+-".join("-" * w for w in widths)
    lines = [_line(headers), divider]
    lines.extend(_line(row) for row in rows)
    return "\n".join(lines)
