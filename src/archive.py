"""
script that process videos and move to target directory

"""

import re
import shutil
import time
from pathlib import Path

from src.core import config, logger
from src.utils import clouddrive, get_avid, get_brand, has_video_suffix, is_video

log = logger.get('archive')
cfg = config.archive

def remove_00(avid: str) -> str:
    match = re.match(r'[A-Z0-9]+-00\d{3,4}', avid)
    if match:
        log.info('Removed 00 for %s', avid)
        return re.sub('00', '', avid, count=1)
    return avid


def check_exists(avid: str, root: Path) -> bool:
    return any(f.name.startswith(avid) for f in root.iterdir() if is_video(f))


def multi_part_video_check(videos: list[Path]) -> bool:
    if len(videos) == 1:
        msg = 'only one video file'
        raise ValueError(msg)

    # check videos only have different digits
    non_digit_parts = {re.sub(r'\d+', '', video.name) for video in videos}
    if len(non_digit_parts) == 1:
        return True
    # check videos like xxx-A.mp4 xxx-B.mp4
    non_index_parts = {re.sub(r'-[A-Z]', '', video.name) for video in videos}
    return len(non_index_parts) == 1


def rename(root: Path) -> None:
    renamed_any = False
    if not root.is_dir():
        msg = f'{root} is not a directory'
        raise ValueError(msg)
    avids: dict[str, set[Path]] = {}
    for video in root.iterdir():
        if not is_video(video):
            continue
        avid = remove_00(get_avid(video.name))
        avids.setdefault(avid, set()).add(video)
    for avid, videos_set in avids.items():
        videos = sorted(videos_set, key=lambda x: x.name)
        for i, video in enumerate(videos):
            suffix = f'-cd{i + 1}{video.suffix}' if len(videos) > 1 else video.suffix
            new_name = f'{avid}{suffix}'
            if video.name == new_name:
                log.warning('no change for %s, skipping', video.relative_to(root))
                continue
            log.notice('%s\n -> %s', video.relative_to(root), new_name)
            video.rename(root / new_name)
            renamed_any = True
    if renamed_any:
        log.info('Sleeping 5 seconds after renaming')
        time.sleep(5)


def flatten(root: Path, dst_dir: Path) -> None:  # noqa: C901
    flattened_any = False
    if not root.is_dir():
        msg = f'{root} is not a directory'
        raise ValueError(msg)
    exist_avids = {get_avid(f.name) for f in root.iterdir() if is_video(f)}
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        videos = [f for f in folder.iterdir() if is_video(f) and f.stat().st_size > cfg.min_size * 1024 * 1024]
        if len(videos) == 0:
            folder_avid = get_avid(folder.name)
            log.info('%s has no video files larger than %dMB', folder.name, cfg.min_size)
            if not folder_avid:
                continue
            folder_avid = remove_00(folder_avid)
            folder_avid_dst_dir = find_dst_dir(folder_avid, dst_dir)
            if not folder_avid_dst_dir.exists():
                continue
            for f in folder_avid_dst_dir.iterdir():
                if not is_video(f) or not f.name.startswith(folder_avid):
                    continue
                log.warning('%s has no video and %s exists (%s), deleting', folder.name, folder_avid, f)
                shutil.rmtree(folder)
                break
            continue
        # check avid
        avids = [get_avid(t.name) for t in videos]
        if len(set(avids)) != 1:
            log.warning(
                'multiple avid result: %s found in %s in %s, skipping', ', '.join(avids), folder.name, ', '.join([t.name for t in videos]),
            )
            continue
        # check multiple videos naming
        if len(videos) > 1 and not multi_part_video_check(videos):
            log.warning('multiple videos found, but seems not multi-part video, skipping %s', folder.name)
            continue
        avid = avids[0]
        if not avid:
            log.warning('failed to get avid for %s, skipping folder', ', '.join([t.name for t in videos]))
            continue
        avid = remove_00(avid)
        if avid in exist_avids:
            log.warning('%s exists in %s, skipping', avid, root)
            continue
        log.notice('flattening %s', folder.name)
        exist_avids.add(avid)
        for v in videos:
            dst = root / v.name
            if dst.exists():
                msg = f'{dst} exists'
                raise FileExistsError(msg)
            v.rename(dst)
        shutil.rmtree(folder)
        flattened_any = True
    if flattened_any:
        log.info('Sleeping 5 seconds after flattening')
        time.sleep(5)

def clear_dirname(root: Path) -> None:
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        if has_video_suffix(folder):
            new_name = folder.stem + folder.suffix.replace('.', '-')
            log.info('clearing dirname for %s -> %s', folder.name, new_name)
            new_path = root / new_name
            counter = 1
            while new_path.exists():
                new_name_with_counter = new_name + f'-{counter}'
                log.info('%s exists, trying %s', new_name, new_name_with_counter)
                new_path = root / new_name_with_counter
                counter += 1
                if counter > 5:
                    break
            if new_path.exists():
                log.warning('failed to clear dirname for %s, skipping', folder.name)
                continue
            folder.rename(new_path)

def find_dst_dir(avid: str, dst_dir: Path) -> Path:
    brand = get_brand(avid)
    if not (brand := get_brand(avid)):
        log.warning('failed to get brand for %s, skipping find_dst', avid)
        return None
    # check if in brand_mapping
    for brand_dst, brand_avids in cfg.brand_mapping.items():
        if brand in brand_avids:
            return cfg.dst_dir / brand_dst / brand
    return dst_dir / brand

def find_video_dst(video: Path, dst_dir: Path) -> Path | None:
    if not is_video(video):
        return None
    if not (avid := get_avid(video.name)):
        log.warning('failed to get avid for %s, skipping find_video_dst', video.relative_to(cfg.src_dir))
        return None
    return find_dst_dir(avid, dst_dir) / video.name


def archive(src_dir: Path, dst_dir: Path) -> None:
    if not src_dir.is_dir():
        msg = f'{src_dir} is not a directory'
        raise ValueError(msg)
    if not dst_dir.is_dir():
        msg = f'{dst_dir} is not a directory'
        raise ValueError(msg)

    for video in src_dir.iterdir():
        if not (dst := find_video_dst(video, dst_dir)):
            continue
        if not dst.parent.exists():
            dst.parent.mkdir(parents=True)
        if dst.exists():
            log.warning('%s exists, skipping', dst.relative_to(cfg.dst_dir))
            continue
        log.notice('moving %s to %s', video.relative_to(src_dir), dst.relative_to(cfg.dst_dir))
        video.rename(dst)


def main() -> None:
    # refresh task dir
    clouddrive.get_sub_files(config.clouddrive.task_dir_path, force_refresh=True)
    for src, dst in cfg.mapping.items():
        src_path = cfg.src_dir / src
        dst_path = cfg.dst_dir / dst
        log.info('processing %s -> %s', src_path, dst_path)
        clear_dirname(src_path)
        flatten(src_path, dst_path)
        rename(src_path)
        archive(src_path, dst_path)

if __name__ == '__main__':
    main()
