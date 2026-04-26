#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
LLM sanity-check for skill suggestions and gap candidates.

Fixes the failure mode surfaced by run-probes-project-aware.ts: project-
boosted suggestions that share tokens with the bank but aren't actually
relevant (e.g. `fieldtheory-cli-bookmarks` for "fix the login flow" via
the `cli` token). TF-IDF weighting helps but vocabulary overlap is not
semantic relevance.

This script asks an OpenAI-compatible LLM (Fireworks/Kimi by default,
read from review-with-memory/.env) two kinds of questions:

  --mode filter-suggestions:
    Given a prompt + a list of candidate skills, return only the ones
    that genuinely apply. JSON in, JSON out, batched into a single call.

  --mode validate-gap:
    Given a topic that skill-sync flagged as a gap (no covering skill),
    answer: is this a real gap, or do existing skills cover it? Returns
    the closest existing skills, plus a yes/no verdict.

Why a separate script: the suggester runs in Bun/TS and shouldn't grow
an HTTP client + LLM provider abstraction. This script is a thin shim
behind one CLI entry point — easy to swap the provider without touching
the TS code.

Usage:
    cat candidates.json | llm_validate.py --mode filter-suggestions \\
                                          --prompt "fix the login flow"
    llm_validate.py --mode validate-gap --topic "asyncpg-to-sqlalchemy" \\
                                          --skills-index ~/.agents/skills-index.json

Environment (in priority order):
    LLM_API_KEY / FIREWORKS_API_KEY / OPENAI_API_KEY
    LLM_BASE_URL  (default https://api.fireworks.ai/inference/v1)
    LLM_MODEL     (default accounts/fireworks/routers/kimi-k2p5-turbo)

Or load from review-with-memory/.env:
    HINDSIGHT_API_LLM_API_KEY
    HINDSIGHT_API_LLM_BASE_URL
    HINDSIGHT_API_LLM_MODEL

Exit codes:
    0  validated; output is the filtered/answered JSON on stdout
    1  hard error (no API key, network fail after retries)
    2  bad arguments
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"
DEFAULT_MODEL = "accounts/fireworks/routers/kimi-k2p5-turbo"
ENV_FILE_CANDIDATES = [
    Path.home() / "Coding/Tooling/coding-toolbelt/review-with-memory/.env",
]


def _load_env_file() -> None:
    """Best-effort load of HINDSIGHT_API_LLM_* from review-with-memory/.env."""
    for path in ENV_FILE_CANDIDATES:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


def _resolve_provider() -> tuple[str, str, str]:
    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("FIREWORKS_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("HINDSIGHT_API_LLM_API_KEY")
    )
    base_url = (
        os.environ.get("LLM_BASE_URL")
        or os.environ.get("HINDSIGHT_API_LLM_BASE_URL")
        or DEFAULT_BASE_URL
    )
    model = (
        os.environ.get("LLM_MODEL")
        or os.environ.get("HINDSIGHT_API_LLM_MODEL")
        or DEFAULT_MODEL
    )
    if not api_key:
        sys.stderr.write(
            "no API key — set LLM_API_KEY, FIREWORKS_API_KEY, OPENAI_API_KEY, "
            "or HINDSIGHT_API_LLM_API_KEY (e.g. via .env)\n"
        )
        sys.exit(1)
    return api_key, base_url.rstrip("/"), model


def _chat_completion(
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int = 800,
    temperature: float = 0.0,
    timeout: float = 30.0,
    json_mode: bool = True,
) -> str:
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        # OpenAI-spec JSON mode; Fireworks supports it. Falls back gracefully
        # if the provider ignores the field — we still parse the response.
        payload["response_format"] = {"type": "json_object"}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "review-with-memory/llm-validate (python-urllib)",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"llm http {e.code}: {e.read().decode('utf-8', 'replace')[:200]}\n")
        raise
    except Exception as e:
        sys.stderr.write(f"llm call failed: {e!r}\n")
        raise
    choices = payload.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content", "")


def _extract_json_block(text: str) -> dict | list | None:
    """LLMs sometimes wrap JSON in markdown fences or chatter. Pull it out."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # Greedy outermost { ... } or [ ... ]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


# ─── Mode 1: filter-suggestions ────────────────────────────────────────

FILTER_SYSTEM = (
    "You are a strict skill router. Given a user prompt and a list of "
    "candidate skills with descriptions, decide which ones are GENUINELY "
    "useful for the prompt. Skills that share keywords but don't actually "
    "help should be rejected. Reply with valid JSON only — no prose, no "
    "markdown fences."
)


def _filter_prompt(prompt: str, candidates: list[dict]) -> str:
    lines = [
        f'User prompt: "{prompt}"',
        "",
        "Candidates:",
    ]
    for c in candidates:
        name = c.get("name", "?")
        desc = c.get("description", "").strip().replace("\n", " ")[:200]
        why = c.get("matched") or c.get("reasons") or []
        why_str = f" [matched on: {', '.join(why)}]" if why else ""
        lines.append(f"- {name}: {desc}{why_str}")
    lines += [
        "",
        "Reply as JSON: "
        '{"keep": [{"name": "...", "reason": "1-line why it fits"}], '
        '"drop": [{"name": "...", "reason": "1-line why it does not"}]}',
        "Be conservative — when in doubt, drop. The user is better served "
        "by an empty list than a misleading suggestion.",
    ]
    return "\n".join(lines)


def cmd_filter_suggestions(args: argparse.Namespace, provider: tuple) -> None:
    api_key, base_url, model = provider
    payload = json.loads(sys.stdin.read())
    candidates = payload if isinstance(payload, list) else payload.get("candidates", [])
    if not candidates:
        json.dump({"keep": [], "drop": []}, sys.stdout)
        sys.stdout.write("\n")
        return
    user = _filter_prompt(args.prompt, candidates)
    raw = _chat_completion(
        api_key, base_url, model, FILTER_SYSTEM, user,
        max_tokens=args.max_tokens,
    )
    parsed = _extract_json_block(raw)
    if not isinstance(parsed, dict) or "keep" not in parsed:
        sys.stderr.write(f"llm returned non-JSON; passing all through. raw: {raw[:200]}\n")
        json.dump({"keep": [{"name": c.get("name"), "reason": "llm-fallback"} for c in candidates], "drop": []}, sys.stdout)
        sys.stdout.write("\n")
        return
    json.dump(parsed, sys.stdout, indent=2)
    sys.stdout.write("\n")


# ─── Mode 2: validate-gap ──────────────────────────────────────────────

GAP_SYSTEM = (
    "You decide whether a 'topic' is a real gap in a skill catalog. Given "
    "the topic and the closest-named skills, answer: is there an existing "
    "skill that effectively covers this, or is a new skill genuinely "
    "warranted?\n\n"
    "OUTPUT FORMAT: Reply with raw JSON only — no markdown fences, no "
    "preamble, no commentary, no trailing prose. The first character of "
    "your response MUST be '{' and the last MUST be '}'. Keep "
    "'reasoning' to under 200 characters."
)


def _gap_prompt(topic: str, near_skills: list[dict]) -> str:
    lines = [f'Topic flagged as gap: "{topic}"', "", "Closest existing skills:"]
    for s in near_skills:
        name = s.get("name", "?")
        desc = s.get("description", "").strip().replace("\n", " ")[:200]
        lines.append(f"- {name}: {desc}")
    lines += [
        "",
        "Reply as JSON: "
        '{"is_real_gap": true|false, "covered_by": ["skill-name", ...], '
        '"reasoning": "one sentence", '
        '"suggested_skill_name": "<kebab-case>" or null, '
        '"suggested_description": "<one-line description>" or null}',
        "Set is_real_gap=false if any existing skill substantively covers it.",
    ]
    return "\n".join(lines)


def _near_skills(topic: str, index_path: Path, limit: int) -> list[dict]:
    """Cheap lexical near-match: skills whose name/description contains the
    topic token. Quality is fine for an LLM-side validator that does the
    real semantic check."""
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text())
    skills = data.get("skills", {})
    needles = {t for t in re.findall(r"[a-z][a-z0-9_-]{2,}", topic.lower()) if len(t) >= 3}
    if not needles:
        return []
    scored: list[tuple[int, dict]] = []
    for name, rec in skills.items():
        name_l = name.lower()
        desc_l = rec.get("description", "").lower()
        triggers_l = " ".join(rec.get("triggers", []) or []).lower()
        haystack = f"{name_l} {desc_l} {triggers_l}"
        hits = sum(1 for n in needles if n in haystack)
        if hits > 0:
            scored.append((hits, {"name": name, "description": rec.get("description", "")}))
    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored[:limit]]


def cmd_validate_gap(args: argparse.Namespace, provider: tuple) -> None:
    api_key, base_url, model = provider
    near = _near_skills(args.topic, Path(args.skills_index).expanduser(), args.near_limit)
    user = _gap_prompt(args.topic, near)
    raw = _chat_completion(
        api_key, base_url, model, GAP_SYSTEM, user,
        max_tokens=args.max_tokens,
    )
    parsed = _extract_json_block(raw)
    if not isinstance(parsed, dict):
        sys.stderr.write(f"llm returned non-JSON. raw: {raw[:200]}\n")
        json.dump(
            {"is_real_gap": None, "covered_by": [], "reasoning": "llm-parse-failed",
             "suggested_skill_name": None, "suggested_description": None},
            sys.stdout,
        )
        sys.stdout.write("\n")
        return
    json.dump(parsed, sys.stdout, indent=2)
    sys.stdout.write("\n")


# ─── Entry ─────────────────────────────────────────────────────────────


def main() -> None:
    _load_env_file()
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("filter-suggestions", aliases=["filter"])
    f.add_argument("--prompt", required=True)
    f.add_argument("--max-tokens", type=int, default=800)
    f.set_defaults(func=cmd_filter_suggestions)

    g = sub.add_parser("validate-gap", aliases=["gap"])
    g.add_argument("--topic", required=True)
    g.add_argument("--skills-index", default=str(Path.home() / ".agents/skills-index.json"))
    g.add_argument("--near-limit", type=int, default=8)
    g.add_argument("--max-tokens", type=int, default=800)
    g.set_defaults(func=cmd_validate_gap)

    # legacy --mode flag for back-compat
    ap.add_argument("--mode", choices=["filter-suggestions", "validate-gap"], default=None)
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--topic", default=None)
    ap.add_argument("--skills-index", default=str(Path.home() / ".agents/skills-index.json"))
    ap.add_argument("--near-limit", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=800)

    args = ap.parse_args()

    # Compatibility shim for --mode form
    if args.cmd is None and args.mode:
        if args.mode == "filter-suggestions":
            args.cmd = "filter-suggestions"
            args.func = cmd_filter_suggestions
        else:
            args.cmd = "validate-gap"
            args.func = cmd_validate_gap

    provider = _resolve_provider()
    args.func(args, provider)


if __name__ == "__main__":
    main()
