# Campaign analysis

## What it does

Account managers ask the same campaign questions every week, and the answers should come from the same cleaning rules and calculations every time. This plugin answers the supported weekly questions from a CSV export, and it tells you which rows it left out and why instead of quietly using bad data.

## Quick start

You need Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the marketplace:

```text
/plugin install campaign-analysis --marketplace ChangYeongJeong1103/claude-toolkit
```

Ask in plain English and give the CSV path:

```text
How did Fall Thriller do last week? Use examples/campaign-analysis/campaign_performance.csv.
```

The example path only exists in a clone of this repository. Approve the `campaign-performance` skill the first time it runs, or call it directly with `/campaign-analysis:campaign-performance`.

## Example

The sample CSV supports three kinds of question:

- how a campaign did in the latest complete Monday–Sunday week, compared with the week before
- streaming versus live TV
- underperforming campaigns and potential waste

Ask `Which rows were excluded?` to see the row-level reasons. To share an answer, ask for a Gmail draft and give the recipient. Sending is a separate, explicit request, and a confirmation prompt appears before anything goes out. Without a compatible Gmail connector, the skill writes a local HTML draft instead.

## Input format

Required columns: `campaign_id`, `campaign_name`, `date`, `impressions`, `tune_ins`, `spend`, `platform` and `content_type`. Each row is one campaign on one date on one platform.

The script normalizes the documented platform spellings, currency separators, `MM/DD/YYYY` dates and exact duplicates. It excludes and reports conflicting duplicates, missing or negative values, zero impressions, more tune-ins than impressions, unknown platforms, unreadable dates and non-finite numbers.

Metrics:

- tune-in rate = tune-ins ÷ impressions
- cost per tune-in = spend ÷ tune-ins
- CPM = spend ÷ impressions × 1,000
- underperforming = cost per tune-in at least 1.5× the median for the same platform; spend with zero tune-ins is always flagged

## How it works

- **Skill (`campaign-performance`):** picks the supported command and presents the result.
- **Script (`campaign_report.py`):** CSV cleaning, calculations, thresholds, and Markdown or HTML output.
- **Hook (`PreToolUse`):** runs only on Gmail send, reply and forward calls. It shows the fields being sent and asks for confirmation. It does not run after every script call.
- **Gmail connector:** optional, part of your own Claude configuration, and not bundled here.

The tests cover the report math, exclusions, identical numbers in HTML and Markdown, and the hook's decisions.

## Limitations

- Supported periods are the latest complete week and, for some commands, the whole file.
- Arbitrary date ranges, campaign-to-campaign comparisons and content-type breakdowns are not implemented.
- Missing days are shown in the output but not interpreted.
- The no-connector fallback and Gmail behavior depend on your environment.
- All bundled examples and fixtures are synthetic.
