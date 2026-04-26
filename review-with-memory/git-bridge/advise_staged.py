#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hindsight-client>=0.5",
# ]
# ///
"""
Pre-commit advisory: print Hindsight memories relevant to the staged files.

Designed as a non-blocking git pre-commit hook (always exits 0). Use as:
    git config core.hooksPath /path/to/this/dir
    # or symlink: ln -s advise_staged.py .git/hooks/pre-commit

Manual invocation:
    advise_staged.py                     # uses staged files
    advise_staged.py --files a.ts b.go   # explicit list
    advise_staged.py --query "auth"      # custom query, ignores staged files
    advise_staged.py --max 5 --budget low

Output is human-readable, terse, color where stdout is a TTY. Never blocks
the commit, even on errors.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s


def _bold(s): return _c("1", s)
def _dim(s): return _c("2", s)
def _green(s): return _c("32", s)
def _yellow(s): return _c("33", s)
def _cyan(s): return _c("36", s)


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE)


def _repo_root() -> Path:
    return Path(_run(["git", "rev-parse", "--show-toplevel"]).strip())


def _bank_id(repo_root: Path) -> str:
    prefix = os.environ.get("HINDSIGHT_BANK_PREFIX", "kh")
    return f"{prefix}-::{repo_root.name}"


def _staged_files() -> list[str]:
    out = _run(["git", "diff", "--name-only", "--cached"])
    return [l.strip() for l in out.splitlines() if l.strip()]


def _build_tags(files: list[str]) -> list[str]:
    tags = []
    seen: set[str] = set()
    for f in files[:30]:
        t = f"file:{f}"
        if t not in seen:
            seen.add(t)
            tags.append(t)
    roots = {f.split("/", 1)[0] for f in files if "/" in f}
    for r in sorted(roots)[:8]:
        t = f"module:{r}"
        if t not in seen:
            seen.add(t)
            tags.append(t)
    return tags


def _format_result(r) -> str:
    text = getattr(r, "text", None) or getattr(r, "content", "") or ""
    rtype = getattr(r, "type", None) or ""
    when = getattr(r, "occurred_start", None) or getattr(r, "mentioned_at", None) or ""
    when_short = str(when)[:10] if when else ""
    snippet = (text or "").strip().replace("\n", " ")
    if len(snippet) > 220:
        snippet = snippet[:220] + "…"
    meta_parts = [p for p in (rtype, when_short) if p]
    meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
    return f"{snippet}{_dim(meta)}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--query", default=None, help="override query (default: file list)")
    ap.add_argument("--max", type=int, default=4, help="max memories to print")
    ap.add_argument("--budget", default="low", choices=["low", "mid", "high"])
    ap.add_argument("--tags-match", default="any_strict",
                    choices=["any", "all", "any_strict", "all_strict"])
    ap.add_argument("--max-tokens", type=int, default=600)
    ap.add_argument("--silent-on-empty", action="store_true",
                    help="suppress output when nothing matched (good for hooks)")
    args = ap.parse_args()

    try:
        repo_root = _repo_root()
    except Exception:
        return  # not a git repo; silently no-op
    bank = _bank_id(repo_root)

    files = args.files if args.files is not None else _staged_files()
    if not files and not args.query:
        return  # nothing staged

    tags = _build_tags(files)
    query = args.query or f"context for changes touching: {', '.join(files[:10])}"

    try:
        from hindsight_client import Hindsight
        client = Hindsight(
            base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
            timeout=8.0,
        )
        t0 = time.monotonic()
        resp = client.recall(
            bank_id=bank,
            query=query,
            tags=tags,
            tags_match=args.tags_match,
            budget=args.budget,
            max_tokens=args.max_tokens,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
    except Exception as e:
        # Fail open — never block a commit
        print(_dim(f"[hindsight] advisory unavailable: {e!r}"), file=sys.stderr)
        return

    results = getattr(resp, "results", None) or []
    if not results:
        if not args.silent_on_empty:
            print(_dim(f"[hindsight] no relevant memories for {len(files)} staged files "
                      f"({elapsed_ms}ms)"), file=sys.stderr)
        return

    print(_bold(_cyan(f"[hindsight] {len(results)} memory hit(s) for {len(files)} staged "
                       f"file(s) — {elapsed_ms}ms")), file=sys.stderr)
    for r in results[: args.max]:
        print(f"  {_yellow('★')} {_format_result(r)}", file=sys.stderr)
    if len(results) > args.max:
        print(_dim(f"  …and {len(results) - args.max} more"), file=sys.stderr)


if __name__ == "__main__":
    main()
