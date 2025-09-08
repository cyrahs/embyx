import httpx
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
        tasks = [cls.scrape_one_page(actor_id, i) for i in range(1, total_page+1)]
        res = await tqdm_asyncio.gather(*tasks, leave=False, desc='Scraping from javbus')
        return [i for j in res for i in j]
