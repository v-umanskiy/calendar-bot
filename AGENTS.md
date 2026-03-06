# AGENTS.md

This file defines how coding agents should work in this repository.

## Core Principles

1. Integrate before inventing.
2. Keep code minimal and readable.
3. Add only what is requested.

## Integration-First Development

When implementing a feature or fix:

1. Discover existing structure first:
   - Review current handlers, services, repositories, utilities, and shared abstractions.
   - Identify the best existing place for the change.
2. Prefer extending existing code paths over adding parallel ones.
3. Reuse existing utilities and abstractions whenever possible.
4. Create new files/modules/abstractions only when existing structure cannot cleanly support the requirement

## Validation and Defensive Checks

Validate only cases that can actually occur.
Before adding a guard/check, inspect upstream flow and data contracts.
If upstream already guarantees a condition, do not add redundant downstream checks.

## No Speculative Scope

Do not add "nice-to-have" behavior unless explicitly requested.

## Change Style

1. Prefer small, targeted edits over broad rewrites.
2. Minimize duplication by merging with existing flows.
3. Extract reused code if necessary.
