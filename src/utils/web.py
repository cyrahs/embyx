import asyncio
import inspect
import logging
import random
import re
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

import httpx
import humanfriendly
from pyquery import PyQuery
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from tqdm.asyncio import tqdm_asyncio

log = logging.getLogger('embyx-monitor.javbus')

PageProgressCallback = Callable[[int, int | None, int | None], Awaitable[None] | None]


class JavBusPaginationError(RuntimeError):
    """Raised when JavBus pagination cannot be completed without silently losing pages."""


class javbus:  # noqa: N801
    host = 'https://www.javbus.com'
    max_actor_pages = 200
    _client: httpx.AsyncClient | None = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                headers={
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Cookie': 'existmag=all',
                },
                timeout=60,
                limits=httpx.Limits(max_keepalive_connections=0, max_connections=10),
                proxy=None,
            )
        return cls._client

    @classmethod
    async def aclose(cls) -> None:
        if cls._client is None:
            return
        await cls._client.aclose()
        cls._client = None

    @classmethod
    async def scrape_one_page(cls, actor_id: str, page: int) -> list[str]:
        res = await cls._fetch_actor_page(actor_id, page)
        if res is None:
            return []
        ids, _ = cls._parse_actor_page(actor_id, res.text)
        return list(ids)

    @classmethod
    async def get_total_page(  # noqa: C901
        cls,
        actor_id: str,
        progress_callback: PageProgressCallback | None = None,
    ) -> int:
        """Discover the real final page instead of trusting one sliding pagination window."""
        first = await cls._fetch_actor_page(actor_id, 1)
        if first is None:
            message = f'JavBus actor {actor_id!r} was not found'
            raise JavBusPaginationError(message)

        ids, linked_pages = cls._parse_actor_page(actor_id, first.text)
        await cls._notify_progress(progress_callback, 0, None, 1)
        if not ids and not linked_pages:
            return 1

        fingerprints = {ids} if ids else set()
        highest = 1
        current_links = linked_pages

        while True:
            linked_max = max(current_links, default=highest)
            if linked_max > cls.max_actor_pages:
                message = f'JavBus actor pagination exceeds the {cls.max_actor_pages}-page safety limit'
                raise JavBusPaginationError(message)

            if linked_max > highest:
                highest = linked_max
                response = await cls._fetch_actor_page(actor_id, highest)
                if response is None:
                    message = f'JavBus actor pagination has a gap at page {highest}'
                    raise JavBusPaginationError(message)
                page_ids, current_links = cls._parse_actor_page(actor_id, response.text)
                if page_ids:
                    fingerprints.add(page_ids)
                await cls._notify_progress(progress_callback, 0, None, highest)
                continue

            if highest >= cls.max_actor_pages:
                message = f'JavBus actor pagination reached the {cls.max_actor_pages}-page safety limit without an end'
                raise JavBusPaginationError(message)

            probe = highest + 1
            response = await cls._fetch_actor_page(actor_id, probe)
            if response is None:
                return highest
            page_ids, page_links = cls._parse_actor_page(actor_id, response.text)
            await cls._notify_progress(progress_callback, 0, None, probe)
            if not page_ids:
                if max(page_links, default=highest) > highest:
                    message = f'JavBus actor pagination returned an empty gap at page {probe}'
                    raise JavBusPaginationError(message)
                return highest
            if page_ids in fingerprints:
                return highest

            fingerprints.add(page_ids)
            highest = probe
            current_links = page_links

    @classmethod
    async def scrape(
        cls,
        actor_id: str,
        progress_callback: PageProgressCallback | None = None,
    ) -> list[str]:
        await cls._notify_progress(progress_callback, 0, None, None)
        if progress_callback is None:
            total_page = await cls.get_total_page(actor_id)
        else:
            total_page = await cls.get_total_page(actor_id, progress_callback=progress_callback)
        await cls._notify_progress(progress_callback, 0, total_page, None)

        if progress_callback is None:
            tasks = [cls.scrape_one_page(actor_id, page) for page in range(1, total_page + 1)]
            pages = await tqdm_asyncio.gather(*tasks, leave=False, desc='Scraping from javbus')
        else:

            async def fetch(page: int) -> tuple[int, list[str]]:
                return page, await cls.scrape_one_page(actor_id, page)

            pending = [asyncio.create_task(fetch(page)) for page in range(1, total_page + 1)]
            by_page: dict[int, list[str]] = {}
            completed = 0
            try:
                for task in asyncio.as_completed(pending):
                    page, page_ids = await task
                    by_page[page] = page_ids
                    completed += 1
                    await cls._notify_progress(progress_callback, completed, total_page, page)
            finally:
                for task in pending:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            pages = [by_page[page] for page in range(1, total_page + 1)]

        if total_page > 1 and any(not page for page in pages):
            empty_page = next(index for index, page in enumerate(pages, start=1) if not page)
            message = f'JavBus actor pagination returned an empty page at {empty_page}'
            raise JavBusPaginationError(message)
        return list(dict.fromkeys(video_id for page in pages for video_id in page))

    @classmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _fetch_actor_page(cls, actor_id: str, page: int) -> httpx.Response | None:
        url = f'{cls.host}/star/{actor_id}' if page == 1 else f'{cls.host}/star/{actor_id}/{page}'
        response = await cls._get_client().get(url=url)
        if response.status_code in {404, 410}:
            return None
        response.raise_for_status()
        return response

    @classmethod
    def _parse_actor_page(cls, actor_id: str, html: str) -> tuple[tuple[str, ...], frozenset[int]]:
        doc = PyQuery(html)
        ids: list[str] = []
        for item in doc('a.movie-box').items():
            href = str(item.attr('href') or '')
            path = urlparse(href).path.rstrip('/')
            video_id = path.rsplit('/', 1)[-1].strip().upper()
            if video_id:
                ids.append(video_id)

        page_pattern = re.compile(rf'/star/{re.escape(actor_id)}/([1-9]\d*)/?')
        linked_pages: set[int] = set()
        for item in doc('a[href]').items():
            href = str(item.attr('href') or '')
            parsed = urlparse(href)
            if parsed.netloc and parsed.netloc != urlparse(cls.host).netloc:
                continue
            match = page_pattern.fullmatch(parsed.path)
            if match is not None:
                linked_pages.add(int(match.group(1)))
        return tuple(dict.fromkeys(ids)), frozenset(linked_pages)

    @staticmethod
    async def _notify_progress(
        callback: PageProgressCallback | None,
        completed: int,
        total: int | None,
        current: int | None,
    ) -> None:
        if callback is None:
            return
        result = callback(completed, total, current)
        if inspect.isawaitable(result):
            await result

    @classmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_magnets(cls, video_id: str) -> list[dict]:
        """
        Get magnet links with filesize for a video ID.

        Returns:
            List of dicts with keys: magnet, size, size_int
            Example: [{"magnet": "magnet:?xt=...", "size": "2.02GB", "size_int": 2168958156}]

        Raises:
            httpx.HTTPError: If network request fails.
        """
        url = f'{cls.host}/{video_id}'
        res = await cls._get_client().get(url)
        res.raise_for_status()
        content = res.text

        gid_match = re.search(r'var gid = (\d+);', content)
        uc_match = re.search(r'var uc = (\d+);', content)
        img_match = re.search(r"var img = '([^']+)';", content)

        if not (gid_match and uc_match and img_match):
            return []

        gid = gid_match.group(1)
        uc = uc_match.group(1)
        img = img_match.group(1)
        floor = str(random.randint(1, 1000))  # noqa: S311

        ajax_url = f'{cls.host}/ajax/uncledatoolsbyajax.php?gid={gid}&lang=zh&img={img}&uc={uc}&floor={floor}'

        headers = {
            'Referer': url,
        }

        res = await cls._get_client().get(ajax_url, headers=headers)
        res.raise_for_status()
        doc = PyQuery(res.text)

        results = []
        seen_magnets = set()

        # Each row contains: title+magnet, size, date
        for row in doc('tr').items():
            cells = row('td')
            if cells.length < 2:  # noqa: PLR2004
                continue

            # Get magnet from first cell
            raw_magnet = row('td:first-child a[href^="magnet"]').attr('href')
            if not raw_magnet:
                continue

            # Extract hash from magnet link
            hash_match = re.search(r'urn:btih:([a-fA-F0-9]+)', raw_magnet)
            if not hash_match:
                continue

            magnet_hash = hash_match.group(1).lower()
            if magnet_hash in seen_magnets:
                continue
            seen_magnets.add(magnet_hash)

            # Build simplified magnet link
            magnet_link = f'magnet:?xt=urn:btih:{magnet_hash}&dn={video_id}'

            # Get size from second cell
            size_text = row('td:nth-child(2)').text().strip()
            try:
                size_int = humanfriendly.parse_size(size_text)
            except humanfriendly.InvalidSize:
                size_int = 0

            results.append(
                {
                    'magnet': magnet_link,
                    'size': size_text,
                    'size_int': size_int,
                },
            )

        return results
