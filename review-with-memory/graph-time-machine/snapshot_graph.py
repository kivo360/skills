#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "code-review-graph",
#     "hindsight-client>=0.5",
# ]
# ///
"""
Capture a snapshot of the code-review-graph state and retain it to Hindsight
as a time-stamped memory. Run after any meaningful graph rebuild — typically
post-commit, or via cron.

Each snapshot includes:
    - node/edge/file/community counts
    - top-N hubs (by total degree)
    - top-N bridges (by betweenness centrality)
    - knowledge-gap summary (isolated, thin, untested-hot, single-file)
    - delta vs the most recent prior snapshot in the bank (when available)

The snapshot is retained with timestamp = the commit timestamp (when --commit
or --head are used), so temporal queries like ``recall("how did module:auth
evolve last month")`` return ordered results.

Usage:
    snapshot_graph.py                         # snapshot HEAD
    snapshot_graph.py --commit <sha>          # snapshot a specific commit
    snapshot_graph.py --no-delta              # skip prior-snapshot lookup
    snapshot_graph.py --top-n 20 --dry-run

Idempotent: document_id = ``graph-snapshot-<sha>`` so re-runs upsert.

Environment:
    HINDSIGHT_BASE_URL    default http://localhost:8888
    HINDSIGHT_BANK_PREFIX default "kh"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True, stderr=subprocess.PIPE)


def _repo_root() -> Path:
    return Path(_run(["git", "rev-parse", "--show-toplevel"]).strip())


def _bank_id(repo_root: Path) -> str:
    prefix = os.environ.get("HINDSIGHT_BANK_PREFIX", "kh")
    return f"{prefix}-::{repo_root.name}"


def _commit_meta(repo_root: Path, sha: str) -> dict:
    fmt = "%H\x1f%aI\x1f%s"
    raw = _run(["git", "log", "-1", f"--format={fmt}", sha], cwd=repo_root)
    parts = raw.split("\x1f", 2)
    if len(parts) < 3:
        return {"sha": sha, "iso_date": dt.datetime.now(dt.timezone.utc).isoformat(), "subject": ""}
    return {"sha": parts[0].strip(), "iso_date": parts[1].strip(), "subject": parts[2].strip()}


def _gather_stats(repo_root: Path, top_n: int) -> dict[str, Any]:
    """Pull counts + hubs + bridges + gaps directly from the graph store.

    Bypasses CRG's tools.analysis_tools wrappers that have a tuple-vs-store bug
    (already documented in setup_crg_mental_models.py).
    """
    from code_review_graph.analysis import (
        find_bridge_nodes,
        find_hub_nodes,
        find_knowledge_gaps,
    )
    from code_review_graph.tools._common import _get_store

    store, _ = _get_store(str(repo_root))

    # Counts come from the store's helpers.
    nodes_all = store.get_all_nodes(exclude_files=False)
    nodes_no_files = store.get_all_nodes(exclude_files=True)
    edges = store.get_all_edges()
    files = [n for n in nodes_all if getattr(n, "kind", "") == "File"]
    communities = store.get_all_community_ids()
    community_count = len({v for v in communities.values() if v is not None})

    hubs = find_hub_nodes(store, top_n=top_n)
    bridges = find_bridge_nodes(store, top_n=top_n)
    try:
        gaps = find_knowledge_gaps(store)
    except Exception as e:
        # CRG's find_knowledge_gaps has a sqlite3.Row vs dict bug in some
        # versions. Snapshot is still useful without it.
        sys.stderr.write(f"[snapshot] knowledge_gaps unavailable: {e!r}\n")
        gaps = {}

    return {
        "node_count": len(nodes_no_files),
        "file_count": len(files),
        "edge_count": len(edges),
        "community_count": community_count,
        "hubs": [
            {
                "name": h.get("name"),
                "qualified_name": h.get("qualified_name"),
                "kind": h.get("kind"),
                "file": h.get("file"),
                "total_degree": h.get("total_degree"),
            }
            for h in hubs
        ],
        "bridges": [
            {
                "name": b.get("name"),
                "qualified_name": b.get("qualified_name"),
                "file": b.get("file"),
                "betweenness": b.get("betweenness"),
            }
            for b in bridges
        ],
        "gap_summary": {k: len(v) for k, v in gaps.items()},
    }


def _format_content(stats: dict, meta: dict, repo_root: Path,
                    delta: dict | None) -> str:
    lines = [
        f"Graph snapshot for {repo_root.name} at {meta['sha'][:8]} ({meta['iso_date']})",
        f"Subject: {meta['subject']}" if meta.get("subject") else "",
        "",
        "## Stats",
        f"- nodes: {stats['node_count']}",
        f"- files: {stats['file_count']}",
        f"- edges: {stats['edge_count']}",
        f"- communities: {stats['community_count']}",
        "",
    ]
    if stats["hubs"]:
        lines.append("## Top hubs (highest fanout)")
        for h in stats["hubs"][:10]:
            qn = h.get("qualified_name") or h.get("name") or ""
            lines.append(f"- `{h.get('name')}` (deg {h.get('total_degree')}) — {qn}")
        lines.append("")
    if stats["bridges"]:
        lines.append("## Top bridges (architectural chokepoints)")
        for b in stats["bridges"][:5]:
            qn = b.get("qualified_name") or b.get("name") or ""
            lines.append(f"- `{b.get('name')}` — {qn}")
        lines.append("")
    if stats.get("gap_summary"):
        lines.append("## Knowledge gaps")
        for k, v in stats["gap_summary"].items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    if delta:
        lines.append("## Delta from previous snapshot")
        prev_sha = delta.get("prev_sha", "?")[:8]
        lines.append(f"Compared to: {prev_sha}")
        for k in ("node_count", "file_count", "edge_count", "community_count"):
            cur = stats.get(k, 0) or 0
            prev = delta.get("prev_stats", {}).get(k, cur) or 0
            diff = cur - prev
            sign = "+" if diff >= 0 else ""
            lines.append(f"- {k}: {prev} → {cur} ({sign}{diff})")
        # Hub churn
        prev_hub_qns = {h["qualified_name"] for h in delta.get("prev_stats", {}).get("hubs", []) if h.get("qualified_name")}
        cur_hub_qns = {h["qualified_name"] for h in stats["hubs"] if h.get("qualified_name")}
        new_hubs = cur_hub_qns - prev_hub_qns
        gone_hubs = prev_hub_qns - cur_hub_qns
        if new_hubs:
            lines.append(f"- new hubs: {', '.join(sorted(new_hubs))[:300]}")
        if gone_hubs:
            lines.append(f"- hubs left top-N: {', '.join(sorted(gone_hubs))[:300]}")

    return "\n".join(l for l in lines if l is not None)


def _build_tags(stats: dict, meta: dict, repo_root: Path) -> list[str]:
    tags = [
        f"repo:{repo_root.name}",
        "source:graph-snapshot",
        f"commit:{meta['sha'][:8]}",
    ]
    seen = set(tags)
    # Tag top hubs so recall on `node:<qn>` surfaces snapshots where this node
    # was hub-class — useful for time-series queries on a specific hot-spot.
    for h in stats["hubs"][:8]:
        qn = h.get("qualified_name")
        if qn:
            t = f"node:{qn}"
            if t not in seen:
                seen.add(t)
                tags.append(t)
    return tags


def _try_recall_prev(client, bank: str) -> dict | None:
    """Find the most recent prior snapshot in this bank. Returns parsed stats."""
    try:
        resp = client.recall(
            bank_id=bank,
            query="most recent graph snapshot",
            tags=["source:graph-snapshot"],
            tags_match="all_strict",
            budget="low",
            max_tokens=2048,
        )
    except Exception:
        return None

    results = getattr(resp, "results", None) or []
    if not results:
        return None
    # Crude: pick the most recent by mentioned_at, parse counts out of text.
    best = max(results, key=lambda r: getattr(r, "mentioned_at", "") or "")
    text = getattr(best, "text", None) or getattr(best, "content", "") or ""
    nums: dict[str, int] = {}
    for key in ("nodes", "files", "edges", "communities"):
        m = re.search(rf"{key}\s*:\s*(\d+)", text)
        if m:
            nums[f"{key.rstrip('s')}_count" if key != "files" else "file_count"] = int(m.group(1))
    # Best-effort hub list parse: lines like ``- `name` (deg N) — qualname``
    hubs = []
    for line in text.splitlines():
        m = re.match(r"-\s*`([^`]+)`\s*\(deg\s*(\d+)\)\s*—\s*(.+)", line)
        if m:
            hubs.append({
                "name": m.group(1),
                "total_degree": int(m.group(2)),
                "qualified_name": m.group(3).strip(),
            })
    sha_m = re.search(r"snapshot.*?at\s+([0-9a-f]{7,8})", text)
    return {
        "prev_sha": sha_m.group(1) if sha_m else "",
        "prev_stats": {**nums, "hubs": hubs},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--no-delta", action="store_true",
                    help="don't query for prior snapshot")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    repo_root = _repo_root()
    bank = _bank_id(repo_root)
    sha = _run(["git", "rev-parse", args.commit], cwd=repo_root).strip()
    meta = _commit_meta(repo_root, sha)

    db_path = repo_root / ".code-review-graph" / "graph.db"
    if not db_path.exists():
        if not args.quiet:
            print(f"no graph DB at {db_path} — run `code-review-graph build` first",
                  file=sys.stderr)
        sys.exit(0)  # don't break commits

    if not args.quiet:
        print(f"repo: {repo_root}")
        print(f"bank: {bank}")
        print(f"snapshotting {sha[:8]} — {meta.get('subject', '')[:60]}")

    stats = _gather_stats(repo_root, top_n=args.top_n)

    delta = None
    if not args.no_delta:
        try:
            from hindsight_client import Hindsight
            client = Hindsight(
                base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
                timeout=15.0,
            )
            delta = _try_recall_prev(client, bank)
        except Exception as e:
            if not args.quiet:
                print(f"  prior-snapshot lookup failed (non-fatal): {e!r}",
                      file=sys.stderr)

    content = _format_content(stats, meta, repo_root, delta)
    tags = _build_tags(stats, meta, repo_root)

    if args.dry_run:
        print("\n--- snapshot content ---")
        print(content)
        print(f"\n--- {len(tags)} tags ---")
        for t in tags:
            print(f"  {t}")
        return

    try:
        from hindsight_client import Hindsight
        client = Hindsight(
            base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
            timeout=60.0,
        )
        try:
            timestamp = dt.datetime.fromisoformat(meta["iso_date"])
        except ValueError:
            timestamp = dt.datetime.now(dt.timezone.utc)
        client.retain(
            bank_id=bank,
            content=content,
            context="graph-snapshot",
            tags=tags,
            timestamp=timestamp,
            document_id=f"graph-snapshot-{sha}",
            metadata={"sha": sha, "stats_json": json.dumps({
                k: stats[k] for k in ("node_count", "file_count", "edge_count", "community_count")
            })},
        )
        if not args.quiet:
            print(f"  retained snapshot ({len(content)} chars, {len(tags)} tags)"
                  + (f" — delta vs {delta['prev_sha']}" if delta and delta.get("prev_sha") else " — no prior snapshot"))
    except Exception as e:
        print(f"retain failed: {e!r}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
