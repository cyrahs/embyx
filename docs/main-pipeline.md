# Main pipeline overview

This repo's automation uses a combined monitor:
- `src/monitor.py` runs RSS + archive every 30 minutes, and runs a full STRM mapping rebuild once at startup then watches for `.strm` changes.

`src/main.py` still runs a single pass of RSS + archive + mapping for manual runs. Each component is a standalone module with its own config section in `src/core/config.py`.

## 1) RSS magnet ingestion (`src/rss.py`)

Purpose: pull unread RSS items, resolve magnet links, add offline tasks to CloudDrive, and refresh completed tasks.

Flow:
- Load items from FreshRSS label "Actor" by default; if `--rank` or `-r` is passed to `./.venv/bin/python run.py rss`, use label "Rank".
- Parse each item title into an AVID (unique ID for a JAV) with `src/utils/avid.get_avid`.
- Resolve a magnet per avid:
  - Async search on sukebei (largest trusted or size weighted).
  - If not found, parse magnet from RSS item HTML summary table.
  - If still not found, scrape javbus magnets and choose largest size.
  - If none found, leave one item unread and mark the rest as read.
- Batch magnets in groups of 20 and call `clouddrive.add_offline_file`.
  - Treat gRPC "task already exists" as duplicate and still mark items as read.
  - Retry HTTP operations via tenacity; log failures but continue.
- After any additions, sleep 10 seconds, then refresh CloudDrive state:
  - `clouddrive.get_sub_files(task_dir_path, force_refresh=True)`.
  - List finished offline files and refresh each one.
  - If all refreshes succeed, clear finished offline file records.

Key config inputs (see `src/core/config.py`):
- `config.freshrss` for FreshRSS URL, API key, and optional proxy.
- `config.clouddrive.task_dir_path` for where offline tasks are added and refreshed.
- `config.log_dir` for magnet logging.

Notes:
- `src/utils/magnet.py` writes chosen magnets to `magnets.log`.
- Failed AVIDs are put on a 24-hour cooldown in memory; restarting the monitor clears the cooldown.
- `src/rss.py` is callable directly for RSS-only runs (no CLI flags). Use `./.venv/bin/python run.py rss --rank` for rank runs.

## 2) Archive pipeline (`src/archive.py`)

Purpose: normalize file naming and move new videos from archive intake into final library layout.

Flow for each mapping in `config.archive.mapping`:
- Refresh CloudDrive task directory to see newly downloaded files.
- `clear_dirname`: if a folder name ends with a video suffix (like `.mp4`), rewrite the folder name to avoid suffix confusion.
- `flatten`: move valid video files from subfolders into the intake root (flat structure).
  - Skips folders when video filenames yield multiple different AVIDs (i.e., the AVIDs in the folder do not match each other).
  - Honors `config.archive.min_size` in MB.
  - Handles multi-part naming and 4k variants.
  - Removes folders that have no large videos but already exist in destination.
- `rename`: rename files to `AVID.ext` or `AVID-cdN.ext` for multi-part videos.
  - `remove_00` strips patterns like `ABC-00123` to `ABC-123`.
- `archive`: move each video into destination:
  - Destination path is based on `get_brand(avid)` and `config.archive.brand_mapping`.
  - Creates brand directory if missing; skips if target already exists.

Key config inputs:
- `config.archive.src_dir` and `config.archive.dst_dir`.
- `config.archive.mapping` for per subdirectory routing.
- `config.archive.min_size` and `config.archive.brand_mapping`.

## 3) STRM mapping rebuild (`src/mapping.py`)

Purpose: rebuild STRM mappings from a flat remote layout into a per title folder layout for local playback.

Design rationale (captured in code behavior):
- Remote storage keeps a flat structure to reduce CloudDrive access.
- Local storage adds a folder per STRM to avoid Emby misclassification.

Flow:
- `update`: copy each `.strm` from `src_dir` to `dst_dir` using:
  - Source: `xx/yy/zz.strm`
  - Destination: `xx/yy/zz/zz.strm` (extra directory named after avid).
  - Skip if destination is newer than source.
- `delete`: remove `.strm` files in destination that no longer exist in source.
- `delete_empty_dirs`: remove directories that no longer contain `.strm` files.

Key config inputs:
- `config.mapping.src_dir` and `config.mapping.dst_dir`.

## Entry points

- `src/monitor.py`: `rss.main()` + `archive.main()` every 30 minutes, and `mapping.main()` once at startup then on `.strm` changes.
- `src/main.py`: one-shot run in order (`rss.main()`, `archive.main()`, `mapping.main()`).
