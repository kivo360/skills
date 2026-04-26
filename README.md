# Coding Toolbelt

The utility belt for coding agents — skills, hooks, agents, commands, tools, and plugins for Claude Code, OpenCode, and any AI coding agent.

## What's Inside

```
coding-toolbelt/
├── skills/              11 authored agent skills
├── hooks/
│   ├── claude-code/     2 Claude Code hooks (memory trigger, Python loader)
│   ├── opencode/        8 OpenCode hooks (linter escalation, schema guards)
│   └── opencode-scripts/ 30 OpenCode script hooks (session, quality, security)
├── agents/
│   ├── claude-code/     21 Claude Code agent definitions
│   └── opencode/        2 OpenCode agent definitions
├── commands/            63 OpenCode slash commands
├── tools/               7 TypeScript tools (coverage, lint, test, security)
├── plugins/
│   └── asyncpg-to-sqlalchemy-converter/  Database migration plugin
├── quickhooks/          Full Python hooks library (absorbed from kivo360/quickhooks)
├── docs/                Session progress, ecosystem maps, analyses
└── prompts/             Reusable test and sync prompts
```

## Skills

| Skill | Description |
|-------|-------------|
| **[eval-driven-dev](skills/eval-driven-dev)** | 7-stage workflow: Discover → Explore → Spec → Eval (tests first) → Implement → Verify → Iterate |
| **[saas-bootstrap](skills/saas-bootstrap)** | Bootstrap a full SaaS stack — detect project, install skills, scaffold configs |
| **[my-stack](skills/my-stack)** | Master router for full SaaS stack — Next.js, Better Auth, Drizzle, Stripe, Resend |
| **[better-auth-complete](skills/better-auth-complete)** | Meta skill routing all Better Auth work — auth, OAuth, 2FA, orgs, testing, security |
| **[better-auth-test-utils](skills/better-auth-test-utils)** | Better Auth test helpers — factories, getCookies, OTP capture, Vitest integration |
| **[better-auth-ui](skills/better-auth-ui)** | Pre-built shadcn/ui auth components — sign in, sign up, settings, orgs, API keys |
| **[dogfood-complete](skills/dogfood-complete)** | Unified QA + Playwright test generation — video, annotated screenshots, reports |
| **[omoios-forge](skills/omoios-forge)** | Agent-driven 5-phase pipeline for omoios-forge SaaS boilerplate |
| **[linter-loop-escalation](skills/linter-loop-escalation)** | Detects stuck agents and injects escalating guidance via hooks |
| **[oh-my-openagent](skills/oh-my-openagent)** | Multi-model orchestration harness config and optimization |
| **[ai-subscription-tracker](skills/ai-subscription-tracker)** | Track AI provider pricing, costs, and usage |

## Hooks

### Claude Code (`hooks/claude-code/`)
- `memory-trigger.sh` — Memory system trigger
- `python-skill-loader.sh` — Python skill loading

### OpenCode (`hooks/opencode/`)
- `linter-loop-escalation.mjs` — 4-tier escalation when agents get stuck
- `edit-block-on-escalation.mjs` — Block edits during escalation
- `schema-edit-guard.mjs` / `schema-write-guard.mjs` — Schema protection
- `test-hooks.mjs` — Hook testing utility

### OpenCode Scripts (`hooks/opencode-scripts/`)
30 lifecycle and automation hooks — session start/end, pre-bash guards, post-edit formatters, cost tracking, security monitoring, quality gates.

## Agents

### Claude Code (`agents/claude-code/`)
21 domain-specific agents — ad auditing (budget, compliance, creative, Google, Meta, tracking), auth debugging, code review, creative strategy, documentation, visual design, and web research.

### OpenCode (`agents/opencode/`)
- `dogfooder.md` — Exploratory QA agent
- `playwright-writer.md` — E2E test generation agent

## Commands (`commands/`)
63 slash commands covering build/fix, code review, language-specific testing (Go, Rust, Kotlin, C++, Python), deployment, security, session management, and workflow orchestration.

## Tools (`tools/`)
7 TypeScript tools: `check-coverage`, `format-code`, `git-summary`, `lint-check`, `run-tests`, `security-audit`, plus index.

## Install Skills

```bash
# Install all skills
npx skills add kivo360/coding-toolbelt

# Install a specific skill
npx skills add kivo360/coding-toolbelt --skill better-auth-complete
```

## License

MIT
