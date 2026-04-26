#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Backfill `source:claude-code-conversation` onto conversation documents
that pre-date the retainTags update in ~/.hindsight/claude-code.json.

Background: until 2026-04-26 the Claude Code Hindsight plugin retained
documents tagged only with the session UUID (`["{session_id}"]`). After
the config update, new retains carry both the UUID and
`source:claude-code-conversation`, putting them on the same tag schema
as the other 5 retain streams. This script gives historical retains
the same treatment so cross-stream recall (e.g.
`tags=["source:claude-code-conversation"]`) finds them too.

What it does:
    1. Lists documents in a bank, page by page.
    2. Identifies "conversation" documents: tags include a UUID-shaped
       string (8-4-4-4-12 hex pattern) AND no existing `source:` tag.
    3. PATCHes each match to add `source:claude-code-conversation` to
       its tags. Existing tags are preserved.

Caveats:
    - This updates DOCUMENT tags. Whether memory-unit tags (the things
      recall returns) auto-sync with the parent document depends on
      Hindsight's internals. The script reports both pre- and post-
      backfill memory-tag counts so you can see if recall picks up the
      new tag without re-ingestion.
    - PATCH is idempotent — re-running is safe.
    - --dry-run is the default; pass --apply to actually write.

Usage:
    backfill_conversation_tags.py --bank kh-::coding-toolbelt
    backfill_conversation_tags.py --bank kh-::coding-toolbelt --apply
    backfill_conversation_tags.py --bank kh-::coding-toolbelt --apply --limit 50

Environment:
    HINDSIGHT_BASE_URL     default http://localhost:8888
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
SOURCE_PREFIX = "source:"
NEW_TAG = "source:claude-code-conversation"


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 30.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_documents(base_url: str, bank: str, limit: int, offset: int) -> dict:
    params = urlencode({"limit": limit, "offset": offset})
    url = f"{base_url}/v1/default/banks/{bank}/documents?{params}"
    return _http_json("GET", url)


def patch_document_tags(base_url: str, bank: str, doc_id: str, tags: list[str]) -> dict:
    url = f"{base_url}/v1/default/banks/{bank}/documents/{doc_id}"
    return _http_json("PATCH", url, body={"tags": tags}, timeout=20)


def recall_count_for_tag(base_url: str, bank: str, tag: str) -> int:
    """Best-effort count of memories carrying `tag`, via recall with that tag."""
    url = f"{base_url}/v1/default/banks/{bank}/memories/recall"
    body = {
        "query": "ping",
        "tags": [tag],
        "tags_match": "all_strict",
        "max_tokens": 4096,
        "budget": "low",
    }
    try:
        resp = _http_json("POST", url, body=body, timeout=15)
    except Exception:
        return -1
    return len(resp.get("results") or [])


def _is_conversation_doc(tags: list[str]) -> bool:
    has_uuid = any(UUID_RE.match(t) for t in tags)
    has_source = any(t.startswith(SOURCE_PREFIX) for t in tags)
    return has_uuid and not has_source


def _doc_id(doc: dict) -> str | None:
    for key in ("id", "document_id", "documentId"):
        v = doc.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _doc_tags(doc: dict) -> list[str]:
    v = doc.get("tags")
    return list(v) if isinstance(v, list) else []


def _docs_from_response(resp: dict) -> list[dict]:
    """Hindsight response may use 'documents', 'items', or 'data'."""
    for key in ("documents", "items", "data", "results"):
        v = resp.get(key)
        if isinstance(v, list):
            return v
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bank", required=True)
    ap.add_argument(
        "--base-url",
        default=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually PATCH documents; default is dry-run",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=10_000,
        help="max documents to update in one run (safety cap; default 10k)",
    )
    ap.add_argument("--page-size", type=int, default=100)
    ap.add_argument("--start-offset", type=int, default=0)
    ap.add_argument(
        "--max-pages",
        type=int,
        default=200,
        help="hard ceiling on pagination loops (default 200 → 20k docs at page 100)",
    )
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")

    print(f"bank: {args.bank}")
    print(f"base: {base_url}")
    print(f"mode: {'APPLY (writes)' if args.apply else 'dry-run (no writes)'}")
    print()

    pre_count = recall_count_for_tag(base_url, args.bank, NEW_TAG)
    print(f"pre-backfill: {pre_count} memor{'y' if pre_count == 1 else 'ies'} currently tagged '{NEW_TAG}'")

    seen = 0
    candidates = 0
    updated = 0
    failed = 0
    offset = args.start_offset

    for page_idx in range(args.max_pages):
        try:
            resp = list_documents(base_url, args.bank, args.page_size, offset)
        except urllib.error.HTTPError as e:
            print(f"list_documents page {page_idx} failed: HTTP {e.code} {e.reason}", file=sys.stderr)
            break
        except Exception as e:
            print(f"list_documents page {page_idx} failed: {e!r}", file=sys.stderr)
            break

        docs = _docs_from_response(resp)
        if not docs:
            break

        for d in docs:
            seen += 1
            tags = _doc_tags(d)
            if not _is_conversation_doc(tags):
                continue
            doc_id = _doc_id(d)
            if not doc_id:
                continue
            candidates += 1
            new_tags = sorted({*tags, NEW_TAG})
            if not args.apply:
                if candidates <= 10:
                    print(f"  would patch {doc_id}: {tags} → {new_tags}")
                continue
            try:
                patch_document_tags(base_url, args.bank, doc_id, new_tags)
                updated += 1
                if updated % 25 == 0:
                    print(f"  ... patched {updated} so far")
            except urllib.error.HTTPError as e:
                failed += 1
                print(f"  fail {doc_id}: HTTP {e.code} {e.reason}", file=sys.stderr)
            except Exception as e:
                failed += 1
                print(f"  fail {doc_id}: {e!r}", file=sys.stderr)

            if updated >= args.limit:
                print(f"  hit --limit {args.limit}; stopping")
                break
        if updated >= args.limit:
            break
        offset += len(docs)
        if len(docs) < args.page_size:
            break

    print()
    print(f"seen: {seen} documents")
    print(f"conversation candidates: {candidates}")
    if args.apply:
        print(f"updated: {updated}")
        print(f"failed: {failed}")
        # Re-check memory-side tag count to see if PATCH propagated.
        post_count = recall_count_for_tag(base_url, args.bank, NEW_TAG)
        delta = post_count - pre_count if pre_count >= 0 else None
        delta_str = f" (delta {'+' if delta and delta >= 0 else ''}{delta})" if delta is not None else ""
        print(f"post-backfill: {post_count} memor{'y' if post_count == 1 else 'ies'} now tagged '{NEW_TAG}'{delta_str}")
        if pre_count >= 0 and post_count == pre_count:
            print()
            print("note: document tags updated but memory-level recall count unchanged.")
            print("  this likely means Hindsight stores memory tags separately from")
            print("  document tags. New retains will carry the new schema; historical")
            print("  memory units may need re-ingestion to inherit the tag.")
    else:
        print()
        print("dry-run only. re-run with --apply to actually update tags.")


if __name__ == "__main__":
    main()
