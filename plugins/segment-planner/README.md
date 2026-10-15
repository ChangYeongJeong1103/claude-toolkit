# Segment planner

## Problem

Audience recommendations should use only catalog segments that satisfy the applicable targeting policy, and delivery estimates should follow reproducible math. This plugin separates brief interpretation from deterministic eligibility and reach calculations.

## Quick start

Requirements: Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the public marketplace:

```text
/plugin install segment-planner --marketplace ChangYeongJeong1103/claude-toolkit
```

Ask with a brief and catalog folder:

```text
Recommend segments for examples/segment-planner/briefs/brightwell-allergy.md using examples/segment-planner/catalog.
```

The repository example paths require cloning this repository. You can also invoke `/segment-planner:plan-segments`.

## Representative example

For the synthetic Brightwell brief, the skill reads the requested audiences, confirms the budget and flight dates, checks every catalog row against the policy config, selects fitting eligible IDs, and runs the delivery calculation. Excluded rows remain visible with their rule IDs. A quoted CPM in the brief does not replace catalog pricing.

## Configuration/input contract

The catalog CSV requires `segment_id`, `name`, `type`, `description`, `households`, `cpm_usd`, `status`, `expires_on`, `sensitive_category`, `age_floor`, and `exclusive_group`.

The JSON policy config identifies the policy title, owner, effective date, default frequency cap, and rules. Supported rule kinds are:

- `banned_sensitive_category`
- `min_households`
- `active_through_flight_end`
- `banned_type_for_advertiser`
- `min_age_floor_for_advertiser`

The config metadata must match the policy document. Briefs must provide a total budget and exact flight dates. The script uses an even budget split and catalog CPM.

## Architecture/verification boundary

The `plan-segments` skill interprets the brief, chooses an advertiser category, selects fitting eligible segments, and explains the fit. `segments.py` applies configured rules, rejects unknown or excluded IDs, and computes impressions and reach with exact fractions before rounding down for output.

There is no hook. Deterministic rejection occurs inside the script, while segment relevance remains model judgment. Tests cover eligibility rules, boundaries, refusals, portability, and delivery math.

## Limitations

- Only the five documented rule kinds are supported.
- Budgets are split evenly; weighted allocation is not implemented.
- Combined reach is a range unless segments share an exclusive group; there is no household-level deduplication.
- Validation covers required columns, core numeric/date fields, and positive delivery inputs, but not every possible semantic inconsistency in a custom catalog or policy.
- Activation and price negotiation are outside scope.
- All bundled advertisers, briefs, policies, and segments are synthetic.
