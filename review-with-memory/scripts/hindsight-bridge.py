#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hindsight-client>=0.1",
# ]
# ///
"""
Bridge between the review-with-memory skill and a local Hindsight server.

Subcommands:
  health                              Verify the server is reachable.
  retain  --bank --content [...]      Store one memory.
  recall  --bank --query [...]        Retrieve memories.

All output is JSON on stdout. Non-zero exit on failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888")


def _emit(payload: dict[str, Any], *, ok: bool = True) -> None:
    print(json.dumps({"ok": ok, **payload}, default=str))


def _fail(msg: str, **extra: Any) -> None:
    _emit({"error": msg, **extra}, ok=False)
    sys.exit(1)


def cmd_health(args: argparse.Namespace) -> None:
    url = args.base_url.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            _emit({"status": resp.status, "body": body[:200]})
    except urllib.error.URLError as e:
        _fail(f"unreachable: {e}", base_url=args.base_url)
    except Exception as e:
        _fail(f"unexpected: {e!r}", base_url=args.base_url)


def _client(base_url: str):
    from hindsight_client import Hindsight

    return Hindsight(base_url=base_url)


def cmd_retain(args: argparse.Namespace) -> None:
    client = _client(args.base_url)
    tags = [t for t in (args.tags.split(",") if args.tags else []) if t.strip()]
    metadata = json.loads(args.metadata) if args.metadata else None
    res = client.retain(
        bank_id=args.bank,
        content=args.content,
        context=args.context,
        document_id=args.document_id,
        metadata=metadata,
        tags=tags or None,
    )
    _emit({"retained": True, "response": _to_dict(res), "tags": tags})


def cmd_recall(args: argparse.Namespace) -> None:
    client = _client(args.base_url)
    tags = [t for t in (args.tags.split(",") if args.tags else []) if t.strip()]
    res = client.recall(
        bank_id=args.bank,
        query=args.query,
        tags=tags or None,
        tags_match=args.tags_match,
        budget=args.budget,
        max_tokens=args.max_tokens,
        types=args.types.split(",") if args.types else None,
    )
    _emit({"response": _to_dict(res), "tags": tags, "tags_match": args.tags_match})


def _to_dict(obj: Any) -> Any:
    """Best-effort serialization of pydantic / dataclass / dict."""
    for attr in ("model_dump", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Hindsight server URL (default: {DEFAULT_BASE_URL})",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp_health = sub.add_parser("health")
    sp_health.set_defaults(func=cmd_health)

    sp_retain = sub.add_parser("retain")
    sp_retain.add_argument("--bank", required=True)
    sp_retain.add_argument("--content", required=True)
    sp_retain.add_argument("--context", default=None)
    sp_retain.add_argument("--document-id", default=None)
    sp_retain.add_argument("--tags", default="", help="comma-separated")
    sp_retain.add_argument("--metadata", default=None, help="JSON object string")
    sp_retain.set_defaults(func=cmd_retain)

    sp_recall = sub.add_parser("recall")
    sp_recall.add_argument("--bank", required=True)
    sp_recall.add_argument("--query", required=True)
    sp_recall.add_argument("--tags", default="", help="comma-separated")
    sp_recall.add_argument(
        "--tags-match",
        default="any",
        choices=["any", "all", "any_strict", "all_strict"],
    )
    sp_recall.add_argument("--budget", default="mid", choices=["low", "mid", "high"])
    sp_recall.add_argument("--max-tokens", type=int, default=4096)
    sp_recall.add_argument("--types", default=None, help="comma-separated fact types")
    sp_recall.set_defaults(func=cmd_recall)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
