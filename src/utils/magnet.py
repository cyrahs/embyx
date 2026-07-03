import asyncio
import logging
from urllib.parse import unquote

import httpx
import humanfriendly
import nyaapy.parser
import nyaapy.torrent
from pyquery import PyQuery
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core import config, logger
from src.utils.avid import get_avid

log = logger.get('magnet')

# Create separate magnet log handler
_MAGNET_HANDLER_MARKER = '_embyx_magnet_file_handler'


def _get_magnet_logger() -> logging.Logger:
    magnet_logger = logging.getLogger('magnet_chosen')
    magnet_logger.setLevel(logging.INFO)
    magnet_logger.propagate = False
    if any(getattr(handler, _MAGNET_HANDLER_MARKER, False) for handler in magnet_logger.handlers):
        return magnet_logger

    try:
        config.log_dir.mkdir(parents=True, exist_ok=True)
        magnet_file_handler = logging.FileHandler(config.log_dir / 'magnets.log', encoding='utf-8')
    except OSError as exc:
        log.warning('Magnet file logging disabled: %s', exc)
        return magnet_logger

    magnet_formatter = logging.Formatter('%(message)s')
    magnet_file_handler.setFormatter(magnet_formatter)
    setattr(magnet_file_handler, _MAGNET_HANDLER_MARKER, True)
    magnet_logger.addHandler(magnet_file_handler)
    return magnet_logger


def close_magnet_logger() -> None:
    magnet_logger = logging.getLogger('magnet_chosen')
    for handler in list(magnet_logger.handlers):
        if not getattr(handler, _MAGNET_HANDLER_MARKER, False):
            continue
        magnet_logger.removeHandler(handler)
        handler.close()


class sukebei:  # noqa: N801
    max_concurrency = 5
    site = nyaapy.torrent.TorrentSite.SUKEBEINYAASI
    url = site.value
    _client: httpx.AsyncClient | None = None
    _semaphore: asyncio.Semaphore | None = None
    _semaphore_loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._client is None:
            cls._client = httpx.AsyncClient(proxy=None, limits=httpx.Limits(max_connections=cls.max_concurrency), timeout=20)
        return cls._client

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if cls._semaphore is None or cls._semaphore_loop is not loop:
            cls._semaphore = asyncio.Semaphore(cls.max_concurrency)
            cls._semaphore_loop = loop
        return cls._semaphore

    @classmethod
    async def aclose(cls) -> None:
        if cls._client is not None:
            await cls._client.aclose()
        cls._client = None
        cls._semaphore = None
        cls._semaphore_loop = None

    @classmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def search(cls, keyword: str, category: int = 2, subcategory: int = 2, filters: int = 0, page: int = 0) -> list[dict] | None:
        # category 2 and subcategory 2 refer to videos
        params = {
            'f': filters,
            'c': f'{category}_{subcategory}',
            'q': keyword,
        }
        if page > 0:
            params['p'] = page
        async with cls._get_semaphore():
            try:
                res = await cls._get_client().get(cls.url, params=params)
                res.raise_for_status()
            except (httpx.HTTPError, httpx.TimeoutException):
                log.exception('Failed to get %s with %s', cls.url, params)
                raise
        return nyaapy.parser.parse_nyaa(res.text, limit=None, site=cls.site)


    @classmethod
    async def get_magnet(cls, keyword: str, category: int = 2, subcategory: int = 2, filters: int = 0, page: int = 0) -> str | None:
        try:
            result = await cls.search(keyword, category=category, subcategory=subcategory, filters=filters, page=page)
        except (httpx.HTTPError, httpx.TimeoutException):
            return None
        if not result:
            return None
        # sort by filesize like 2.4 GiB
        parsed_result = []
        for i in result:
            try:
                i['size_int'] = humanfriendly.parse_size(i['size'])
            except humanfriendly.InvalidSize:
                log.warning('Skipping result with invalid size %s for %s', i.get('size'), keyword)
                continue
            i['magnet'] = i['magnet'].split('&')[0]
            i['magnet'] = i['magnet'] + f'&dn={keyword}'
            parsed_result.append(i)
        result = parsed_result
        if not result:
            return None
        result.sort(key=lambda x: x['size_int'], reverse=True)
        trusted = [x for x in result if x['type'] == 'trusted']
        choosed = result.index(trusted[0]) if trusted and trusted[0]['size_int'] >= result[0]['size_int'] * 0.8 else 0
        display_result = result[:5]
        if trusted and trusted[0] not in display_result:
            display_result.append(trusted[0])
        # logging
        log.notice('Found %d results for %s from searching:', len(result), keyword)
        log_lines: list[str] = ['Display top 5 largest + trusted:']
        for i, r in enumerate(display_result):
            trusted = '--'
            if r['type'] == 'trusted':
                trusted = '🔰'
            mark = '--'
            if i == choosed:
                mark = '✅'
            log_lines.append(f'{mark}{trusted}{r["size"]} {r["name"]}')
            log_lines.append(r['magnet'])

        log.info('\n'.join(log_lines))

        # Log the chosen magnet to separate magnet log file
        chosen_magnet = result[choosed]['magnet']
        _get_magnet_logger().info(chosen_magnet)

        return chosen_magnet

class rss:  # noqa: N801
    @classmethod
    def get_magnet(cls, item: dict) -> dict | None:
        try:
            content = item['summary']['content']
        except KeyError:
            log.warning('Error getting magnets from rss item: %s', item)
            return None
        rows = PyQuery(content)("table tbody tr").filter(lambda _, el: PyQuery(el)("a[href^='magnet:']").length)
        avid = get_avid(item['title'])

        results = []
        for row in rows.items():
            a = row("td:nth-child(1) a[href^='magnet:']")
            r = a.attr("href")
            size = row("td:nth-child(2)").text().strip()
            try:
                size_int = humanfriendly.parse_size(size)
            except humanfriendly.InvalidSize:
                log.warning('Skipping RSS magnet with invalid size %s for %s', size, avid)
                continue
            # process info
            try:
                r, name = r.split('&dn=')
                name = unquote(name)
            except ValueError:
                r = r.split('&')[0]
                name = 'Unknown'
            results.append({"magnet": f'{r}&dn={avid}', "size": size, "name": name, 'size_int': size_int})
        if not results:
            return None
        results.sort(key=lambda x: x['size_int'], reverse=True)
        # logging
        log.notice('Found %d results for %s from RSS:', len(results), avid)
        log_lines: list[str] = ['Display top 5 largest:']
        for i, r in enumerate(results[:5]):
            mark = '✅' if i == 0 else '--'
            log_lines.append(f'{mark}--{r["size"]} {r["name"]}')
            log_lines.append(r['magnet'])
        log.info('\n'.join(log_lines))
        return results[0]['magnet']
