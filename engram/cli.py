"""Command-line interface for working with an Engram vault.

Use the CLI when you want to record text, recall exact or containing memory
items, search by query, or inspect vault maintenance state from the shell.

The common path is:
1. `engram init`
2. `engram record "TEXT"`
3. `engram recall MID` or `engram search "QUERY"`
4. `engram context` when an agent needs a multi-horizon prompt
5. `engram vault ...` when you need inspection or repair details

Spec references:
- docs/specs/11-minimum-write-search-context-slice.md [MWS-27], [MWS-28]
- docs/specs/12-local-app-surface.md [LAS-8], [LAS-12], [LAS-20]
- docs/specs/13-context-assembly-and-arcs.md [CAA-11]
- docs/specs/15-foundation-contracts-and-invariants.md [FCI-24], [FCI-25]
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
from pathlib import Path
from typing import Any, NoReturn

from engram._constants import (
    DEFAULT_IMPORTANCE,
    EXIT_ERROR,
    EXIT_NOT_FOUND,
    EXIT_SUCCESS,
    RECALL_SCOPE_ITEM,
    __version__,
    normalize_recall_scope,
    recall_scope_tier,
)
from engram._exceptions import (
    EngramError,
    MemoryItemNotFoundError,
    VaultNotFoundError,
)
from engram.commands import memory as commands

HELP_FORMATTER = argparse.RawDescriptionHelpFormatter
CLI_EPILOG = "Run `engram COMMAND --help` for command-specific guidance."
VAULT_ARG_HELP = (
    "Path to the target Engram vault. Omit this to use the default vault resolution."
)
JSON_ARG_HELP = "Emit the command result as machine-readable JSON."
RECALL_JSON_ARG_HELP = (
    "Emit the recalled item as JSON. This flag is accepted for output-contract "
    "symmetry."
)
INIT_HELP = """Use init to create a new Engram vault.

Initialize a vault once per memory namespace. This creates the local state
store, retrieval index location, and embedded runtime scaffolding so later
commands can record and recall against the same durable memory.
"""
VERSION_HELP = """Use version when you need the installed Engram build string.

This is mainly for debugging, support, and release checks.
"""
VAULT_HELP = """Use vault subcommands when you need inspection or maintenance.

The `vault` group is for operational tasks such as health inspection, local
repair, and index rebuild. Day-to-day read and write work stays on the top
level through commands like `record`, `search`, `context`, and `recall`.
"""


def main(argv: list[str] | None = None) -> int:
    """Run the Engram CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    memory: Any | None = None

    if args.command == "version":
        print(__version__)
        return EXIT_SUCCESS

    try:
        vault_path = Path(args.vault).expanduser() if args.vault is not None else None
        memory = commands.open_vault(vault_path, create=args.command == "init")
        if args.command == "init":
            if args.json:
                print(json.dumps({"vault_path": str(memory.vault_path)}))
            else:
                print(memory.vault_path)
            return EXIT_SUCCESS
        if args.command == "record":
            item_id = commands.record(
                memory,
                args.text,
                importance=args.importance,
            )
            if args.json:
                print(json.dumps({"id": item_id}))
            else:
                print(item_id)
            return EXIT_SUCCESS
        if args.command == "search":
            results = commands.search(memory, args.query, limit=args.limit)
            if args.json:
                print(json.dumps(results))
                return EXIT_SUCCESS
            for result in results:
                print(
                    f"{result['id']}\t{result['tier']}\t{result['source']}\t"
                    f"{float(result['score']):.4f}\t{result['text']}"
                )
            return EXIT_SUCCESS
        if args.command == "context":
            context = commands.context(memory, term=args.term, total_tokens=args.tokens)
            if args.json:
                print(
                    json.dumps(
                        {
                            "context": context,
                            "term": args.term,
                            "total_tokens": args.tokens,
                        }
                    )
                )
            else:
                print(context)
            return EXIT_SUCCESS
        if args.command == "recall":
            scope, item_id = _parse_recall_args(args.recall_args, parser)
            item = commands.recall(memory, item_id, scope=scope)
            if item is None:
                raise MemoryItemNotFoundError(
                    item_id,
                    tier=_recall_not_found_tier(scope),
                )
            print(json.dumps(item))
            return EXIT_SUCCESS
        if args.command == "set-importance":
            print(
                json.dumps(
                    commands.set_importance(
                        memory,
                        args.item_id,
                        importance=args.importance,
                    )
                )
            )
            return EXIT_SUCCESS
        if args.command == "vault":
            if args.vault_command == "status":
                indent = None if args.json else 2
                print(
                    json.dumps(
                        commands.status(memory, failed_item_limit=args.failed_limit),
                        indent=indent,
                    )
                )
                return EXIT_SUCCESS
            if args.vault_command == "rebuild-index":
                indent = None if args.json else 2
                print(json.dumps(commands.rebuild_index(memory), indent=indent))
                return EXIT_SUCCESS
            if args.vault_command == "process":
                process_result = commands.process(memory, max_passes=args.max_passes)
                if args.json:
                    print(json.dumps(process_result))
                    return EXIT_SUCCESS
                print(
                    "processed="
                    f"{process_result['processed_ids']} "
                    f"created_episodes={process_result['created_episode_ids']} "
                    f"created_arcs={process_result['created_arc_ids']} "
                    f"failed_items={process_result['failed_item_ids']}"
                )
                return EXIT_SUCCESS
        parser.error(f"unknown command: {args.command}")
    except MemoryItemNotFoundError as exc:
        print(str(exc))
        return EXIT_NOT_FOUND
    except VaultNotFoundError as exc:
        print(str(exc))
        return EXIT_NOT_FOUND
    except EngramError as exc:
        print(str(exc))
        return EXIT_ERROR
    finally:
        if memory is not None:
            memory.close()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="engram",
        description=_help_text(__doc__),
        epilog=CLI_EPILOG,
        formatter_class=HELP_FORMATTER,
    )
    parser.add_argument("--vault", help=VAULT_ARG_HELP)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "version",
        help=_help_summary(VERSION_HELP),
        description=_help_text(VERSION_HELP),
        formatter_class=HELP_FORMATTER,
    )
    init = subparsers.add_parser(
        "init",
        help=_help_summary(INIT_HELP),
        description=_help_text(INIT_HELP),
        formatter_class=HELP_FORMATTER,
    )
    init.add_argument("--json", action="store_true", help=JSON_ARG_HELP)

    record = subparsers.add_parser(
        "record",
        help=_help_summary(commands.record),
        description=_help_text(commands.record),
        formatter_class=HELP_FORMATTER,
    )
    record.add_argument("text", help="Moment text to record.")
    record.add_argument(
        "--importance",
        type=int,
        default=DEFAULT_IMPORTANCE,
        help="Initial importance as an integer greater than or equal to 1.",
    )
    record.add_argument("--json", action="store_true", help=JSON_ARG_HELP)

    search = subparsers.add_parser(
        "search",
        help=_help_summary(commands.search),
        description=_help_text(commands.search),
        formatter_class=HELP_FORMATTER,
    )
    search.add_argument("query", help="Query text for hybrid retrieval.")
    search.add_argument("--limit", type=int, default=20, help="Maximum results.")
    search.add_argument("--json", action="store_true", help=JSON_ARG_HELP)

    context = subparsers.add_parser(
        "context",
        help=_help_summary(commands.context),
        description=_help_text(commands.context),
        formatter_class=HELP_FORMATTER,
    )
    context.add_argument(
        "--term",
        help="Optional topic that should influence context assembly.",
    )
    context.add_argument(
        "--tokens",
        type=int,
        default=8192,
        help="Total token budget for the assembled context.",
    )
    context.add_argument("--json", action="store_true", help=JSON_ARG_HELP)

    recall = subparsers.add_parser(
        "recall",
        help=_help_summary(_recall_cli_help()),
        description=_recall_cli_help(),
        formatter_class=HELP_FORMATTER,
    )
    recall.add_argument(
        "recall_args",
        nargs="+",
        metavar="TOKEN",
        help=(
            "Use either `ID` for exact recall or `SCOPE ID` for containing "
            "summary recall. `SCOPE` may be `episode`, `arc`, or an integer "
            "tier such as `1`, `2`, or `3`."
        ),
    )
    recall.add_argument("--json", action="store_true", help=RECALL_JSON_ARG_HELP)

    set_importance = subparsers.add_parser(
        "set-importance",
        help=_help_summary(commands.set_importance),
        description=_help_text(commands.set_importance),
        formatter_class=HELP_FORMATTER,
    )
    set_importance.add_argument("item_id", type=int, help="Memory item ID.")
    set_importance.add_argument(
        "importance",
        type=int,
        help="New importance as an integer greater than or equal to 1.",
    )
    set_importance.add_argument("--json", action="store_true", help=JSON_ARG_HELP)

    vault = subparsers.add_parser(
        "vault",
        help=_help_summary(VAULT_HELP),
        description=_help_text(VAULT_HELP),
        formatter_class=HELP_FORMATTER,
    )
    vault_subparsers = vault.add_subparsers(dest="vault_command", required=True)

    status = vault_subparsers.add_parser(
        "status",
        help=_help_summary(commands.status),
        description=_help_text(commands.status),
        formatter_class=HELP_FORMATTER,
    )
    status.add_argument(
        "--failed-limit",
        type=int,
        default=5,
        help="Maximum failed items to include in the report.",
    )
    status.add_argument("--json", action="store_true", help=JSON_ARG_HELP)

    rebuild = vault_subparsers.add_parser(
        "rebuild-index",
        help=_help_summary(commands.rebuild_index),
        description=_help_text(commands.rebuild_index),
        formatter_class=HELP_FORMATTER,
    )
    rebuild.add_argument("--json", action="store_true", help=JSON_ARG_HELP)

    process = vault_subparsers.add_parser(
        "process",
        help=_help_summary(commands.process),
        description=_help_text(commands.process),
        formatter_class=HELP_FORMATTER,
    )
    process.add_argument(
        "--max-passes",
        type=int,
        default=1000,
        help="Maximum local repair passes before the command stops.",
    )
    process.add_argument("--json", action="store_true", help=JSON_ARG_HELP)

    return parser


def _parse_recall_args(
    recall_args: list[str],
    parser: argparse.ArgumentParser,
) -> tuple[str | int, int]:
    """Parse flexible recall CLI args into canonical scope and integer ID."""

    if len(recall_args) == 1:
        return RECALL_SCOPE_ITEM, _parse_recall_item_id(
            recall_args[0],
            parser,
        )
    if len(recall_args) == 2:
        return _parse_recall_scope(recall_args[0], parser), _parse_recall_item_id(
            recall_args[1],
            parser,
        )
    parser.error(
        "recall expects ID or SCOPE ID",
    )


def _parse_recall_item_id(
    value: str,
    parser: argparse.ArgumentParser,
) -> int:
    """Parse a recall item ID or fail through argparse."""

    try:
        return int(value)
    except ValueError:
        parser.error(f"recall ID must be an integer: {value!r}")


def _parse_recall_scope(
    value: str,
    parser: argparse.ArgumentParser,
) -> str | int:
    """Parse a recall scope token for CLI use."""

    try:
        scope = normalize_recall_scope(value)
    except ValueError as exc:
        parser.error(str(exc))
    if scope == RECALL_SCOPE_ITEM:
        parser.error(
            "recall scope must be a summary tier name like 'episode' or an integer tier"
        )
    return scope


def _recall_not_found_tier(scope: str | int) -> int | None:
    """Return the missing tier for scoped recall errors."""

    return recall_scope_tier(scope)


def _help_text(subject: Any) -> str:
    """Return cleaned help text from a docstring or literal help string."""

    if isinstance(subject, str):
        return inspect.cleandoc(subject)
    return inspect.getdoc(subject) or ""


def _help_summary(subject: Any) -> str:
    """Return the first help line for parser command listings."""

    text = _help_text(subject)
    if not text:
        return ""
    return text.splitlines()[0]


def _recall_cli_help() -> str:
    """Return CLI-specific recall help derived from the command docstring."""

    return re.sub(
        r"Command-layer callers receive\s+`None` for missing items\.",
        "CLI callers exit with the not-found code for missing items.",
        _help_text(commands.recall),
    )


def app() -> NoReturn:
    """Console-script entry point."""
    raise SystemExit(main())
