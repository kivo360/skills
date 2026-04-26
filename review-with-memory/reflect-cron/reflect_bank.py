#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hindsight-client>=0.5",
# ]
# ///
"""
Run Hindsight's `reflect` agentic synthesis over a bank, then retain the
synthesis back into the bank as a recallable memory.

reflect() is a 10-iteration agentic loop — too expensive for the per-prompt
path. This script is meant to be run periodically (weekly cron) per active
bank. Each run produces one new "reflection" memory tagged so future recalls
surface synthesized patterns alongside raw facts.

Usage:
    reflect_bank.py --bank kh-::coding-toolbelt
    reflect_bank.py --banks-file ~/.hindsight/known-banks.txt
    reflect_bank.py --bank <id> --window weekly      # built-in prompts
    reflect_bank.py --bank <id> --query "custom prompt..."
    reflect_bank.py --bank <id> --window weekly --dry-run

Environment:
    HINDSIGHT_BASE_URL    default http://localhost:8888
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

WINDOW_QUERIES: dict[str, str] = {
    "daily": (
        "Summarize what was worked on in the last 24 hours: decisions made, "
        "bugs found, files touched, and questions left open. Highlight anything "
        "surprising or contradicting earlier patterns."
    ),
    "weekly": (
        "What patterns, recurring failures, and emerging conventions have "
        "we seen this week? Surface anything new, anything that contradicts "
        "earlier decisions, and any modules that received unusual amounts of "
        "attention. Be specific with file paths and module names."
    ),
    "monthly": (
        "Major architectural decisions, bugs, and refactors over the past "
        "month. What changed about how this codebase is built or maintained? "
        "Which assumptions from a month ago are no longer true?"
    ),
}


def _bank_ids(args: argparse.Namespace) -> list[str]:
    if args.bank:
        return [args.bank]
    if args.banks_file:
        p = Path(args.banks_file).expanduser()
        return [
            line.strip()
            for line in p.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    print("must pass --bank or --banks-file", file=sys.stderr)
    sys.exit(2)


def _resolve_query(args: argparse.Namespace) -> tuple[str, str]:
    if args.query:
        return args.query, "custom"
    return WINDOW_QUERIES[args.window], args.window


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bank", default=None, help="single bank id")
    ap.add_argument("--banks-file", default=None, help="path with one bank id per line")
    ap.add_argument("--window", choices=list(WINDOW_QUERIES), default="weekly")
    ap.add_argument("--query", default=None, help="override prompt; if set, ignores --window")
    ap.add_argument("--budget", choices=["low", "mid", "high"], default="mid")
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--no-retain", action="store_true",
                    help="run reflect but don't retain the result back to the bank")
    ap.add_argument("--dry-run", action="store_true",
                    help="print bank+query+budget but don't call reflect")
    args = ap.parse_args()

    banks = _bank_ids(args)
    query, window_label = _resolve_query(args)

    print(f"banks: {len(banks)}")
    print(f"window: {window_label}")
    print(f"budget: {args.budget}, max_tokens: {args.max_tokens}")
    print(f"query: {query[:120]}{'…' if len(query) > 120 else ''}")

    if args.dry_run:
        for b in banks:
            print(f"  would reflect: {b}")
        return

    from hindsight_client import Hindsight

    client = Hindsight(
        base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
        timeout=600.0,  # reflect is a long agentic loop
    )

    for bank in banks:
        print(f"\n=== reflecting on {bank} ===")
        try:
            resp = client.reflect(
                bank_id=bank,
                query=query,
                budget=args.budget,
                max_tokens=args.max_tokens,
            )
        except Exception as e:
            print(f"  reflect failed: {e!r}", file=sys.stderr)
            continue

        answer = (
            getattr(resp, "answer", None)
            or getattr(resp, "text", None)
            or getattr(resp, "response", None)
            or str(resp)
        )
        if not isinstance(answer, str):
            answer = str(answer)
        print(answer[:600] + ("…" if len(answer) > 600 else ""))

        if args.no_retain:
            continue
        if not answer.strip():
            print("  empty answer — skipping retain", file=sys.stderr)
            continue

        try:
            now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            client.retain(
                bank_id=bank,
                content=f"Reflection ({window_label}, {now}):\n\n{answer}",
                context=f"reflection-{window_label}",
                tags=[
                    "source:reflection",
                    f"window:{window_label}",
                    f"reflected-bank:{bank}",
                ],
                document_id=f"reflection-{window_label}-{now[:10]}",
            )
            print(f"  retained reflection ({len(answer)} chars)")
        except Exception as e:
            print(f"  retain of reflection failed: {e!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
