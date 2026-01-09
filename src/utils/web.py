import random
import re

import httpx
import humanfriendly
from pyquery import PyQuery
from tqdm.asyncio import tqdm_asyncio

from src.core import logger

log = logger.get('javbus')


class javbus:  # noqa: N801
    host = 'https://www.javbus.com'
    client = httpx.AsyncClient(
        headers={
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cookie': 'existmag=all',
        },
        timeout=60,
        limits=httpx.Limits(max_keepalive_connections=0, max_connections=10),
        proxy=None,
    )

    @classmethod
    async def scrape_one_page(cls, actor_id: str, page: int) -> list[str]:
        res = await cls.client.get(url=f'{cls.host}/star/{actor_id}/{page}')
        doc = PyQuery(res.text)
        videos = doc('a[class="movie-box"]')
        ids = [str(i.attr('href')).split('/')[-1].upper() for i in videos.items()]
        return list(set(ids))

    @classmethod
    async def get_total_page(cls, actor_id: str) -> int:
        url = f'{cls.host}/star/{actor_id}'
        res = await cls.client.get(url=url)
        doc = PyQuery(res.text)
        links = doc(f'a[href^="/star/{actor_id}/"]')
        if links:
            page_nums = [int(str(i.attr('href')).replace(f'/star/{actor_id}/', '')) for i in links.items()]
            return max(page_nums)
        return 1

    @classmethod
    async def scrape(cls, actor_id: str) -> list[str]:
        total_page = await cls.get_total_page(actor_id)
        tasks = [cls.scrape_one_page(actor_id, i) for i in range(1, total_page + 1)]
        res = await tqdm_asyncio.gather(*tasks, leave=False, desc='Scraping from javbus')
        return [i for j in res for i in j]

    @classmethod
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
        res = await cls.client.get(url)
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

        res = await cls.client.get(ajax_url, headers=headers)
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
