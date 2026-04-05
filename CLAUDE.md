# AI Context

This directory provides context for AI assistants working on the kid-verbal project.

## Task & Bug Execution Rules

1. Before working on each task or bug, read `goal.md`, `architecture_summary.md`, and `current_state.md` for essential context
2. Do not implement until 0 ambiguity - if any ambiguity, stop for human guidance
3. After implementation is done, restart the website and prompt for local testing
4. Before pushing to remote GitHub, ALWAYS update context first:
   - Mark the task/bug file as `Done`
   - Update `current_state.md` with the change in Recent Changes
   - Include context updates in the same commit, then push

## Files

| File | Purpose |
|------|---------|
| `goal.md` | What the app is, who it's for, what it does and doesn't do |
| `architecture_summary.md` | Tech stack, project structure, database schema, key patterns |
| `coding_rules.md` | Conventions for backend, frontend, naming, git |
| `current_state.md` | What's built, what works, known issues, recent changes |
| `backlog.md` | Prioritized list of future work |
| `decisions.md` | Key architectural decisions with rationale |

## Directories

| Directory | Purpose |
|-----------|---------|
| `tasks/` | Active task specs (detailed requirements for in-progress work) |
| `bugs/` | Bug reports (detailed descriptions of issues to fix) |
| `summaries/` | Session summaries (what was done, what changed, what's next) |

## Usage

Refer to `coding_rules.md` before writing code. Check `backlog.md` for planned work.

After completing significant work, update `current_state.md` and optionally add a summary to `summaries/`.
