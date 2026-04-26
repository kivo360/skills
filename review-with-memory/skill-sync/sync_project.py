#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hindsight-client>=0.5",
#     "code-review-graph",
# ]
# ///
"""
Project-aware skill onboarding.

Reads the toolbelt's existing skills-index.json, gathers signals from the
current project (CRG hubs, Hindsight bank tags, repo structure, package
manifests), and prints a report of:

  PROMOTE  cold/staging skills with strong project signal — `toolbelt skills install <name>`
  DEMOTE   active skills with effectively no project signal (observational)
  GAPS     project topics with high mass but no covering skill — suggested skill name

Suggest-only: never installs, demotes, or drafts files. You decide.

Usage:
    sync_project.py                         # current cwd
    sync_project.py --repo /path/to/proj
    sync_project.py --json                  # machine-readable
    sync_project.py --quiet                 # silent unless something's actionable
    sync_project.py --top-n 8

Environment:
    HINDSIGHT_BASE_URL    default http://localhost:8888
    HINDSIGHT_BANK_PREFIX default "kh"
    SKILLS_INDEX          default ~/.agents/skills-index.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

STOPWORDS = {
    # English fillers
    "the", "and", "for", "with", "from", "into", "your", "this", "that",
    "all", "any", "are", "via", "such", "also", "more", "most", "very",
    "across", "between", "many", "each", "etc", "should", "would", "could",
    "when", "what", "where", "why", "how", "you", "we", "they", "their",
    "it", "its", "is", "be", "do", "does", "doing", "to", "of", "in",
    "on", "at", "by", "as", "or", "an", "if", "then", "than",
    "so", "but", "not", "just", "only", "other", "own", "same",
    "different", "various", "well", "much", "still", "yet",
    "now", "today", "yesterday", "tomorrow",
    # Generic verbs that match every skill
    "use", "uses", "using", "used", "make", "made", "create", "creates",
    "creating", "build", "builds", "building", "run", "runs", "running",
    "have", "has", "been", "include", "includes", "including",
    "support", "supports", "supported", "based", "set", "get", "see",
    "add", "added", "adds", "adding", "remove", "removes", "removed",
    "find", "finds", "found", "show", "shows", "shown",
    "before", "after", "while", "during",
    "like", "either", "though", "instead", "rather",
    # Generic software nouns
    "skill", "skills", "task", "tasks", "tool", "tools", "user",
    "users", "code", "codebase", "project", "projects", "data", "info",
    "context", "actions", "action", "process", "processes", "setup",
    "config", "configuration", "options", "option", "system", "systems",
    "module", "modules", "file", "files", "function", "functions",
    "feature", "features", "domain", "domains", "core", "common",
    "specific", "general", "default", "defaults", "main", "type", "types",
    "import", "imports", "export", "exports", "library", "package",
    "scripts", "script", "command", "commands", "argument", "arguments",
    # Time/date noise from memory text
    "when", "time", "times", "date", "dates", "ago", "minute", "minutes",
    "hour", "hours", "day", "days", "week", "weeks", "month", "months",
    "year", "years",
}


def _looks_like_timestamp_or_number(token: str) -> bool:
    """Drop pure-numeric, hex, date-ish, or version-string tokens."""
    if token.isdigit():
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", token):
        return True
    if re.fullmatch(r"\d+[a-z]?", token):
        return True
    if re.fullmatch(r"v?\d+\.\d+.*", token):
        return True
    if re.fullmatch(r"[0-9a-f]{8,}", token):  # commit-sha-like
        return True
    return False

TIER_BONUS = {"S": 3, "A": 2, "B": 1, "C": 0}


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s


def _bold(s): return _c("1", s)
def _dim(s): return _c("2", s)
def _green(s): return _c("32", s)
def _yellow(s): return _c("33", s)
def _blue(s): return _c("34", s)
def _cyan(s): return _c("36", s)
def _red(s): return _c("31", s)


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    raw = re.findall(r"[a-z][a-z0-9_-]{2,}", text.lower())  # leading letter required
    return {
        t for t in raw
        if t not in STOPWORDS and not _looks_like_timestamp_or_number(t)
    }


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 5) -> str:
    try:
        return subprocess.check_output(
            cmd, cwd=cwd, text=True, stderr=subprocess.DEVNULL, timeout=timeout
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return ""


@dataclass
class Project:
    repo_root: Path
    name: str
    bank_id: str
    is_git: bool
    has_crg_db: bool
    manifest_files: list[str] = field(default_factory=list)


@dataclass
class Skill:
    name: str
    tier: str
    description: str
    triggers: list[str]
    installed_path: str | None
    cold_path: str | None
    staging_path: str | None
    protected: bool

    @property
    def state(self) -> str:
        if self.installed_path:
            return "active"
        if self.staging_path:
            return "staging"
        if self.cold_path:
            return "cold"
        return "unknown"


@dataclass
class Scored:
    skill: Skill
    score: float
    reasons: list[str]


def detect_project(cwd: Path) -> Project | None:
    # Anchor on git toplevel if available; else cwd.
    git_root = _run(["git", "rev-parse", "--show-toplevel"], cwd=cwd).strip()
    repo_root = Path(git_root) if git_root else cwd.resolve()

    # Refuse trivial roots.
    home = Path.home().resolve()
    if repo_root in (home, Path("/"), Path("/tmp")):
        return None
    # Refuse if the path contains "Downloads" or other obvious non-project dirs.
    if any(part in ("Downloads", "Desktop") for part in repo_root.parts):
        return None

    is_git = bool(git_root)
    has_crg_db = (repo_root / ".code-review-graph" / "graph.db").exists()
    manifest_candidates = [
        "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
        "Gemfile", "build.gradle", "pom.xml", "deno.json",
    ]
    manifests = [m for m in manifest_candidates if (repo_root / m).exists()]

    if not (is_git or has_crg_db or manifests):
        return None

    prefix = os.environ.get("HINDSIGHT_BANK_PREFIX", "kh")
    return Project(
        repo_root=repo_root,
        name=repo_root.name,
        bank_id=f"{prefix}-::{repo_root.name}",
        is_git=is_git,
        has_crg_db=has_crg_db,
        manifest_files=manifests,
    )


def load_skills(index_path: Path) -> dict[str, Skill]:
    data = json.loads(index_path.read_text())
    skills_map = data.get("skills", {})
    out: dict[str, Skill] = {}
    for name, rec in skills_map.items():
        out[name] = Skill(
            name=name,
            tier=rec.get("tier", "C"),
            description=rec.get("description", ""),
            triggers=rec.get("triggers", []) or [],
            installed_path=rec.get("installedPath"),
            cold_path=rec.get("coldPath"),
            staging_path=rec.get("stagingPath"),
            protected=bool(rec.get("protected")),
        )
    return out


def gather_crg_signals(repo_root: Path, top_n: int) -> dict[str, Any]:
    db_path = repo_root / ".code-review-graph" / "graph.db"
    if not db_path.exists():
        return {"hubs": [], "tokens": set(), "available": False}
    try:
        from code_review_graph.analysis import find_hub_nodes
        from code_review_graph.tools._common import _get_store
        store, _ = _get_store(str(repo_root))
        hubs = find_hub_nodes(store, top_n=top_n) or []
    except ImportError:
        return {"hubs": [], "tokens": set(), "available": False}
    except Exception as e:
        sys.stderr.write(f"[skill-sync] CRG signals partial: {e!r}\n")
        hubs = []
    tokens: set[str] = set()
    for h in hubs:
        for field_ in ("name", "qualified_name", "file"):
            tokens |= _tokens(str(h.get(field_, "")))
    return {"hubs": hubs, "tokens": tokens, "available": True}


def gather_bank_signals(bank_id: str, sample_n: int) -> dict[str, Any]:
    """Pull a sample of recent memories and aggregate frequent tokens + tags."""
    try:
        from hindsight_client import Hindsight
        client = Hindsight(
            base_url=os.environ.get("HINDSIGHT_BASE_URL", "http://localhost:8888"),
            timeout=15.0,
        )
        resp = client.recall(
            bank_id=bank_id,
            query="what topics, modules, and patterns has work in this project covered?",
            budget="low",
            max_tokens=4096,
        )
    except Exception as e:
        sys.stderr.write(f"[skill-sync] bank signals unavailable: {e!r}\n")
        return {"tokens": set(), "tag_counts": Counter(), "memory_count": 0, "available": False}

    results = getattr(resp, "results", None) or []
    tokens: set[str] = set()
    tag_counts: Counter[str] = Counter()
    for r in results[:sample_n]:
        text = getattr(r, "text", None) or getattr(r, "content", "") or ""
        tokens |= _tokens(text)
        for t in (getattr(r, "tags", None) or []):
            tag_counts[t] += 1
    return {
        "tokens": tokens,
        "tag_counts": tag_counts,
        "memory_count": len(results),
        "available": True,
    }


def gather_repo_signals(project: Project) -> dict[str, Any]:
    tokens: set[str] = set()
    # Top-level dir names and well-known content.
    for entry in project.repo_root.iterdir():
        if entry.name.startswith(".") or entry.is_file():
            continue
        tokens |= _tokens(entry.name)
    # Manifest deps — names only.
    for manifest in project.manifest_files:
        path = project.repo_root / manifest
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")[:50000]
            tokens |= _tokens(content)
        except Exception:
            continue
    return {"tokens": tokens}


def _project_tags_cache_path(bank_id: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", bank_id).strip("-") or "default"
    return Path.home() / ".cache" / "review-with-memory" / "project-tags" / f"{slug}.json"


def _tag_token_weights(bank_id: str) -> dict[str, float]:
    """Mirror of loadProjectBoosts in cli/src/lib/context-rules.ts. Reads the
    same cache file so skill-sync's scoring is consistent with what the live
    suggester applies via the project-boost rule."""
    path = _project_tags_cache_path(bank_id)
    if not path.exists():
        return {}
    try:
        cache = json.loads(path.read_text())
    except Exception:
        return {}
    out: dict[str, float] = {}
    for t in cache.get("top_tags", []):
        tag = t.get("tag", "")
        weight = float(t.get("weight", 0))
        if weight <= 0:
            continue
        colon = tag.find(":")
        value = tag[colon + 1:] if colon >= 0 else tag
        for tok in re.findall(r"[a-z][a-z0-9_-]{2,}", value.lower()):
            out[tok] = max(out.get(tok, 0), weight)
    return out


def score_skill(
    skill: Skill,
    project_tokens: set[str],
    project_keyword_anchors: set[str],
    tag_weights: dict[str, float],
) -> Scored:
    desc_tokens = _tokens(skill.description)
    trigger_tokens = {t.lower() for t in skill.triggers}
    reasons: list[str] = []
    score = 0.0

    # 1. Project-boost (mirrors the TS suggester's loadProjectBoosts).
    # Strongest tag-token weight matched by trigger or name → sqrt-scaled boost.
    if tag_weights:
        best_w = 0.0
        name_tokens = {t for t in re.split(r"[-_]", skill.name.lower()) if len(t) >= 3}
        for tok in trigger_tokens | name_tokens:
            w = tag_weights.get(tok, 0.0)
            if w > best_w:
                best_w = w
        if best_w > 0:
            boost = (best_w ** 0.5) * 16  # cap=16 sqrt-scaled, matches TS
            score += boost
            reasons.append(f"project-boost {boost:.1f} (best tag w={best_w:.2f})")

    # 2. Description-token overlap — secondary signal.
    overlap = desc_tokens & project_tokens
    if overlap:
        bonus = min(len(overlap), 6)
        score += bonus
        reasons.append(f"{len(overlap)} desc-token overlap (e.g. {sorted(overlap)[:3]})")

    # 3. Trigger overlap with manifest/repo anchors (separate from project tags).
    trigger_hits = trigger_tokens & project_keyword_anchors
    if trigger_hits:
        score += 3 * len(trigger_hits)
        reasons.append(f"trigger anchor: {sorted(trigger_hits)[:3]}")

    # 4. Tier bonus only when there's already signal.
    if score > 0:
        bonus = TIER_BONUS.get(skill.tier, 0)
        if bonus:
            score += bonus
            reasons.append(f"tier {skill.tier} +{bonus}")

    return Scored(skill=skill, score=score, reasons=reasons)


def detect_gaps(
    skills: dict[str, Skill], project_tokens: set[str], top_per_skill: int = 80
) -> list[dict[str, Any]]:
    """Find project tokens that no active skill mentions.

    Sorts by specificity — compound (hyphenated) terms first, then by
    length descending. Generic short single-word tokens fall to the back
    of the list because they're rarely real gaps; multi-word identifiers
    (e.g. ``asyncpg-to-sqlalchemy-converter``) are.
    """
    covered: set[str] = set()
    for s in skills.values():
        if s.state != "active":
            continue
        covered |= _tokens(s.description) | {t.lower() for t in s.triggers}
    uncovered = project_tokens - covered

    def specificity(token: str) -> tuple[int, int, int, str]:
        # Higher tuple = more specific. Sort descending.
        has_hyphen = 1 if "-" in token else 0
        parts = len(token.split("-"))
        return (has_hyphen, parts, len(token), token)

    ranked = sorted(uncovered, key=specificity, reverse=True)[:30]
    if not ranked:
        return []
    return [{"uncovered_tokens": ranked}]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress output unless promotions/gaps exist")
    ap.add_argument("--top-n", type=int, default=8,
                    help="how many promote/demote/gap items to show")
    ap.add_argument("--promote-threshold", type=float, default=4.0)
    ap.add_argument("--demote-threshold", type=float, default=0.5)
    ap.add_argument(
        "--validate-gaps",
        type=int,
        default=0,
        metavar="N",
        help="run llm_validate.py on the top N gap tokens to confirm they "
        "really aren't covered by existing skills (costs ~3s per validation).",
    )
    ap.add_argument("--skills-index", default=os.environ.get(
        "SKILLS_INDEX", str(Path.home() / ".agents/skills-index.json")
    ))
    args = ap.parse_args()

    cwd = Path(args.repo).resolve() if args.repo else Path.cwd()
    project = detect_project(cwd)
    if not project:
        if not args.quiet:
            print(f"[skill-sync] not a meaningful project at {cwd}", file=sys.stderr)
        return

    skills_path = Path(args.skills_index).expanduser()
    if not skills_path.exists():
        sys.stderr.write(f"[skill-sync] missing skills index: {skills_path}\n")
        sys.exit(1)
    skills = load_skills(skills_path)

    crg = gather_crg_signals(project.repo_root, top_n=15)
    bank = gather_bank_signals(project.bank_id, sample_n=50)
    repo_sig = gather_repo_signals(project)

    project_tokens = repo_sig["tokens"] | crg["tokens"] | bank["tokens"]
    # Keyword anchors: stronger lexical hooks (top-level dir names, manifest names).
    keyword_anchors = repo_sig["tokens"] | crg["tokens"]

    tag_weights = _tag_token_weights(project.bank_id)
    scored = [score_skill(s, project_tokens, keyword_anchors, tag_weights) for s in skills.values()]

    promotes: list[Scored] = sorted(
        [s for s in scored if s.skill.state in ("cold", "staging") and s.score >= args.promote_threshold],
        key=lambda x: -x.score,
    )[: args.top_n]

    demotes: list[Scored] = sorted(
        [s for s in scored if s.skill.state == "active" and not s.skill.protected and s.score < args.demote_threshold],
        key=lambda x: x.score,
    )[: args.top_n]

    gaps = detect_gaps(skills, project_tokens)

    if args.quiet and not (promotes or gaps):
        return

    if args.json:
        out = {
            "project": {
                "repo_root": str(project.repo_root),
                "name": project.name,
                "bank_id": project.bank_id,
                "is_git": project.is_git,
                "has_crg_db": project.has_crg_db,
                "manifests": project.manifest_files,
            },
            "signals": {
                "repo_tokens": len(repo_sig["tokens"]),
                "crg_tokens": len(crg["tokens"]),
                "crg_available": crg.get("available", False),
                "bank_memory_count": bank["memory_count"],
                "bank_tokens": len(bank["tokens"]),
                "bank_available": bank.get("available", False),
            },
            "promotes": [
                {"name": s.skill.name, "tier": s.skill.tier, "state": s.skill.state,
                 "score": s.score, "reasons": s.reasons}
                for s in promotes
            ],
            "demotes": [
                {"name": s.skill.name, "tier": s.skill.tier, "state": s.skill.state,
                 "score": s.score, "reasons": s.reasons}
                for s in demotes
            ],
            "gaps": gaps,
        }
        print(json.dumps(out, indent=2, default=str))
        return

    print(f"{_bold('skill-sync')} {_dim(str(project.repo_root))}")
    print(
        f"{_dim('signals:')} "
        f"{'CRG ✓' if crg.get('available') else 'CRG –'}  "
        f"{'bank ✓ (' + str(bank['memory_count']) + ' memories)' if bank.get('available') else 'bank –'}  "
        f"{'manifests: ' + ','.join(project.manifest_files) if project.manifest_files else 'no manifest'}"
    )

    if promotes:
        print(f"\n{_bold(_green('PROMOTE'))}  ({len(promotes)})")
        for s in promotes:
            print(f"  {_green('★')} {s.skill.name}  {_dim('[' + s.skill.state + '→active, tier ' + s.skill.tier + ']')}  score {s.score:.1f}")
            print(f"     {_dim('· '.join(s.reasons))}")
            print(f"     {_cyan('toolbelt skills install ' + s.skill.name)}")
    elif not args.quiet:
        print(f"\n{_dim('PROMOTE  (none — no cold/staging skills score above ' + str(args.promote_threshold) + ')')}")

    if demotes and not args.quiet:
        print(f"\n{_bold(_yellow('DEMOTE (observational)'))}  ({len(demotes)})")
        for s in demotes:
            print(f"  {_yellow('·')} {s.skill.name}  {_dim('[active, tier ' + s.skill.tier + ']')}  score {s.score:.1f}")
            print(f"     {_dim('no project signal — global demote: toolbelt skills demote ' + s.skill.name)}")

    if gaps:
        print(f"\n{_bold(_red('GAP'))}  ({len(gaps[0]['uncovered_tokens'])} project tokens uncovered)")
        toks = gaps[0]["uncovered_tokens"][: args.top_n * 2]
        print("  " + ", ".join(toks))
        print(_dim("  consider creating skills for project topics that recur but no skill covers."))

        if args.validate_gaps > 0:
            print(f"\n{_bold(_red('GAP — LLM-validated'))}  (top {args.validate_gaps} via llm_validate.py)")
            llm_validate = Path(__file__).parent / "llm_validate.py"
            for token in toks[: args.validate_gaps]:
                try:
                    proc = subprocess.run(
                        [str(llm_validate), "validate-gap", "--topic", token],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                    print(f"  {_dim('skip ' + token + ': ' + repr(e))}")
                    continue
                if proc.returncode != 0:
                    print(f"  {_dim('skip ' + token + ': llm exited ' + str(proc.returncode))}")
                    continue
                try:
                    parsed = json.loads(proc.stdout.strip())
                except json.JSONDecodeError:
                    print(f"  {_dim('skip ' + token + ': non-JSON')}")
                    continue
                is_real = parsed.get("is_real_gap")
                if is_real is True:
                    name = parsed.get("suggested_skill_name") or "?"
                    desc = parsed.get("suggested_description") or ""
                    print(f"  {_red('!')} {token}  {_dim('→ suggested:')} {_bold(name)}")
                    if desc:
                        print(f"     {_dim(desc[:160])}")
                elif is_real is False:
                    covered = parsed.get("covered_by") or []
                    reason = parsed.get("reasoning") or ""
                    cov = ", ".join(covered) if covered else "(no specific skills listed)"
                    print(f"  {_dim('· ' + token + ' — not a gap; covered by ' + cov + '. ' + reason[:80])}")
                else:
                    print(f"  {_dim('? ' + token + ' — llm verdict null')}")

    print()


if __name__ == "__main__":
    main()
