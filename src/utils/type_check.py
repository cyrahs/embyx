from pathlib import Path


def is_video(path: Path) -> bool:
    if not path.is_file():
        return False
    return path.suffix.lower() in ('.mp4', '.mkv', '.avi', '.wmv', '.mov', '.flv', '.m4v', '.ts', '.rmvb')
