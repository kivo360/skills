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

## MANDATORY: Startup Protocol

**When this skill loads, ALWAYS execute this sequence before doing anything else:**

### Step 1: Health Check
```bash
bun run forge doctor --json
```
If unhealthy, fix issues before proceeding.

### Step 2: Read Steering Rules
Read `STEERING_RULES.md`. These are the coding conventions. Internalize them — they're enforced by regression evals.

### Step 3: Pipeline State
```bash
bun run forge status --json
```
This tells you what features exist and what phase they're in.

### Step 4: Determine Next Action

Based on the status output, pick ONE:

| Status Output | What To Do |
|---------------|------------|
| `features: []` (empty) | Read ROADMAP.md → find the first pending cycle → start Phase 1 (Scope) |
| Feature in `"specced"` phase | Start Phase 4 (gen evals) then Phase 5 (build) |
| Feature in `"building"` phase | Continue Phase 5 (tailor code, run eval loop) |
| Feature evals all pass | Proceed to Phase 6 (E2E tests) |
| E2E tests pass | Proceed to Phase 7 (Dogfood) |
| All features complete | Read ROADMAP.md → find the next pending cycle → start Phase 1 |

### Step 5: Run the Pipeline

**DO NOT skip phases. DO NOT jump to code. Execute phases in order.**

**If starting a new feature** — go to Phase 1 below.
**If resuming** — pick up at the feature's current phase.

---

## The 5-Phase Pipeline

Every feature goes through ALL five phases in order. Each phase has a gate — you cannot proceed until the gate passes.

### Phase 1: Scope
**Load skill: `socratic-scoping`**

Read the app plan docs (ROADMAP.md, any docs/*.md plans). Interview the user to narrow scope:
- Max 3 questions per round
- Be adversarial: "You said 5 things. Which ONE ships first?"
- Never discuss tech stack (it's decided)
- Produce: what we're doing AND what we're NOT doing yet

**Gate:** One-sentence scope, narrow enough for one build cycle, user confirms.

### Phase 2: PRD
**Load skill: `prd-creator`**

Interview the user through 5 rounds:
1. Actors & roles (must map to owner/admin/member)
2. Entities & fields for THIS cycle only
3. Permission matrix (entity × role × CRUD — every cell filled)
4. User flows (happy + failure + adversarial per actor)
5. Cross-actor interactions (when A does X, how does it affect B?)

**Gate:** Every actor has role, every entity has permission matrix, flows have failure paths, user approves.

### Phase 3: Spec
**Load skill: `openspec-writer`**

Convert PRD into machine-readable spec at `specs/{feature}.spec.md`. Include:
- Typed entities (camelCase columns, organizationId/createdBy/createdAt required)
- Commands catalog (one per Server Action)
- Per-role flows as numbered steps
- Constraints and out-of-scope

**Gate:** Every entity typed, every command documented, every permission cell has eval.

### Phase 4: Evals
```bash
bun run forge gen evals {feature} --spec specs/{feature}.spec.md
```
Review generated scripts. Every permission cell = one eval. Verify scripts are executable.

**Gate:** Eval scripts exist and are runnable.

### Phase 5: Build
```bash
bun run forge gen feature {feature} --spec specs/{feature}.spec.md
```

Then tailor the generated code — make it real:
1. **Load skill: `feature-builder`** for the build loop (it auto-loads `page-scaffolder`)
2. Select page pattern (list/detail/dashboard/settings/wizard) based on spec commands
3. Pull required shadcn components: `bunx --bun shadcn@latest add {components}`
4. Add Drizzle tables to `packages/database/schema.ts`
5. Implement real queries in each action file (getSession, org scoping, Zod validation)
6. Generate page components per pattern (NOT bare stubs)
7. Register feature in sidebar navigation
8. After each change: `bun run forge eval {feature}`
9. When feature evals pass: `bun run forge eval --regression`
10. **Load skill: `steering-enforcer`** for final compliance check

**Conditional skills** (auto-load based on spec):
- Mentions email → load `react-email` + `resend`
- Mentions payments → load `stripe-best-practices`
- Mentions org roles → load `organization-best-practices`
- Mentions analytics → load `posthog-instrumentation`

**Gate:** All feature evals pass, regression evals pass (18 pass, 2 skip), `bun run check` passes.

### Phase 6: E2E Tests
**Load skill: `e2e-scaffolder`**

Generate Playwright tests from the spec:
1. Create Page Object at `apps/app/e2e/page-objects/{feature}.po.ts`
2. Create E2E test suite at `apps/app/e2e/{feature}.spec.ts`
3. Tests per role from permission matrix (owner can X, member cannot Y)
4. Auth fixtures using better-auth testUtils plugin
5. Run: `bunx playwright test e2e/{feature}.spec.ts`

**Gate:** All E2E tests pass. Page Object covers CRUD operations.

### Phase 7: Dogfood
**Load skill: `dogfood-complete`**

Agent explores the feature like a real user:
1. Navigate to the feature via sidebar
2. Test all CRUD operations visually
3. Test as different roles (owner, admin, member)
4. Capture annotated screenshots of each state
5. Report any bugs with repro steps
6. Generate additional Playwright tests from exploration

**Gate:** No P0/P1 bugs found. All screenshots captured. QA report produced.

**Gate:** All feature evals pass, regression evals pass (18 pass, 2 skip), `bun run check` passes.

---

## CLI Commands

```bash
omoios-forge init <project-name>          # Scaffold new project from GitHub template
omoios-forge env:clone <source-project>   # Copy env credentials from existing project
omoios-forge doctor --json                # Health check (docs, evals, tools)
omoios-forge status --json                # Pipeline status per feature
omoios-forge eval --regression --json     # Run 20 regression evals (expect 18 pass, 2 skip)
omoios-forge eval <feature> --json        # Run feature-specific evals
omoios-forge gen feature <name> --spec specs/<name>.spec.md --json       # Scaffold feature
omoios-forge gen feature <name> --spec specs/<name>.spec.md --dry-run    # Preview without writing
omoios-forge gen evals <name> --spec specs/<name>.spec.md --json         # Generate eval scripts
```

Inside the monorepo, use `bun run forge` instead of `omoios-forge`.

## Spec File Format

Specs live in `specs/{feature}.spec.md`:

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
- permissions: { owner: Y/N, admin: Y/N, member: Y/N }

## Constraints
- ...

## Out of Scope
- ...
```

## Steering Rules Summary

| Rule | Summary |
|------|---------|
| Zero Styling | shadcn + Tailwind defaults only. No custom visual CSS. |
| Server Components | Data fetched in Server Components. Mutations via Server Actions. |
| Auth Imports | Apps import from `@repo/auth/client` only. |
| Schema Convention | camelCase columns. All entities need organizationId, createdBy, createdAt. |
| Action Contract | Return `{ data }` on success, `{ error }` on failure. |
| One Action Per File | Each action in `actions/{feature}/`. Never barrel exports. |

## Project Structure

```
specs/                           # OpenSpec documents
.claude/evals/                   # Regression + feature eval scripts
.claude/evals/run-regression.sh  # Regression suite runner
.agents/pipeline-config.json     # Phase → skill mapping
packages/cli/                    # @repo/cli — the forge CLI
STEERING_RULES.md                # Enforced coding conventions
PIPELINE.md                      # Pipeline documentation
ROADMAP.md                       # Feature tracking + parking lot
```

## Related Skills

Loaded automatically at the right pipeline phase:

| Phase | Skills | Purpose |
|-------|--------|---------|
| 1 Scope | `socratic-scoping` | Narrow feature scope |
| 2 PRD | `prd-creator`, `organization-best-practices` | Permission matrices, flows |
| 3 Spec | `openspec-writer`, `drizzle-orm` | Machine-readable spec |
| 4 Evals | `steering-enforcer` | Generate + run evals |
| 5 Build | `feature-builder`, `query-scaffolder`, `page-scaffolder`, `shadcn` | Actions, pages, layouts |
| 6 E2E | `e2e-scaffolder`, `playwright-best-practices`, `better-auth-test-utils` | Page Objects, Playwright tests |
| 7 Dogfood | `dogfood-complete`, `agent-browser` | Visual QA, bug discovery |

Conditional (auto-loaded based on spec):
- `react-email` + `resend` — when spec mentions email
- `stripe-best-practices` — when spec mentions payments
- `posthog-instrumentation` — when spec mentions analytics
- `sentry-fix-issues` — when spec mentions error tracking
