# Client Deliverable Rules

Owner: Client Insights · Last updated: 2026-09-01

Every client deliverable is checked against these rules before it is sent.
- **Blocker**: the deliverable must not be sent until it is fixed.
- **Warning**: should be fixed; the analyst may send with a note.
- A deliverable is **ready to send** only when it has no blockers.

## R1. Client confidentiality (Blocker)
A deliverable may name only the client it is addressed to. The names and aliases of every other client in `clients.csv` (active or former) must not appear anywhere, including benchmark lines and footnotes.
Exception: another client may be named in a benchmark only if `clients.csv` shows `benchmark_consent = yes` for that client.
Benchmarks without consent must be described generically, for example "category benchmark".

## R2. Metric accuracy (Blocker)
Every derived metric (rates, costs, CPM, frequency, lift) must equal the value computed from the base numbers shown in the same deliverable, using the formulas in `metric-definitions.md`, after rounding to the precision shown.

## R3. Metric names (Warning)
Use the metric names in `metric-definitions.md`. Do not use other names for them (for example, "conversion rate" for tune-in rate).

## R4. Measurement period (Blocker)
The deliverable must state its measurement period with a start and an end date.

## R5. Methodology (Blocker)
The deliverable must include a "Methodology" section that names the data source and states the minimum reporting threshold (50 households).

## R6. Minimum reporting threshold (Blocker)
No segment, row, or cell may be reported if it is based on fewer than 50 households.

## R7. Number format (Warning)
Percentages are shown with one decimal place. Currency is shown with two decimal places.

## R8. Forward-looking claims (Warning)
Do not promise future results. Avoid "guarantee", "guaranteed", and "will increase".

## R9. Client name (Warning)
The client's name must match its `display_name` in `clients.csv` exactly (aliases are fine in body text, but the title must use the display name).

## R10. Draft markers (Blocker)
No "TODO", "TBD", "XX", or "[placeholder]" may remain.
