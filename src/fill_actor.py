import asyncio
import re
from collections.abc import Coroutine
from pathlib import Path

from tap import Tap
from tqdm.asyncio import tqdm_asyncio

from src.core import config, logger
from src.utils import get_brand, magnet, web

log = logger.get('fill_actor')
cfg = config.fill_actor

class Args(Tap):
    actor_ids: list[str]
    """actor_ids in javbus like 11w6"""

    def configure(self) -> None:
        self.add_argument('actor_ids', nargs='+', help='actor_ids in javbus like 11w6')

args = Args().parse_args()

def find_exists_in_actor(avid: str) -> list[Path]:
    avid = avid.upper()
    brand = get_brand(avid)
    brand_path = cfg.actor_brand_path / brand
    log.info('Checking %s', brand_path)
    if not brand_path.exists():
        log.info('No such directory: %s', brand_path)
        return []
    avid_paths = list(brand_path.iterdir())
    return [p for p in avid_paths if re.match(avid + r'(?:-cd\d{1,2})?\..+', p.name)]

def find_exists_in_additional(avid: str) -> list[Path]:
    avid = avid.upper()
    brand = get_brand(avid)
    result = []
    for p in cfg.additional_brand_path:
        brand_path = p / brand
        log.info('Checking %s', brand_path)
        if not brand_path.exists():
            log.info('No such directory: %s', brand_path)
            continue
        avid_paths = list(brand_path.iterdir())
        result += [p for p in avid_paths if re.match(avid + r'(?:-cd\d{1,2})?\..+', p.name)]
    return result

async def main(actor_ids: list[str]) -> None:  # noqa: C901, PLR0912
    if isinstance(actor_ids, str):
        actor_ids = [actor_ids]
    non_exists: set[str] = set()
    for actor_id in actor_ids:
        log.info('Scraping %s from javbus', actor_id)
        res = await web.javbus.scrape(actor_id)
        res = set(res)
        log.info('Found %d videos', len(res))
        log.info('Checking if videos exist in actor folder')
        for r in res:
            r_clean = match.group(1) if (match := re.match(r'(.+)_\d{4}-\d{2}-\d{2}', r)) else r
            if not find_exists_in_actor(r_clean):
                non_exists.add(r)
    if not non_exists:
        log.info('All exists')
        return
    # check additional
    avid_video: dict[str, list[Path]] = {}
    log.info('Checking if videos exist in additional folder')
    for avid in non_exists:
        find = find_exists_in_additional(avid)
        if find:
            avid_video[avid] = find
            log.notice(f'{avid} found in additional:\n - {"\n - ".join(str(i) for i in find)}')
    move: list[Path] = []
    for avid in non_exists.copy():
        if avid in avid_video:
            move += avid_video[avid]
            non_exists.remove(avid)
    if move:
        log.info('Input y to move to %s, other to skip', cfg.move_in_path)
        if input() == 'y':
            for i in move:
                log.info('Moving %s to %s', i, cfg.move_in_path / i.name)
                i.rename(cfg.move_in_path / i.name)
        else:
            log.warning('Skip move')
    # online
    non_exists = {i.split('_')[0] for i in non_exists}
    log.info('Find %d non exists:\n%s', len(non_exists), ' '.join(non_exists))
    magnets: list[str] = []

    async def _wrapper(coroutine: Coroutine) -> None:
        result = await coroutine
        if result:
            magnets.append(result)

    try:
        tasks = [_wrapper(magnet.sukebei.get_magnet(avid)) for avid in non_exists]
        await tqdm_asyncio.gather(*tasks, desc='Getting magnets', leave=False)
    finally:
        log_lines = [f'found {len(magnets)} magnets:']
        log_lines.extend(magnets)
        log.notice('\n'.join(log_lines))
    log.info('Check rsshub: docker logs -t -n 10 rsshub')
    for actor_id in actor_ids:
        log.info('Rss link: http://rsshub/javbus/star/%s', actor_id)


if __name__ == '__main__':
    asyncio.run(main(args.actor_ids))
