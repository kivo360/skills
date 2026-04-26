#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hindsight-client>=0.5",
# ]
# ///
"""
Retain git commits into Hindsight as long-term decision memory.

Three modes:
    retain_commit.py                    # retain HEAD (post-commit hook usage)
    retain_commit.py <sha>              # retain a specific commit
    retain_commit.py --backfill N       # retain the last N commits in one batched call
    retain_commit.py --backfill --since=2026-01-01

Each commit becomes one memory item with:
    content   = subject + body + changed file list (+ optional truncated diff)
    timestamp = commit author date (so temporal queries are accurate)
    document_id = full sha (so re-runs upsert, never duplicate)
    tags      = repo:<name>, commit:<sha8>, author:<slug>, file:<path...>, source:git

Bank ID matches the Claude Code Hindsight plugin format ``<prefix>-::<repo>``
so commit memories share the bank with conversation transcripts and CRG retains.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

# Use 0x1F (Unit Separator) as a field delimiter — unlikely in commit messages
# and tolerated by Python's text-mode subprocess (NUL is not).
SEP = "\x1f"
COMMIT_FORMAT = f"%H{SEP}%aI{SEP}%an{SEP}%ae{SEP}%s{SEP}%b"
MAX_FILES_TAGGED = 30
MAX_BODY_CHARS = 2000
MAX_DIFF_CHARS = 4000


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True, stderr=subprocess.PIPE)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-") or "anon"


def _repo_root(start: Path | None = None) -> Path:
    out = _run(["git", "rev-parse", "--show-toplevel"], cwd=start).strip()
    return Path(out)


def _bank_id(repo_root: Path) -> str:
    prefix = os.environ.get("HINDSIGHT_BANK_PREFIX", "kh")
    return f"{prefix}-::{repo_root.name}"


def _commit_meta(repo_root: Path, sha: str) -> dict:
    raw = _run(
        ["git", "log", "-1", f"--format={COMMIT_FORMAT}", sha],
        cwd=repo_root,
    )
    parts = raw.split(SEP, 5)
    if len(parts) < 6:
        raise ValueError(f"bad git log output for {sha!r}: {raw!r}")
    full_sha, iso_date, author, email, subject, body = parts
    files = [
        f
        for f in _run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", full_sha],
            cwd=repo_root,
        ).splitlines()
        if f.strip()
    ]
    return {
        "sha": full_sha.strip(),
        "iso_date": iso_date.strip(),
        "author": author.strip(),
        "email": email.strip(),
        "subject": subject.strip(),
        "body": body.strip(),
        "files": files,
    }


def _commit_diff(repo_root: Path, sha: str, max_chars: int) -> str:
    try:
        out = _run(
            ["git", "show", "--no-color", "--stat", "--patch", sha], cwd=repo_root
        )
    except subprocess.CalledProcessError:
        return ""
    if len(out) > max_chars:
        return out[:max_chars] + f"\n…[truncated, +{len(out) - max_chars} chars]"
    return out


def _build_content(meta: dict, diff: str | None) -> str:
    body = meta["body"]
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n…[body truncated]"
    files_block = "\n".join(f"  - {f}" for f in meta["files"][:50])
    if len(meta["files"]) > 50:
        files_block += f"\n  - …and {len(meta['files']) - 50} more"
    out = [
        f"Commit {meta['sha'][:8]} by {meta['author']} on {meta['iso_date']}",
        f"Subject: {meta['subject']}",
    ]
    if body:
        out += ["", "Body:", body]
    if files_block:
        out += ["", "Changed files:", files_block]
    if diff:
        out += ["", "Diff (truncated):", diff]
    return "\n".join(out)


def _build_tags(meta: dict, repo_root: Path) -> list[str]:
    tags = [
        f"repo:{repo_root.name}",
        f"commit:{meta['sha'][:8]}",
        f"author:{_slug(meta['author'])}",
        "source:git",
    ]
    seen = set(tags)
    for f in meta["files"][:MAX_FILES_TAGGED]:
        t = f"file:{f}"
        if t not in seen:
            seen.add(t)
            tags.append(t)
    # tag a few path roots for module-level recall
    roots = {f.split("/", 1)[0] for f in meta["files"] if "/" in f}
    for r in sorted(roots)[:10]:
        t = f"module:{r}"
        if t not in seen:
            seen.add(t)
            tags.append(t)
    return tags


def _resolve_shas(repo_root: Path, args: argparse.Namespace) -> list[str]:
    if args.commit and args.commit != "HEAD":
        return [args.commit]
    if args.backfill is None and not args.since:
        return [_run(["git", "rev-parse", "HEAD"], cwd=repo_root).strip()]
    cmd = ["git", "log", "--format=%H"]
    if args.since:
        cmd += [f"--since={args.since}"]
    if args.backfill is not None:
        cmd += ["-n", str(args.backfill)]
    cmd += ["--reverse"]
    out = _run(cmd, cwd=repo_root).splitlines()
    return [s.strip() for s in out if s.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("commit", nargs="?", default="HEAD")
    ap.add_argument("--backfill", type=int, default=None, metavar="N")
    ap.add_argument("--since", default=None, help="git --since= expression")
    ap.add_argument("--include-diff", action="store_true")
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _repo_root()
    bank = _bank_id(repo_root)
    shas = _resolve_shas(repo_root, args)

    if not shas:
        print("no commits to retain", file=sys.stderr)
        return

    if not args.quiet:
        print(f"repo: {repo_root}")
        print(f"bank: {bank}")
        print(f"commits to retain: {len(shas)}")

    items: list[dict] = []
    for sha in shas:
        try:
            meta = _commit_meta(repo_root, sha)
        except Exception as e:
            print(f"  skip {sha[:8]}: {e}", file=sys.stderr)
            continue
        if not meta["files"]:
            # merges with no file changes — skip
            continue
        diff = _commit_diff(repo_root, sha, MAX_DIFF_CHARS) if args.include_diff else None
        content = _build_content(meta, diff)
        tags = _build_tags(meta, repo_root)
        try:
            timestamp = dt.datetime.fromisoformat(meta["iso_date"])
        except ValueError:
            timestamp = dt.datetime.now(dt.timezone.utc)
        items.append(
            {
                "content": content,
                "timestamp": timestamp,
                "context": "git-commit",
                "tags": tags,
                "document_id": meta["sha"],
                "metadata": {
                    "sha": meta["sha"],
                    "subject": meta["subject"],
                    "author_email": meta["email"],
                },
            }
        )
        if not args.quiet:
            short = meta["subject"][:60]
            print(f"  + {meta['sha'][:8]} {short}  [{len(tags)} tags, {len(meta['files'])} files]")

    if not items:
        print("no items prepared (only merges or errors)", file=sys.stderr)
        return

    if args.dry_run:
        print(f"\ndry-run: would retain {len(items)} items to bank '{bank}'")
        return

    from hindsight_client import Hindsight

    client = Hindsight(
        base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
        timeout=180.0,
    )
    if len(items) == 1:
        client.retain(bank_id=bank, **items[0])
    else:
        client.retain_batch(bank_id=bank, items=items)

    if not args.quiet:
        print(f"\nretained {len(items)} commits to bank '{bank}'")


if __name__ == "__main__":
    main()
