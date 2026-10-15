# Core dev

## What it does

A coding agent can run Python in the wrong conda environment, overwrite a `.env` file full of secrets, jump to a fix without tracing the bug, or review architecture without looking at the project's documented boundaries. Core dev adds opt-in guardrails for those four cases.

## Quick start

You need Claude Code 2.1.275 or later and `python3` on `PATH`. Install from the marketplace:

```text
/plugin install core-dev --marketplace ChangYeongJeong1103/claude-toolkit
```

Start a new session or run `/reload-plugins`. There are no settings on purpose. If the guards don't fit a project, disable or uninstall the plugin:

```text
/plugin disable core-dev
/plugin uninstall core-dev
```

## Example

- **Debugging.** A bug report loads `debug-workflow`, which goes Intent → Tiny Trace → Input/State/Control Flow/Output → Edge Cases → Minimal Fix + Guard.
- **Conda.** A recognized `python` or `pip` command in conda `base`, or in an environment it can't identify, gets an `ask` decision.
- **Other plugins.** Core dev also checks Python commands started by other plugins, including the `python3` script calls in this marketplace's workflow skills. A confirmation prompt in conda `base` or an unknown environment is expected.
- **`.env` files.** A recognized write to `.env` or `.env.local` gets a `deny` decision; `.env.example`, `.env.sample` and `.env.template` are allowed.
- **Architecture review.** `core-dev:arch-reviewer` does a read-only first-pass review against the documented architecture.

## How the guards decide

The conda guard looks for the environment in this order, where it applies: an explicit interpreter path, `conda run`, an activate or deactivate earlier in the same shell command, a virtual-environment activation, and finally `CONDA_DEFAULT_ENV`.

The `.env` guard checks the file paths of `Write` and `Edit` calls plus the destinations of redirects and selected shell commands. Both guards split shell commands with quote and heredoc handling, and if a guard hits an internal error it returns `ask` rather than letting the command through.

## How it works

- **Skill (`debug-workflow`):** instructions for the model, not code.
- **Agent (`arch-reviewer`):** read-only.
- **Hooks (`PreToolUse`):** two deterministic heuristics that run before matching tool calls. They don't try to catch every way a process could change a file or start Python.

All hook scripts are found through `${CLAUDE_PLUGIN_ROOT}`. The tests import the guard functions, run the hooks as real subprocesses, inject failures and run every command exactly as written in `hooks.json`.

## Limitations

- The hooks reduce accidents. They are not a security sandbox.
- Command forms the guards don't recognize can slip through, including commands inside quoted scripts or heredoc bodies.
- The conda guard recognizes Python and pip names, not every Python-related executable.
- The `.env` guard does not block deletion and does not inspect arbitrary code that writes an environment file.
- If Python can't start, a script has a syntax error or a hook times out, Claude Code's own hook error handling applies.
