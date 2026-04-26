#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# ///
"""
Derive Hindsight tags from a list of changed file paths.

Reads file paths from stdin (one per line) or from positional args.
Emits JSON: {"tags": [...], "modules": [...], "files": [...], "repo": "..."}.

Tag scheme (identity-scoped, not classification):
  repo:<basename>      derived from `git rev-parse --show-toplevel` if available
  module:<top-dir>     first path component (e.g. "src", "cli", "api")
  file:<full-path>     one per input file
  lang:<ext>           inferred from extension when known

Tags are stable identifiers — used to filter recall to "memories about this
subsystem". Don't add severity/topic/type tags here; those belong in content.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import PurePosixPath

LANG_BY_EXT = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".lua": "lua",
    ".sql": "sql",
    ".vue": "vue",
    ".svelte": "svelte",
    ".ipynb": "jupyter",
}


def repo_basename() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if out.returncode == 0:
            return os.path.basename(out.stdout.strip()) or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def main() -> None:
    if len(sys.argv) > 1:
        files = [a for a in sys.argv[1:] if a.strip()]
    else:
        files = [line.strip() for line in sys.stdin if line.strip()]

    if not files:
        json.dump({"tags": [], "modules": [], "files": [], "repo": None}, sys.stdout)
        sys.stdout.write("\n")
        return

    repo = repo_basename()
    modules: set[str] = set()
    langs: set[str] = set()
    file_tags: list[str] = []

    for raw in files:
        p = PurePosixPath(raw.replace("\\", "/"))
        parts = [pt for pt in p.parts if pt not in ("", ".", "..")]
        if parts:
            modules.add(parts[0])
        ext = p.suffix.lower()
        if ext in LANG_BY_EXT:
            langs.add(LANG_BY_EXT[ext])
        file_tags.append(f"file:{p.as_posix()}")

    tags: list[str] = []
    if repo:
        tags.append(f"repo:{repo}")
    tags.extend(f"module:{m}" for m in sorted(modules))
    tags.extend(f"lang:{l}" for l in sorted(langs))
    tags.extend(file_tags)

    json.dump(
        {
            "tags": tags,
            "modules": sorted(modules),
            "files": files,
            "repo": repo,
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
