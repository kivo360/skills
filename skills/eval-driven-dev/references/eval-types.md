# Eval Types Guide

## Table of Contents
- [1. Deterministic Tests](#1-deterministic-tests)
- [2. Fuzzy Evals](#2-fuzzy-evals)
- [3. Integration Evals](#3-integration-evals)
- [4. QA Dogfood Evals](#4-qa-dogfood-evals)
- [5. Regression Evals](#5-regression-evals)
- [6. Non-Deterministic Tests](#6-non-deterministic-tests)
- [Related References](#related-references)

## 1. Deterministic Tests
Playwright E2E and Vitest unit/integration tests that produce binary pass/fail results consistently.
- **When:** Form submissions, navigation, API responses, database operations.
- **Mechanism:** Run locally or in CI with standard test runners.
- **Example:** `expect(page).toHaveURL('/dashboard')`

## 2. Fuzzy Evals
Screenshot-based LLM evaluations that score UI/UX quality against a specific rubric.
- **When:** UI polish, layout consistency, content quality, UX flow.
- **Mechanism:** Capture an annotated screenshot via `agent-browser`, send it to an LLM with a detailed rubric, and receive a score.
- **Example Rubric:** "Sign-in page has visible social buttons (Y/N), clear error states (Y/N), mobile responsive (Y/N)"

## 3. Integration Evals
Verify the coordination between multiple system layers (Auth, Database, UI).
- **When:** Full user journeys like authentication + data persistence + UI updates.
- **Mechanism:** Uses `better-auth-test-utils` for authentication state while running Playwright.
- **Example:** Create user (DB) → Authenticate (Auth) → Navigate (UI) → Verify data presence (Assertions).

## 4. QA Dogfood Evals
Autonomous exploration of the app by `agent-browser` to find unanticipated issues.
- **When:** After feature implementation but before final merge.
- **Mechanism:** Use `dogfood-complete` QA mode for deep exploration.
- **Output:** Detailed issue reports with screenshots, session videos, and console logs.

## 5. Regression Evals
Rerunning the complete test suite to ensure existing functionality remains intact.
- **When:** Before merging any PR and in automated CI/CD pipelines.
- **Command:** `npx playwright test`
- **Goal:** Catch unintended side effects in unrelated areas.

## 6. Non-Deterministic Tests
Tests involving variable factors like timing, external APIs, or randomness.
- **When:** Email delivery, background job processing, third-party webhooks.
- **Strategy:** Retry with a success threshold (e.g., pass 4/5 runs), mock external services, and use fixed random seeds.
- **Example:** `await expect(emailReceived).toBe(true, { timeout: 10000 })`

## Related References
- [Writing Evals — Templates & Patterns](writing-evals.md)
- [Fuzzy Eval Rubrics](fuzzy-eval-rubrics.md)
- [CI/CD Pipeline Enforcement](ci-enforcement.md)
