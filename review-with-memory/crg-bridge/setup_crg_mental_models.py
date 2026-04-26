#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "code-review-graph",
#     "hindsight-client>=0.5",
# ]
# ///
"""
Define one Hindsight mental model per CRG hub (and optionally per bridge).

Mental models in Hindsight auto-synthesize content from `source_query` over
the bank's retained memories. By tying one model to each CRG-identified hub,
the architectural hot-spots get a self-updating "what we know about this
hot-spot" doc that compounds as conversations and reviews accumulate.

Idempotent: each model gets a stable ID derived from the node qualname, so
re-running this script after a graph rebuild updates names but never
duplicates. Models orphaned by a hub falling out of the top-N stay in the
bank; pass --prune to delete them.

Usage:
    setup_crg_mental_models.py                          # 10 hubs, current repo
    setup_crg_mental_models.py --top-n 20 --include-bridges
    setup_crg_mental_models.py --dry-run
    setup_crg_mental_models.py --prune                  # remove stale crg-* models

Environment:
    HINDSIGHT_BASE_URL    default http://localhost:8888
    HINDSIGHT_BANK_PREFIX default "kh"
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ID_PREFIX_HUB = "crg-hub-"
ID_PREFIX_BRIDGE = "crg-bridge-"


def _slug(qualname: str, repo_root: Path) -> str:
    """Make a stable, collision-resistant ID from a node qualname.

    CRG qualnames are often absolute paths or module-paths with function
    suffixes. We strip the repo root, keep the last few segments, and
    pin uniqueness with an 8-char hash of the full qualname.
    """
    rel = qualname
    root_str = str(repo_root)
    if rel.startswith(root_str):
        rel = rel[len(root_str):].lstrip("/")
    # Keep the last 3 meaningful parts so two functions in different
    # files don't collapse to the same slug.
    parts = re.split(r"[/.:]+", rel)
    parts = [p for p in parts if p]
    tail = "-".join(parts[-3:]) if parts else "node"
    tail_slug = re.sub(r"[^a-z0-9-]+", "-", tail.lower()).strip("-")[:40] or "node"
    digest = hashlib.sha1(qualname.encode("utf-8")).hexdigest()[:8]
    return f"{tail_slug}-{digest}"


def _resolve_repo_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    out = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()
    return Path(out)


def _bank_id(repo_root: Path) -> str:
    prefix = os.environ.get("HINDSIGHT_BANK_PREFIX", "kh")
    return f"{prefix}-::{repo_root.name}"


def _hub_source_query(qualname: str) -> str:
    return (
        f"Recurring failure modes, reviewer feedback, debugging insights, "
        f"and architectural decisions involving '{qualname}'. Include "
        f"changes that broke things downstream and patterns that keep recurring."
    )


def _bridge_source_query(qualname: str) -> str:
    return (
        f"Architectural risk and historical incidents around '{qualname}', "
        f"a betweenness-centrality chokepoint. Include outages, refactor "
        f"attempts, and what features depend on this path."
    )


def _model_tags(node: dict, repo_root: Path) -> list[str]:
    qn = node.get("qualified_name") or node.get("name", "")
    file = node.get("file") or ""
    root_str = str(repo_root)
    if file.startswith(root_str):
        file = file[len(root_str):].lstrip("/")
    tags = [f"node:{qn}", "source:crg-mental-model"]
    if file:
        tags.append(f"file:{file}")
    return tags


def _build_models(
    repo_root: Path, top_n: int, include_bridges: bool
) -> list[dict]:
    # Bypass tools.analysis_tools.get_hub_nodes_func — installed CRG <0.x has a
    # tuple-vs-store bug there. Call the analysis layer directly.
    from code_review_graph.analysis import find_bridge_nodes, find_hub_nodes
    from code_review_graph.tools._common import _get_store

    store, _ = _get_store(str(repo_root))
    hubs = find_hub_nodes(store, top_n=top_n)
    bridges = find_bridge_nodes(store, top_n=top_n) if include_bridges else []

    models: list[dict] = []
    for h in hubs:
        qn = h.get("qualified_name")
        if not qn:
            continue
        models.append(
            {
                "id": f"{ID_PREFIX_HUB}{_slug(qn, repo_root)}",
                "name": f"Hub: {h.get('name') or qn} (deg {h.get('total_degree', 0)})",
                "source_query": _hub_source_query(qn),
                "tags": _model_tags(h, repo_root),
            }
        )
    for b in bridges:
        qn = b.get("qualified_name")
        if not qn:
            continue
        models.append(
            {
                "id": f"{ID_PREFIX_BRIDGE}{_slug(qn, repo_root)}",
                "name": f"Bridge: {b.get('name') or qn}",
                "source_query": _bridge_source_query(qn),
                "tags": _model_tags(b, repo_root),
            }
        )
    return models


def _existing_ids(client, bank: str) -> set[str]:
    try:
        resp = client.list_mental_models(bank)
    except Exception:
        return set()
    items = getattr(resp, "items", None) or getattr(resp, "mental_models", None) or []
    out: set[str] = set()
    for it in items:
        mid = getattr(it, "id", None) or (it.get("id") if isinstance(it, dict) else None)
        if mid:
            out.add(mid)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--include-bridges", action="store_true")
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--prune",
        action="store_true",
        help="Delete crg-hub-* / crg-bridge-* models no longer in the top-N.",
    )
    ap.add_argument(
        "--no-refresh-trigger",
        action="store_true",
        help="Skip the refresh_after_consolidation trigger (manual-only refresh).",
    )
    args = ap.parse_args()

    repo_root = _resolve_repo_root(args.repo_root)
    bank = _bank_id(repo_root)

    desired = _build_models(repo_root, args.top_n, args.include_bridges)
    desired_ids = {m["id"] for m in desired}

    print(f"repo_root: {repo_root}")
    print(f"bank: {bank}")
    print(f"desired models: {len(desired)} ({sum(1 for m in desired if m['id'].startswith(ID_PREFIX_HUB))} hubs, {sum(1 for m in desired if m['id'].startswith(ID_PREFIX_BRIDGE))} bridges)")

    if args.dry_run:
        for m in desired:
            print(f"  would create/update: {m['id']} — {m['name']}")
        return

    from hindsight_client import Hindsight

    client = Hindsight(
        base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
        timeout=30.0,
    )

    existing = _existing_ids(client, bank)
    trigger = None if args.no_refresh_trigger else {"refresh_after_consolidation": True}

    created = updated = skipped = pruned = failed = 0

    for m in desired:
        try:
            if m["id"] in existing:
                client.update_mental_model(
                    bank_id=bank,
                    mental_model_id=m["id"],
                    name=m["name"],
                    source_query=m["source_query"],
                    tags=m["tags"],
                    trigger=trigger,
                )
                updated += 1
                print(f"  updated: {m['id']}")
            else:
                client.create_mental_model(
                    bank_id=bank,
                    id=m["id"],
                    name=m["name"],
                    source_query=m["source_query"],
                    tags=m["tags"],
                    trigger=trigger,
                )
                created += 1
                print(f"  created: {m['id']}")
        except Exception as e:
            failed += 1
            sys.stderr.write(f"  FAIL {m['id']}: {e!r}\n")

    if args.prune:
        for mid in existing:
            if (mid.startswith(ID_PREFIX_HUB) or mid.startswith(ID_PREFIX_BRIDGE)) and mid not in desired_ids:
                try:
                    client.delete_mental_model(bank_id=bank, mental_model_id=mid)
                    pruned += 1
                    print(f"  pruned: {mid}")
                except Exception as e:
                    failed += 1
                    sys.stderr.write(f"  FAIL prune {mid}: {e!r}\n")

    print(
        f"done — created={created} updated={updated} pruned={pruned} "
        f"skipped={skipped} failed={failed}"
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
