import asyncio

import httpx
from tap import Tap
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from tqdm.asyncio import tqdm_asyncio

from src.core import config, logger
from src.utils import freshrss, get_avid, magnet

cfg = config.rss


class Args(Tap):
    rank: bool = False

    def configure(self) -> None:
        self.add_argument('-r', '--rank', action='store_true', help='get magnets from rank category')


args = Args().parse_args()

log = logger.get('rss')


def main() -> None:
    label = 'Rank' if args.rank else 'Actor'
    items = freshrss.get_items(label)
    log.info('Find %d items in %s', len(items), label)
    if not items:
        return
    avid_item = {}
    for item in items:
        avid = get_avid(item['title'])
        if not avid:
            log.warning('Failed to get avid for %s', item['title'])
            continue
        if avid not in avid_item:
            avid_item[avid] = []
        avid_item[avid].append(item)
    log.info('Find %d unique avids in %s', len(avid_item), label)
    # get magnets
    avid_magnet = {}
    tasks = [get_magnet(k, v, avid_magnet) for k, v in avid_item.items()]
    try:
        asyncio.run(tqdm_asyncio.gather(*tasks))
    except (Exception, KeyboardInterrupt):
        log.exception('Failed to get magnets')
    finally:
        magnet_lines = list(avid_magnet.values())
        log_lines = [f'found {len(magnet_lines)} magnets:']
        log_lines.extend(magnet_lines)
        log.info('\n'.join(log_lines))
        # store to txt
        failed_avid = [i for i in avid_item if i not in avid_magnet]
        if failed_avid:
            log_lines = [f'Failed to get magnets for {len(failed_avid)} items:']
            for i in failed_avid:
                log_lines.append(f'{i}')
            log.warning(' '.join(log_lines))
    # add magnets to 115
    add_magnets_and_read(avid_magnet, avid_item)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
def add_magnets(magnets: list[str]) -> dict[str, list[str]]:
    for link in magnets:
        if not isinstance(link, str):
            msg = f'magnet link must be a string, but got {type(link)}'
            raise TypeError(msg)
        if not link.lower().startswith('magnet:'):
            msg = f'magnet link must start with "magnet:", but got {link}'
            raise ValueError(msg)

    url = f'{cfg.open115_url}/magnet/add'
    payload = {
        'magnets': magnets,
        'dir_id': cfg.task_dir_id,
    }
    res = httpx.post(url, json=payload, timeout=10)
    res.raise_for_status()
    return res.json()


def add_magnets_and_read(avid_magnet: dict[str, str], avid_item: dict[str, list[dict]]) -> None:
    magnets = list(avid_magnet.values())
    avids = list(avid_magnet.keys())
    for i in range(0, len(magnets), 20):
        magnets_batch = magnets[i:i+20]
        avid_batch = avids[i:i+20]
        try:
            results = add_magnets(magnets_batch)
        except Exception:
            log.exception('Failed to add magnets to 115')
            continue
        mark_as_read_item_id = []
        for avid, result in zip(avid_batch, results, strict=True):
            # mark as read
            if result['type'] in ['success', 'duplicate']:
                mark_as_read_item_id.extend([item['id'] for item in avid_item[avid]])
            # log for warning
            if result['type'] == 'duplicate':
                log.warning('Duplicate magnet for %s', avid)
            if result['type'] == 'failed':
                log.warning('Failed to add magnet to 115: %s', avid)
        if mark_as_read_item_id:
            try:
                freshrss.read_items(mark_as_read_item_id)
            except Exception:
                log.exception('Failed to mark %d items as read', len(mark_as_read_item_id))


async def get_magnet(avid: str, items: list[dict], avid_magnet: dict[str, str]) -> None:
    # first try searching because most task is for recent videos, sukebei is more reliable
    # get from searching
    link = await magnet.sukebei.get_magnet(avid)
    if link:
        avid_magnet[avid] = link
        return
    # get from RSS
    link = magnet.rss.get_magnet(items[0])
    if link:
        avid_magnet[avid] = link
        return
    # leave one item unread when failed to get magnet
    if len(items) == 1:
        log.warning('Failed to get magnet for %s', items[0]['title'])
    else:
        log.warning('Failed to get magnet for %s. Find %d items, leave 1 unread.', items[0]['title'], len(items))
        # Mark all items except the first as read
        item_ids = [item['id'] for item in items[1:]]
        try:
            freshrss.read_items(item_ids)
        except Exception:
            log.exception('Failed to mark %d items as read', len(item_ids))




if __name__ == '__main__':
    main()
