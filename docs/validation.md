# Validation

## Tests and strict validation

Each plugin has its own standard-library `unittest` suite:

| Plugin | Tests |
|---|---:|
| campaign-analysis | 31 |
| policy-assistant | 46 |
| deliverable-qa | 44 |
| segment-planner | 19 |
| core-dev | 27 |
| **Total** | **167** |

The marketplace and all five plugins pass `claude plugin validate --strict` with Claude Code 2.1.296. CI reruns the tests on Python 3.10 to 3.13 and the strict validation on every push.

## What the suites cover

- **Campaign analysis:** CSV normalization and exclusions, duplicate handling, complete-week selection, campaign lookup, campaign and platform metrics, underperformer thresholds, potential waste, the same numbers in Markdown and HTML output, and the Gmail send-confirmation hook.
- **Policy assistant:** metadata and date parsing, document status, supersession and section replacement, section retrieval, coverage, contacts and links, missing references, citation validation, limiting the hook to the current turn, relative paths, hook errors that fail open, and Korean text right after an otherwise valid reference.
- **Deliverable QA:** the rulebook format, every bundled draft fixture, formulas and rounding, prose claims, evidence validation, severity and verdict, a second team's rulebook, CLI error output, fixture integrity and the draft-edit confirmation hook.
- **Segment planner:** all five policy rule kinds, expiration boundaries, refusing unknown and excluded segments, configurable thresholds, delivery math, household caps, combined-reach ranges and CLI errors.
- **Core dev:** shell tokenization, wrappers and activation commands, conda environment inference, `.env` path detection, shell writes, the hook contract over a real subprocess, `ask` when a guard itself fails, and running every `${CLAUDE_PLUGIN_ROOT}` command exactly as declared in `hooks.json`.

## Bugs that became regression tests

Some examples from reviews during development, each now covered by a test:

- **Campaign analysis:** `nan`/`inf` values poisoned totals; decimal commas (`200,50`) were read as thousands separators; an exact 1.5× threshold was missed by floating-point error; a partial campaign name matched the wrong campaign.
- **Policy assistant:** a truncated contact passed a substring check; citations with real section numbers but invented titles passed; unsupported statuses were treated as active; a correct link followed directly by a Korean particle was rejected. After the first public release (fixed in 0.1.1): a document marked Superseded showed as superseded even for dates before its replacement took effect, and any real citation let an answer to an uncovered question skip the "say so and give a contact" check.
- **Deliverable QA:** a warning on the same line hid a blocker that was never reported; a prose metric needed summed inputs; lowercase aliases and BOM-prefixed client files failed; malformed formulas and findings crashed instead of returning structured errors.
- **Segment planner:** before release, I found that non-positive budgets, caps, household counts and CPMs could reach the delivery math, and a malformed number in the catalog raised an unstructured error. Input validation now rejects them before planning.
- **Core dev:** the tests cover both the recognized commands and the fail-safe paths. Public packaging changed documentation and paths, not guard logic, and 0.1.1 only rewrote the guard messages in English.

## Live sessions

### During development

These sessions ran before the plugins were packaged for this repository. Packaging later changed the directory layout, the documentation and the quoting of skill script paths, so the results describe the pre-packaging plugins.

- **Campaign analysis:** triggered for all three question families in fresh sessions and used the script without permission denials; a later fresh session rechecked the formatting. The Gmail flow created a draft, showed the send hook's confirmation and sent only after approval. The no-Gmail fallback and a declined send were not tested end to end.
- **Policy assistant:** six fresh headless sessions (five policy scenarios and one unrelated prompt), then five follow-up questions in one session with the script rerun each time. After the regression fixes, every citation, contact and link matched the documents.
- **Deliverable QA:** all three demo questions in one fresh interactive session. All three used `scan`, `calc` and `report` and matched the hand-computed findings. Only the first question loaded the skill in a new conversation.
- **Segment planner:** three headless demos in separate fresh sessions plus an interactive check. The first two plans matched the script and tests; the third asked for the missing budget and dates without suggesting segments.
- **Core dev:** covered by unit and subprocess tests only; no comparable multi-question demo was run.

### Public release check

On 2026-10-14 I checked the published repository at commit `bd768d4` with Claude Code 2.1.296. This was before the two policy-assistant fixes in 0.1.1, so the policy demo below ran on the earlier status and hook logic.

- **Install from GitHub.** In an empty Claude Code config, `claude plugin install campaign-analysis --marketplace ChangYeongJeong1103/claude-toolkit` cloned the repository and added the marketplace, and `claude plugin install <name>@claude-toolkit` installed the other four. All five were enabled at version 0.1.0.
- **Path with spaces.** Before publishing, a headless segment-planner session run from a checkout path containing spaces ran `check` and `plan` through the skill's quoted, pre-approved script command with no permission denials.
- **One demo per workflow plugin,** each in a fresh headless session using the GitHub-installed copy, with only the `Skill` tool pre-approved:

| Plugin | Prompt | What I checked | Result |
|---|---|---|---|
| campaign-analysis | How did Fall Thriller do last week? | Script ran without a permission prompt; numbers in the answer are the script's | Pass |
| policy-assistant | Can I use Cursor with client data? | Script ran; answer is "no", cites the in-effect documents, names the approved alternative and flags the conflicting FAQ | Pass |
| deliverable-qa | Is kestrel-q3-recap.md ready to send? | `scan`, `calc` and `report` ran; verdict NOT READY TO SEND with 3 blockers and 1 warning | Pass |
| segment-planner | Recommend segments for lumen-playoffs.md | `check` and `plan` ran; only eligible segments, delivery table from the script | Pass |

- **Core dev alongside another plugin.** With core-dev enabled and conda `base` active, the conda guard stopped the segment-planner script before it ran, and the model asked which environment to use instead of working around it. This is the intended behavior.

Model wording changes from run to run, so I compare numbers, verdicts, citations, allowed segments and hook decisions rather than exact text. I did not resend real Gmail messages for this check.

## Running the checks

From the repository root:

```shell
for plugin in campaign-analysis policy-assistant deliverable-qa segment-planner core-dev; do
  python3 -B -m unittest discover -s "plugins/$plugin/tests"
done

claude plugin validate --strict .
for plugin in campaign-analysis policy-assistant deliverable-qa segment-planner core-dev; do
  claude plugin validate --strict "plugins/$plugin"
done
```

## Limitations

- The fixtures and examples are synthetic. They are good demonstrations, not real policy or business guidance.
- The model can still misread meaning even when the references and arithmetic are correct.
- Policy retrieval is keyword-based, and its Stop hook checks that references exist, not that the answer follows from them.
- Deliverable QA supports Markdown and the documented rulebook and formula subset. Its draft guard does not cover edits made through the shell.
- Segment planning supports five rule kinds, an even budget split and a reach range rather than household-level deduplication. Validation covers the required columns and the core number and date fields, but it is not a general CSV schema system.
- Campaign analysis answers its documented periods and questions, not arbitrary exploratory analysis.
- Core dev hooks are opt-in heuristics and can miss command forms they do not recognize.
