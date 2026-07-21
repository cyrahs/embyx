# embyx-monitor

Python automation for media archiving, RSS ingestion, STRM mapping, and continuous monitoring.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync --locked
```

## Commands

```bash
./.venv/bin/python run.py rss
./.venv/bin/python run.py rss --rank
./.venv/bin/python run.py archive
./.venv/bin/python run.py mapping
./.venv/bin/python run.py monitor
./.venv/bin/python run.py fill_actor ACTOR_ID [ACTOR_ID ...]
./.venv/bin/python run.py merge SEARCH_DIR DST_DIR [-f FILTER]
```

For the combined RSS, archive, and mapping flow, see [the pipeline overview](docs/main-pipeline.md).

## Project layout

- `run.py` provides the command-line entry point.
- `src/` contains application modules and shared utilities.
- `src/embyx_monitor_runtime/` exposes the configuration-light integration API.
- `src/embyx_runtime/` preserves the legacy runtime import path.
- `scripts/` contains standalone maintenance utilities.
- `tests/` contains the pytest suite.

## Checks

```bash
./.venv/bin/python -m pytest
./.venv/bin/python -m ruff check .
```
