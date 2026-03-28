# CI/CD Pipeline Enforcement

## Table of Contents
- [GitHub Actions Workflow](#github-actions-workflow)
- [Required Status Checks](#required-status-checks)
- [Running Fuzzy Evals in CI](#running-fuzzy-evals-in-ci)
- [Artifact Upload for Eval Evidence](#artifact-upload-for-eval-evidence)
- [Branch Protection Rules](#branch-protection-rules)
- [Related References](#related-references)

## GitHub Actions Workflow
```yaml
name: Eval Gate
on: [pull_request]
jobs:
  deterministic:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test --reporter=github
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/

  regression:
    needs: deterministic
    runs-on: ubuntu-latest
    steps:
      - run: npx playwright test --reporter=list
```

## Required Status Checks
- Block merging PRs until all jobs in the `Eval Gate` workflow pass successfully.
- This ensures that only code passing all deterministic and regression tests enters the main branch.

## Running Fuzzy Evals in CI
Integrate screenshot capture and LLM scoring as part of the pipeline:
- Use an action to trigger `agent-browser` or a similar tool.
- Send the screenshots to an LLM for evaluation based on predefined rubrics.
- Fail the job if the scoring falls below the required threshold.

## Artifact Upload for Eval Evidence
Always upload test artifacts (screenshots, session videos, and reports) on failure to facilitate debugging:
- Use `actions/upload-artifact@v4` with a descriptive name.
- Set a retention period to avoid storage bloat.

## Branch Protection Rules
Enforce the following on the `main` branch:
- **Require status checks to pass before merging:** Specifically the `Eval Gate` jobs.
- **Require linear history:** Prevent merge commits if possible.
- **Require approvals:** At least one human approval alongside automated eval results.

## Related References
- [Eval Types Guide](eval-types.md)
- [Writing Evals — Templates & Patterns](writing-evals.md)
- [Fuzzy Eval Rubrics](fuzzy-eval-rubrics.md)
