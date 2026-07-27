"""Argument parser construction for HashSight CLI."""
from __future__ import annotations

import argparse
from typing import Any, Optional

try:
    import argcomplete
except ImportError:  # optional dependency
    argcomplete = None

from ..version import __version__
from .commands import (
    MIN_RESULT_CERTAINTY,
    MIN_VISIBLE_CANDIDATE_CERTAINTY,
    _bounded_percent,
    _cmd_completion,
    _cmd_hash,
    _cmd_signature,
)


def _cfg_section(config: Optional[dict[str, Any]], key: str) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    section = config.get(key)
    return section if isinstance(section, dict) else {}


def _cfg_int(section: dict[str, Any], key: str, default: int) -> int:
    value = section.get(key, default)
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _cfg_int_alias(section: dict[str, Any], keys: list[str], default: int) -> int:
    for key in keys:
        if key in section:
            return _cfg_int(section, key, default)
    return default


def _cfg_str(section: dict[str, Any], key: str, default: Optional[str]) -> Optional[str]:
    value = section.get(key, default)
    if value is None:
        return None
    return str(value)


def _cfg_bool(section: dict[str, Any], key: str, default: bool) -> bool:
    value = section.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _cfg_optional_bool(section: dict[str, Any], key: str, default: Optional[bool]) -> Optional[bool]:
    if key not in section:
        return default
    value = section.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def build_parser(config: Optional[dict[str, Any]] = None) -> argparse.ArgumentParser:
    global_cfg = _cfg_section(config, "global")
    hash_cfg = _cfg_section(config, "hash")
    signature_cfg = _cfg_section(config, "signature")

    default_no_banner = _cfg_bool(global_cfg, "no_banner", False)
    default_no_update_check = _cfg_bool(global_cfg, "no_update_check", False)

    default_hash_exact_only = _cfg_bool(hash_cfg, "exact_only", False)
    default_hash_top = _cfg_int(hash_cfg, "top", None) if hash_cfg.get("top") is not None else None
    default_hash_json = _cfg_bool(hash_cfg, "json", False)
    default_hash_context = _cfg_str(hash_cfg, "context", None)
    default_hash_full_mode = _cfg_bool(hash_cfg, "full_mode", False)
    default_hash_full_hash = _cfg_bool(hash_cfg, "full_hash", False)
    default_hash_progress = _cfg_optional_bool(hash_cfg, "progress", None)
    default_hash_min_certainty = _cfg_int_alias(
        hash_cfg,
        ["min_candidate_certainty", "min_certainty"],
        MIN_VISIBLE_CANDIDATE_CERTAINTY,
    )
    default_hash_min_result_certainty = _cfg_int_alias(
        hash_cfg,
        ["min_overall_certainty", "min_result_certainty"],
        MIN_RESULT_CERTAINTY,
    )

    default_sig_mode = _cfg_int(signature_cfg, "mode", None) if signature_cfg.get("mode") is not None else None
    default_sig_category = _cfg_str(signature_cfg, "category", None)
    default_sig_name = _cfg_str(signature_cfg, "name", None)
    default_sig_top = _cfg_int(signature_cfg, "top", 20)
    default_sig_json = _cfg_bool(signature_cfg, "json", False)

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
            "Configuration file defaults:\n"
            "  Global config: ~/.config/hashsight/config.json\n"
            "  Local default: ./config.json\n"
            "  Local override: ./.hashsight.json\n"
            "  Explicit override: HASHSIGHT_CONFIG=/path/to/config.json\n\n"
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
    parser.add_argument("--no-banner", action="store_true", default=default_no_banner, help="Suppress the startup banner.")
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
        default=default_no_update_check,
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
    hash_parser.add_argument("--exact-only", action="store_true", default=default_hash_exact_only, help="Only show Exact matches.")
    hash_parser.add_argument("--top", type=int, default=default_hash_top, help="Limit ambiguous candidates to the top N.")
    hash_parser.add_argument("--json", action="store_true", default=default_hash_json, help="Output as JSON instead of a table.")
    hash_parser.add_argument(
        "--context",
        type=str,
        default=default_hash_context,
        help="Optional context hint (e.g. 'windows ad', 'linux shadow', 'wordpress') to improve ambiguous ranking.",
    )
    hash_parser.add_argument(
        "--full-mode",
        action="store_true",
        default=default_hash_full_mode,
        help="Include broad catalog fallback candidates for otherwise-unknown hash-like input (can return many results).",
    )
    hash_parser.add_argument(
        "--full-hash",
        action="store_true",
        default=default_hash_full_hash,
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
        default=default_hash_min_certainty,
        help=(
            "Hide ambiguous candidates below this certainty percentage "
            f"(0-100, default: {default_hash_min_certainty})."
        ),
    )
    hash_parser.add_argument(
        "--min-result-certainty",
        type=_bounded_percent,
        default=default_hash_min_result_certainty,
        help=(
            "Ignore whole hash results below this certainty percentage "
            f"(0-100, default: {default_hash_min_result_certainty})."
        ),
    )
    hash_parser.set_defaults(func=_cmd_hash, progress=default_hash_progress)

    sig_parser = subparsers.add_parser("signature", help="List or search the signature database.")
    sig_parser.add_argument("--mode", type=int, default=default_sig_mode, help="Filter by hashcat mode number.")
    sig_parser.add_argument("--category", type=str, default=default_sig_category, help="Filter by category.")
    sig_parser.add_argument("--name", type=str, default=default_sig_name, help="Search by signature/candidate name.")
    sig_parser.add_argument(
        "--top",
        type=int,
        default=default_sig_top,
        help=f"Limit ranked signature search results (default: {default_sig_top}).",
    )
    sig_parser.add_argument("--json", action="store_true", default=default_sig_json, help="Output signature search results as JSON.")
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
