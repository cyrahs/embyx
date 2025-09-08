import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.core import config, logger
from src.utils import get_avid

log = logger.get('merge')

search_dir = config.mapping.src_dir / 'type/vr'

def get_cds(search_dir: Path) -> dict[str, list[Path]]:
    cds: list[Path] = []
    for root, _, files in search_dir.walk():
        cds += [root / f for f in files if re.search(r'-cd\d+\.strm', f)]
    avid_cds = {}
    for cd in cds:
        avid = get_avid(cd.name)
        if avid not in avid_cds:
            avid_cds[avid] = []
        avid_cds[avid].append(cd)
    # sort cds and verify range
    for avid, cds in avid_cds.items():
        cds.sort(key=lambda x: int(re.search(r'-cd(\d+)\.strm', x.name).group(1)))
        indexes = [int(re.search(r'-cd(\d+)\.strm', cd.name).group(1)) for cd in cds]
        if sorted(indexes) != list(range(min(indexes), max(indexes) + 1)):
            log.error('%s has missing CD, skip', avid)
            del avid_cds[avid]
    return avid_cds

def merge(cds: list[Path], dst: Path) -> bool:
    if dst.exists():
        log.warning('%s already exists, skip', dst)
        return False
    with tempfile.TemporaryDirectory(prefix='embyx-merge-') as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        txt_path = tmp_dir_path / 'merge.txt'
        tmp_output_path = tmp_dir_path / 'output.mp4'
        txt_path.write_text('\n'.join([f'file {cd}' for cd in cds]))
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(txt_path),
            '-c', 'copy',
            str(tmp_output_path),
        ]
        try:
            result = subprocess.run(cmd, check=False)  # noqa: S603
            if result.returncode != 0:
                log.error('failed to merge %s: return code %d', cds, result.returncode)
                return False
        except subprocess.CalledProcessError:
            log.exception('failed to merge %s', cds)
            return False
        log.info('moving %s to %s', tmp_output_path, dst)
        shutil.move(tmp_output_path, dst)
        log.info('done')
        return True

def main() -> None:
    avid_cds = get_cds(search_dir)
    for avid, cds in avid_cds.items():
        log.notice('start merging %s', avid)
        real_cds = [Path(cd.read_text()) for cd in cds]
        success = merge(real_cds, real_cds[0].parent / f'{avid}.mp4')
        if success:
            for real_cd in real_cds:
                real_cd.unlink()


if __name__ == '__main__':
    main()
