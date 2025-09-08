from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel

from src.core import config, logger
from src.utils.avid import get_id

log = logger.get('emby')


class ImageTags(BaseModel):
    Primary: str


class Item(BaseModel):
    Name: str
    ServerId: str
    Id: str
    Path: str
    RunTimeTicks: int
    IsFolder: bool
    Type: str
    ImageTags: ImageTags
    BackdropImageTags: list[str]
    MediaType: str

cfg = config.emby
headers = {'X-Emby-Token': cfg.api_key}
client = httpx.AsyncClient(headers=headers)
avid_id = {}


async def get_item_playbackinfo(item_id: str) -> dict:
    url = f'{cfg.url}/Items/{item_id}/PlaybackInfo'
    res = await client.get(url)
    res.raise_for_status()
    return res.json()


async def get_item_info(item_id: str) -> dict:
    url = f'{cfg.url}/Users/{cfg.user_id}/Items/{item_id}'
    res = await client.get(url)
    res.raise_for_status()
    return res.json()


async def mark_unplayed(item_id: str) -> None:
    url = f'{cfg.url}/Users/{cfg.user_id}/PlayedItems/{item_id}'
    res = await client.delete(url)
    res.raise_for_status()


async def get_strm_content(item_id: str) -> str:
    result = await get_item_playbackinfo(item_id)
    return result['MediaSources'][0]['Path']


async def get_items(item_type: str | None = None, ids: list[str] | None = None) -> list[Item]:
    url = f'{cfg.url}/Items'
    params = {
        'IncludeItemTypes': item_type,
        'Recursive': True,
        'Fields': 'Path',
    }
    if ids:
        params['Ids'] = ','.join(ids)
    res = await client.get(url, params=params)
    res.raise_for_status()
    return res.json()['Items']


async def get_image(item_id: str, route: str) -> bytes:
    url = f'{cfg.url}/Items/{item_id}/Images/{route}'
    res = await client.get(url)
    res.raise_for_status()
    return res.content


async def list_playlist(playlist: str) -> list[dict]:
    name_id = {i['Name']: i['Id'] for i in await get_items('Playlist')}
    if playlist not in name_id:
        msg = f'Playlist not found: {playlist}'
        raise ValueError(msg)
    url = f'{cfg.url}/Playlists/{name_id[playlist]}/Items'
    res = await client.get(url)
    res.raise_for_status()
    return res.json()['Items']


async def playlist_add(playlist: str, item_id_list: list[str]) -> None:
    name_id = {i['Name']: i['Id'] for i in await get_items('Playlist')}
    url = f'{cfg.url}/Playlists/{name_id[playlist]}/Items'
    data = {
        'Ids': ','.join(item_id_list),
    }
    res = await client.post(url, json=data)
    res.raise_for_status()


async def playlist_remove(playlist: str, playlist_item_id_list: list[str]) -> None:
    name_id = {i['Name']: i['Id'] for i in await get_items('Playlist')}
    if playlist not in name_id:
        msg = f'Playlist not found: {playlist}'
        raise ValueError(msg)
    url = f'{cfg.url}/Playlists/{name_id[playlist]}/Items'
    data = {
        'EntryIds': ','.join(playlist_item_id_list),
    }
    res = await client.delete(url, params=data)
    res.raise_for_status()


async def playlist_dedup(playlist: str) -> None:
    items = await list_playlist(playlist)
    ids_map = {i['Id']: i for i in items}
    ids = []
    dup_ids = []
    for item in items:
        if item['Id'] in ids:
            dup_ids.append(item['Id'])
        else:
            ids.append(item['Id'])
    if not dup_ids:
        return
    for idv in dup_ids:
        log.info('Duplicate: %s in playlist %s', ids_map[idv]['Name'], playlist)
    if input('Input y to delete all but one\n') != 'y':
        return
    await playlist_remove(playlist, [ids_map[i]['PlaylistItemId'] for i in dup_ids])


async def all_playlist_dedup() -> None:
    items = await get_items('Playlist')
    for item in items:
        await playlist_dedup(item['Name'])


async def collection_add(collection: str, item_id_list: list[str]) -> None:
    name_id = {i['Name']: i['Id'] for i in await get_items('BoxSet')}
    url = f'{cfg.url}/Collections/{name_id[collection]}/Items'
    data = {
        'Ids': ','.join(item_id_list),
    }
    res = await client.post(url, json=data)
    res.raise_for_status()

async def get_id_by_avid(avid: str) -> str | None:
    if not avid_id:
        items = await get_items('Movie')
        for i in items:
            _avid = get_id(i['Name'])
            if not _avid:
                msg = f'Failed to get avid in {i["Name"]}'
                raise ValueError(msg)
            if _avid in avid_id:
                msg = f'Duplicate avid: {i["Name"]}'
                raise ValueError(msg)
            avid_id[_avid] = i['Id']
    if avid not in avid_id:
        return None
    return avid_id[avid]


async def refresh(item_id: str) -> None:
    url = f'{cfg.url}/Items/{item_id}/Refresh'
    params = {
        'Recursive': True,
    }
    res = await client.post(url, params=params)
    res.raise_for_status()


async def refresh_library() -> None:
    libs = await get_items('CollectionFolder')
    for lib in libs:
        await refresh(lib['Id'])


async def get_the_latest_update() -> datetime:
    url = f'{cfg.url}/Items'
    params = {
        'Fields': 'DateCreated',
        'Limit': 1,
        'SortBy': 'DateCreated',
        'SortOrder': 'Descending',
        'Recursive': True,
    }
    res = await client.get(url, params=params)
    res.raise_for_status()
    return datetime.fromisoformat(res.json()['Items'][0]['DateCreated']).astimezone(UTC)


async def is_updated() -> bool:
    return (await get_the_latest_update()) > datetime.now(UTC) - timedelta(minutes=10)
