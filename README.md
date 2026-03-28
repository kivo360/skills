# Skills

Agent skills for full-stack SaaS development.

## Install

```bash
# Install all skills
npx skills add kivo360/skills

# Install a specific skill
npx skills add kivo360/skills --skill better-auth-complete
npx skills add kivo360/skills --skill better-auth-test-utils
npx skills add kivo360/skills --skill better-auth-ui
npx skills add kivo360/skills --skill dogfood-complete
npx skills add kivo360/skills --skill my-stack
npx skills add kivo360/skills --skill saas-bootstrap
npx skills add kivo360/skills --skill eval-driven-dev
```

## Skills

| Skill | Description |
|-------|-------------|
| **[eval-driven-dev](skills/eval-driven-dev)** | 7-stage workflow: Discover → Explore → Spec → Eval (tests first) → Implement → Verify → Iterate. Enforces test-first development with deterministic, fuzzy, integration, QA, and regression evals. |
| **[saas-bootstrap](skills/saas-bootstrap)** | Bootstrap a full SaaS stack — detect project, install all skills, scaffold configs, automate credential setup |
| **[my-stack](skills/my-stack)** | Master router for full SaaS stack — Next.js, Better Auth, Drizzle, Stripe, Resend, Sentry, PostHog |
| **[better-auth-complete](skills/better-auth-complete)** | Meta skill routing all Better Auth work — auth setup, OAuth, 2FA, orgs, email, testing, security |
| **[better-auth-test-utils](skills/better-auth-test-utils)** | Better Auth test helpers — factories, getCookies for Playwright, OTP capture, Vitest integration |
| **[better-auth-ui](skills/better-auth-ui)** | Pre-built shadcn/ui auth components — sign in, sign up, settings, orgs, API keys |
| **[dogfood-complete](skills/dogfood-complete)** | Unified QA + Playwright test generation using agent-browser — video, annotated screenshots, reports |

## Stack Coverage

These skills cover the full SaaS development lifecycle:

- **Auth**: Better Auth + Better Auth UI (sign in, sign up, 2FA, orgs, passkeys)
- **Testing**: agent-browser exploration, QA reports with video evidence, Playwright test generation
- **Database**: Drizzle ORM integration with Better Auth
- **Payments**: Stripe integration patterns
- **Email**: Resend + React Email templates
- **Monitoring**: Sentry error tracking, PostHog analytics
- **UI**: shadcn/ui + Tailwind CSS
- **Infrastructure**: Turborepo monorepo, Vercel deployment

## License

MIT
