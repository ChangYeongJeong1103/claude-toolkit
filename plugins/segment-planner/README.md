# Segment planner

## What it does

An audience recommendation should only use catalog segments that pass the targeting policy, and the delivery estimate should come from math anyone can reproduce. This plugin keeps those two apart: the model reads the brief, and a script decides eligibility and computes reach.

## Quick start

You need Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the marketplace:

```text
/plugin install segment-planner --marketplace ChangYeongJeong1103/claude-toolkit
```

Ask with a brief and a catalog folder:

```text
Recommend segments for examples/segment-planner/briefs/brightwell-allergy.md using examples/segment-planner/catalog.
```

The example paths only exist in a clone of this repository. You can also call the skill directly with `/segment-planner:plan-segments`.

## Example

For the Brightwell brief, the skill reads the requested audiences, confirms the budget and flight dates, checks every catalog row against the policy config, picks the eligible segments that fit and runs the delivery calculation. Excluded segments stay visible with the rule that excluded them. A CPM quoted in the brief does not replace the catalog price.

## Input format

The catalog CSV needs `segment_id`, `name`, `type`, `description`, `households`, `cpm_usd`, `status`, `expires_on`, `sensitive_category`, `age_floor` and `exclusive_group`.

The JSON policy config gives the policy title, owner, effective date, default frequency cap and rules. Supported rule kinds:

- `banned_sensitive_category`
- `min_households`
- `active_through_flight_end`
- `banned_type_for_advertiser`
- `min_age_floor_for_advertiser`

The config's title, owner and effective date must match the policy document. A brief must give a total budget and exact flight dates. The script splits the budget evenly and uses the catalog CPM.

## How it works

- **Skill (`plan-segments`):** interprets the brief, picks the advertiser category, selects the eligible segments that fit and explains each fit.
- **Script (`segments.py`):** applies the configured rules, rejects unknown or excluded IDs, and computes impressions and reach with exact fractions, rounding down only for output.
- **No hook.** The script itself refuses bad segment IDs; whether a segment is relevant stays the model's call.

The tests cover the eligibility rules, date boundaries, refusals, a different policy config and the delivery math.

## Limitations

- Only the five rule kinds above are supported.
- The budget is always split evenly; weighted allocation is not implemented.
- Combined reach is a range unless the segments share an exclusive group. There is no household-level deduplication.
- Validation covers the required columns, the core number and date fields, and positive delivery inputs, but not every inconsistency a custom catalog or policy could have.
- Activation in ad platforms and price negotiation are out of scope.
- All bundled advertisers, briefs, policies and segments are synthetic.
