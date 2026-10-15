---
name: campaign-performance
description: >-
  Answers account-manager questions about campaign performance from a campaign_performance CSV export:
  how a campaign did last week, how streaming compares with live TV, and which campaigns are
  underperforming or wasting spend. Every number comes from a bundled script, never from the model.
  Use when the user asks things like "how did my campaign do last week", "how is <campaign> doing",
  "streaming vs live TV", "which campaigns are underperforming", "where are we wasting spend",
  "which rows were excluded", or asks about tune-in rate, cost per tune-in, or CPM in a campaign export.
  Also use when the user asks to email, send, or share such an answer ("email this to …",
  "send this to my manager"). Do NOT trigger for general marketing or media-buying advice, for editing
  or cleaning the CSV file itself, or for data that is not a campaign_performance export.
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/campaign_report.py" *) mcp__claude_ai_Gmail__create_draft
---

# Campaign performance

Answers the three weekly account-manager questions from a CSV export by running `scripts/campaign_report.py` and presenting its output. The script owns all cleaning, validation, and arithmetic; this skill picks the right command and keeps the answer short and faithful.

## Why this exists
Analysts spend 20–30 minutes on each of these questions every week. Account managers can now ask in plain English and get the same answer, with every number traceable to the export.

## Invariants (do not violate)
1. **Every number in the answer is copied from the script output.** Never calculate, round, convert, or estimate a number yourself, including differences and percentages. Counting items (for example, how many campaigns are flagged) is calculating too: name the items instead.
2. **Never read the CSV directly** (no Read, `cat`, `head`, or spreadsheet tools). Only the script reads it.
3. **If the script prints an `ERROR:` line or exits non-zero, show the error and stop.** Do not fall back to estimating.
4. **Below the headline, paste the script's output verbatim.** You may drop the `##` title line. Do not add, drop, reorder, or reword any other line.
5. **Do not explain causes or add interpretation the script output does not state.** For example, do not say why a number changed, or why a day has no data. The headline is at most two sentences.
6. **If no command answers the question as asked**, say which questions the script can answer and offer one. Examples: last month, a specific date, comparing two campaigns, a content-type breakdown. Never derive the answer from other output or from the CSV.

## Process
1. **Find the CSV.** Use the path the user gave. If there is none, ask: "Which CSV export should I use? Please give the file path." Do not search the disk.
2. **Pick the command.**

   | The user asks | Command |
   |---|---|
   | how a campaign did (last week) | `campaign --campaign "<id or name>"` |
   | streaming vs live TV | `platforms` |
   | underperforming campaigns or wasted spend | `underperformers` |
   | which rows were excluded, and why | `exclusions` |
   | email, send, or share an answer | see **Share by email** below |

   - `platforms` and `underperformers` cover last week by default. Add `--period all` only when the user asks about the whole file.
   - If the user says "my campaign" without naming it, ask which campaign.
3. **Run it, exactly in this form**, keeping the quoted script path (the form is pre-approved, so the user is not prompted):
   ```
   python3 "${CLAUDE_SKILL_DIR}/scripts/campaign_report.py" <command> --csv "<path>" [options]
   ```
4. **Answer** using the output format below.
   - If the script returns "No single campaign matches", show its list and ask the user to pick one.
   - If it says the campaign has no usable rows, show that and offer the exclusions list.

## Share by email
Drafting is safe; sending is not. Draft by default, and send only when the user explicitly asks.
1. **Recipient.** Use the address the user gave. If there is none, ask. Never guess, complete, or invent an address.
2. **Body.** Re-run the command that produced the answer, in the same form, with `--format html --question "<the user's question>"` added.
   - The email body is that HTML output, exactly.
   - Don't copy numbers or tables from the chat, and don't add your headline.
3. **Draft.** If a Gmail create-draft tool is available (for example `mcp__claude_ai_Gmail__create_draft`), create a draft:
   - `to` = the recipient
   - `subject` = `Campaign answer: <the question, shortened>`
   - `htmlBody` = the HTML output

   Then reply with the draft link and: "Say 'send it' to send it."
4. **Send only on an explicit request** ("send it", "send now").
   - Use the Gmail send tool with the same `to`, `subject`, and `htmlBody`. Never send by `draftId`; a confirmation hook blocks it.
   - The user then sees a confirmation with the recipient, subject, and preview. If they decline, say that nothing was sent.
   - After a confirmed send, delete the draft if a delete-draft tool is available.
5. **No Gmail tool.** Run the same command with `> "email-draft-<YYYYMMDD-HHMM>.html"` appended, so the file comes straight from the script. Then tell the user that Gmail isn't connected, and where the file is.

## Output format
1. A headline of at most two sentences, using only numbers and facts that appear in the script output (for example, which campaign is flagged, or which platform has the lower cost per tune-in). No explanations of causes (invariant 5).
2. The script's output, verbatim (invariant 4). This includes the data and period lines, tables, rule, difference and waste lines, notes, and the exclusion line.
3. If the exclusion line says rows were excluded from this answer, offer the row-level list (`exclusions`).
