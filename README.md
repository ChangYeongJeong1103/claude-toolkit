# Claude Code Plugin Toolkit

Five focused Claude Code plugins for repeatable analysis, policy guidance, quality checks, audience planning, and developer guardrails.

This is an unofficial community project and is not affiliated with or endorsed by Anthropic. All company, client, policy, campaign, and audience data in the examples and test fixtures is synthetic.

## Motivation

This toolkit is an independent public reproduction of a recurring cross-functional engineering pattern: one team builds a useful analysis or workflow, other teams want to use it, and the original code must be adapted to their data, rules, and operating constraints before it is genuinely reusable.

The repository turns that support work into installable plugins with documented input contracts, configurable team-owned data, deterministic checks, targeted guardrails, and regression tests. It demonstrates how an AI engineer can help other teams adopt AI-assisted workflows rather than building one-off automation for a single user.

The design is informed by prior experience supporting engineering teams, but the implementation was created independently for this public repository. It contains no employer code, data, documents, or internal workflow definitions.

## Plugins

| Plugin | Category | What it does | Tests |
|---|---|---|---|
| [campaign-analysis](plugins/campaign-analysis) | Enterprise workflow | Answers weekly campaign-performance questions from a CSV export with script-computed metrics and optional Gmail drafting | 31 |
| [policy-assistant](plugins/policy-assistant) | Enterprise workflow | Answers AI-tool policy questions from Markdown policy documents with checked citations and contacts | 41 |
| [deliverable-qa](plugins/deliverable-qa) | Enterprise workflow | Checks a Markdown deliverable against a team rulebook, recomputes metrics, and returns a verdict | 44 |
| [segment-planner](plugins/segment-planner) | Enterprise workflow | Recommends eligible audience segments for a brief under a configurable targeting policy | 19 |
| [core-dev](plugins/core-dev) | Developer guardrail | Adds a debugging workflow, a read-only architecture reviewer, and conda and `.env` guard hooks | 27 |

### Enterprise workflows

#### Campaign analysis

Ask how a campaign performed last week, compare streaming with live TV, identify underperformers, or inspect excluded CSV rows. A bundled standard-library script performs the cleaning and calculations; the skill presents its output. An optional Gmail workflow drafts first and uses a confirmation hook before sending.

#### Policy assistant

Ask AI-tool policy questions against a local Markdown policy folder. A script determines document status, retrieves sections, and extracts citations and contacts. The skill writes the answer, and a Stop hook checks that cited sections, links, and contacts exist in the source documents.

#### Deliverable QA

Check a Markdown deliverable against a portable three-file rulebook. Deterministic code parses rules, recomputes defined metrics, validates evidence, assigns configured severity, and calculates the verdict. The skill maps evidence to rules, while a path-based hook asks before supported edit tools touch a `drafts/` folder.

#### Segment planner

Recommend eligible catalog segments for an advertiser brief. A configurable JSON policy drives exclusions, and a script computes impressions and reach without summing potentially overlapping audiences. Missing budgets or flight dates are requested instead of assumed.

### Developer guardrails

#### Core dev

Opt-in guardrails for development sessions: a structured debugging skill, a read-only architecture reviewer, a conda environment check, and protection against accidental `.env` writes. The hooks are heuristic safeguards for mistakes, not a security boundary.

When enabled, core-dev also checks Python commands invoked by other plugins, including the workflow skills' script calls. Requests for confirmation in conda `base` or an unknown environment are intentional.

## Quick start

Claude Code 2.1.275 or later can install directly from this marketplace:

```text
/plugin install campaign-analysis --marketplace ChangYeongJeong1103/claude-toolkit
/plugin install policy-assistant --marketplace ChangYeongJeong1103/claude-toolkit
/plugin install deliverable-qa --marketplace ChangYeongJeong1103/claude-toolkit
/plugin install segment-planner --marketplace ChangYeongJeong1103/claude-toolkit
/plugin install core-dev --marketplace ChangYeongJeong1103/claude-toolkit
```

Alternatively, add the marketplace once and install plugins by name:

```text
/plugin marketplace add ChangYeongJeong1103/claude-toolkit
/plugin install campaign-analysis@claude-toolkit
```

Install only the plugins you need. After installation, start a new Claude Code session or run `/reload-plugins`.

The human demo inputs under `examples/` are repository files, so clone the repository before using those paths:

```shell
git clone https://github.com/ChangYeongJeong1103/claude-toolkit.git
cd claude-toolkit
claude
```

Then try:

```text
How did Fall Thriller do last week? Use examples/campaign-analysis/campaign_performance.csv.
Can I use Cursor with client data? The policies are in examples/policy-assistant/policy-docs.
Is examples/deliverable-qa/drafts/kestrel-q3-recap.md ready to send?
Recommend segments for examples/segment-planner/briefs/brightwell-allergy.md using examples/segment-planner/catalog.
```

## How responsibilities are separated

- **Model + skill judgment:** select the applicable workflow, interpret a question or brief, map evidence to rules, and explain results.
- **Deterministic scripts:** perform reproducible parsing, calculations, date/status handling, and rule checks where a plugin implements them.
- **Lifecycle-specific hooks:** run at their configured Claude Code event, such as before a supported tool call or when a response is stopping. Hooks do not form a universal sequence after scripts.
- **Optional MCP connectors:** provide external capabilities only where configured by the user. Campaign email drafting can use a Gmail connector; the repository does not bundle credentials or an MCP server.

See [architecture](docs/architecture.md) for component boundaries and [validation](docs/validation.md) for the evidence and limitations behind the release.

## Development

The runtime code uses the Python standard library and is compatible with the repository's tested Python versions. Run every suite from the repository root:

```shell
for plugin in campaign-analysis policy-assistant deliverable-qa segment-planner core-dev; do
  python3 -B -m unittest discover -s "plugins/$plugin/tests"
done
```

Release validation uses Claude Code 2.1.296:

```shell
claude plugin validate --strict .
for plugin in campaign-analysis policy-assistant deliverable-qa segment-planner core-dev; do
  claude plugin validate --strict "plugins/$plugin"
done
```

Tests use fixtures under each plugin's `tests/fixtures/`; they do not depend on `examples/`.

## License

MIT © 2026 ChangYeong Jeong. See [LICENSE](LICENSE).
