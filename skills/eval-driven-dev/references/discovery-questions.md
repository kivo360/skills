# Socratic Discovery Questions

## Table of Contents
- [Layer 1 — Problem Space](#layer-1--problem-space)
- [Layer 2 — Technical Scope](#layer-2--technical-scope)
- [Layer 3 — Priorities](#layer-3--priorities)
- [Layer 4 — Verticals & MVPs](#layer-4--verticals--mvps)
- [Example Output: Organization Billing](#example-output-organization-billing)
- [Related References](#related-references)

## Layer 1 — Problem Space
- What problem are you solving? Why does this matter?
- Who is this for? Describe the user.
- What does success look like from the user's perspective?
- What's the MVP? What's the full vision?
- What happens if you DON'T build this?

## Layer 2 — Technical Scope
- Which parts of the stack does this touch?
- Does this create new features or modify existing?
- What are the integration points?
- What existing patterns should this follow?
- What data models are involved?

## Layer 3 — Priorities
- Rank: speed, quality, scope — which two do you pick?
- What's the hardest part? What might go wrong?
- What are you willing to cut from MVP?
- Any deadline or constraint?

## Layer 4 — Verticals & MVPs
After gathering answers, synthesize the request into manageable technical verticals:
- **Vertical 1:** [Core feature] — MVP: [Minimal functional version]
- **Vertical 2:** [Adjacent feature] — MVP: [Minimal version]
- **Recommendation:** Start with Vertical [N] because [Specific technical or user-value reason]

## Example Output: Organization Billing
**Request:** "Add organization billing to our SaaS."

**Synthesis:**
- **Vertical 1: Subscription Management** — MVP: Allow org admins to select a plan and store a payment method via Stripe Checkout.
- **Vertical 2: Usage Reporting** — MVP: Simple dashboard showing current month's seat count and projected cost.
- **Recommendation:** Start with Vertical 1 because it establishes the baseline database schema and Stripe integration required for any billing logic.

## Related References
- [Codebase Exploration Protocol](explore-protocol.md)
- [Eval Types Guide](eval-types.md)
