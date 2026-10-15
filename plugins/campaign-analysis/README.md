# Campaign analysis

## Problem

Recurring campaign questions should use the same cleaning rules and calculations every time. This plugin answers supported weekly questions from a CSV export and reports excluded data instead of silently using invalid rows.

## Quick start

Requirements: Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the public marketplace:

```text
/plugin install campaign-analysis --marketplace ChangYeongJeong1103/claude-toolkit
```

Ask in plain English and provide the CSV path:

```text
How did Fall Thriller do last week? Use examples/campaign-analysis/campaign_performance.csv.
```

The repository example path requires cloning this repository. On first use, approve the `campaign-performance` skill. You can also invoke `/campaign-analysis:campaign-performance`.

## Representative example

The synthetic CSV supports three recurring question families:

- campaign performance for the latest complete Monday–Sunday week, compared with the previous week
- streaming versus live TV
- underperforming campaigns and potential waste

Ask `Which rows were excluded?` for row-level reasons. To share an answer, ask for a Gmail draft and provide the recipient. Sending is a separate explicit action guarded by a confirmation prompt. If no compatible Gmail connector is configured, the skill can create a local HTML draft.

## Configuration/input contract

Required CSV columns are `campaign_id`, `campaign_name`, `date`, `impressions`, `tune_ins`, `spend`, `platform`, and `content_type`. Each row represents one campaign, date, and platform.

The script normalizes documented platform spellings, currency separators, `MM/DD/YYYY` dates, and exact duplicates. It excludes and reports conflicting duplicates, missing or negative values, zero impressions, tune-ins greater than impressions, unknown platforms, unreadable dates, and non-finite numbers.

Metrics are:

- tune-in rate = tune-ins ÷ impressions
- cost per tune-in = spend ÷ tune-ins
- CPM = spend ÷ impressions × 1,000
- underperforming = cost per tune-in at least 1.5× the same-platform campaign median; spend with zero tune-ins is always flagged

## Architecture/verification boundary

The `campaign-performance` skill selects a supported command and presents results. `campaign_report.py` performs CSV cleaning, calculations, thresholds, and Markdown or HTML rendering. The optional Gmail MCP connector belongs to the user's Claude configuration and is not bundled here.

The `PreToolUse` hook runs only on matching Gmail send, reply, or forward calls. It previews supplied fields and asks for confirmation; it does not run after every script call. Tests cover report calculations, exclusions, HTML/Markdown numeric parity, and hook decisions.

## Limitations

- Supported periods are the latest complete week and, for selected commands, the whole file.
- Arbitrary date ranges, campaign-to-campaign comparisons, and content-type breakdowns are outside the implemented commands.
- Missing-day coverage is shown in output but not interpreted for the user.
- The connector fallback and external Gmail behavior depend on the user's environment.
- All bundled examples and fixtures are synthetic.
