import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tap import Tap

from src.core import config, logger
from src.utils import get_avid

log = logger.get('merge')


class Args(Tap):
    search_dir: Path
    dst_dir: Path
    filter: str

    def configure(self) -> None:
        self.add_argument('search_dir', type=Path, default='type/vr', help='search directory')
        self.add_argument('dst_dir', type=Path, help='destination directory')
        self.add_argument('-f', '--filter', type=str, default='', help='filter to merge')


args = Args().parse_args()
search_dir = config.mapping.src_dir / args.search_dir
if not search_dir.is_dir():
    log.error('%s is not a directory', args.search_dir)
    sys.exit(1)
if not args.dst_dir.exists():
    log.info('creating %s', args.dst_dir)
    args.dst_dir.mkdir(parents=True)

def get_cds(search_dir: Path, filter_pattern: str) -> dict[str, list[Path]]:
    cds: list[Path] = []
    for root, _, files in search_dir.walk():
        cds += [root / f for f in files if re.search(r'-cd\d+\.strm', f)]
    avid_cds: dict[str, list[Path]] = {}
    for cd in cds:
        avid = get_avid(cd.name)
        if filter_pattern and not re.search(filter_pattern, avid):
            continue
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
    tmp_dir_ctx = tempfile.TemporaryDirectory(prefix='embyx-merge-', dir='./data')
    tmp_dir_path = Path(tmp_dir_ctx.name)
    txt_path = tmp_dir_path / 'merge.txt'
    tmp_output_path = tmp_dir_path / 'output.mp4'
    try:
        txt_path.write_text('\n'.join([f'file {cd}' for cd in cds]))
        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(txt_path),
            '-c', 'copy',
            str(tmp_output_path),
        ]
        result = subprocess.run(cmd, check=False)  # noqa: S603
        if result.returncode != 0:
            log.error('failed to merge %s: return code %d', cds, result.returncode)
            return False
        log.info('moving %s to %s', tmp_output_path, dst)
        shutil.move(tmp_output_path, dst)
        log.info('done')
    except subprocess.CalledProcessError:
        log.exception('failed to merge %s', cds)
        return False
    except KeyboardInterrupt:
        log.warning('keyboard interrupt while merging %s, removing %s', cds, tmp_dir_path)
        raise
    finally:
        tmp_dir_ctx.cleanup()
    return True

def main() -> None:
    avid_cds = get_cds(search_dir, args.filter)
    log.notice('find %d avids to merge', len(avid_cds))
    for avid, cds in avid_cds.items():
        log.notice('avid: %s, cds: %s', avid, ', '.join([cd.name for cd in cds]))
    for avid, cds in avid_cds.items():
        log.notice('start merging %s', avid)
        real_cds = [Path(cd.read_text()) for cd in cds]
        success = merge(real_cds, args.dst_dir / f'{avid}.mp4')
        if success:
            for real_cd in real_cds:
                real_cd.unlink()


if __name__ == '__main__':
    main()
