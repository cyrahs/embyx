from pathlib import Path


def has_video_suffix(path: Path) -> bool:
    return path.suffix.lower() in ('.mp4', '.mkv', '.avi', '.wmv', '.mov', '.flv', '.m4v', '.ts', '.rmvb')

def is_video(path: Path) -> bool:
    if not path.is_file():
        return False
    return has_video_suffix(path)
