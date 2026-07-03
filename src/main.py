import asyncio

from src import archive, mapping, rss
from src.core import logger

log = logger.get('main')


async def main() -> None:
    await rss.main()
    archive.main()
    mapping.main()


if __name__ == '__main__':
    asyncio.run(main())
