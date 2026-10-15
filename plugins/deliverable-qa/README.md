# Deliverable QA

## What it does

Before a Markdown deliverable goes to a client, it should be checked against the same rulebook and metric definitions every time. This plugin scans the draft, recomputes the supported metrics, checks the evidence behind every finding, separates blockers from warnings and gives a ready-to-send verdict. It never edits the draft.

## Quick start

You need Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the marketplace:

```text
/plugin install deliverable-qa --marketplace ChangYeongJeong1103/claude-toolkit
```

Ask for a check, and name the rulebook if it isn't next to the drafts folder:

```text
Is examples/deliverable-qa/drafts/kestrel-q3-recap.md ready to send? Use examples/deliverable-qa/rulebook.
```

The example paths only exist in a clone of this repository. You can also call the skill directly with `/deliverable-qa:qa-check`.

## Example

A check runs in four steps:

1. **`scan`** returns the rulebook, client, metric, table and line evidence as JSON.
2. **`calc`** recomputes the prose claims it supports from numbers shown in the draft.
3. **The skill** maps the evidence to rules and proposes fixes.
4. **`report`** rejects unknown rule IDs, wrong line quotes and unambiguous evidence that was left out, then reads the severity from the rulebook and prints the verdict.

The sample Kestrel draft has a metric mismatch and other rulebook problems, so it comes back with blockers and a warning, and the file is left untouched.

## Input format

Drafts must be Markdown. The rulebook folder has three files:

- `deliverable-rules.md`: one `## <ID>. <Title> (Blocker|Warning)` section per rule
- `metric-definitions.md`: a Markdown table with `Metric`, `Formula` and `Shown as`
- `clients.csv`: `display_name`, semicolon-separated `aliases`, `status` and `benchmark_consent`

Formulas can use `÷`, `×`, `−`, `+`, parentheses, `/` and `*`. Constants are written without thousands separators. The script finds a `rulebook/` folder beside or inside the drafts folder unless you pass `--rulebook`.

## How it works

- **Skill (`qa-check`):** decides which documented rule applies and words the suggested fixes.
- **Script (`qa.py`):** rule parsing, supported calculations, evidence validation, severity and the verdict.
- **Hook (`PreToolUse`):** asks before a supported edit tool touches a path under a directory named `drafts`. It is path-based, does not run after the QA script and does not cover edits made through the shell.

The tests use their own rulebook and draft fixtures, including a second team's rulebook with different rule IDs, metrics and clients.

## Limitations

- PowerPoint and PDF are not supported, and the plugin never sends anything.
- The hook does not catch shell edits such as redirects or `sed -i`.
- Some prose evidence, rule terms and title checks are still the model's judgment.
- Formulas cannot use ASCII `-`, `x`, constants like `1,000` or scaled inputs like `3.05 million`.
- JSON passed on the shell cannot contain apostrophes under the current skill instructions.
- All bundled clients, drafts, rules and metrics are synthetic.
