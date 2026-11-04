## What changed

<!-- One or two sentences. What does this do that the base branch did not? -->

## Why

<!-- The problem, not the solution. -->

## Does this change a number?

Carbon accounting has a property most software does not: a number that has
already been issued is a commercial fact somebody bought against. Tick what
applies.

- [ ] No — docs, tooling, tests, or presentation only
- [ ] Yes, but only for vintages that have **not** been issued
- [ ] Yes, for a vintage that **has** been issued — explain below, and treat
      it as an incident rather than an update

<!-- If a number moved, say which and by how much. -->

## Checks

- [ ] `python -m pytest` passes
- [ ] New behaviour has a test that fails without the change
- [ ] If a methodology, emission factor, allometry or deduction changed, the
      source is cited in the code near it
- [ ] If a placeholder is still a placeholder, it is still marked as one
