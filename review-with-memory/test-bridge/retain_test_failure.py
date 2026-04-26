#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hindsight-client>=0.5",
# ]
# ///
"""
Wrap a test command. On failure, retain the failure context to Hindsight.

Treats any non-zero exit code as a failure. Retains:
    - test command + exit code
    - stdout/stderr (truncated)
    - files changed since the last successful run (uses ``git diff --name-only HEAD``
      because if the test was passing before this commit, the diff is the suspect set)
    - timestamp

Tagged so future debugging recall surfaces "this kind of failure happened
before in this file."

Usage:
    retain_test_failure.py -- vitest run
    retain_test_failure.py -- bun test
    retain_test_failure.py -- pytest tests/
    retain_test_failure.py --label "ci-suite-1" -- npm test

The wrapper passes through the test runner's exit code, so it slots into
CI / pre-commit / Husky / etc. without changing pass/fail semantics.

Environment:
    HINDSIGHT_BASE_URL    default http://localhost:8888
    HINDSIGHT_BANK_PREFIX default "kh"
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

MAX_OUT_CHARS = 8000


def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else Path.cwd()


def _changed_files(repo_root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=False,
    )
    if out.returncode != 0:
        return []
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def _bank_id(repo_root: Path) -> str:
    prefix = os.environ.get("HINDSIGHT_BANK_PREFIX", "kh")
    return f"{prefix}-::{repo_root.name}"


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    head = s[: max_chars // 2]
    tail = s[-max_chars // 2:]
    return f"{head}\n…[truncated {len(s) - max_chars} chars]…\n{tail}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    ap.add_argument("--label", default=None, help="optional label tag, e.g. 'ci-suite-1'")
    ap.add_argument("--no-retain-on-success", action="store_true", default=True,
                    help="(default) only retain on failure")
    ap.add_argument("--retain-on-success", action="store_true",
                    help="also retain successful runs (noisy; off by default)")
    ap.add_argument("--quiet", action="store_true", help="suppress wrapper logs on stderr")
    ap.add_argument("command", nargs=argparse.REMAINDER,
                    help="test command after `--`, e.g. `-- vitest run`")
    args = ap.parse_args()

    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("missing test command after --", file=sys.stderr)
        return 2

    if not shutil.which(cmd[0]):
        # Don't fail the run because of this; just warn — `npm`, `bun`, etc.
        # are sometimes shell built-ins or shimmed.
        if not args.quiet:
            print(f"[test-bridge] note: '{cmd[0]}' not on PATH (continuing)", file=sys.stderr)

    repo_root = _repo_root()
    started = dt.datetime.now(dt.timezone.utc)

    # Stream stdout/stderr to the user while also capturing them.
    # We use Popen + reading both pipes so the test runner output stays live.
    proc = subprocess.Popen(
        cmd,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge so order is preserved
        text=True,
        bufsize=1,
    )
    captured: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        captured.append(line)
    proc.wait()
    output = "".join(captured)
    elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()

    rc = proc.returncode
    failed = rc != 0
    if not failed and not args.retain_on_success:
        if not args.quiet:
            print(f"[test-bridge] passed in {elapsed:.1f}s (no retain)", file=sys.stderr)
        return rc

    changed = _changed_files(repo_root)
    bank = _bank_id(repo_root)
    cmd_str = " ".join(cmd)
    nonce = hashlib.sha1(f"{started.isoformat()}::{cmd_str}".encode()).hexdigest()[:8]

    tags: list[str] = [
        f"repo:{repo_root.name}",
        "source:test-run",
        f"status:{'fail' if failed else 'pass'}",
    ]
    if args.label:
        tags.append(f"label:{args.label}")
    seen = set(tags)
    for f in changed[:30]:
        t = f"file:{f}"
        if t not in seen:
            seen.add(t)
            tags.append(t)
    for r in sorted({f.split("/", 1)[0] for f in changed if "/" in f})[:8]:
        t = f"module:{r}"
        if t not in seen:
            seen.add(t)
            tags.append(t)

    files_block = "\n".join(f"  - {f}" for f in changed[:30]) or "  (no uncommitted changes)"
    content = (
        f"Test run {'FAILED' if failed else 'passed'} (exit {rc}) at {started.isoformat()}\n"
        f"Command: {cmd_str}\n"
        f"Elapsed: {elapsed:.1f}s\n"
        f"\nUncommitted changes (suspect set):\n{files_block}\n"
        f"\nOutput (truncated):\n"
        f"{_truncate(output, MAX_OUT_CHARS)}"
    )

    try:
        from hindsight_client import Hindsight
        client = Hindsight(
            base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
            timeout=60.0,
        )
        client.retain(
            bank_id=bank,
            content=content,
            context="test-failure" if failed else "test-pass",
            tags=tags,
            timestamp=started,
            document_id=f"test-{nonce}",
        )
        if not args.quiet:
            print(
                f"[test-bridge] retained {'failure' if failed else 'pass'} "
                f"to bank '{bank}' ({len(tags)} tags, {len(content)} chars)",
                file=sys.stderr,
            )
    except Exception as e:
        if not args.quiet:
            print(f"[test-bridge] retain failed (non-fatal): {e!r}", file=sys.stderr)

    return rc


if __name__ == "__main__":
    sys.exit(main())
