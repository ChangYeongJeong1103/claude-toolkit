---
name: qa-check
description: >-
  QA-checks a Markdown client deliverable (a recap, campaign review, brand study, or other report draft) against
  the team's deliverable rulebook before it goes to a client. Every finding cites a rulebook rule and the exact
  draft line, numbers are recomputed from the metric definitions, blockers are separated from warnings, and the
  verdict says whether the draft is ready to send. Use when someone asks to QA-check, check, or review a draft
  deliverable against the rulebook, asks "is this draft ready to send", wants a draft's blockers and warnings,
  or wants its numbers checked against the metric definitions. Do NOT trigger for PowerPoint or PDF files, for
  sending or emailing a deliverable, for writing or editing a draft, for editing the rulebook, or for general
  proofreading that is not about the rulebook.
argument-hint: "<draft.md> [--rulebook DIR] [--client NAME]"
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/qa.py" *), Read
---

# Deliverable QA

Checks one Markdown draft against a rulebook folder (`deliverable-rules.md`, `metric-definitions.md`, `clients.csv`). `scripts/qa.py` does everything deterministic: rulebook parsing, client and alias matching, metric math and rounding, severity, the verdict, and citation checks. You judge which rule each piece of evidence breaks and word the fixes.

## Invariants (do not violate)
1. **Never change the draft.** Don't edit, write, or move it, even if asked in passing. Fixes are suggestions in the report; the analyst decides.
2. **Only rules in the rulebook.** Every finding cites a rule ID from `rules`, the draft line, and an exact quote from that line. No finding for anything the rulebook doesn't define (spelling, style, totals that no rule covers).
3. **Never judge a number by reading it.** Every derived metric is in `table_checks`, recomputed with `calc`, or noted as not verifiable from the draft.
4. **The answer is the `report` output.** Severity and the verdict come from it. Don't restate them differently or add findings outside it.

## Steps
Run every `qa.py` command with the script path exactly as written below (the absolute path, in double quotes). `allowed-tools` pre-approves only that quoted path, so don't drop the quotes, shorten it to a relative path, or wrap it in another command.

1. **Scope.** The draft must be a `.md` file. For PowerPoint or PDF, say it is out of scope and stop.
2. **Scan.** Run:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/qa.py" scan "<draft>" [--rulebook "<DIR>"] [--client "<NAME>"]`
   - The rulebook is found next to the drafts folder; pass `--rulebook` if the user names one.
   - On `"error"`, tell the user and stop. If `client` is null, ask the analyst which client the draft is for, then rerun with `--client`.
   - Pass the same `--rulebook` and `--client` to every later `qa.py` call.
3. **Read the draft** with Read, for its line numbers and wording.
4. **Recompute the other metrics.** `prose_metric_lines` lists sentences that name a derived metric. `table_unchecked` lists table columns the script couldn't match to formula inputs. For each value shown there, run:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/qa.py" calc "<draft>" --claims '<JSON>' [--rulebook "<DIR>"]`
   - Claims: `[{"line": <line of the value>, "metric": "<metric name or abbreviation>", "inputs": {"<formula variable>": <number shown in the draft, or a list of them to sum>}, "shown": "<value as shown>"}]`.
   - Use the row's line for table values, not the header line. Skip a line that names a metric without a value.
   - If a claim has `errors`, fix the claim; never invent an input. If the base numbers aren't in the draft, or `match` stays null, don't report it: add it to `--notes` as not verifiable from the draft.
5. **Decide the findings.** Go through `rules` in order and read each rule's text. Every evidence item ends as a finding or with a reason it isn't one (an allowed term, a consented benchmark, a defined precision). Map evidence only to a rule that covers it; if no rule covers it, there is no finding.
   - `table_checks` or `calc` with `match: false` → the rule on metric accuracy.
   - `metric_notes` belong to the metric definitions. A number that breaks one → the rule on metric accuracy.
   - `client_mentions` with `own_client: false` → the rule on naming other clients, unless that rule's exception applies (for example, `benchmark_consent: yes`). Mentions with `exact_case: false` may be ordinary words; judge them in context.
   - `small_rows` → the rule on the minimum reporting threshold.
   - `title.has_display_name: false` → the rule on the client's name, if there is one.
   - `rule_terms` are only evidence. Read the rule: some quoted terms are banned, others are allowed examples or required headings.
   - `number_formats` → the rule on number format. First match each value to a defined metric by its column or sentence. A defined metric is checked against its `decimals` in `metrics`; every other value follows the number-format rule. If the two disagree, say so once in `--notes`, not as a finding.
   - Rules with no scan evidence (for example, required sections or dates): compare the rule text with the draft.
6. **Report.** Run:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/qa.py" report "<draft>" --findings '<JSON>' [--notes '<JSON>'] [--rulebook "<DIR>"] [--client "<NAME>"]`
   - Findings: `[{"rule": "<rule ID>", "line": <line>, "quote": "<exact words from that line>", "issue": "...", "fix": "..."}]`.
   - The quote holds the words that break the rule, and it must include the flagged value or name. The issue gives the evidence, with computed values. The fix is a concrete suggestion.
   - Notes (a JSON list of strings) are only for rulebook conflicts and values that can't be verified from the draft. Never use them for issues no rule covers.
   - The JSON is single-quoted in the shell, so it must not contain an apostrophe anywhere. Quote the words next to it ("Acme", not "Acme's"), and write "does not" rather than "doesn't".
   - On `"errors"`, fix exactly what they list (a missing finding, a wrong quote or line, an unknown rule) and rerun.
7. **Answer** with the report exactly as printed.
