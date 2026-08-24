from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .compiler import RequestCompiler
from .config import Config
from .graph import GraphValidationError, WorkingStateGraph
from .storage import TokenTerminatorStore


def _emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    elif isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _runtime() -> tuple[
    Config, TokenTerminatorStore, WorkingStateGraph, RequestCompiler
]:
    config = Config.from_env()
    store = TokenTerminatorStore(
        config.db_path,
        max_artifact_chars=config.max_artifact_chars,
        max_vault_bytes=config.vault_max_bytes,
        max_page_chars=config.max_artifact_page_chars,
    )
    graph = WorkingStateGraph(store)
    return config, store, graph, RequestCompiler(store, graph, config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="token-terminator",
        description="Token Terminator artifact vault, working state, and request compiler.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show structural counts and configuration.")
    status.add_argument("--json", action="store_true")

    artifact = sub.add_parser("artifact", help="Recover or search artifacts.")
    artifact_sub = artifact.add_subparsers(dest="artifact_command", required=True)
    artifact_get = artifact_sub.add_parser("get")
    artifact_get.add_argument("artifact_id")
    artifact_get.add_argument("--offset", type=int, default=0)
    artifact_get.add_argument("--limit", type=int, default=8000)
    artifact_get.add_argument("--json", action="store_true")
    artifact_search = artifact_sub.add_parser("search")
    artifact_search.add_argument("query")
    artifact_search.add_argument("--limit", type=int, default=10)
    artifact_search.add_argument("--json", action="store_true")

    graph = sub.add_parser(
        "working-state", help="Validate/apply bounded working-state operations."
    )
    graph_sub = graph.add_subparsers(dest="graph_command", required=True)
    graph_apply = graph_sub.add_parser("apply")
    graph_apply.add_argument("--file", required=True)
    graph_apply.add_argument("--session", default="")
    graph_apply.add_argument("--dry-run", action="store_true")
    graph_apply.add_argument("--json", action="store_true")
    graph_state = graph_sub.add_parser("state")
    graph_state.add_argument("--include-retired", action="store_true")
    graph_state.add_argument("--limit", type=int, default=50)
    graph_state.add_argument("--json", action="store_true")

    compile_parser = sub.add_parser(
        "compile", help="Compile a provider request fixture."
    )
    compile_parser.add_argument("--request", required=True)
    compile_parser.add_argument("--session", default="")
    compile_parser.add_argument("--request-id", default="")
    compile_parser.add_argument("--json", action="store_true")
    return parser


def run(args: argparse.Namespace) -> int:
    config, store, graph, compiler = _runtime()
    if args.command == "status":
        payload = {
            # counts() separates compiler-stage totals from rows whose final
            # provider payload was actually measured.
            **store.counts(),
            "mode": config.mode,
            "enabled": config.enabled,
            "context_compaction_enabled": config.context_compaction_enabled,
            "min_artifact_chars": config.min_artifact_chars,
            "max_artifact_chars": config.max_artifact_chars,
            "vault_max_bytes": config.vault_max_bytes,
            "inline_lease_exposures": config.inline_lease_exposures,
            "graph_context_chars": config.graph_context_chars,
            "max_artifact_page_chars": config.max_artifact_page_chars,
            "max_search_results": config.max_search_results,
        }
        _emit(payload, as_json=args.json)
        return 0

    if args.command == "artifact" and args.artifact_command == "get":
        page = store.read_artifact(
            args.artifact_id,
            offset=args.offset,
            limit=min(args.limit, config.max_artifact_page_chars),
        )
        _emit(page if args.json else page["content"], as_json=args.json)
        return 0

    if args.command == "artifact" and args.artifact_command == "search":
        hits = [
            asdict(hit)
            for hit in store.search_artifacts(
                args.query, limit=min(args.limit, config.max_search_results)
            )
        ]
        _emit({"results": hits}, as_json=args.json)
        return 0

    if args.command == "working-state" and args.graph_command == "apply":
        operations = _load_json(args.file)
        if not isinstance(operations, list):
            raise GraphValidationError("operation file must contain a JSON array")
        payload = (
            graph.validate(operations)
            if args.dry_run
            else graph.apply(operations, session_id=args.session)
        )
        _emit(payload, as_json=args.json)
        return 0

    if args.command == "working-state" and args.graph_command == "state":
        payload = graph.state(include_retired=args.include_retired, limit=args.limit)
        _emit(payload, as_json=args.json)
        return 0

    if args.command == "compile":
        request = _load_json(args.request)
        if not isinstance(request, dict):
            raise ValueError("request file must contain a JSON object")
        result = compiler.compile(
            request, session_id=args.session, request_id=args.request_id
        )
        payload = {
            **result.as_dict(),
            "artifacts": len(result.artifact_ids),
        }
        _emit(payload, as_json=args.json)
        return 0

    raise ValueError("unsupported command")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (
        GraphValidationError,
        KeyError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI must convert unexpected failures to exit 1
        print(f"fatal: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
