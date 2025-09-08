import asyncio
import json
from pathlib import Path

import aiofiles

from src.core import logger
from src.utils import get_avid
from src.utils.emby import collection_add, get_items

file_path = Path('./playlist.json')
save_path = Path('./not_found.json')
collection_avid = json.load(file_path.open())
log = logger.get('playlist_move')


async def main() -> None:
    movies = await get_items('Movie')
    avid_item = {}
    for movie in movies:
        avid = get_avid(movie['Name'])
        if not avid:
            log.warning('%s no avid', movie["Name"])
        elif avid in avid_item:
            log.warning('%s duplicate', avid)
        else:
            avid_item[avid] = movie['Id']
    not_found = {}
    for collection, avids in collection_avid.items():
        not_found[collection] = []
        items = []
        log.info(collection)
        for avid in avids:
            if avid not in avid_item:
                not_found[collection].append(avid)
                continue
            items.append(avid_item[avid])
        if not_found[collection]:
            log.warning('%d not found:\n%s', len(not_found[collection]), '\n'.join(not_found[collection]))
        async with aiofiles.open(save_path, 'w') as f:
            await f.write(json.dumps(not_found, indent=2))
        await collection_add(collection, items)

if __name__ == '__main__':
    asyncio.run(main())
