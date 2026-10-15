# Architecture

## Repository layout

Each directory under `plugins/` is a complete Claude Code plugin root. The manifest name, marketplace name, and directory name are identical.

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

Runtime code never depends on `examples/`. Each test suite uses only fixtures inside its plugin's `tests/fixtures/` directory or temporary directories created by the test.

## Responsibility boundaries

The toolkit uses four component types, but not every plugin needs all four:

1. **Skills and the model** handle judgment: choosing the workflow, interpreting user intent, selecting relevant evidence, and wording an answer.
2. **Python scripts** handle deterministic work where implemented: parsing inputs, cleaning data, calculating metrics, applying configured rules, and validating report evidence.
3. **Hooks** enforce a lifecycle-specific check. A `PreToolUse` hook runs before its matching tool call; a `Stop` hook runs as a response is stopping. A hook is not assumed to run after a script unless that ordering follows from the actual event flow.
4. **MCP connectors** are optional user-configured integrations. Only campaign analysis contains instructions for a Gmail connector, and no credentials or server configuration ship here.

The scripts use the Python standard library. `${CLAUDE_SKILL_DIR}` locates scripts and bundled skill configuration. `${CLAUDE_PLUGIN_ROOT}` locates hook scripts from `hooks.json`.

## Plugin boundaries

### Campaign analysis

- `campaign-performance` chooses one of four report commands and presents script output.
- `campaign_report.py` owns CSV validation, cleaning, aggregation, thresholds, Markdown output, and HTML rendering.
- The Gmail connector is optional. Creating a draft is the default workflow.
- `confirm_send.py` is a `PreToolUse` hook for matching Gmail send, reply, and forward calls. It asks for confirmation using the supplied fields and rejects a send by draft ID because it cannot preview that content.

### Policy assistant

- `policy-answers` applies authority and conflict-resolution instructions to retrieved sections.
- `policy_context.py` parses document metadata, evaluates status as of a date, retrieves sections, and extracts contacts, links, and missing references.
- `verify_answer.py` is a `Stop` hook. It checks citation, contact, and link existence after a policy script call in the current turn. It checks factual references, not whether the prose accurately summarizes a real section.

### Deliverable QA

- `qa-check` maps scanned evidence to the rulebook and proposes fixes.
- `qa.py` parses the three-file rulebook, recomputes supported metrics, validates finding evidence, reads severity from rules, and determines the verdict.
- `guard_drafts.py` is a `PreToolUse` hook for supported edit tools. It asks before those tools modify a path under a directory named `drafts`.

### Segment planner

- `plan-segments` reads the brief, determines the advertiser category, selects fitting eligible segments, and explains the fit.
- `segments.py` applies the JSON policy configuration and computes impressions and reach.
- No hook is needed for the current read-and-plan workflow. The script rejects unknown or excluded segment IDs.

### Core dev

- `debug-workflow` provides a fixed debugging sequence.
- `arch-reviewer` is a read-only first-pass architecture reviewer.
- `conda-guard.py` asks before recognized Python or pip commands run in conda `base` or when the environment is unknown.
- `env-guard.py` denies recognized writes to `.env` and `.env.*` files while allowing common template names.

Core dev is intentionally not configurable. Users opt in by installing or enabling the plugin and opt out by disabling or uninstalling it. Its conda and `.env` checks are heuristics designed to prevent accidental agent actions, not to resist deliberate bypasses.

## Data flow and trust boundary

Scripts and hooks run locally, and no plugin sends data to a service of its own. Claude Code itself still sends the conversation to the model: file contents Claude reads, tool output (including script output), and prompts can be included in model requests under the user's Claude Code data-usage terms. An optional connector such as Gmail additionally sends data to that service when the user invokes it. Use these plugins only with data you are permitted to process through Claude Code.

Script output narrows the model's calculation surface, but model-written prose remains probabilistic. Hooks add targeted checks, not a general proof of correctness. Consumers should review material decisions and outbound messages.
