# Claude Code Plugin Toolkit

[![Test](https://github.com/ChangYeongJeong1103/claude-toolkit/actions/workflows/test.yml/badge.svg)](https://github.com/ChangYeongJeong1103/claude-toolkit/actions/workflows/test.yml)

Five Claude Code plugins for recurring team workflows: campaign reporting, AI-policy questions, deliverable QA, audience planning and developer guardrails.

This is an unofficial project, not affiliated with Anthropic. The companies, clients and campaigns in the examples and tests are fictional.

## Why I built this

Part of my work as an AI engineer has been supporting other engineering teams. I would build an analysis or workflow for my own team, another team would want to use it, and I would adapt the code to their data, rules and constraints so they could run it themselves instead of coming back to me every time.

This repository is a public reproduction of that support work. I wrote the workflows from scratch and made up all the data, policy documents and drafts in the examples and tests. I packaged each workflow as an installable plugin with a documented input format, configuration the receiving team owns, deterministic checks, guardrails and regression tests.

## Plugins

| Plugin | Category | What it does | Tests |
|---|---|---|---:|
| [campaign-analysis](plugins/campaign-analysis) | Enterprise workflow | Answers weekly campaign-performance questions from a CSV export, with script-computed metrics and optional Gmail drafting | 31 |
| [policy-assistant](plugins/policy-assistant) | Enterprise workflow | Answers AI-tool policy questions from Markdown policy documents, with checked citations and contacts | 46 |
| [deliverable-qa](plugins/deliverable-qa) | Enterprise workflow | Checks a Markdown deliverable against a team rulebook, recomputes its metrics and returns a verdict | 44 |
| [segment-planner](plugins/segment-planner) | Enterprise workflow | Recommends eligible audience segments for a brief under a configurable targeting policy | 19 |
| [core-dev](plugins/core-dev) | Developer guardrail | Adds a debugging workflow, a read-only architecture reviewer, and conda and `.env` guard hooks | 27 |

Every plugin uses the same split:

- **The skill (the model) handles judgment:** which workflow applies, what the question or brief means, which rule a piece of evidence breaks, and how to word the answer.
- **A Python script handles everything that must be reproducible:** parsing, cleaning, arithmetic, dates and rule checks. The model copies the script's numbers instead of computing its own.
- **A hook adds one check at a specific point in the Claude Code lifecycle,** for example before a Gmail send or before a policy answer ends the turn. Hooks are not a general step that runs after every script.
- **MCP connectors are optional.** Only campaign analysis uses one (Gmail), and no credentials or servers ship with this repository.

[docs/architecture.md](docs/architecture.md) describes the components of each plugin, and [docs/validation.md](docs/validation.md) lists what was tested and what is still a limitation.

### Enterprise workflows

#### Campaign analysis

Answers the three questions account managers ask every week: how a campaign did last week, how streaming compares with live TV, and which campaigns are underperforming or wasting spend. You can also ask which CSV rows were excluded and why. A standard-library script does all of the cleaning and math; the skill only picks the command and presents the output. Sharing by email creates a Gmail draft first, and a hook asks for confirmation before anything is sent.

#### Policy assistant

Answers AI-tool policy questions such as "Can I use Cursor with client data?" from a folder of Markdown policy documents. A script works out which documents are in effect on the date in question, pulls the relevant sections and extracts citations and contacts. The skill writes the answer, and a Stop hook checks that every cited section, link and contact really exists in the documents.

#### Deliverable QA

Checks a Markdown client deliverable against a three-file team rulebook before it goes out. The script parses the rules, recomputes every defined metric, validates the evidence behind each finding, applies the configured severity and calculates the verdict. The skill decides which rule each piece of evidence breaks, and a hook asks before an edit tool touches anything under a `drafts/` folder.

#### Segment planner

Recommends catalog audience segments for an advertiser brief. A JSON policy config drives the exclusions, and the script computes impressions and reach without adding up audiences that may overlap. If the brief has no budget or exact flight dates, the skill asks for them instead of guessing.

### Developer guardrails

#### Core dev

Opt-in guardrails for development sessions: a structured debugging skill, a read-only architecture reviewer, a conda environment check and a block on accidental `.env` writes. The hooks are there to catch mistakes, not to act as a security boundary.

Once enabled, core-dev also checks the `python3` calls made by the other plugins, so a confirmation prompt in conda `base` or an unknown environment is expected.

## Quick start

Claude Code 2.1.275 or later can install straight from this marketplace:

```text
/plugin install campaign-analysis --marketplace ChangYeongJeong1103/claude-toolkit
/plugin install policy-assistant --marketplace ChangYeongJeong1103/claude-toolkit
/plugin install deliverable-qa --marketplace ChangYeongJeong1103/claude-toolkit
/plugin install segment-planner --marketplace ChangYeongJeong1103/claude-toolkit
/plugin install core-dev --marketplace ChangYeongJeong1103/claude-toolkit
```

Or add the marketplace once and install plugins by name:

```text
/plugin marketplace add ChangYeongJeong1103/claude-toolkit
/plugin install campaign-analysis@claude-toolkit
```

Install only the plugins you need, then start a new Claude Code session or run `/reload-plugins`.

The demo inputs live in `examples/`, which is not copied by the plugin install, so clone the repository to try them:

```shell
git clone https://github.com/ChangYeongJeong1103/claude-toolkit.git
cd claude-toolkit
claude
```

Then ask:

```text
How did Fall Thriller do last week? Use examples/campaign-analysis/campaign_performance.csv.
Can I use Cursor with client data? The policies are in examples/policy-assistant/policy-docs.
Is examples/deliverable-qa/drafts/kestrel-q3-recap.md ready to send?
Recommend segments for examples/segment-planner/briefs/brightwell-allergy.md using examples/segment-planner/catalog.
```

## Development

All runtime code uses only the Python standard library. To run every test suite from the repository root:

```shell
for plugin in campaign-analysis policy-assistant deliverable-qa segment-planner core-dev; do
  python3 -B -m unittest discover -s "plugins/$plugin/tests"
done
```

To validate the marketplace and every plugin (I use Claude Code 2.1.296):

```shell
claude plugin validate --strict .
for plugin in campaign-analysis policy-assistant deliverable-qa segment-planner core-dev; do
  claude plugin validate --strict "plugins/$plugin"
done
```

The tests only use fixtures under each plugin's `tests/fixtures/`, never `examples/`. CI runs the tests on Python 3.10 to 3.13 and the strict validation in a separate job.

## License

MIT © 2026 ChangYeong Jeong. See [LICENSE](LICENSE).
