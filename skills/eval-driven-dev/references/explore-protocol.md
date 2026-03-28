# Codebase Exploration Protocol

## Table of Contents
- [Config Files](#config-files)
- [Schema Files](#schema-files)
- [Route Structure](#route-structure)
- [Existing Tests](#existing-tests)
- [Environment Variables](#environment-variables)
- [Package Dependencies](#package-dependencies)
- [Existing Patterns](#existing-patterns)
- [Integration Points](#integration-points)
- [Output Format](#output-format)
- [Related References](#related-references)

## Config Files
Scan for project-wide configuration:
- `next.config.js/ts`
- `turbo.json`
- `drizzle.config.ts`
- `auth.ts` / `better-auth.ts`
- `playwright.config.ts`

**Command:** `glob pattern="**/*.config.{ts,js}"`

## Schema Files
Understand data structures and relationships:
- `db/schema.ts`
- `prisma/schema.prisma`

**Command:** `read filePath="db/schema.ts"`

## Route Structure
Map out the application flow:
- `app/` directory (Next.js App Router)
- `pages/api/` (API routes)

**Command:** `glob pattern="app/**/page.tsx"`

## Existing Tests
Locate existing test patterns:
- `tests/`
- `e2e/`
- `__tests__/`

**Command:** `glob pattern="**/*.spec.ts"` or `glob pattern="**/tests/**"`

## Environment Variables
Check for required keys and local setup:
- `.env`
- `.env.example`

**Command:** `read filePath=".env.example"`

## Package Dependencies
Identify available libraries and workspace structure:
- `package.json` for each workspace

**Command:** `read filePath="package.json"`

## Existing Patterns
Look for similar features to copy:
- How are other CRUD operations handled?
- How is authentication enforced on routes?

**Command:** `grep pattern="export const ...Schema =" include="db/schema.ts"`

## Integration Points
Where does this feature connect?
- Layout files
- Navigation components
- Existing API endpoints

**Command:** `grep pattern="<nav" include="**/components/**"`

## Output Format
Organize your findings by relevance:
- **Core Files:** The most important files for this feature.
- **Similar Patterns:** References for how to implement.
- **Risks:** Conflicts or missing configurations found.

## Related References
- [Socratic Discovery Questions](discovery-questions.md)
- [Eval Types Guide](eval-types.md)
