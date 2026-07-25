"""Command-line interface for HashSight."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import asdict
from typing import Any, Optional

try:
    import argcomplete
except ImportError:  # optional dependency
    argcomplete = None

from . import get_hash, get_signature
from .banner import show_banner

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_MIN_VISIBLE_CANDIDATE_CERTAINTY = 25
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _bounded_percent(value: str) -> int:
    """Parse an integer percent value constrained to 0..100."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer between 0 and 100") from exc
    if parsed < 0 or parsed > 100:
        raise argparse.ArgumentTypeError("must be an integer between 0 and 100")
    return parsed


def _format_hash_for_display(value: str, full_hash: bool = False) -> str:
    """Format hashes for human-readable CLI output.

    Default behavior keeps short hashes intact and compacts very long hashes to
    `prefix...suffix (len=N)` so table output remains readable.
    """
    if full_hash or len(value) <= 64:
        return value
    return f"{value[:24]}...{value[-16:]} (len={len(value)})"


def _format_hash_for_table(value: str) -> str:
    """Always return a masked hash preview for table output (never full hash)."""
    preview = value[: min(12, len(value))]
    return f"{preview}... (len={len(value)})"


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a simple fixed-width table for terminal output."""
    widths = [_display_len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], _display_len(cell))

    def _line(parts: list[str]) -> str:
        return " | ".join(_pad_cell(parts[i], widths[i]) for i in range(len(parts)))

    divider = "-+-".join("-" * w for w in widths)
    lines = [_line(headers), divider]
    lines.extend(_line(row) for row in rows)
    return "\n".join(lines)


def _display_len(value: str) -> int:
    """Length of text as displayed in terminal, excluding ANSI escape codes."""
    return len(_ANSI_RE.sub("", value))


def _pad_cell(value: str, width: int) -> str:
    """Right-pad cell while accounting for ANSI escape sequences."""
    pad = max(0, width - _display_len(value))
    return value + (" " * pad)


def _colors_enabled() -> bool:
    """Enable ANSI colors only for interactive terminals unless explicitly disabled."""
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _paint(text: str, *codes: str, enabled: bool) -> str:
    """Wrap text with ANSI styles when color is enabled."""
    if not enabled or not codes:
        return text
    return "".join(codes) + text + _RESET


def _certainty_color(certainty: str) -> str:
    """Map certainty percentages to a semantic color."""
    match = re.match(r"^(\d+)%$", certainty)
    if not match:
        return _DIM
    value = int(match.group(1))
    if value >= 90:
        return _GREEN
    if value >= 70:
        return _CYAN
    if value >= 50:
        return _YELLOW
    if value > 0:
        return _MAGENTA
    return _RED


def _confidence_profile(result: Any) -> tuple[str, str]:
    """Return certainty percentage and rationale based on confidence + candidates."""
    confidence = result.confidence

    if confidence == "Exact":
        return "100%", "Unique signature match."

    if confidence.startswith("Exact (unverified"):
        return "90%", "Format is unique, but mode numbering may drift across releases."

    if confidence == "Ambiguous":
        candidates = result.candidates or []
        if not candidates:
            return "50%", "Shape matches multiple families, but no ranked candidates available."

        scores = [c.get("match_score", c.get("popularity", 0) * 10) for c in candidates]
        top = scores[0]
        second = scores[1] if len(scores) > 1 else 0
        denom = max(top, 10)
        relative_gap = max(0.0, (top - second) / denom)

        # Count real rivals: candidates whose score is close enough to the top one
        # that they're still plausible. This scales with how decisive the win is,
        # instead of the old flat "number of siblings in the family" penalty, which
        # crushed certainty toward the floor for every large family (e.g. the 20-30
        # candidate bare-hex buckets) regardless of how one-sided the evidence was.
        band = max(6, top * 0.15)
        contenders = sum(1 for s in scores if (top - s) <= band)

        certainty = 42 + (relative_gap * 43)
        certainty -= min(18, (contenders - 1) * 3)
        if getattr(result, "hint_applied", False):
            certainty += 10
        if getattr(result, "deterministic_structural_match", False):
            certainty += 20
        elif getattr(result, "structural_hint_applied", False):
            certainty += 8
        certainty = int(round(max(20, min(96, certainty))))

        basis = "Multiple valid modes share this shape; ranked by popularity."
        if getattr(result, "hint_applied", False):
            basis += " Context hint matched candidate metadata and improved ranking confidence."
        if getattr(result, "deterministic_structural_match", False):
            basis += " The hash's salt length matches a documented, mandatory constraint for this format."
        elif getattr(result, "structural_hint_applied", False):
            basis += " The hash's own salt length/format matched this candidate's known structure."
        if contenders > 1:
            basis += f" {contenders} candidates remain closely competitive."
        return f"{certainty}%", basis

    if confidence == "Unknown":
        return "0%", "No signature matched the observed format."

    if confidence == "Invalid":
        return "0%", "Input was empty after trimming whitespace."

    return "0%", "No confidence profile available."


def _per_candidate_certainties(result: Any, top_certainty_pct: int) -> list[int]:
    """Scale the overall certainty down per-candidate based on relative match_score.

    Without this, every sibling in an ambiguous family (which can be 20-30+ entries)
    would display the exact same certainty as the top pick, which is misleading -
    a candidate with 1/10th the popularity and no matching evidence is obviously not
    as certain as the winner.
    """
    candidates = result.candidates or []
    if not candidates:
        return []

    scores = [max(0, c.get("match_score", c.get("popularity", 0) * 10)) for c in candidates]
    top_score = max(scores[0], 1)
    out = []
    for score in scores:
        ratio = score / top_score
        value = int(round(top_certainty_pct * ratio))
        out.append(max(3, min(top_certainty_pct, value)))
    return out


def _visible_candidates(
    candidates: list[dict[str, Any]], certainties: list[int], min_certainty: int
) -> list[tuple[dict[str, Any], int]]:
    """Return only candidates that meet the minimum display certainty threshold."""
    return [
        (candidate, certainty)
        for candidate, certainty in zip(candidates, certainties)
        if certainty >= min_certainty
    ]


def _emit_progress(enabled: bool, message: str) -> None:
    """Write progress updates to stderr to avoid polluting result output."""
    if enabled:
        if sys.stderr.isatty():
            print(f"{_GREEN}- {message}{_RESET}", file=sys.stderr)
        else:
            print(f"- {message}", file=sys.stderr)


def _read_hashes(args: argparse.Namespace) -> list[str]:
    if args.hash:
        return args.hash
    return [line.strip() for line in sys.stdin if line.strip()]


def _cmd_hash(args: argparse.Namespace) -> int:
    values = _read_hashes(args)
    if not values:
        return 0

    progress_enabled = args.progress
    if progress_enabled is None:
        progress_enabled = not args.json
    min_certainty = args.min_certainty

    results = []
    for value in values:
        _emit_progress(progress_enabled, f"analyzing hash (len={len(value)})")
        result = get_hash(
            value,
            exact_only=args.exact_only,
            top=args.top,
            context=args.context,
            full_mode=args.full_mode,
        )
        if result is not None:
            results.append(result)
            _emit_progress(progress_enabled, f"done: {result.confidence}")
        else:
            _emit_progress(progress_enabled, "filtered out by --exact-only")

    if args.json:
        payload = []
        for r in results:
            certainty, basis = _confidence_profile(r)
            item = asdict(r)
            if item.get("candidates"):
                candidate_certainties = _per_candidate_certainties(r, int(certainty.rstrip("%")))
                visible = _visible_candidates(item["candidates"], candidate_certainties, min_certainty)
                item["candidates"] = []
                for candidate, cand_certainty in visible:
                    candidate["john_format"] = candidate.get("john_format") or "-"
                    candidate["certainty"] = f"{cand_certainty}%"
                    item["candidates"].append(candidate)
            item["john_format"] = item.get("john_format") or "-"
            item["certainty"] = certainty
            item["certainty_basis"] = basis
            payload.append(item)
        print(json.dumps(payload, indent=2))
    else:
        if progress_enabled:
            print()

        color_enabled = _colors_enabled()

        summary_rows = []
        reasons = []
        for r in results:
            certainty, basis = _confidence_profile(r)
            hash_table = _format_hash_for_table(r.hash)

            if r.candidates:
                candidate_certainties = _per_candidate_certainties(r, int(certainty.rstrip("%")))
                visible = _visible_candidates(r.candidates, candidate_certainties, min_certainty)
                if not visible:
                    summary_rows.append(
                        [
                            str(r.name or "Ambiguous candidates hidden"),
                            "-",
                            "-",
                            str(r.category or "-"),
                            f"<{min_certainty}% filtered",
                            str(len(r.hash)),
                            hash_table,
                        ]
                    )
                for candidate, cand_certainty in visible:
                    certainty_text = f"{cand_certainty}%"
                    summary_rows.append(
                        [
                            _paint(str(candidate.get("name", "-")), _CYAN, enabled=color_enabled),
                            _paint(str(candidate.get("mode", "-")), _BLUE, enabled=color_enabled),
                            _paint(str(candidate.get("john_format") or "-"), _MAGENTA, enabled=color_enabled),
                            _paint(str(candidate.get("category", "-")), _DIM, enabled=color_enabled),
                            _paint(certainty_text, _certainty_color(certainty_text), _BOLD, enabled=color_enabled),
                            _paint(str(len(r.hash)), _DIM, enabled=color_enabled),
                            _paint(hash_table, _DIM, enabled=color_enabled),
                        ]
                    )
            else:
                summary_rows.append(
                    [
                        _paint("-" if r.name is None else r.name, _CYAN, enabled=color_enabled),
                        _paint("-" if r.mode is None else str(r.mode), _BLUE, enabled=color_enabled),
                        _paint(str(r.john_format or "-"), _MAGENTA, enabled=color_enabled),
                        _paint("-" if r.category is None else r.category, _DIM, enabled=color_enabled),
                        _paint(certainty, _certainty_color(certainty), _BOLD, enabled=color_enabled),
                        _paint(str(len(r.hash)), _DIM, enabled=color_enabled),
                        _paint(hash_table, _DIM, enabled=color_enabled),
                    ]
                )

            reasons.append((hash_table, basis))

        headers = ["Name", "Mode", "John", "Category", "Certainty", "Len", "Hash"]
        if color_enabled:
            headers = [_paint(h, _BOLD, _CYAN, enabled=True) for h in headers]

        print(
            _render_table(
                headers,
                summary_rows,
            )
        )

        print("\n" + _paint("Reasons:", _BOLD, _YELLOW, enabled=color_enabled))
        for hash_table, basis in reasons:
            hash_part = _paint(hash_table, _DIM, enabled=color_enabled)
            basis_part = _paint(basis, _DIM, enabled=color_enabled)
            print(f"- {hash_part}: {basis_part}")

    return 0


def _cmd_signature(args: argparse.Namespace) -> int:
    entries = get_signature(mode=args.mode, category=args.category, name=args.name)
    print(json.dumps(entries, indent=2))
    return 0


def _completion_snippet(shell: str) -> str:
    if shell == "zsh":
        return "\n".join(
            [
                "autoload -U compinit && compinit",
                "autoload -U bashcompinit && bashcompinit",
                "eval \"$(register-python-argcomplete hashsight)\"",
            ]
        )
    return 'eval "$(register-python-argcomplete hashsight)"'


def _cmd_completion(args: argparse.Namespace) -> int:
    register_path = shutil.which("register-python-argcomplete")
    hashsight_path = shutil.which("hashsight")
    has_argcomplete = argcomplete is not None

    if args.check:
        print(f"shell={args.shell}")
        print(f"hashsight={hashsight_path or 'MISSING'}")
        print(f"argcomplete_python_module={'OK' if has_argcomplete else 'MISSING'}")
        print(f"register_python_argcomplete={register_path or 'MISSING'}")

        ready = has_argcomplete and register_path is not None and hashsight_path is not None
        if ready:
            print("status=ready")
            print("snippet:")
            print(_completion_snippet(args.shell))
            return 0

        print("status=not-ready")
        print("hint: install completion extras with: python3 -m pip install '.[completion]'")
        print("hint: run the snippet after install:")
        print(_completion_snippet(args.shell))
        return 1

    print(_completion_snippet(args.shell))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hashsight",
        description="HashSight - identify hashcat modes from a hash string, without cracking anything.",
    )
    parser.add_argument("--no-banner", action="store_true", help="Suppress the startup banner.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    hash_parser = subparsers.add_parser("hash", help="Identify one or more hash strings.")
    hash_parser.add_argument("hash", nargs="*", help="Hash string(s) to identify. Reads stdin if omitted.")
    hash_parser.add_argument("--exact-only", action="store_true", help="Only show Exact matches.")
    hash_parser.add_argument("--top", type=int, default=None, help="Limit ambiguous candidates to the top N.")
    hash_parser.add_argument("--json", action="store_true", help="Output as JSON instead of a table.")
    hash_parser.add_argument(
        "--context",
        type=str,
        default=None,
        help="Optional context hint (e.g. 'windows ad', 'linux shadow', 'wordpress') to improve ambiguous ranking.",
    )
    hash_parser.add_argument(
        "--full-mode",
        action="store_true",
        help="Include broad catalog fallback candidates for otherwise-unknown hash-like input (can return many results).",
    )
    hash_parser.add_argument(
        "--full-hash",
        action="store_true",
        help="Show full hash in plain output instead of compact display.",
    )
    hash_parser.add_argument(
        "--no-progress",
        dest="progress",
        action="store_false",
        help="Disable progress updates while analyzing input hashes.",
    )
    hash_parser.add_argument(
        "--min-certainty",
        type=_bounded_percent,
        default=_MIN_VISIBLE_CANDIDATE_CERTAINTY,
        help="Hide ambiguous candidates below this certainty percentage (0-100, default: 25).",
    )
    hash_parser.set_defaults(func=_cmd_hash, progress=None)

    sig_parser = subparsers.add_parser("signature", help="List or search the signature database.")
    sig_parser.add_argument("--mode", type=int, default=None, help="Filter by hashcat mode number.")
    sig_parser.add_argument("--category", type=str, default=None, help="Filter by category.")
    sig_parser.add_argument("--name", type=str, default=None, help="Filter by name (contains, case-insensitive).")
    sig_parser.set_defaults(func=_cmd_signature)

    comp_parser = subparsers.add_parser("completion", help="Print or validate shell completion setup.")
    comp_parser.add_argument("shell", choices=["bash", "zsh"], help="Target shell to configure completion for.")
    comp_parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that completion prerequisites are installed and print status.",
    )
    comp_parser.set_defaults(func=_cmd_completion)

    if argcomplete is not None:
        argcomplete.autocomplete(parser)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Make `hash` optional: `hashsight <hash>` and `cat hashes.txt | hashsight`
    # behave like `hashsight hash <hash>` and `cat hashes.txt | hashsight hash`.
    known_subcommands = {"hash", "signature", "completion"}
    if argv:
        first = argv[0]
        if first in {"-h", "--help"}:
            pass
        elif first == "--no-banner":
            if len(argv) == 1 and not sys.stdin.isatty():
                argv = ["--no-banner", "hash"]
            elif len(argv) > 1 and argv[1] not in known_subcommands:
                argv = ["--no-banner", "hash", *argv[1:]]
        elif first not in known_subcommands:
            argv = ["hash", *argv]
    elif not sys.stdin.isatty():
        argv = ["hash"]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "completion" and not args.no_banner:
        show_banner()
        print()

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
