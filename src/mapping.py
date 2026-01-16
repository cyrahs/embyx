import shutil
from pathlib import Path

from pydantic import BaseModel

from src.core import config, logger
from src.utils import get_avid

log = logger.get('mapping')
cfg = config.mapping


class Counter(BaseModel):
    files_processed: int = 0
    files_updated: int = 0
    files_skipped: int = 0
    files_deleted: int = 0
    dirs_deleted: int = 0


counter = Counter()


def reset_counter() -> None:
    global counter
    counter = Counter()


def update(src_dir: Path, dst_dir: Path) -> None:
    """
    Map .strm files from src_dir with structure xx/yy/zz.strm
    to dst_dir with structure xx/yy/zz/zz.strm
    """
    for src in src_dir.glob('**/*.strm'):
        # Get relative path from source directory
        rel_path = src.relative_to(src_dir)
        avid = get_avid(src.name)
        if not avid:
            log.warning('failed to get avid for %s, skipping', src.relative_to(src_dir))
            continue
        # Create new path with structure xx/yy/zz/zz.strm
        dst = dst_dir / rel_path.parent / avid / src.name

        # Create directory if it doesn't exist
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Check if file needs to be updated based on modification time
        if dst.exists() and src.stat().st_mtime <= dst.stat().st_mtime:
            counter.files_skipped += 1
            log.debug('skipping %s (unchanged)', src.relative_to(src_dir))
        else:
            # Copy the file
            shutil.copy2(src, dst)  # copy2 preserves metadata
            counter.files_updated += 1
            log.info('updated %s -> %s', src.relative_to(src_dir), dst.relative_to(dst_dir))


def delete(dst_dir: Path, src_dir: Path) -> None:
    """
    Delete .strm files xx/yy/zz/zz.strm from dst_dir that xx/yy/zz.strm are not in src_dir
    """
    for dst in dst_dir.glob('**/*.strm'):
        src_rel_dir = dst.relative_to(dst_dir).parent.parent
        src = src_dir / src_rel_dir / dst.name
        if not src.exists():
            dst.unlink()
            counter.files_deleted += 1
            log.info('deleted %s', dst.relative_to(dst_dir))


def delete_empty_dirs(dst_dir: Path) -> None:
    """
    Delete empty directories in dst_dir
    """
    empty_dirs = [p for p in dst_dir.glob('**/*') if p.is_dir() and not any(p.glob('**/*.strm'))]
    if not empty_dirs:
        return

    # Sort in reverse order to delete deepest directories first
    empty_dirs.sort(reverse=True)
    log.notice('deleting directories:\n%s', '\n'.join([str(d.relative_to(dst_dir)) for d in empty_dirs]))

    # process deletion
    for empty_dir in empty_dirs:
        shutil.rmtree(empty_dir)
        counter.dirs_deleted += 1
        log.info('deleted empty directory: %s', empty_dir.relative_to(dst_dir))



def main() -> None:
    """
    Map .strm files from src_dir with structure xx/yy/zz.strm
    to dst_dir with structure xx/yy/zz/zz.strm

    Args:
        src_dir (str or Path): Source directory containing .strm files
        dst_dir (str or Path): Target directory for the new structure
        logger: Logger object for logging messages

    Returns:
        tuple: (files_processed, files_updated, files_skipped)
    """
    reset_counter()
    src_dir = cfg.src_dir
    dst_dir = cfg.dst_dir
    log.info('starting mapping from %s to %s', src_dir, dst_dir)
    # Argument validation
    if not dst_dir.is_dir():
        msg = f'{dst_dir} is not a directory'
        raise ValueError(msg)
    if not src_dir.is_dir():
        msg = f'{src_dir} is not a directory'
        raise ValueError(msg)
    if not dst_dir.exists():
        dst_dir.mkdir(parents=True)

    update(src_dir, dst_dir)
    delete(dst_dir, src_dir)
    delete_empty_dirs(dst_dir)

    log.info('files updated: %d', counter.files_updated)
    log.info('files skipped (unchanged): %d', counter.files_skipped)
    log.info('files deleted: %d', counter.files_deleted)
    log.info('directories deleted: %d', counter.dirs_deleted)


if __name__ == '__main__':
    main()
