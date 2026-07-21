# embyx-monitor

Small Python automation project for media archive, mapping, RSS, and monitor workflows.

## Setup

```bash
uv sync --locked
```

## Run

```bash
./.venv/bin/python run.py rss
./.venv/bin/python run.py archive
./.venv/bin/python run.py mapping
./.venv/bin/python run.py monitor
```

## Checks

```bash
./.venv/bin/python -m pytest
./.venv/bin/python -m ruff check .
```
