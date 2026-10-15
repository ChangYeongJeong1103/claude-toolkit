# Synthetic examples

All files under `examples/` are synthetic demonstration inputs. Names, organizations, clients, policies, campaigns, and metrics are fictional and are not instructions for real operational decisions.

These paths exist only after cloning the repository. Installed plugins do not copy the root `examples/` directory into an arbitrary working project.

## Campaign analysis

Input: `campaign-analysis/campaign_performance.csv`

```text
How did Fall Thriller do last week? Use examples/campaign-analysis/campaign_performance.csv.
```

## Policy assistant

Input folder: `policy-assistant/policy-docs/`

```text
Can I use Cursor with client data? The policy folder is examples/policy-assistant/policy-docs.
```

The policy set intentionally includes superseded, future-dated, incomplete, and conflicting references to exercise the plugin's documented behavior.

## Deliverable QA

Inputs:

- `deliverable-qa/drafts/`
- `deliverable-qa/rulebook/`

```text
Is examples/deliverable-qa/drafts/kestrel-q3-recap.md ready to send? Use examples/deliverable-qa/rulebook.
```

The drafts intentionally contain issues and should not be treated as client-ready documents.

## Segment planner

Inputs:

- `segment-planner/briefs/`
- `segment-planner/catalog/`

```text
Recommend audience segments for examples/segment-planner/briefs/brightwell-allergy.md using examples/segment-planner/catalog.
```

The catalog and targeting policy are fictional and do not represent a real platform or regulatory policy.
