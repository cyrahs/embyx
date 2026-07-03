import asyncio

from src import archive, mapping, rss
from src.utils.cleanup import aclose_all


async def main() -> None:
    try:
        await rss.main()
        archive.main()
        mapping.main()
    finally:
        await aclose_all()


if __name__ == '__main__':
    asyncio.run(main())
