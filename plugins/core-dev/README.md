# Core dev

## Problem

Development agents can accidentally run Python in an unintended conda environment, overwrite secret-bearing `.env` files, skip a disciplined bug trace, or review architecture without the project's documented boundaries. Core dev packages opt-in guardrails for those cases.

## Quick start

Requirements: Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the public marketplace:

```text
/plugin install core-dev --marketplace ChangYeongJeong1103/claude-toolkit
```

Start a new session or run `/reload-plugins`. The plugin is intentionally not configurable. Disable or uninstall it when its guard policy does not fit the current project:

```text
/plugin disable core-dev
/plugin uninstall core-dev
```

## Representative example

- A bug request loads `debug-workflow`, which follows Intent → Tiny Trace → Input/State/Control Flow/Output → Edge Cases → Minimal Fix + Guard.
- A recognized `python` or `pip` command in conda `base`, or with an unknown environment, triggers an `ask` decision.
- When enabled, core-dev also checks Python commands invoked by other plugins, such as the `python3` script calls in this marketplace's workflow skills. Requests for confirmation in conda `base` or an unknown environment are intentional.
- A recognized write to `.env` or `.env.local` triggers a `deny` decision, while `.env.example`, `.env.sample`, and `.env.template` are allowed.
- `core-dev:arch-reviewer` performs a read-only first-pass review against documented architecture.

## Configuration/input contract

There is no settings file. Environment detection uses explicit interpreter paths, `conda run`, activation or deactivation earlier in the same shell command, virtual-environment activation, and `CONDA_DEFAULT_ENV`, in that order where applicable.

The `.env` guard checks `Write` and `Edit` file paths plus recognized destinations for redirects and selected shell commands. Both guards parse shell words with quote and heredoc handling and emit `ask` on internal parsing errors.

## Architecture/verification boundary

`debug-workflow` is instructional model behavior. `arch-reviewer` is a read-only agent. The two `PreToolUse` command hooks are deterministic heuristics and run before matching tool calls; they do not inspect every possible way a process could modify a file or launch Python.

`${CLAUDE_PLUGIN_ROOT}` resolves all hook scripts. The test suite imports guard functions, executes subprocess hook contracts, injects failures, and runs every command exactly as declared in `hooks.json`.

## Limitations

- These hooks reduce accidental actions; they are not a security sandbox.
- Unrecognized command forms can bypass checks, including commands embedded inside quoted scripts or heredoc bodies.
- The conda guard recognizes Python and pip names, not every Python-related executable.
- The `.env` guard does not block deletion and does not inspect arbitrary code that writes an environment file.
- If the Python executable cannot start, a script has a syntax error, or a hook times out, Claude Code's own hook error behavior applies.
