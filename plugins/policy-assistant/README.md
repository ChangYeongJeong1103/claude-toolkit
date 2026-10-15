# Policy assistant

## What it does

An AI-tool policy question often touches several documents with different dates, statuses and authority. This plugin pulls the relevant sections from a local folder of Markdown policies, works out which policy is in effect on the date you ask about, and answers with citations. It never fills in a link or contact that the documents don't have.

## Quick start

You need Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the marketplace:

```text
/plugin install policy-assistant --marketplace ChangYeongJeong1103/claude-toolkit
```

Ask a question and give the policy folder:

```text
Can I use Cursor with client data? The policy folder is examples/policy-assistant/policy-docs.
```

The example path only exists in a clone of this repository. Approve the `policy-answers` skill the first time it runs.

## Example

The sample policies include active, superseded, future-dated and reference documents. The Cursor question shows:

- the current policy winning over an older FAQ
- citations in `file.md § heading` form
- an approved alternative, but only when the retrieved documents name one
- contacts and links copied from the documents, not invented

## Input format

A folder of Markdown files whose names contain no spaces. Headings become citation targets.

Metadata can be YAML-like front matter or inline lines before the first `##` heading. Supported keys: `status`, `effective`, `last updated`, `supersedes`, `superseded_by` and `replaces`. Supported statuses: Active, Approved and Superseded. Dates can be ISO, slash-separated, month-name or month/year.

A document with no usable date is treated as reference only. An unsupported status means not in effect, and an unreadable date is never treated as active. A Superseded document still applies for `--as-of` dates before its replacement's effective date; if the replacement has no date, it stays superseded. Put the authority rule under a heading containing `Precedence` so it is always included.

## How it works

- **Skill (`policy-answers`):** decides authority, conflicts and which alternative to name.
- **Script (`policy_context.py`):** parses metadata, works out each document's status, retrieves sections and extracts contacts, links and missing references.
- **Hook (`Stop`):** runs only after a policy script call in the current turn. It checks that the cited sections, contacts and links exist, and that an answer to a covered question has a citation. If the documents don't cover the question, the answer must say so and give a contact from the documents, even when it also cites a section. It does not check that the prose summarizes the section correctly.

## Limitations

- Retrieval is keyword-based, not semantic.
- A Stop hook can ask for a revision but cannot take back text already on screen.
- When you resume an old session without reloading the skill, you may need to approve the script again.
- PDF, DOCX, Slack and non-English retrieval are not supported.
- All bundled policies, organizations, contacts and scenarios are synthetic.
