#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "code-review-graph",
#     "hindsight-client>=0.5",
# ]
# ///
"""
Drop-in replacement for the `code-review-graph` CLI/MCP entry point that
also retains every save_result() call into Hindsight.

Why a wrapper instead of forking CRG: CRG's memory.save_result() is the single
chokepoint where Q&A results, reviews, and debug output get persisted as
markdown for later graph re-ingestion. By monkey-patching it before CRG's CLI
dispatches, we add a second sink (Hindsight) without touching upstream code.

Usage:
    crg_with_memory.py build               # same args as `code-review-graph build`
    crg_with_memory.py serve --transport stdio   # MCP server mode
    crg_with_memory.py status

To swap into existing MCP configs, point them at this script instead of the
plain `code-review-graph` binary. The wrapper passes argv unchanged.

Environment:
    HINDSIGHT_BASE_URL    default http://localhost:8888
    HINDSIGHT_BANK_PREFIX default "kh" — must match the Claude Code plugin's
                          bankIdPrefix so CRG and chat memories share a bank
    CRG_HINDSIGHT_QUIET   set to "1" to silence retain confirmations on stderr
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import code_review_graph.memory as _crg_memory

_ORIGINAL_SAVE_RESULT = _crg_memory.save_result


def _resolve_repo_root(repo_root: Any) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        ).strip()
        if out:
            return Path(out)
    except Exception:
        pass
    return Path.cwd()


def _bank_id(repo_root: Path) -> str:
    """Format matches the Hindsight Claude Code plugin's dynamic bank ID
    when granularity = ['agent', 'project']: ``<prefix>-<agent>:<project>``,
    with empty agent slot collapsing to two colons.
    """
    prefix = os.environ.get("HINDSIGHT_BANK_PREFIX", "kh")
    return f"{prefix}-::{repo_root.name}"


def _normalize_node(node: str, repo_root: Path) -> tuple[str, str]:
    """Return (file_part, full_qualname) with the file portion made relative
    to repo_root when possible. Handles CRG's two qualname shapes:
    absolute paths and ``path::Symbol`` qualnames.
    """
    qual = node
    file_part = node.split("::", 1)[0]
    root_str = str(repo_root)
    if file_part.startswith(root_str):
        file_part = file_part[len(root_str):].lstrip("/")
    return file_part, qual


def _derive_tags(repo_root: Path, nodes: list[str] | None, result_type: str) -> list[str]:
    tags = [f"repo:{repo_root.name}", f"crg-result-type:{result_type}", "source:crg"]
    seen = set(tags)
    for n in (nodes or [])[:30]:
        file_part, qual = _normalize_node(n, repo_root)
        for t in (f"node:{qual}", f"file:{file_part}" if ("/" in file_part or "\\" in file_part) else None):
            if t and t not in seen:
                seen.add(t)
                tags.append(t)
    return tags


def _patched_save_result(
    question: str,
    answer: str,
    nodes: list[str] | None = None,
    result_type: str = "query",
    memory_dir: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    path = _ORIGINAL_SAVE_RESULT(
        question=question,
        answer=answer,
        nodes=nodes,
        result_type=result_type,
        memory_dir=memory_dir,
        repo_root=repo_root,
    )

    try:
        from hindsight_client import Hindsight

        resolved_root = _resolve_repo_root(repo_root)
        bank = _bank_id(resolved_root)
        tags = _derive_tags(resolved_root, nodes, result_type)
        client = Hindsight(
            base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
            timeout=15.0,
        )
        client.retain(
            bank_id=bank,
            content=f"Q: {question}\n\nA: {answer}",
            context=f"crg-{result_type}",
            tags=tags,
        )
        if os.environ.get("CRG_HINDSIGHT_QUIET") != "1":
            sys.stderr.write(
                f"[crg-hindsight] retained to bank '{bank}' "
                f"({len(tags)} tags, {len(answer)} chars)\n"
            )
    except Exception as exc:
        sys.stderr.write(f"[crg-hindsight] retain failed (non-fatal): {exc!r}\n")

    return path


_crg_memory.save_result = _patched_save_result


def main() -> None:
    from code_review_graph.cli import main as crg_main

    crg_main()


if __name__ == "__main__":
    main()
