"""Command-line entrypoint orchestration for HashSight."""
from __future__ import annotations

import sys
from typing import Optional

from .banner import show_banner
from .cli_commands import _emit_update_notice, _print_catalog_version
from .cli_parser import build_parser


def _normalize_argv(argv: list[str]) -> list[str]:
    """Normalize convenience command aliases and implicit hash mode."""
    known_subcommands = {"hash", "signature", "completion"}
    global_flags = {"--no-banner", "--no-update-check"}
    passthrough_flags = {"--version", "-h", "--help", "--catalog-version"}
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


def main(argv: Optional[list[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if "--catalog-version" in argv:
        return _print_catalog_version()

    stdin_is_tty = sys.stdin.isatty()

    # Running `hashsight` with no args should show help in interactive shells.
    if not argv and stdin_is_tty:
        if "--no-banner" not in argv:
            show_banner()
            print()
        parser = build_parser()
        parser.print_help()
        print()
        return 0

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
