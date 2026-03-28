# Writing Evals — Templates & Patterns

## Table of Contents
- [Playwright Test Template](#playwright-test-template)
- [Fuzzy Eval Template](#fuzzy-eval-template)
- [Integration Eval Template](#integration-eval-template)
- [QA Dogfood Eval Template](#qa-dogfood-eval-template)
- [Regression Eval Template](#regression-eval-template)
- [Related References](#related-references)

## Playwright Test Template
```typescript
import { test } from '../fixtures/auth';
import { expect } from '@playwright/test';

test.describe('[Feature Name]', () => {
  test('happy path: [description]', async ({ page, authenticatedContext }) => {
    const { user } = await authenticatedContext.asUser();
    // Navigate
    await page.goto('/[path]');
    // Act
    await page.getByRole('button', { name: '[action]' }).click();
    // Assert
    await expect(page.getByText('[expected text]')).toBeVisible();
  });

  test('edge case: [description]', async ({ page }) => {
    await page.goto('/[path]');
    // Trigger edge case (e.g., submit empty form)
    await page.getByRole('button', { name: '[action]' }).click();
    // Assert error handling
    await expect(page.getByText('[error message]')).toBeVisible();
  });
});
```

## Fuzzy Eval Template
```typescript
export const myFeatureVisualEval = {
  name: '[Feature] visual quality',
  type: 'fuzzy',
  rubric: {
    criteria: [
      '[Criterion 1 — Y/N question]',
      '[Criterion 2 — Y/N question]',
      '[Criterion 3 — Y/N question]',
    ],
    threshold: 2, // Out of 3 to pass
  },
};
```

## Integration Eval Template
Uses `better-auth-test-utils` and Playwright to verify cross-system flows:
```typescript
import { test } from '../fixtures/auth';
import { prisma } from '../lib/prisma';

test('create and verify organization', async ({ page, authenticatedContext }) => {
  const { user } = await authenticatedContext.asUser();
  await page.goto('/orgs/new');
  await page.fill('input[name="org-name"]', 'Test Org');
  await page.click('button[type="submit"]');

  // Verify UI update
  await expect(page.getByText('Organization created')).toBeVisible();

  // Verify DB state directly
  const org = await prisma.organization.findFirst({ where: { name: 'Test Org' } });
  expect(org).not.toBeNull();
});
```

## QA Dogfood Eval Template
Commands to initiate `agent-browser` exploration:
- `agent-browser --goal "Explore the new billing dashboard and find any layout or functional bugs." --mode "qa"`
- `agent-browser --goal "Verify that the new user onboarding flow works for all three plan types."`

## Regression Eval Template
Run full test suite locally before pushing:
`npx playwright test --reporter=list`

## Related References
- [Eval Types Guide](eval-types.md)
- [Fuzzy Eval Rubrics](fuzzy-eval-rubrics.md)
- [CI/CD Pipeline Enforcement](ci-enforcement.md)
