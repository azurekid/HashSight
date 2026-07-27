"""Argument parser construction for HashSight CLI."""
from __future__ import annotations

import argparse

try:
    import argcomplete
except ImportError:  # optional dependency
    argcomplete = None

from .cli_commands import (
    MIN_RESULT_CERTAINTY,
    MIN_VISIBLE_CANDIDATE_CERTAINTY,
    _bounded_percent,
    _cmd_completion,
    _cmd_hash,
    _cmd_signature,
)
from .version import __version__


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
            "  HashSight checks PyPI and signatures catalog versions in interactive sessions (cached daily).\n"
            "  Disable with: --no-update-check or HASHSIGHT_NO_UPDATE_CHECK=1\n\n"
            "Certainty thresholds:\n"
            "  Candidate threshold: hashsight hash --min-certainty N '<hash>'\n"
            "  Result threshold:    hashsight hash --min-result-certainty N '<hash>'\n"
            "  See full hash options: hashsight hash --help\n\n"
            "Catalog version:\n"
            "  Show bundled signatures version: hashsight --catalog-version\n\n"
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
        "--catalog-version",
        action="store_true",
        help="Show bundled signatures catalog version metadata and exit.",
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
    hash_parser.add_argument(
        "--min-result-certainty",
        type=_bounded_percent,
        default=MIN_RESULT_CERTAINTY,
        help="Ignore whole hash results below this certainty percentage (0-100, default: 0).",
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
