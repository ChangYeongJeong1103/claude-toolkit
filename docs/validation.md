# Validation evidence

## Confirmed baseline

The public snapshot preserves five standard-library `unittest` suites and their assertions:

- campaign-analysis: 31 tests
- policy-assistant: 41 tests
- deliverable-qa: 44 tests
- segment-planner: 19 tests
- core-dev: 27 tests
- total: 162 tests

All five plugin manifests and the marketplace passed `claude plugin validate --strict` with Claude Code 2.1.296 before this release was prepared. The release workflow reruns the same checks.

## What the suites check

### Campaign analysis

The suite covers CSV normalization and exclusions, duplicate handling, complete-week selection, campaign lookup, campaign and platform metrics, underperformer thresholds, potential waste, Markdown/HTML numeric parity, and the Gmail send-confirmation hook.

### Policy assistant

The suite covers metadata and date parsing, document status, supersession and section replacement, section retrieval, coverage, contacts and links, missing references, citation validation, current-turn hook scoping, relative paths, fail-open hook errors, and multilingual punctuation around otherwise valid references.

### Deliverable QA

The suite covers the rulebook contract, all bundled draft fixtures, formulas and rounding, prose claims, evidence validation, severity and verdict calculation, alternate-team portability, CLI error output, fixture integrity, and the draft-edit confirmation hook.

### Segment planner

The suite covers all five supported policy rule kinds, expiration boundaries, unknown and excluded segment refusals, configurable policy thresholds, delivery calculations, household caps, combined-reach ranges, and CLI errors.

### Core dev

The suite covers shell tokenization, wrappers and activation commands, conda environment inference, `.env` path detection, supported shell writes, subprocess hook contracts, fail-safe `ask` behavior, and execution of the declared `${CLAUDE_PLUGIN_ROOT}` hook commands without bytecode output.

## Review findings converted to regression coverage

Selected examples from reviews during development:

- **Campaign analysis:** fixed non-finite values contaminating totals, decimal commas being misread as thousands separators, an exact 1.5× threshold missed by floating-point error, and partial campaign names matching the wrong campaign. Regression tests preserve each fix.
- **Policy assistant:** fixed truncated contacts passing substring checks, citations with real section numbers but invented titles, unsupported statuses falling through as active, and correct references followed by Korean particles being falsely rejected. The legitimate Korean regression cases remain in the suite.
- **Deliverable QA:** fixed a warning on the same line hiding unreported blocker evidence, added summed inputs for a prose metric, handled lowercase aliases and BOM-prefixed client files, and converted malformed formulas and findings into structured errors.
- **Segment planner:** public-release review found that non-positive budgets, caps, household counts, and CPMs could reach the delivery math, while malformed numeric cells could raise an unstructured error. Input validation and regression tests now reject those cases before planning.
- **Core dev:** tests exercise both recognized behavior and explicit fail-safe paths. The release changes documentation and path layout, not guard logic.

## Fresh-session evidence

During development, these behavioral checks were run before the plugins were packaged for this public repository. Public packaging later changed the directory layout, documentation, and the quoting of skill script paths, so these results describe the pre-packaging plugins:

- Campaign analysis triggered for its three supported question families in fresh sessions, used script output without permission denials in the reproduced user environment, and passed a later fresh-session formatting recheck. The optional Gmail flow created a draft, showed the send hook's confirmation, and sent only after user approval. The no-Gmail fallback and declined-send path were not exercised end to end.
- Policy assistant ran six fresh headless sessions during its primary check: five policy scenarios plus one unrelated prompt. A later single-process session exercised five practical follow-up questions and reran the script for each. Citation, contact, and link checks matched the documents after the recorded regression fixes.
- Deliverable QA ran its three demo questions in a fresh interactive plugin session. All three used scan, calculation, and report commands and matched the hand-computed findings. The three questions shared that session, so only the first loaded the skill text from a new conversation.
- Segment planner ran three headless demos in separate fresh sessions and was also checked interactively. The first two produced plans matching the script and tests; the third asked for the missing budget and dates without suggesting segments.
- Core dev is covered by unit and subprocess hook tests; no comparable multi-question demo suite was run during development.

After the path-quoting change, a headless segment-planner session with Claude Code 2.1.296, run from a checkout path containing spaces, loaded the skill and ran `check` and `plan` through the skill's quoted, pre-approved script command with no permission denials. The other three workflow skills use the same quoted command form.

Model-generated wording is stochastic. Demos check invariants, cited evidence, script values, verdicts, and lifecycle decisions rather than exact prose.

## Release commands

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

- The test fixtures and examples are synthetic; they are useful demonstrations, not production policy or business guidance.
- Model judgment can still misclassify meaning even when deterministic references and arithmetic are correct.
- Policy coverage is keyword-based, and its Stop hook checks reference existence rather than semantic entailment.
- Deliverable QA supports Markdown and its documented rulebook/formula subset. Its draft guard does not cover shell-based edits.
- Segment planning supports five policy rule kinds, an even budget split, and a reach range rather than household-level deduplication. Validation covers required columns and core numeric/date fields but is not a general CSV schema system.
- Campaign analysis supports its documented periods and questions, not arbitrary exploratory analysis.
- Core dev hooks are opt-in heuristics and can miss unrecognized command forms.
