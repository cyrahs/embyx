import asyncio
import time

import httpx
from grpc import RpcError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from tqdm.asyncio import tqdm_asyncio

from src.core import config, logger
from src.utils import clouddrive, freshrss, get_avid, magnet, web

log = logger.get('rss')
COOLDOWN_SECONDS = 24 * 60 * 60
FAILED_AVID_COOLDOWN: dict[str, float] = {}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
def add_magnets(magnets: list[str]) -> dict[str, list[str]]:
    results = []
    for link in magnets:
        if not isinstance(link, str):
            msg = f'Magnet link must be a string, but got {type(link)}'
            raise TypeError(msg)
        if not link.lower().startswith('magnet:'):
            msg = f'Magnet link must start with "magnet:", but got {link}'
            raise ValueError(msg)
        try:
            res = clouddrive.add_offline_file(link, config.clouddrive.task_dir_path)
            if res.success:
                log.info('Added magnet to 115: %s', link)
                results.append({'type': 'success', 'link': link})
            else:
                log.error('Failed to add magnet to 115: %s: %s', link, res)
                results.append({'type': 'failed', 'link': link, 'response': res})
        except RpcError as e:
            if '任务已存在' in e.details():
                log.warning('Duplicate magnet for %s', link)
                results.append({'type': 'duplicate', 'link': link})
            else:
                log.exception('Failed to add magnet to 115: %s: %s', link, e.details())
                results.append({'type': 'failed', 'link': link, 'response': e.details()})
    return results


def add_magnets_and_read(avid_magnet: dict[str, str], avid_item: dict[str, list[dict]]) -> None:
    magnets = list(avid_magnet.values())
    avids = list(avid_magnet.keys())
    for i in range(0, len(magnets), 20):
        magnets_batch = magnets[i : i + 20]
        avid_batch = avids[i : i + 20]
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
    if len(magnets) > 0:
        log.info('Wait 10 seconds for magnets ')
        time.sleep(10)


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
    # get from javbus
    try:
        magnets = await web.javbus.get_magnets(avid)
        if magnets:
            # select the largest magnet
            best = max(magnets, key=lambda x: x['size_int'])
            avid_magnet[avid] = best['magnet']
            return
    except Exception:
        log.exception('Failed to get magnet from javbus for %s', avid)
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


def refresh_finished_magnets() -> None:
    log.info('Start to refresh finished magnets')
    clouddrive.get_sub_files(config.clouddrive.task_dir_path, force_refresh=True)
    log.info('List finished magnets')
    targets = clouddrive.list_finished_offline_files_by_path(config.clouddrive.task_dir_path).offlineFiles
    all_success = True
    for target in targets:
        try:
            log.info('Refreshing %s', target.name)
            clouddrive.get_sub_files(config.clouddrive.task_dir_path + '/' + target.name, force_refresh=True)
        except FileNotFoundError:
            log.warning('Path not found, skip')
            continue
        except NotADirectoryError:
            log.warning('Not a directory, skip')
            continue
        except Exception:
            log.exception('Failed to refresh %s', target.name)
            all_success = False
            continue
    if all_success:
        log.info('Clear finished magnet records')
        clouddrive.clear_finished_offline_files(config.clouddrive.task_dir_path)


async def main(*, rank: bool = False) -> None:  # noqa: C901, PLR0912
    label = 'Rank' if rank else 'Actor'
    items = freshrss.get_items(label)
    log.info('Find %d items in %s', len(items), label)
    if not items:
        refresh_finished_magnets()
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
    cooldown = FAILED_AVID_COOLDOWN
    now = time.time()
    expired_avids = [avid for avid, ts in cooldown.items() if now - ts >= COOLDOWN_SECONDS]
    for avid in expired_avids:
        cooldown.pop(avid, None)
    active_avid_item = {}
    skipped_avids = []
    for avid, avid_items in avid_item.items():
        if avid in cooldown:
            skipped_avids.append(avid)
            continue
        active_avid_item[avid] = avid_items
    if skipped_avids:
        log.info('Skipping %d avids due to cooldown', len(skipped_avids))
    if not active_avid_item:
        refresh_finished_magnets()
        return
    # get magnets
    avid_magnet = {}
    tasks = [get_magnet(k, v, avid_magnet) for k, v in active_avid_item.items()]
    try:
        await tqdm_asyncio.gather(*tasks)
    except (Exception, KeyboardInterrupt):
        log.exception('Failed to get magnets')
    finally:
        magnet_lines = list(avid_magnet.values())
        log_lines = [f'Found {len(magnet_lines)} magnets']
        log_lines.extend(magnet_lines)
        log.info('\n'.join(log_lines))
        # store to txt
        failed_avid = [i for i in active_avid_item if i not in avid_magnet]
        if failed_avid:
            log_lines = [f'Failed to get magnets for {len(failed_avid)} items:']
            for i in failed_avid:
                log_lines.append(f'{i}')
            log.warning(' '.join(log_lines))
            failure_time = time.time()
            for avid in failed_avid:
                cooldown[avid] = failure_time
    # add magnets to 115
    add_magnets_and_read(avid_magnet, active_avid_item)
    refresh_finished_magnets()


if __name__ == '__main__':
    asyncio.run(main())
