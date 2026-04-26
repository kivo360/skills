#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hindsight-client>=0.5",
# ]
# ///
"""
Risk forecaster: surface historical findings for a set of files, scored by
how strongly file co-occurrence predicts risk.

Inputs (pick one):
    --files a.ts b.go            explicit list
    --staged                     git-diff --cached
    --diff <ref>                 files in `git diff --name-only <ref>...HEAD`
    --node <qualname>            (TODO) CRG blast radius for a node

Output: scored memories grouped into HIGH / MEDIUM / CONTEXT, with the
co-occurrence count and bonus reasons shown so you can judge the call.

Scoring (per memory M, given input file set F):
    overlap = |M.tags ∩ {file:f for f in F}|        # how many input files this memory touches
    base    = min(overlap, 5)                       # cap so a single high-overlap doesn't dominate
    +3 if M has tag "status:fail"                   # actual test failure
    +2 if M is a git fix commit                     # git-bridge tag + content starts with fix:
    +2 if M has tag "source:test-run"               # test-bridge entries (any status)
    +1 if M has tag "source:review"                 # human review finding
    +0 if M has tag "source:reflection"             # context, not risk

    HIGH ≥ 5     ·     MEDIUM ≥ 2     ·     CONTEXT < 2

Environment:
    HINDSIGHT_BASE_URL    default http://localhost:8888
    HINDSIGHT_BANK_PREFIX default "kh"
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s


def _bold(s): return _c("1", s)
def _dim(s): return _c("2", s)
def _red(s): return _c("31", s)
def _yellow(s): return _c("33", s)
def _blue(s): return _c("34", s)
def _cyan(s): return _c("36", s)


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True, stderr=subprocess.PIPE)


def _repo_root() -> Path:
    return Path(_run(["git", "rev-parse", "--show-toplevel"]).strip())


def _bank_id(repo_root: Path) -> str:
    prefix = os.environ.get("HINDSIGHT_BANK_PREFIX", "kh")
    return f"{prefix}-::{repo_root.name}"


def _resolve_files(args: argparse.Namespace, repo_root: Path) -> list[str]:
    if args.files:
        return [f.strip() for f in args.files if f.strip()]
    if args.staged:
        out = _run(["git", "diff", "--name-only", "--cached"], cwd=repo_root)
        return [l.strip() for l in out.splitlines() if l.strip()]
    if args.diff:
        out = _run(
            ["git", "diff", "--name-only", f"{args.diff}...HEAD"], cwd=repo_root
        )
        return [l.strip() for l in out.splitlines() if l.strip()]
    raise SystemExit("must pass one of --files, --staged, --diff <ref>")


@dataclass
class Scored:
    memory_id: str
    text: str
    rtype: str
    when: str
    tags: list[str]
    score: int
    overlap: int
    reasons: list[str] = field(default_factory=list)


def _score(memory_tags: list[str], memory_text: str, memory_rtype: str,
           input_file_tags: set[str]) -> Scored | None:
    overlap = sum(1 for t in memory_tags if t in input_file_tags)
    if overlap == 0:
        return None
    base = min(overlap, 5)
    reasons: list[str] = [f"{overlap} file overlap"]
    score = base
    tagset = set(memory_tags)
    text_lower = memory_text.lower()

    if "status:fail" in tagset:
        score += 3
        reasons.append("test failure")
    if "source:test-run" in tagset and "status:fail" not in tagset:
        score += 2
        reasons.append("test run")
    if "source:git" in tagset:
        # heuristic: conventional-commit "fix" prefix in extracted text
        if text_lower.startswith("fix") or "fix:" in text_lower[:80]:
            score += 2
            reasons.append("git fix commit")
    if "source:review" in tagset or "crg-result-type:review" in tagset:
        score += 1
        reasons.append("review finding")
    if "source:reflection" in tagset:
        reasons.append("synthesis (context)")

    return Scored(
        memory_id="",  # filled by caller
        text=memory_text,
        rtype=memory_rtype,
        when="",
        tags=memory_tags,
        score=score,
        overlap=overlap,
        reasons=reasons,
    )


def _format_block(label: str, color_fn, items: list[Scored], max_per: int) -> None:
    if not items:
        return
    print(f"\n{_bold(color_fn(label))}  ({len(items)} memor{'y' if len(items) == 1 else 'ies'})")
    for s in items[:max_per]:
        snippet = s.text.strip().replace("\n", " ")
        if len(snippet) > 200:
            snippet = snippet[:200] + "…"
        head = f"  [score {s.score}]  {snippet}"
        meta = f"     {_dim('· '.join(s.reasons))} {_dim('·')} {_dim(s.rtype)} {_dim(s.when[:10])}"
        print(head)
        print(meta)
    if len(items) > max_per:
        print(_dim(f"  …and {len(items) - max_per} more"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--files", nargs="*", default=None)
    src.add_argument("--staged", action="store_true")
    src.add_argument("--diff", default=None, metavar="REF")
    ap.add_argument("--max-per-bucket", type=int, default=5)
    ap.add_argument("--budget", choices=["low", "mid", "high"], default="mid")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--bank", default=None,
                    help="override bank id (default: derived from repo)")
    args = ap.parse_args()

    repo_root = _repo_root()
    bank = args.bank or _bank_id(repo_root)
    files = _resolve_files(args, repo_root)
    if not files:
        print("no input files — nothing to forecast", file=sys.stderr)
        return

    input_file_tags = {f"file:{f}" for f in files}

    print(f"{_bold('Risk forecast')}  {_dim('bank=' + bank)}")
    print(f"{_dim('input files:')} {len(files)}  ({', '.join(files[:6])}{'…' if len(files) > 6 else ''})")

    from hindsight_client import Hindsight
    client = Hindsight(
        base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
        timeout=30.0,
    )

    resp = client.recall(
        bank_id=bank,
        query=f"failures, fixes, reviews and risks involving: {', '.join(files[:10])}",
        tags=sorted(input_file_tags),
        tags_match="any_strict",
        budget=args.budget,
        max_tokens=args.max_tokens,
    )

    results = getattr(resp, "results", None) or []
    print(f"{_dim('recalled memories:')} {len(results)}")
    if not results:
        print(_dim("\nno historical signal — proceed normally"))
        return

    scored: list[Scored] = []
    for r in results:
        text = getattr(r, "text", None) or getattr(r, "content", "") or ""
        rtype = getattr(r, "type", None) or ""
        when = getattr(r, "occurred_start", None) or getattr(r, "mentioned_at", None) or ""
        tags = getattr(r, "tags", None) or []
        s = _score(tags, text, rtype, input_file_tags)
        if not s:
            continue
        s.memory_id = getattr(r, "id", "") or ""
        s.when = str(when)
        scored.append(s)

    scored.sort(key=lambda x: (-x.score, -x.overlap))

    high = [s for s in scored if s.score >= 5]
    medium = [s for s in scored if 2 <= s.score < 5]
    context = [s for s in scored if s.score < 2]

    _format_block("HIGH RISK", _red, high, args.max_per_bucket)
    _format_block("MEDIUM RISK", _yellow, medium, args.max_per_bucket)
    _format_block("CONTEXT", _blue, context, max(2, args.max_per_bucket // 2))

    print()
    summary = (
        f"{_bold('summary')}  "
        f"{_red(str(len(high)) + ' high')}  ·  "
        f"{_yellow(str(len(medium)) + ' medium')}  ·  "
        f"{_blue(str(len(context)) + ' context')}"
    )
    print(summary)


if __name__ == "__main__":
    main()
