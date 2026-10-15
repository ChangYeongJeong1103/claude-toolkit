---
name: plan-segments
description: >-
  Recommends audience segments for an advertiser brief from the team's segment catalog, following the targeting
  policy. Cites each recommended segment ID with the reason it fits, lists the segments the policy excludes with
  the rule behind each, and computes impressions and reach with a script. Asks for a missing budget or flight
  dates instead of assuming. Use when someone asks to recommend, plan, or pick audience segments for a brief, or
  asks for impressions, reach, or total reach for a campaign's segments. Do NOT trigger for activating segments in
  ad platforms, for negotiating prices, or for editing the catalog or the policy.
argument-hint: "<brief.md> [catalog folder] [policy config.json]"
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/segments.py" *), Read
---

# Audience segment planner

Plans segments for one brief from a catalog folder: a segment catalog CSV and the targeting policy document. `scripts/segments.py` does everything exact: the policy rules (`check`) and the delivery math (`plan`). You read the brief, choose which eligible segments fit it, and write the reasons.

## Invariants (do not violate)
1. **Only eligible catalog segments.** Recommend only IDs from the `check` output's Eligible table. Never invent a segment, a size, or a price.
2. **Every number comes from the script.** Households, CPM, budget, impressions, and reach are copied from the script output. Never compute or estimate one yourself.
3. **Never add reach across segments that can overlap.** If the brief asks for total reach, give the script's combined-reach line and say why it is a range.
4. **Catalog CPM only.** A quoted or negotiated price in the brief is noted and ignored (D1). Pricing negotiation and activation in ad platforms are out of scope.
5. **Never assume a missing budget or flight date.** Ask for it.

## Steps
Run every `segments.py` command with the script path exactly as written below (the absolute path, in double quotes). `allowed-tools` pre-approves only that quoted path, so don't drop the quotes, shorten the path, or wrap it in another command.

1. **Inputs.** The brief is a Markdown file. The catalog folder holds the segment catalog CSV and the targeting policy document (`.md`). If the user didn't name the catalog folder, ask for it.
2. **Policy config.** The rules run from a JSON config, never from your reading of the policy text.
   - Use the config the user names, or else the bundled `${CLAUDE_SKILL_DIR}/config/targeting-policy.json`.
   - Read the policy document and the config. The config's `policy`, `owner`, and `effective` must match the document's title, owner, and effective date.
   - If they don't match, stop and ask for a config written for that policy (the format is in the plugin README). Never write or edit rules yourself.
3. **Read the brief.** Required (D5): the total budget as a dollar amount, and exact flight start and end dates.
   - If either is missing or vague ("to be confirmed", "sometime in Q1"), stop. Quote the brief's wording, say what is missing, and ask for it. Don't run the script or suggest segments.
   - Note the frequency cap if the brief gives one.
4. **Advertiser category.** Pick one from the config's `advertisers` lists (for example `health`, `pharma`, `otc_medicine`, `alcohol`), or `other` if none applies, from the brief's advertiser and product. If you can't tell whether a restricted category applies, ask.
5. **Check.** Run:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/segments.py" check --catalog "<csv>" --policy "<config>" --advertiser "<category>" --flight-end "<YYYY-MM-DD>"`
   On `error:`, tell the user and stop.
6. **Choose segments.** For each audience the brief describes, pick the eligible segments whose name and description match it.
   - Give each one a one-sentence reason in the brief's terms. Say when the fit is partial (for example, an age band wider than the brief's).
   - If the brief asks for a segment by name that isn't in the catalog, say so. You may offer the closest eligible segment as an alternative, labeled as one.
   - If an audience matches only excluded segments, say so and cite the rule from the Excluded table.
   - Don't add segments that don't fit the brief.
7. **Plan.** Run:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/segments.py" plan --catalog "<csv>" --policy "<config>" --advertiser "<category>" --flight-end "<YYYY-MM-DD>" --budget "<USD amount, digits only>" --segments "<ID,ID,...>" [--frequency-cap "<N>"]`
   - Pass `--frequency-cap` only if the brief gives one; otherwise the policy default applies.
   - An error about an unknown or excluded ID means your selection is wrong: fix the selection and rerun. Never work around it.
8. **Answer** in this format:

```
## Segment plan: <brief title>
Advertiser: <name> → category `<category>` (<why>) · Flight: <start> – <end> · Budget: $<amount>

### Recommended segments
- **<ID> <name>**: <reason>

### Delivery
<the plan output from its "Budget:" line to the end, verbatim>

### Excluded by policy
<the check output's Excluded table, verbatim>

### Notes
- <requested segments not in the catalog, ignored quoted prices, audiences with no eligible segment; omit if none>
```
