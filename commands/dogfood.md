# Dogfood — Exploratory QA Testing

Load the following skills before proceeding:
- `dogfood-complete` — Full exploration protocol, agent-browser workflows, QA report generation
- `playwright-best-practices` — Test patterns, locators, assertions (for test gen mode)
- `better-auth-test-utils` — Auth fixtures, getCookies, test factories (for auth-aware testing)

Then invoke the **@dogfooder** agent with this task:

**Target:** $ARGUMENTS

**Instructions for @dogfooder:**

1. Set up agent-browser and output directories (`dogfood-output/screenshots/`, `dogfood-output/videos/`)
2. Navigate to the target URL
3. Start video recording
4. Systematically explore the application:
   - Visit every visible page/route
   - Test all interactive elements (forms, buttons, links, modals)
   - Check responsive behavior at different viewport sizes
   - Monitor console for errors throughout
5. Document every issue found with full evidence (screenshots, video, console errors)
6. Generate a QA report at `dogfood-output/report.md`
7. Optionally generate Playwright tests from the exploration session

**Default mode:** QA report. If the user says "and tests" or "generate tests", also produce Playwright test files.
