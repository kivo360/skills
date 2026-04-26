# Write Tests — Playwright Test Generation

Load the following skills before proceeding:
- `playwright-best-practices` — Full test patterns, POM, locators, assertions, debugging, CI/CD
- `better-auth-test-utils` — Auth fixtures, getCookies, OTP capture, test factories
- `better-auth-complete` — Full auth implementation context (for auth-aware testing)

Then invoke the **@playwright-writer** agent with this task:

**Target:** $ARGUMENTS

**Instructions for @playwright-writer:**

1. First, explore the codebase to understand:
   - Existing test patterns and conventions (check `tests/`, `e2e/`, `__tests__/`)
   - The app's auth setup (Better Auth config, routes, middleware)
   - Page components and routes to derive Page Object Models
   - Existing Playwright config (`playwright.config.ts`)
2. Create or update auth fixtures if the app uses Better Auth
3. Generate Page Object Models for pages under test
4. Write comprehensive E2E tests covering:
   - Happy path flows
   - Error states and edge cases
   - Auth boundaries (authenticated vs unauthenticated)
   - Accessibility (axe-core if available)
5. Run the tests and fix any failures
6. Only report completion when all tests pass

**Test file location:** Follow existing project conventions. Default to `tests/` or `e2e/` directory.
