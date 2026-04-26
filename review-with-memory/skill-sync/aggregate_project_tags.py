#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hindsight-client>=0.5",
# ]
# ///
"""
Aggregate per-project tag distributions from Hindsight into a JSON cache
that the suggester's project-boost context rule reads at startup.

Phase 2 of the migration plan in docs/highlight-memory-evaluation.md:
this is the data layer. The boost rule itself lives in TS
(cli/src/lib/context-rules.ts) and is gated behind
HINDSIGHT_PROJECT_BOOST_ENABLED=1.

Usage:
    aggregate_project_tags.py --bank kh-::<repo>
    aggregate_project_tags.py --banks-file ~/.hindsight/known-banks.txt
    aggregate_project_tags.py --all-discovered     # walk ~/.hindsight-docker

Output: ~/.cache/review-with-memory/project-tags/<bank-slug>.json
    {
      "bank": "kh-::coding-toolbelt",
      "generated_at": "2026-04-26T10:42:00Z",
      "memory_count": 99,
      "top_tags": [
        {"tag": "file:cli/src/lib/matcher.ts", "count": 12, "weight": 0.83},
        {"tag": "module:cli", "count": 28, "weight": 1.00},
        ...
      ]
    }

The cache is read by the TS suggester via a small JSON lookup keyed by
the current repo's bank id. Background-friendly — runs in <2 s for a
99-memory bank, recall is the only Hindsight call.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "review-with-memory" / "project-tags"
DEFAULT_QUERY = (
    "What modules, files, topics, and patterns has work in this project covered? "
    "What conventions, decisions, recurring concerns, and recurring failures are "
    "characteristic of this codebase?"
)
TAG_PREFIXES_KEPT = (
    # Identity-scoping tags that describe the *project*, not who touched it.
    "file:", "module:", "node:", "lang:",
    "user-pref:", "label:", "outcome:",
    # `author:` and `test-marker:` are intentionally excluded — author tags
    # spam personal-name tokens that match nothing useful in the skill catalog,
    # and test-markers are unique nonces from individual test runs.
)


def _slug(bank: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", bank).strip("-") or "default"


def _read_banks(args: argparse.Namespace) -> list[str]:
    if args.bank:
        return [args.bank]
    if args.banks_file:
        p = Path(args.banks_file).expanduser()
        return [
            line.strip()
            for line in p.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    if args.all_discovered:
        # Best-effort: list directories under the docker volume that look
        # like bank-id slugs. Hindsight stores banks in pgdata; we don't
        # crack open Postgres. Fall back to known-banks.txt if it exists.
        banks_file = Path.home() / ".hindsight" / "known-banks.txt"
        if banks_file.exists():
            return [
                line.strip()
                for line in banks_file.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            ]
        sys.stderr.write(
            "[aggregate] --all-discovered: no ~/.hindsight/known-banks.txt; "
            "pass --bank or --banks-file explicitly\n"
        )
        return []
    print("must pass --bank, --banks-file, or --all-discovered", file=sys.stderr)
    sys.exit(2)


def _aggregate_one(
    client, bank: str, sample_n: int, max_tokens: int
) -> dict:
    try:
        resp = client.recall(
            bank_id=bank,
            query=DEFAULT_QUERY,
            budget="mid",
            max_tokens=max_tokens,
        )
    except Exception as e:
        return {"bank": bank, "error": repr(e), "memory_count": 0, "top_tags": []}

    results = getattr(resp, "results", None) or []
    counts: Counter[str] = Counter()
    for r in results[:sample_n]:
        for t in (getattr(r, "tags", None) or []):
            if not any(t.startswith(p) for p in TAG_PREFIXES_KEPT):
                continue
            counts[t] += 1

    if not counts:
        return {"bank": bank, "memory_count": len(results), "top_tags": []}

    max_count = max(counts.values())
    top_tags = [
        {"tag": tag, "count": count, "weight": round(count / max_count, 3)}
        for tag, count in counts.most_common(50)
    ]
    return {
        "bank": bank,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "memory_count": len(results),
        "top_tags": top_tags,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bank", default=None)
    ap.add_argument("--banks-file", default=None)
    ap.add_argument("--all-discovered", action="store_true")
    ap.add_argument("--sample-size", type=int, default=200,
                    help="how many recall results to aggregate per bank")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--cache-dir", default=str(CACHE_DIR))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--print-summary", action="store_true",
                    help="print top-15 tags per bank to stdout after writing")
    args = ap.parse_args()

    banks = _read_banks(args)
    if not banks:
        return

    cache_dir = Path(args.cache_dir).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for bank in banks:
            out_path = cache_dir / f"{_slug(bank)}.json"
            print(f"would aggregate {bank} → {out_path}")
        return

    from hindsight_client import Hindsight
    client = Hindsight(
        base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
        timeout=60.0,
    )

    for bank in banks:
        result = _aggregate_one(client, bank, args.sample_size, args.max_tokens)
        out_path = cache_dir / f"{_slug(bank)}.json"
        out_path.write_text(json.dumps(result, indent=2))
        if "error" in result:
            print(f"  {bank}: ERROR {result['error']}", file=sys.stderr)
            continue
        print(
            f"  {bank}: {result['memory_count']} memories, "
            f"{len(result['top_tags'])} unique tags → {out_path}"
        )
        if args.print_summary and result["top_tags"]:
            for t in result["top_tags"][:15]:
                print(f"    {t['tag']}  ({t['count']}× w={t['weight']})")


if __name__ == "__main__":
    main()
