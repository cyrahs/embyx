# embyx — Agent Guide (AGENTS.md)

This repo is a small Python project using a `pyproject.toml` + `uv.lock` workflow and a `src/` + `tests/` layout. Treat it as a “keep things stable” codebase: make focused changes, avoid drive‑by refactors, and keep the developer experience predictable.

## Hard rules (non‑negotiable)

1. **DO NOT open, read, print, or modify `config.toml` or `.env`.**
   - Assume these may contain secrets or user-specific configuration.
   - Don’t mention their contents in PRs, issues, logs, or output.
   - If you need configuration, add/consult a *safe* template file (e.g., `.env.example`) **only if asked**—otherwise, proceed without touching secrets.

2. **Use the repo virtual environment Python: `./.venv/bin/python`.**
   - All Python commands should be run via `./.venv/bin/python ...`
   - Do not rely on `python`, `python3`, or a global interpreter in docs/commands you add.

3. **Keep changes minimal and intentional.**
   - Avoid formatting the whole repo.
   - Don’t rename files or reorganize directories unless the task explicitly requires it.

4. **Write code comments and docs in English.**
   - All new or updated comments in code must be in English.
   - All new or updated content in `docs/` must be in English.

## Repo map (high-level)

- `src/` — main library / application code (src-layout).
- `tests/` — test suite.
- `run.py` — likely a simple entrypoint to run the app locally.
- `pyproject.toml` — dependencies, tooling config, packaging metadata.
- `uv.lock` — locked dependency graph for reproducible installs.
- `.github/workflows/` — CI definitions (mirror CI commands locally when possible).
- `Dockerfile` — container build (optional path for running/packaging).

## Environment setup (expected workflow)

This project uses `uv` for dependency management.

### Create / sync the virtual environment

Preferred (uses the lockfile, avoids surprise dependency drift):

```bash
uv sync --locked
```

That should create/update `./.venv/` and install dependencies.

> If you intentionally changed dependencies in `pyproject.toml`, it may be appropriate to update `uv.lock` using `uv lock` or `uv sync` without `--locked` **as part of that same change**. Otherwise, do not churn the lockfile.

### Sanity check interpreter

```bash
./.venv/bin/python --version
```

(If there is a `.python-version` file, prefer that Python version locally.)

## Running the project

Start with the simplest entrypoint:

```bash
./.venv/bin/python run.py
```

If `run.py` is not the correct entrypoint, inspect `README.md` and `pyproject.toml` for documented scripts/entrypoints and follow those.

## Tests

There is a `tests/` directory. Prefer running tests via the venv Python:

Most likely (pytest-style):

```bash
./.venv/bin/python -m pytest
```

If pytest isn’t configured, use the CI workflow in `.github/workflows/` as the source of truth for the exact test command. Mirror CI locally whenever possible.

## Lint / format (only if configured)

Tooling varies by repo. Use `pyproject.toml` as the single source of truth for:

* formatting (ruff/black/etc.)
* linting (ruff/flake8/etc.)
* typing (mypy/pyright/etc.)

Run tools via the venv Python, e.g.:

```bash
./.venv/bin/python -m ruff check .
./.venv/bin/python -m ruff format .
./.venv/bin/python -m mypy src
```

Only run what’s actually configured/used by the repo (don’t introduce new tooling in a drive-by change).

## Making changes safely

### Before you change code

* Identify the minimal files needed (usually in `src/` and matching tests in `tests/`).
* Search for existing patterns and follow them.
* Prefer small commits that are easy to review.

### Dependency changes

If you must add/change dependencies:

* Update `pyproject.toml` using `uv add ...` (preferred).
* Update `uv.lock` in the same PR.
* Keep dependency diffs small and justified.

### Secrets / config hygiene

* Never add real tokens/URLs/passwords to the repo.
* Never log environment variables or config values.
* Again: **do not access `config.toml` or `.env`**.

## PR checklist (what “done” looks like)

* [ ] Change is minimal and directly addresses the task.
* [ ] Tests pass (or there is a clear reason they can’t run).
* [ ] No accidental lockfile churn (unless dependencies were intentionally changed).
* [ ] No secrets/config files were accessed or modified (`config.toml`, `.env`).
* [ ] Commands in docs use `./.venv/bin/python` (not `python` / `python3`).

## When unsure

* Use `pyproject.toml` + `.github/workflows/` to determine canonical commands.
* Prefer matching existing conventions over introducing new ones.
* If a task requires configuration: **stop and ask for a safe template approach** (but still do not open `config.toml` or `.env`).
