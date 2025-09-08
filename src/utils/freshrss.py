import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core import config

cfg = config.freshrss
if not cfg.proxy:
    cfg.proxy = None
client = httpx.Client(proxy=cfg.proxy)
headers = {'Authorization': f'GoogleLogin auth={cfg.freshrss_api_key}'}
_edit_token: str | None = None

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.RequestError, httpx.TimeoutException)),
    reraise=True,
)
def _refresh_edit_token() -> str:
    """Get fresh edit token for FreshRSS API operations."""
    global _edit_token
    res = httpx.get(f'{cfg.freshrss_url}/token', headers=headers, timeout=10, proxy=cfg.proxy)
    res.raise_for_status()
    _edit_token = res.text
    return _edit_token

def _get_edit_token() -> str:
    """Get edit token, refreshing if necessary."""
    if _edit_token is None:
        return _refresh_edit_token()
    return _edit_token

def get_items(label: str) -> list[dict]:
    """Get RSS items from a specific label."""
    params = {'xt': 'user/-/state/com.google/read'}
    items = []
    while True:
        url = f'{cfg.freshrss_url}/stream/contents/user/-/label/{label}'
        res = client.get(url, headers=headers, params=params, timeout=10)
        content = res.json()
        items += content['items']
        if content.get('continuation'):
            params['c'] = content['continuation']
        else:
            break
    return items

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
def read_items(item_ids: list[str]) -> None:
    """Mark multiple items as read in a single API call."""
    if not item_ids:
        return
    body = {
        'i': item_ids,
        'a': 'user/-/state/com.google/read',
        'T': _get_edit_token(),
    }

    res = client.post(f'{cfg.freshrss_url}/edit-tag', headers=headers, data=body, timeout=10)
    res.raise_for_status()
