---
name: omoios-forge
description: >-
  Agent-driven development CLI and pipeline for omoios-forge SaaS boilerplate. Use when
  initializing new projects, adding features via the 5-phase pipeline (Scope → PRD → Spec →
  Evals → Build), running regression evals, scaffolding from specs, or working with any
  omoios-forge project. Trigger on "forge", "omoios-forge", "pipeline", "forge doctor",
  "forge init", "forge gen", "forge eval", "forge status", "add feature", "run evals",
  "scaffold feature", "spec file", "regression evals", "steering rules", or any project
  with a STEERING_RULES.md or .agents/pipeline-config.json file.
---

# omoios-forge

Agent-driven development pipeline for SaaS apps built on the omoios-forge boilerplate.

## Detection

You're in an omoios-forge project if ANY of these exist:
- `STEERING_RULES.md` in project root
- `.agents/pipeline-config.json`
- `packages/cli/` with `@repo/cli` package
- `bun run forge --version` returns a version

## CLI Commands

```bash
omoios-forge init <project-name>          # Scaffold new project from GitHub template
omoios-forge doctor --json                # Health check (docs, evals, tools)
omoios-forge status --json                # Pipeline status per feature
omoios-forge eval --regression --json     # Run 20 regression evals (expect 18 pass, 2 skip)
omoios-forge eval <feature> --json        # Run feature-specific evals
omoios-forge gen feature <name> --spec specs/<name>.spec.md --json       # Scaffold feature from spec
omoios-forge gen feature <name> --spec specs/<name>.spec.md --dry-run    # Preview without writing
omoios-forge gen evals <name> --spec specs/<name>.spec.md --json         # Generate eval scripts from spec
```

Inside the monorepo, use `bun run forge` instead of `omoios-forge`.

## The 5-Phase Pipeline

Every feature goes through these phases in order:

### Phase 1: Scope (skill: socratic-scoping)
Narrow the feature to what ships in one build cycle. Produces a scoped brief for ROADMAP.md.

### Phase 2: PRD (skill: prd-creator)
Generate enriched PRD with permission matrices (entity × role × CRUD), user flows (happy/failure/adversarial), and cross-actor interactions. Roles are always: owner, admin, member.

### Phase 3: Spec (skill: openspec-writer)
Convert PRD to machine-readable spec at `specs/{feature}.spec.md`. Contains typed entities, commands catalog, per-role flows, and query patterns.

### Phase 4: Evals (CLI: forge gen evals)
Generate eval scripts from spec. Entity evals check schema.ts. Command evals check action files for auth + org scoping. Permission evals generate Vitest test stubs.

### Phase 5: Build (skill: feature-builder + query-scaffolder)
Scaffold from spec → tailor generated code → run evals → fix → repeat. Uses steering-enforcer to run regression evals after changes.

## Spec File Format

Specs live in `specs/{feature}.spec.md`. The parser accepts this format:

```markdown
# Feature: FeatureName

## Entities

### EntityName
- id: text, primary key
- fieldName: type, required/optional, default value
- organizationId: text, required
- createdBy: text, required
- createdAt: timestamp, default now

## Commands

### commandName
- type: Server Action
- file: actions/feature-name/action-name.ts
- input: { field: type, field: type }
- auth: required
- permissions: { owner: Y, admin: Y, member: Y/N }

## Constraints
- Constraint 1
- Constraint 2

## Out of Scope
- Not building this yet
- Or this
```

Required entity fields: `id`, `organizationId`, `createdBy`, `createdAt`.
Column naming: camelCase (Better Auth convention).
One action file per command: `apps/app/app/actions/{feature}/{name}.ts`.

## Steering Rules

Every omoios-forge project has `STEERING_RULES.md` with enforced conventions:

| Rule | Summary |
|------|---------|
| Zero Styling | Use shadcn + Tailwind defaults only. No custom visual CSS. |
| Server Components | Data fetched in Server Components. Mutations via Server Actions. |
| Auth Imports | Apps import from `@repo/auth/client` only. Never import better-auth directly. |
| Schema Convention | camelCase columns. All entities have organizationId, createdBy, createdAt. |
| Action Contract | Server Actions return `{ data }` on success, `{ error }` on failure. |
| One Action Per File | Each Server Action in its own file under `actions/{feature}/`. |
| Import Boundaries | No cross-app imports. Use `@repo/*` packages. |

## Regression Eval Baseline

20 evals in `.claude/evals/`. Expected baseline:
- **18 PASS** — Active rules enforced
- **2 SKIP** — E-REG-15 (Zustand not installed), E-REG-20 (TanStack Query not installed)
- **0 FAIL** — Any failure means a steering rule was violated

Run after every significant code change: `bun run forge eval --regression --json`

## Feature Development Workflow

```
1. Receive app plan (from docs/app-plan-prompt.md template)
2. Load skill: socratic-scoping → narrow scope
3. Load skill: prd-creator → generate PRD with permission matrices
4. Load skill: openspec-writer → produce specs/{feature}.spec.md
5. Run: bun run forge gen evals {feature} --spec specs/{feature}.spec.md
6. Run: bun run forge gen feature {feature} --spec specs/{feature}.spec.md
7. Tailor generated code (add real logic, validation, queries)
8. Run: bun run forge eval {feature} → fix until all pass
9. Run: bun run forge eval --regression → verify no regressions
10. Load skill: steering-enforcer → final compliance check
```

## Project Structure

```
specs/                           # OpenSpec documents (Phase 3 output)
.claude/evals/                   # Regression + feature eval scripts
.claude/evals/run-regression.sh  # Regression suite runner
.agents/pipeline-config.json     # Phase → skill mapping
.agents/skills/                  # 6 pipeline skills
packages/cli/                    # @repo/cli — the forge CLI
STEERING_RULES.md                # Enforced coding conventions
PIPELINE.md                      # 5-phase pipeline documentation
ROADMAP.md                       # Feature tracking + parking lot
```

## Related Skills

Load these for specific pipeline phases:
- `socratic-scoping` — Phase 1 (Scope)
- `prd-creator` — Phase 2 (PRD)
- `openspec-writer` — Phase 3 (Spec)
- `steering-enforcer` — Phase 4-5 (Eval enforcement)
- `feature-builder` — Phase 5 (Build loop)
- `query-scaffolder` — Phase 5 (Server Action generation)
- `eval-driven-dev` — Overall eval-first methodology
- `my-stack` — Full stack routing (parent skill)
