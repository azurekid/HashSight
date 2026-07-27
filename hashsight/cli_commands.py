"""Command handlers and CLI utility helpers for HashSight."""
from __future__ import annotations

import argparse
import json
import select
import shutil
import sys
from dataclasses import asdict

try:
    import argcomplete
except ImportError:  # optional dependency
    argcomplete = None

from . import get_hash, get_signature_catalog_info, get_signature_catalog_version
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
from .update_check import get_signature_update_notice, get_update_notice
from .version import __version__

MIN_VISIBLE_CANDIDATE_CERTAINTY = 25
MIN_RESULT_CERTAINTY = 0


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
    # Avoid blocking on non-interactive stdin when no data is actually piped.
    readable, _, _ = select.select([sys.stdin], [], [], 0)
    if not readable:
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
    min_candidate_certainty = args.min_certainty
    min_result_certainty = args.min_result_certainty

    results = []
    for value in values:
        _emit_progress(progress_enabled, f"analyzing hash (len={len(value)})")
        result = get_hash(
            value,
            exact_only=args.exact_only,
            min_certainty=min_result_certainty,
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
                visible = visible_candidates(item["candidates"], certainties, min_candidate_certainty)
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
    previous_hash: str | None = None

    for result in results:
        certainty, basis = confidence_profile(result)
        hash_table = format_hash_for_table(result.hash)

        if previous_hash is not None and result.hash != previous_hash:
            summary_rows.append(["", "", "", "", "", "", ""])

        if result.candidates:
            certainties = per_candidate_certainties(result, int(certainty.rstrip("%")))
            visible = visible_candidates(result.candidates, certainties, min_candidate_certainty)
            if not visible:
                summary_rows.append(
                    [
                        str(result.name or "Ambiguous candidates hidden"),
                        "-",
                        "-",
                        str(result.category or "-"),
                        f"<{min_candidate_certainty}% filtered",
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
        previous_hash = result.hash

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


def _emit_update_notice(args: argparse.Namespace) -> None:
    """Optionally print a one-line update notice in interactive sessions."""
    if args.no_update_check:
        return
    if not sys.stderr.isatty():
        return

    notices = []
    package_notice = get_update_notice(__version__)
    if package_notice:
        notices.append(package_notice)

    catalog_notice = get_signature_update_notice(get_signature_catalog_version())
    if catalog_notice:
        notices.append(catalog_notice)

    if not notices:
        return

    color_enabled = colors_enabled()
    prefix = paint("update", BOLD, YELLOW, enabled=color_enabled)
    for notice in notices:
        body = paint(notice, DIM, enabled=color_enabled)
        print(f"{prefix}: {body}", file=sys.stderr)


def _print_catalog_version() -> int:
    """Print bundled signature catalog version metadata and exit."""
    info = get_signature_catalog_info()
    print(f"signatures {info.get('version', '-')}")
    print(f"top_level_signatures {info.get('signature_count', '-')}")
    print(f"candidate_entries {info.get('candidate_count', '-')}")
    print(f"mode_references {info.get('mode_reference_count', '-')}")
    print(f"unique_modes {info.get('unique_mode_count', '-')}")
    source = info.get("source") or "-"
    print(f"source {source}")
    return 0
