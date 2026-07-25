"""Command-line interface for HashSight."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from typing import Optional

try:
    import argcomplete
except ImportError:  # optional dependency
    argcomplete = None

from . import get_hash
from .banner import show_banner
from .hash_confidence import confidence_profile, per_candidate_certainties, visible_candidates
from .signature_search import signature_search_rows
from .terminal_ui import (
    BOLD,
    CYAN,
    DIM,
    GREEN,
    MAGENTA,
    WHITE,
    YELLOW,
    certainty_color,
    colors_enabled,
    format_hash_for_table,
    paint,
    render_table,
)
from .update_check import get_update_notice
from .version import __version__

MIN_VISIBLE_CANDIDATE_CERTAINTY = 25


def _bounded_percent(value: str) -> int:
    """Parse an integer percent value constrained to 0..100."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer between 0 and 100") from exc
    if parsed < 0 or parsed > 100:
        raise argparse.ArgumentTypeError("must be an integer between 0 and 100")
    return parsed


def _emit_progress(enabled: bool, message: str) -> None:
    """Write progress updates to stderr to avoid polluting result output."""
    if not enabled:
        return
    if sys.stderr.isatty():
        print(f"{GREEN}- {message}\033[0m", file=sys.stderr)
    else:
        print(f"- {message}", file=sys.stderr)


def _read_hashes(args: argparse.Namespace) -> list[str]:
    if args.hash:
        return args.hash
    if sys.stdin.isatty():
        return []
    return [line.strip() for line in sys.stdin if line.strip()]


def _cmd_hash(args: argparse.Namespace) -> int:
    values = _read_hashes(args)
    if not values:
        print(
            "No hash input provided. Pass one or more hashes, or pipe input via stdin.",
            file=sys.stderr,
        )
        return 2

    progress_enabled = args.progress if args.progress is not None else not args.json
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
        for result in results:
            certainty, basis = confidence_profile(result)
            item = asdict(result)
            if item.get("candidates"):
                certainties = per_candidate_certainties(result, int(certainty.rstrip("%")))
                visible = visible_candidates(item["candidates"], certainties, min_certainty)
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
        return 0

    if progress_enabled:
        print()

    color_enabled = colors_enabled()
    summary_rows: list[list[str]] = []
    reasons: list[tuple[str, str]] = []

    for result in results:
        certainty, basis = confidence_profile(result)
        hash_table = format_hash_for_table(result.hash)

        if result.candidates:
            certainties = per_candidate_certainties(result, int(certainty.rstrip("%")))
            visible = visible_candidates(result.candidates, certainties, min_certainty)
            if not visible:
                summary_rows.append(
                    [
                        str(result.name or "Ambiguous candidates hidden"),
                        "-",
                        "-",
                        str(result.category or "-"),
                        f"<{min_certainty}% filtered",
                        str(len(result.hash)),
                        hash_table,
                    ]
                )
            for candidate, cand_certainty in visible:
                certainty_text = f"{cand_certainty}%"
                summary_rows.append(
                    [
                        paint(str(candidate.get("name", "-")), CYAN, enabled=color_enabled),
                        paint(
                            str(candidate["mode"]) if candidate.get("mode") is not None else "-",
                            WHITE,
                            BOLD,
                            enabled=color_enabled,
                        ),
                        paint(str(candidate.get("john_format") or "-"), MAGENTA, enabled=color_enabled),
                        paint(str(candidate.get("category", "-")), DIM, enabled=color_enabled),
                        paint(certainty_text, certainty_color(certainty_text), BOLD, enabled=color_enabled),
                        paint(str(len(result.hash)), DIM, enabled=color_enabled),
                        paint(hash_table, DIM, enabled=color_enabled),
                    ]
                )
        else:
            summary_rows.append(
                [
                    paint("-" if result.name is None else result.name, CYAN, enabled=color_enabled),
                    paint("-" if result.mode is None else str(result.mode), WHITE, BOLD, enabled=color_enabled),
                    paint(str(result.john_format or "-"), MAGENTA, enabled=color_enabled),
                    paint("-" if result.category is None else result.category, DIM, enabled=color_enabled),
                    paint(certainty, certainty_color(certainty), BOLD, enabled=color_enabled),
                    paint(str(len(result.hash)), DIM, enabled=color_enabled),
                    paint(hash_table, DIM, enabled=color_enabled),
                ]
            )

        reasons.append((hash_table, basis))

    headers = ["Name", "Mode", "John", "Category", "Certainty", "Len", "Hash"]
    if color_enabled:
        headers = [paint(h, BOLD, CYAN, enabled=True) for h in headers]
    print(render_table(headers, summary_rows))

    print("\n" + paint("Reasons:", BOLD, YELLOW, enabled=color_enabled))
    for hash_table, basis in reasons:
        print(
            f"- {paint(hash_table, DIM, enabled=color_enabled)}: "
            f"{paint(basis, DIM, enabled=color_enabled)}"
        )
    print()

    return 0


def _cmd_signature(args: argparse.Namespace) -> int:
    rows = signature_search_rows(mode=args.mode, category=args.category, name=args.name)
    if args.top is not None:
        rows = rows[: args.top]

    if args.json:
        payload = [
            {
                "name": row["name"],
                "mode": row["mode"],
                "john_format": row["john"],
                "category": row["category"],
                "certainty": f"{row['certainty']}%",
            }
            for row in rows
        ]
        print(json.dumps(payload, indent=2))
        return 0

    color_enabled = colors_enabled()
    summary_rows = []
    for row in rows:
        certainty_text = f"{row['certainty']}%"
        summary_rows.append(
            [
                paint(str(row["name"]), CYAN, enabled=color_enabled),
                paint(str(row["mode"]) if row["mode"] is not None else "-", WHITE, BOLD, enabled=color_enabled),
                paint(str(row["john"]), MAGENTA, enabled=color_enabled),
                paint(str(row["category"]), DIM, enabled=color_enabled),
                paint(certainty_text, certainty_color(certainty_text), BOLD, enabled=color_enabled),
            ]
        )

    headers = ["Name", "Mode", "John", "Category", "Certainty"]
    if color_enabled:
        headers = [paint(h, BOLD, CYAN, enabled=True) for h in headers]

    if summary_rows:
        print(render_table(headers, summary_rows))
    else:
        print("No signatures matched the provided filters.")
    print()
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


def _normalize_argv(argv: list[str]) -> list[str]:
    """Normalize convenience command aliases and implicit hash mode."""
    known_subcommands = {"hash", "signature", "completion"}
    global_flags = {"--no-banner", "--no-update-check"}
    passthrough_flags = {"--version", "-h", "--help"}
    alias_to_command = {
        "--hash": "hash",
        "--signature": "signature",
        "--completion": "completion",
    }

    prefix: list[str] = []
    while argv and argv[0] in global_flags:
        prefix.append(argv[0])
        argv = argv[1:]

    if not argv:
        if not sys.stdin.isatty():
            return [*prefix, "hash"]
        return prefix

    first = argv[0]

    # Keep top-level parser flags as-is.
    if first in passthrough_flags:
        return [*prefix, *argv]

    # Explicit long-form command aliases.
    if first in alias_to_command:
        return [*prefix, alias_to_command[first], *argv[1:]]

    # Existing explicit subcommands.
    if first in known_subcommands:
        return [*prefix, *argv]

    # Default to hash mode for direct hash args and piped input.
    return [*prefix, "hash", *argv]


def _emit_update_notice(args: argparse.Namespace) -> None:
    """Optionally print a one-line update notice in interactive sessions."""
    if args.no_update_check:
        return
    if not sys.stderr.isatty():
        return
    notice = get_update_notice(__version__)
    if not notice:
        return
    color_enabled = colors_enabled()
    prefix = paint("update", BOLD, YELLOW, enabled=color_enabled)
    body = paint(notice, DIM, enabled=color_enabled)
    print(f"{prefix}: {body}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hashsight",
        description="HashSight - identify hashcat modes from a hash string, without cracking anything.",
        epilog=(
            "Command aliases:\n"
            "  --hash         alias for the 'hash' command\n"
            "  --signature    alias for the 'signature' command\n"
            "  --completion   alias for the 'completion' command\n\n"
            "Feedback / pull requests:\n"
            "  Open issues or PRs at: https://github.com/azurekid/HashSight\n"
            "  Include the output of: hashsight --help and your sample hash shape (masked).\n\n"
            "Version checks:\n"
            "  HashSight checks PyPI for new versions in interactive sessions (cached daily).\n"
            "  Disable with: --no-update-check or HASHSIGHT_NO_UPDATE_CHECK=1\n\n"
            "Examples:\n"
            "  hashsight --hash '$6$rounds=5000$abc$def...'\n"
            "  hashsight '$6$rounds=5000$abc$def...'\n"
            "  hashsight --hash < hashes.txt\n"
            "  hashsight --signature --mode 1800\n"
            "  hashsight --completion zsh --check"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--no-banner", action="store_true", help="Suppress the startup banner.")
    parser.add_argument(
        "--version",
        action="version",
        version=f"hashsight {__version__}",
        help="Show HashSight version and exit.",
    )
    parser.add_argument(
        "--no-update-check",
        action="store_true",
        help="Disable automatic update checks for newer releases.",
    )
    parser.add_argument(
        "--hash",
        dest="hash_alias",
        action="store_true",
        help="Alias for the 'hash' command (supports direct hashes and stdin).",
    )
    parser.add_argument(
        "--signature",
        dest="signature_alias",
        action="store_true",
        help="Alias for the 'signature' command.",
    )
    parser.add_argument(
        "--completion",
        dest="completion_alias",
        action="store_true",
        help="Alias for the 'completion' command.",
    )

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
        default=MIN_VISIBLE_CANDIDATE_CERTAINTY,
        help="Hide ambiguous candidates below this certainty percentage (0-100, default: 25).",
    )
    hash_parser.set_defaults(func=_cmd_hash, progress=None)

    sig_parser = subparsers.add_parser("signature", help="List or search the signature database.")
    sig_parser.add_argument("--mode", type=int, default=None, help="Filter by hashcat mode number.")
    sig_parser.add_argument("--category", type=str, default=None, help="Filter by category.")
    sig_parser.add_argument("--name", type=str, default=None, help="Search by signature/candidate name.")
    sig_parser.add_argument("--top", type=int, default=20, help="Limit ranked signature search results (default: 20).")
    sig_parser.add_argument("--json", action="store_true", help="Output signature search results as JSON.")
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

    # Show logo on help output (unless user explicitly suppresses the banner).
    if any(arg in {"-h", "--help"} for arg in argv) and "--no-banner" not in argv:
        show_banner()
        print()

    argv = _normalize_argv(argv)

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "completion" and not args.no_banner:
        show_banner()
        print()
    if args.command != "completion":
        _emit_update_notice(args)

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
