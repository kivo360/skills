#!/usr/bin/env bash
# review-with-memory installer (local-mode, no PyPI required)
#
# Registers the in-repo skill + tooling in canonical locations via symlinks.
# Edits in the repo go live immediately; the install only updates pointers.
#
# What it does:
#   1. State dir   ~/.config/review-with-memory/  + empty repos.json
#   2. Skill link  ~/.agents/skills/review-with-memory  →  $REPO/review-with-memory
#   3. Mirrors     ~/.claude/skills/  and  ~/.config/opencode/skills/  (if dirs exist)
#   4. zshenv      $CODING_TOOLBELT_HOME + $REVIEW_WITH_MEMORY_HOME (marker-fenced, idempotent)
#   5. zshrc       sources ensure-graph/hook.zsh   (marker-fenced, idempotent)
#   6. Doctor      checks uv / git / code-review-graph / Hindsight reachability
#
# Idempotent: re-running is safe. Use --uninstall to reverse every step
# except the state dir (your repos.json is left in place).
#
# Flags:
#   --uninstall            reverse every install step (state dir kept)
#   --dry-run              print actions, change nothing
#   --skip-skill           don't (un)link the skill into ~/.agents/skills
#   --skip-mirrors         don't (un)link harness mirrors
#   --skip-zshrc           don't touch ~/.zshrc
#   --skip-zshenv          don't touch ~/.zshenv
#   --skip-state           don't create state dir
#   --skip-doctor          don't run final health check
#   -h, --help             this help

set -euo pipefail

# ─── argument parsing ───────────────────────────────────────────────────────

ACTION="install"
DRY_RUN=0
SKIP_SKILL=0
SKIP_MIRRORS=0
SKIP_ZSHRC=0
SKIP_ZSHENV=0
SKIP_STATE=0
SKIP_DOCTOR=0

usage() { sed -n '2,/^set/p' "$0" | sed 's/^# \?//' | head -n -1; }

while [[ $# -gt 0 ]]; do
    case $1 in
        --uninstall)     ACTION="uninstall" ;;
        --dry-run)       DRY_RUN=1 ;;
        --skip-skill)    SKIP_SKILL=1 ;;
        --skip-mirrors)  SKIP_MIRRORS=1 ;;
        --skip-zshrc)    SKIP_ZSHRC=1 ;;
        --skip-zshenv)   SKIP_ZSHENV=1 ;;
        --skip-state)    SKIP_STATE=1 ;;
        --skip-doctor)   SKIP_DOCTOR=1 ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
    shift
done

# ─── source resolution ──────────────────────────────────────────────────────

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RWM_HOME="$HERE"
TOOLBELT_HOME="$(cd "$HERE/.." && pwd)"

# ─── target paths ───────────────────────────────────────────────────────────

SKILLS_AGENTS="$HOME/.agents/skills"
SKILLS_CLAUDE="$HOME/.claude/skills"
SKILLS_OPENCODE="$HOME/.config/opencode/skills"
STATE_DIR="$HOME/.config/review-with-memory"
ZSHRC="$HOME/.zshrc"
ZSHENV="$HOME/.zshenv"

ZSHRC_BEGIN="# >>> review-with-memory ensure-graph hook >>>"
ZSHRC_END="# <<< review-with-memory ensure-graph hook <<<"
ZSHENV_BEGIN="# >>> review-with-memory paths >>>"
ZSHENV_END="# <<< review-with-memory paths <<<"

# ─── pretty output ──────────────────────────────────────────────────────────

if [[ -t 1 ]]; then
    C_HEAD=$'\033[36;1m'; C_OK=$'\033[32m'; C_SKIP=$'\033[33m'
    C_FAIL=$'\033[31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
    C_HEAD=""; C_OK=""; C_SKIP=""; C_FAIL=""; C_DIM=""; C_OFF=""
fi

step()  { printf '%s▸%s %s\n' "$C_HEAD" "$C_OFF" "$1"; }
ok()    { printf '  %s✓%s %s\n' "$C_OK" "$C_OFF" "$1"; }
skip()  { printf '  %s↷%s %s %s(%s)%s\n' "$C_SKIP" "$C_OFF" "$1" "$C_DIM" "$2" "$C_OFF"; }
fail()  { printf '  %s✗%s %s\n' "$C_FAIL" "$C_OFF" "$1"; FAILURES=$((FAILURES+1)); }
note()  { printf '    %s%s%s\n' "$C_DIM" "$1" "$C_OFF"; }
do_run() {
    if [[ $DRY_RUN -eq 1 ]]; then
        printf '    %s[dry-run]%s %s\n' "$C_DIM" "$C_OFF" "$*"
    else
        "$@"
    fi
}

FAILURES=0

# ─── helpers ────────────────────────────────────────────────────────────────

ensure_dir() { [[ -d "$1" ]] || do_run mkdir -p "$1"; }

# Idempotently create a symlink at $1 pointing at $2.
# - If a correct symlink already exists: skip
# - If a stale symlink: replace
# - If a non-symlink exists: fail (refuse to overwrite real files)
link() {
    local target=$1 source=$2
    if [[ -L "$target" ]]; then
        local current
        current="$(readlink "$target")"
        if [[ "$current" == "$source" ]]; then
            skip "$target" "already linked"
            return 0
        fi
        do_run rm "$target"
        do_run ln -s "$source" "$target"
        ok "$target → $source (replaced stale: $current)"
    elif [[ -e "$target" ]]; then
        fail "$target exists and is not a symlink — refusing to overwrite"
        return 1
    else
        do_run ln -s "$source" "$target"
        ok "$target → $source"
    fi
}

unlink_if_ours() {
    local target=$1 expected=$2
    if [[ ! -L "$target" ]]; then
        skip "$target" "not a symlink"
        return 0
    fi
    local current
    current="$(readlink "$target")"
    if [[ "$current" != "$expected" ]]; then
        skip "$target" "points elsewhere ($current)"
        return 0
    fi
    do_run rm "$target"
    ok "$target removed"
}

# Marker-fenced block management for ~/.zshrc and ~/.zshenv. Lets us update
# or remove our additions without touching anything around them.
write_block() {
    local file=$1 begin=$2 end=$3 content=$4
    if [[ ! -f "$file" ]]; then
        do_run touch "$file"
    fi
    if grep -Fq "$begin" "$file" 2>/dev/null; then
        skip "$file" "block already present"
        return 0
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
        printf '    %s[dry-run]%s would append block to %s\n' "$C_DIM" "$C_OFF" "$file"
        printf '%s\n%s\n%s\n' "$begin" "$content" "$end" | sed "s/^/      $C_DIM/;s/\$/$C_OFF/"
        return 0
    fi
    {
        printf '\n%s\n' "$begin"
        printf '%s\n' "$content"
        printf '%s\n' "$end"
    } >> "$file"
    ok "$file block appended"
}

remove_block() {
    local file=$1 begin=$2 end=$3
    if [[ ! -f "$file" ]] || ! grep -Fq "$begin" "$file" 2>/dev/null; then
        skip "$file" "no block to remove"
        return 0
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
        printf '    %s[dry-run]%s would remove block from %s\n' "$C_DIM" "$C_OFF" "$file"
        return 0
    fi
    # Delete from the begin marker through the end marker (inclusive),
    # preserving everything else.
    local tmp
    tmp="$(mktemp)"
    awk -v b="$begin" -v e="$end" '
        index($0, b) { skipping=1; next }
        skipping && index($0, e) { skipping=0; next }
        !skipping
    ' "$file" > "$tmp"
    mv "$tmp" "$file"
    ok "$file block removed"
}

# ─── install steps ──────────────────────────────────────────────────────────

step_state() {
    step "state dir → $STATE_DIR"
    if [[ -d "$STATE_DIR" ]]; then
        skip "$STATE_DIR" "exists"
    else
        ensure_dir "$STATE_DIR"
        ok "$STATE_DIR created"
    fi
    if [[ ! -f "$STATE_DIR/repos.json" ]]; then
        if [[ $DRY_RUN -eq 1 ]]; then
            printf '    %s[dry-run]%s would seed empty repos.json\n' "$C_DIM" "$C_OFF"
        else
            printf '%s\n' '{}' > "$STATE_DIR/repos.json"
            ok "$STATE_DIR/repos.json seeded"
        fi
    else
        skip "$STATE_DIR/repos.json" "already present"
    fi
}

step_skill() {
    step "skill link → $SKILLS_AGENTS/review-with-memory"
    ensure_dir "$SKILLS_AGENTS"
    link "$SKILLS_AGENTS/review-with-memory" "$RWM_HOME"
}

step_mirrors() {
    # Per CLAUDE.md: harness skill dirs are mirrors of the canonical agents store,
    # not direct repo links. So mirrors → ~/.agents/skills/X → repo (two hops).
    step "harness mirrors"
    local canonical="$SKILLS_AGENTS/review-with-memory"
    for dir in "$SKILLS_CLAUDE" "$SKILLS_OPENCODE"; do
        if [[ -d "$dir" ]]; then
            link "$dir/review-with-memory" "$canonical"
        else
            skip "$dir" "harness not present"
        fi
    done
}

step_zshenv() {
    step "zshenv → \$CODING_TOOLBELT_HOME / \$REVIEW_WITH_MEMORY_HOME"
    # Skip if vars already set by hand (no marker) — avoid duplicates.
    if [[ -f "$ZSHENV" ]] && grep -Eq '^[[:space:]]*export[[:space:]]+CODING_TOOLBELT_HOME=' "$ZSHENV" \
        && ! grep -Fq "$ZSHENV_BEGIN" "$ZSHENV"; then
        skip "$ZSHENV" "vars already set without our marker — leaving alone"
        note "to take ownership: delete the manual lines, then re-run"
        return 0
    fi
    write_block "$ZSHENV" "$ZSHENV_BEGIN" "$ZSHENV_END" \
"export CODING_TOOLBELT_HOME=\"$TOOLBELT_HOME\"
export REVIEW_WITH_MEMORY_HOME=\"\$CODING_TOOLBELT_HOME/review-with-memory\""
}

step_zshrc() {
    step "zshrc → ensure-graph chpwd hook"
    # Skip if user already sources our hook by hand (no marker).
    if [[ -f "$ZSHRC" ]] && grep -Fq 'ensure-graph/hook.zsh' "$ZSHRC" \
        && ! grep -Fq "$ZSHRC_BEGIN" "$ZSHRC"; then
        skip "$ZSHRC" "hook already sourced without our marker"
        return 0
    fi
    write_block "$ZSHRC" "$ZSHRC_BEGIN" "$ZSHRC_END" \
'# Prompts to bootstrap CRG on first cd into a git repo.
# State at $REVIEW_WITH_MEMORY_STATE_DIR (default ~/.config/review-with-memory).
[[ -n "$REVIEW_WITH_MEMORY_HOME" && -f "$REVIEW_WITH_MEMORY_HOME/ensure-graph/hook.zsh" ]] && \
  source "$REVIEW_WITH_MEMORY_HOME/ensure-graph/hook.zsh"'
}

step_doctor() {
    step "doctor"
    command -v uv               >/dev/null && ok "uv on PATH"               || fail "uv not on PATH (uv installs the script deps)"
    command -v git              >/dev/null && ok "git on PATH"              || fail "git not on PATH"
    command -v code-review-graph >/dev/null && ok "code-review-graph on PATH" \
        || skip "code-review-graph" "not on PATH (optional, install via uvx if needed)"

    if [[ -n "${HINDSIGHT_BASE_URL:-}" ]]; then
        ok "HINDSIGHT_BASE_URL = $HINDSIGHT_BASE_URL"
        if curl -sf --max-time 3 "$HINDSIGHT_BASE_URL/health" >/dev/null 2>&1; then
            ok "hindsight reachable"
        else
            fail "hindsight not reachable at $HINDSIGHT_BASE_URL"
        fi
    else
        skip "HINDSIGHT_BASE_URL" "unset — set in ~/.zshrc to point at hosted Hindsight"
    fi

    [[ -L "$SKILLS_AGENTS/review-with-memory" ]] && ok "skill symlink present" || fail "skill symlink missing"
    [[ -f "$STATE_DIR/repos.json" ]] && ok "state file present" || fail "state file missing"
}

# ─── uninstall steps ────────────────────────────────────────────────────────

uninstall_skill()    { step "remove skill link"; unlink_if_ours "$SKILLS_AGENTS/review-with-memory" "$RWM_HOME"; }
uninstall_mirrors()  {
    step "remove harness mirrors"
    local canonical="$SKILLS_AGENTS/review-with-memory"
    unlink_if_ours "$SKILLS_CLAUDE/review-with-memory" "$canonical"
    unlink_if_ours "$SKILLS_OPENCODE/review-with-memory" "$canonical"
}
uninstall_zshrc()    { step "remove zshrc block";  remove_block "$ZSHRC"  "$ZSHRC_BEGIN"  "$ZSHRC_END"; }
uninstall_zshenv()   { step "remove zshenv block"; remove_block "$ZSHENV" "$ZSHENV_BEGIN" "$ZSHENV_END"; }

# ─── main ───────────────────────────────────────────────────────────────────

main() {
    printf '%sreview-with-memory %s%s\n' "$C_HEAD" "$ACTION" "$C_OFF"
    note "source: $RWM_HOME"
    note "toolbelt: $TOOLBELT_HOME"
    [[ $DRY_RUN -eq 1 ]] && note "(dry-run)"
    echo

    if [[ "$ACTION" == "install" ]]; then
        [[ $SKIP_STATE   -eq 0 ]] && step_state
        [[ $SKIP_SKILL   -eq 0 ]] && step_skill
        [[ $SKIP_MIRRORS -eq 0 ]] && step_mirrors
        [[ $SKIP_ZSHENV  -eq 0 ]] && step_zshenv
        [[ $SKIP_ZSHRC   -eq 0 ]] && step_zshrc
        [[ $SKIP_DOCTOR  -eq 0 ]] && step_doctor
    else
        [[ $SKIP_SKILL   -eq 0 ]] && uninstall_skill
        [[ $SKIP_MIRRORS -eq 0 ]] && uninstall_mirrors
        [[ $SKIP_ZSHRC   -eq 0 ]] && uninstall_zshrc
        [[ $SKIP_ZSHENV  -eq 0 ]] && uninstall_zshenv
        printf '%snote%s state dir kept at %s — remove manually if desired\n' \
            "$C_DIM" "$C_OFF" "$STATE_DIR"
    fi

    echo
    if [[ $FAILURES -gt 0 ]]; then
        printf '%s%d failure(s)%s — review output above\n' "$C_FAIL" "$FAILURES" "$C_OFF"
        exit 1
    fi
    printf '%sdone%s\n' "$C_OK" "$C_OFF"

    if [[ "$ACTION" == "install" && $DRY_RUN -eq 0 && $SKIP_ZSHRC -eq 0 ]]; then
        note ""
        note "Reload your shell to pick up the chpwd hook:"
        note "  exec zsh   # or just open a new terminal"
    fi
}

main
