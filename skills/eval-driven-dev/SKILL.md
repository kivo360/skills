---
name: eval-driven-dev
description: >-
  Enforces a 7-stage development workflow: Discover (Socratic questioning) → Explore (codebase scan)
  → Spec (acceptance criteria) → Eval (write tests FIRST) → Implement → Verify → Iterate.
  Supports deterministic tests (Playwright, unit), fuzzy evals (screenshot + LLM-as-judge),
  integration evals, QA dogfood, and regression suites. Strong nudge enforcement — agents are
  pressured to follow each stage but can override with justification. Trigger on "eval driven,"
  "test first," "write tests first," "TDD," "eval," "acceptance criteria," "spec first,"
  "workflow," "development process," "how should I build this," or any new feature request.
  Hooks into my-stack for skill routing and dogfood-complete for QA/test generation.
---

# Eval-Driven Development

Seven stages. Tests before code. Proof before shipping. Feedback loops built in.

## The Workflow

```
Stage 0: DISCOVER ─── Socratic questioning → problem statement + priorities
    │
Stage 1: EXPLORE ──── Codebase scan → context + integration points
    │
Stage 2: SPEC ─────── Acceptance criteria → eval types needed
    │
Stage 3: EVAL ─────── Write ALL tests FIRST → tests that define "done"
    │                  (all tests FAIL at this point — that's correct)
    │
Stage 4: IMPLEMENT ── Write code until tests pass
    │
Stage 5: VERIFY ───── All evals pass → evidence of completion
    │
Stage 6: ITERATE ──── Review → loop back to any earlier stage
                       Spec wrong? → Stage 2
                       New edge case? → Stage 3
                       Feature needs expansion? → Stage 0
```

**Enforcement:** Strong nudge. The agent SHOULD follow each stage in order. Skipping a stage requires explicit justification stated in the response. "I'm skipping Stage 3 because [reason]."

## Stage 0: DISCOVER (Socratic Method)

**Goal:** Understand what the user actually wants before touching code.

**DO NOT write code, create files, or run commands in this stage.**

Ask deep, layered questions using the `AskQuestion` tool:

### Question Layers

**Layer 1 — Problem Space:**
- What problem are you solving?
- Who is this for? (user persona)
- What does success look like from the user's perspective?
- What's the MVP vs the full vision?

**Layer 2 — Technical Scope:**
- Which part of the stack does this touch? (auth, payments, UI, database, API)
- Does this modify existing features or create new ones?
- What are the dependencies / integration points?
- Are there existing patterns in the codebase to follow?

**Layer 3 — Priorities & Constraints:**
- What's the most important thing to get right?
- What are you willing to compromise on?
- Timeline / effort constraints?
- Any known risks or unknowns?

### Output

A clear problem statement:
```markdown
## Feature: [Name]
**Problem:** [What problem this solves]
**User:** [Who benefits]
**MVP scope:** [Minimum viable version]
**Full scope:** [Everything, if time allows]
**Stack touchpoints:** [auth, database, UI, API, etc.]
**Priority:** [What matters most]
**Risks:** [Known unknowns]
```

## Stage 1: EXPLORE

**Goal:** Scan the codebase to understand what exists before specifying.

Load relevant skills from `my-stack` based on the stack touchpoints identified in Stage 0.

**Actions:**
- Fire explore agents to find existing patterns, implementations, and integration points
- Read relevant files (config, schemas, existing tests)
- Map the current state: what works, what's missing, what's adjacent

**Output:** Codebase context summary — files involved, patterns to follow, integration points, existing test coverage.

See [explore-protocol.md](references/explore-protocol.md) for the exploration checklist.

## Stage 2: SPEC

**Goal:** Define acceptance criteria and choose eval types.

### Acceptance Criteria Format

```markdown
## Acceptance Criteria: [Feature Name]

### Happy Path
- [ ] User can [action] and sees [result]
- [ ] Data is persisted to [database/table]
- [ ] [Related system] is updated correctly

### Edge Cases
- [ ] When [condition], user sees [error/fallback]
- [ ] When [invalid input], form shows [validation message]
- [ ] When [auth required], unauthenticated user is redirected

### Non-Functional
- [ ] No console errors during flow
- [ ] Page loads within [N] seconds
- [ ] Accessible (keyboard navigable, screen reader friendly)
```

### Eval Type Selection

For each criterion, assign an eval type:

| Eval Type | When to Use | Tool |
|-----------|------------|------|
| **Deterministic** | Binary pass/fail, same result every time | Playwright, Vitest |
| **Fuzzy** | AI-judged quality (does it look right? is the UX good?) | Screenshot + LLM rubric |
| **Integration** | Cross-system (auth + DB + UI chain) | Playwright + test-utils |
| **QA Dogfood** | Exploratory — find unknown issues | dogfood-complete (QA mode) |
| **Regression** | After changes — nothing else broke | Full Playwright suite |
| **Non-deterministic** | Timing, randomness, external services | Retry logic + thresholds |

See [eval-types.md](references/eval-types.md) for detailed guidance on each type.

## Stage 3: EVAL (Write Tests FIRST)

**Goal:** Write all tests before implementation. Tests define "done."

**All tests should FAIL at this point. That's correct.**

### Deterministic Tests (Playwright)

Load: `playwright-best-practices`, `better-auth-test-utils`

```typescript
// tests/generated/feature-name.spec.ts
import { test } from '../fixtures/auth';
import { expect } from '@playwright/test';

test('user can create a project from dashboard', async ({ page, authenticatedContext }) => {
  const { user } = await authenticatedContext.asUser();
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Create Project' }).click();
  await page.getByRole('textbox', { name: 'Project Name' }).fill('Test Project');
  await page.getByRole('button', { name: 'Create' }).click();
  await expect(page.getByText('Project created')).toBeVisible();
  await expect(page).toHaveURL(/\/projects\/[\w-]+/);
});
```

### Fuzzy Evals (Screenshot + LLM-as-Judge)

Load: `dogfood-complete`

```typescript
// evals/visual/sign-in-page.eval.ts
export const signInPageEval = {
  name: 'Sign-in page visual quality',
  type: 'fuzzy',
  rubric: {
    criteria: [
      'Social login buttons are visible and properly styled',
      'Email and password fields are clearly labeled',
      'Form has adequate spacing and alignment',
      'Error states are visually distinct',
      'Mobile responsive (no horizontal scroll)',
    ],
    threshold: 4, // out of 5 criteria must pass
  },
  capture: async () => {
    // agent-browser captures annotated screenshot
    // LLM evaluates against rubric
  },
};
```

### Integration Evals

```typescript
test('auth + database + UI integration', async ({ page, testUtils }) => {
  // Create user via test-utils (DB)
  const user = testUtils.createUser({ email: 'integration@test.com' });
  await testUtils.saveUser(user);
  // Authenticate via cookies (Auth)
  const cookies = await testUtils.getCookies({ userId: user.id });
  await page.context().addCookies(cookies);
  // Navigate to protected page (UI)
  await page.goto('/dashboard');
  await expect(page.getByText(user.name)).toBeVisible();
  // Cleanup
  await testUtils.deleteUser(user.id);
});
```

See [writing-evals.md](references/writing-evals.md) for templates for each eval type.

## Stage 4: IMPLEMENT

**Goal:** Write code until tests pass.

Load the right skills via `my-stack` routing. Follow existing codebase patterns identified in Stage 1.

**Rules:**
- Run tests frequently (`npx playwright test --reporter=list`)
- Fix one test at a time — don't try to make everything pass at once
- If a test is wrong (spec was wrong), go back to Stage 2, not Stage 4
- Never delete or weaken a test to make it pass

## Stage 5: VERIFY

**Goal:** Prove the feature works with evidence.

### Verification Checklist

```markdown
## Verification: [Feature Name]

### Deterministic Tests
- [ ] All Playwright tests pass: `npx playwright test tests/generated/feature-name.spec.ts`
- [ ] No flaky tests: `npx playwright test --repeat-each=5`

### Fuzzy Evals
- [ ] Visual quality meets rubric threshold
- [ ] LLM-as-judge passes on content/UX criteria

### Integration
- [ ] Auth + DB + UI chain verified end-to-end

### QA Dogfood
- [ ] agent-browser exploration found no new issues
- [ ] No console errors during flow
- [ ] No failed network requests (4xx/5xx)

### Regression
- [ ] Full test suite passes: `npx playwright test`
- [ ] No pre-existing tests broken
```

## Stage 6: ITERATE

**Goal:** Feedback loop — review and loop back if needed.

| Signal | Action |
|--------|--------|
| Spec was wrong (tests don't match user intent) | → Back to Stage 2 (SPEC) |
| New edge case discovered during implementation | → Back to Stage 3 (EVAL) to add test |
| Feature needs expansion beyond MVP | → Back to Stage 0 (DISCOVER) |
| QA found issues in adjacent features | → Back to Stage 1 (EXPLORE) |
| All evals pass, user confirms | → **DONE** — merge/ship |

## Activity-Based Reference Guide

| Activity | Reference |
|----------|-----------|
| **Socratic questioning templates** | [discovery-questions.md](references/discovery-questions.md) |
| **Codebase exploration checklist** | [explore-protocol.md](references/explore-protocol.md) |
| **All eval types explained** | [eval-types.md](references/eval-types.md) |
| **Test/eval writing templates** | [writing-evals.md](references/writing-evals.md) |
| **Fuzzy eval rubrics** | [fuzzy-eval-rubrics.md](references/fuzzy-eval-rubrics.md) |
| **CI/CD pipeline enforcement** | [ci-enforcement.md](references/ci-enforcement.md) |

## Integration with Other Skills

| Skill | Stage | Role |
|-------|-------|------|
| `my-stack` | Stage 1, 4 | Routes to right skills for explore + implement |
| `dogfood-complete` | Stage 3, 5 | QA evals + test generation |
| `agent-browser` | Stage 3, 5 | Browser automation for evals |
| `better-auth-test-utils` | Stage 3 | Auth state for tests |
| `playwright-best-practices` | Stage 3, 4 | Test quality |
| `better-auth-complete` | Stage 4 | Auth implementation guidance |
