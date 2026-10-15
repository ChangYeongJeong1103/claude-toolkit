# Deliverable QA

## Problem

A client-facing Markdown draft should be checked against the same rulebook and metric definitions before it is sent. This plugin scans a draft, recomputes supported metrics, validates evidence for findings, separates blockers from warnings, and calculates a ready-to-send verdict without editing the draft.

## Quick start

Requirements: Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the public marketplace:

```text
/plugin install deliverable-qa --marketplace ChangYeongJeong1103/claude-toolkit
```

Ask for a check and name the rulebook when it is not discoverable beside the draft:

```text
Is examples/deliverable-qa/drafts/kestrel-q3-recap.md ready to send? Use examples/deliverable-qa/rulebook.
```

The repository example paths require cloning this repository. You can also invoke `/deliverable-qa:qa-check`.

## Representative example

A report follows this flow:

1. `scan` returns rulebook, client, metric, table, and line evidence as JSON.
2. `calc` recomputes supported prose claims from numbers shown in the draft.
3. The skill maps evidence to rules and proposes fixes.
4. `report` rejects unknown rule IDs, bad line quotes, and omitted unambiguous evidence, then reads severity from the rulebook and prints the verdict.

The synthetic Kestrel draft includes a metric mismatch and rulebook issues that produce blockers and a warning without modifying the file.

## Configuration/input contract

Drafts must be Markdown. The rulebook directory contains:

- `deliverable-rules.md`: one `## <ID>. <Title> (Blocker|Warning)` section per rule
- `metric-definitions.md`: a Markdown table with `Metric`, `Formula`, and `Shown as`
- `clients.csv`: `display_name`, semicolon-separated `aliases`, `status`, and `benchmark_consent`

Supported formula operators are `÷`, `×`, `−`, `+`, parentheses, `/`, and `*`. Constants do not use thousands separators. The script discovers `rulebook/` beside or inside the drafts folder unless `--rulebook` is supplied.

## Architecture/verification boundary

The `qa-check` skill decides which documented rule applies and words suggested fixes. `qa.py` owns rule parsing, supported calculations, evidence validation, rule severity, and the verdict.

The `PreToolUse` hook asks before supported edit tools touch a path under a directory named `drafts`. It is path-based and does not run after the QA script or cover shell-based edits. Tests use self-contained rulebook and draft fixtures, including an alternate-team contract.

## Limitations

- PowerPoint and PDF are outside the current scope, and the plugin sends nothing.
- The hook does not cover Bash edits such as redirects or `sed -i`.
- Some prose evidence, rule terms, and title judgments remain model decisions.
- Formula parsing does not support ASCII `-`, `x`, constants such as `1,000`, or scaled inputs such as `3.05 million`.
- Shell JSON arguments cannot contain apostrophes under the current skill contract.
- All bundled clients, drafts, rules, and metrics are synthetic.
