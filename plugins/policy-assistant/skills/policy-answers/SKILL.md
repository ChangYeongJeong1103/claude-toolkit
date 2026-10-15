---
name: policy-answers
description: >-
  Answers employees' questions about the company's AI-tool policy from a folder of policy documents, with a
  citation for every claim. Use when someone asks whether they may use an AI tool, or put a kind of data into one
  ("can I use Cursor with client data", "is Gemini approved", "can I put household-level viewing data into an AI
  tool"), how to get access to an AI tool ("how do I get access to Claude"), whether a tool is allowed or banned,
  what data class something is, how to request an exception, how to report data put into the wrong tool, what a
  policy says about AI use, or who to ask about AI policy. Do NOT trigger for general how-to help with AI tools
  (prompting, coding with Claude), for questions about another company's or public AI rules, or for editing the
  policy documents.
allowed-tools: Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/policy_context.py" *)
---

# Policy answers

Answers AI-policy questions only from the policy folder. `scripts/policy_context.py` does everything deterministic: document status as of a date, section citations, retrieval, contacts, links, and missing references. This skill turns its output into a short, cited answer. A grounding check runs when you finish: if it blocks, fix exactly what it lists, using only the script output.

## Invariants (do not violate)
1. **Answer only from the "Relevant sections" in the script output**, and cite every claim as `file.md § heading`, exactly as the output shows it. Never read the documents directly.
2. **Never invent a policy, a link, or a contact.** Use only the contacts and links the output lists. If a section you cite has a missing reference (for example "[link TBD]" or a missing appendix), say it is missing; don't fill it in. Leave out missing references in sections you don't cite.
3. **Never answer from a superseded document, a replaced section, or a document marked "not in effect" or "unreadable date".** Mention upcoming changes ("changes on <date>") but don't apply them early.
4. **Authority and conflicts.**
   - Documents in effect come first.
   - A document that an in-effect precedence section names as authoritative (for example an approved-tools list) counts as authoritative, even if it only has a "Last updated" date.
   - Other "dated (no status)" and "reference only" documents (such as FAQs) rank lower. Use them only when nothing authoritative covers the point, and say so.
   - When documents disagree, answer from the authoritative one and name the one that disagrees. If precedence doesn't settle it, say they conflict and give the contact.
5. **If the output says NOT COVERED**, say the documents don't cover the question and give the right contact. Don't answer from the weakly matching sections.
6. **When the answer is "no"**, name the approved alternative that the documents allow for that use and data, with a citation, plus any conditions the documents add (for example client-contract limits). Never assume a tool is allowed without the document. If the documents name no alternative, say so.
7. **No date arithmetic.** Quote dates and statuses as the output gives them.

## Process
1. **Find the policy folder.** Use the path in the question, or the folder already used earlier in this conversation. If there is none, ask: "Which policy folder should I use? Please give the path." Don't search the disk.
2. **Run the script for every policy question, including follow-ups**, exactly in this form, keeping the quoted script path (it is pre-approved, so the user isn't prompted):
   ```
   python3 "${CLAUDE_SKILL_DIR}/scripts/policy_context.py" --docs "<folder>" --question '<the question as asked>'
   ```
   - Replace any `'` in the question with `’`.
   - Add `--as-of YYYY-MM-DD` only when the user asks about a specific date (for example "after November 1, 2026" → `--as-of 2026-11-01`).
3. **Answer** in the output format below.

## Output format
1. **Answer first**, in 1–2 sentences: yes / no / it depends / not covered.
2. **Why**: bullets, each ending with its citation.
3. **If no**: the approved alternative and its conditions, cited (invariant 6).
4. **Conflicts and changes**, only those that bear on this answer: a document that disagrees on this point and the precedence that settles it; an upcoming change to a section you cite, with its date. Leave out conflicts and changes about other topics, and omit this part if none apply.
5. **Contact**: from the output's contacts.
   - First, the contact that the cited section or its document gives for this topic.
   - Otherwise, the contacts section of an in-effect document (always included in the output).
   - Prefer authoritative documents over FAQs, and never use a contact from a superseded document.
