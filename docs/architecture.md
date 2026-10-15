# Architecture

## Repository layout

Each directory under `plugins/` is a complete Claude Code plugin root. I kept the directory name, the manifest name and the marketplace entry identical so there is only one name to remember per plugin.

```text
.claude-plugin/marketplace.json
plugins/
  campaign-analysis/
  policy-assistant/
  deliverable-qa/
  segment-planner/
  core-dev/
examples/
docs/
```

Runtime code has no hard-coded dependency on `examples/`; the Quick start passes those files in as input. Each test suite uses only its own `tests/fixtures/` directory or temporary directories it creates.

## Four component types

Not every plugin needs all four:

1. **Skill (the model).** Chooses the workflow, interprets what the user wants, picks the relevant evidence and words the answer.
2. **Python script.** Does the deterministic work: parsing inputs, cleaning data, calculating metrics, applying configured rules and validating report evidence.
3. **Hook.** Runs one check at a specific lifecycle event. A `PreToolUse` hook runs before its matching tool call; a `Stop` hook runs when a response is about to end. A hook does not run "after the script" unless the event order actually works that way.
4. **MCP connector.** An optional integration the user configures. Only campaign analysis has instructions for one (Gmail), and no credentials or server configuration ship here.

Scripts are located with `${CLAUDE_SKILL_DIR}` from the skill, and hook scripts with `${CLAUDE_PLUGIN_ROOT}` from `hooks.json`. Both paths are quoted, so a plugin still works when it is installed under a path with spaces.

## What each plugin owns

### Campaign analysis

- **Skill (`campaign-performance`):** picks one of four report commands and presents the output.
- **Script (`campaign_report.py`):** CSV validation, cleaning, aggregation, thresholds, Markdown output and HTML rendering.
- **Hook (`confirm_send.py`, `PreToolUse`):** runs on Gmail send, reply and forward calls. It shows the recipient, subject and a preview and asks for confirmation. A send by draft ID is rejected, because the hook cannot preview that content.
- **Connector:** Gmail is optional. Creating a draft is the default; sending is a separate request.

### Policy assistant

- **Skill (`policy-answers`):** applies the authority and conflict rules to the retrieved sections.
- **Script (`policy_context.py`):** parses document metadata, works out each document's status on a date, retrieves sections and extracts contacts, links and missing references.
- **Hook (`verify_answer.py`, `Stop`):** after a policy script call in the current turn, it checks that every cited section, contact and link exists. It checks that references are real, not that the prose summarizes them correctly.

### Deliverable QA

- **Skill (`qa-check`):** maps the scanned evidence to rulebook rules and proposes fixes.
- **Script (`qa.py`):** parses the three-file rulebook, recomputes supported metrics, validates finding evidence, reads severity from the rules and determines the verdict.
- **Hook (`guard_drafts.py`, `PreToolUse`):** asks before a supported edit tool modifies a file under a directory named `drafts`.

### Segment planner

- **Skill (`plan-segments`):** reads the brief, determines the advertiser category, selects fitting eligible segments and explains why each one fits.
- **Script (`segments.py`):** applies the JSON policy config and computes impressions and reach.
- **No hook.** The workflow only reads and plans, and the script itself rejects unknown or excluded segment IDs.

### Core dev

- **Skill (`debug-workflow`):** a fixed debugging sequence.
- **Agent (`arch-reviewer`):** a read-only first-pass architecture review.
- **Hook (`conda-guard.py`):** asks before a recognized Python or pip command runs in conda `base` or in an unknown environment.
- **Hook (`env-guard.py`):** denies recognized writes to `.env` and `.env.*` files but allows common template names.

Core dev has no settings on purpose. You opt in by installing or enabling it and opt out by disabling or uninstalling it. Its checks are heuristics that stop accidental agent actions; they are not designed to stop someone bypassing them deliberately.

## Where data goes

Scripts and hooks run locally, and no plugin sends data to a service of its own. Claude Code itself still sends the conversation to the model, so file contents Claude reads, tool output (including script output) and prompts can be part of model requests under your Claude Code data-usage terms. An optional connector such as Gmail also sends data to that service when you use it. Only use these plugins with data you are allowed to process through Claude Code.

Moving the math into scripts removes most of the places where the model could get a number wrong, but the model still writes the surrounding prose. Hooks add targeted checks, not a proof of correctness, so review important decisions and anything that leaves your machine.
