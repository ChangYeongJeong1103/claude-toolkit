# Policy assistant

## Problem

AI-tool policy questions often span documents with different dates, statuses, and authority. This plugin retrieves relevant sections from a local Markdown folder, identifies the policy in effect for the requested date, and produces cited answers without inventing missing links or contacts.

## Quick start

Requirements: Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the public marketplace:

```text
/plugin install policy-assistant --marketplace ChangYeongJeong1103/claude-toolkit
```

Ask a question and provide the policy folder:

```text
Can I use Cursor with client data? The policy folder is examples/policy-assistant/policy-docs.
```

The repository example path requires cloning this repository. On first use, approve the `policy-answers` skill.

## Representative example

The synthetic policy set includes active, superseded, future-dated, and reference documents. A question about a tool and client data demonstrates:

- current policy taking precedence over an older FAQ
- citations in `file.md § heading` form
- an allowed alternative only when named by the retrieved documents
- contacts and links copied from the documents rather than invented

## Configuration/input contract

Use a folder of Markdown files with names that contain no spaces. Headings become citation targets.

Document metadata can be YAML-like front matter or inline metadata before the first `##` heading. Supported keys are `status`, `effective`, `last updated`, `supersedes`, `superseded_by`, and `replaces`. Supported statuses are Active, Approved, and Superseded. Supported dates include ISO dates, slash-separated dates, month-name dates, and month/year dates.

A document with no usable date is reference-only. An unsupported status is not in effect, and an unreadable date is never treated as active. Put the authority rule in a heading containing `Precedence` so it is always included.

## Architecture/verification boundary

The `policy-answers` skill applies authority, conflict, and alternative-selection judgment. `policy_context.py` deterministically parses metadata, evaluates status, retrieves sections, and extracts contacts, links, and missing references.

A `Stop` hook checks answers only after a policy script call in the current turn. It verifies that cited sections, contacts, and links exist and that covered answers contain a citation. It does not prove that the prose correctly summarizes a real section.

## Limitations

- Retrieval is keyword-based rather than semantic.
- A Stop hook can request a revision but cannot retract text already displayed.
- Resuming a prior process may require reapproving the script if the skill is not reloaded.
- PDF, DOCX, Slack, and non-English retrieval are outside the current contract.
- All bundled policies, organizations, contacts, and scenarios are synthetic.
