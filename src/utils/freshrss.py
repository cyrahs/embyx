import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core import config

_edit_token: str | None = None
_client: httpx.Client | None = None
FRESHRSS_RETRY_EXCEPTIONS = (httpx.HTTPError, httpx.RequestError, httpx.TimeoutException, KeyError, ValueError)


def _get_proxy() -> str | None:
    return config.freshrss.proxy or None


def _get_headers() -> dict[str, str]:
    return {'Authorization': f'GoogleLogin auth={config.freshrss.freshrss_api_key}'}


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(proxy=_get_proxy())
    return _client


def close_client() -> None:
    global _client, _edit_token
    if _client is not None:
        _client.close()
    _client = None
    _edit_token = None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.RequestError, httpx.TimeoutException)),
    reraise=True,
)
def _refresh_edit_token() -> str:
    """Get fresh edit token for FreshRSS API operations."""
    global _edit_token
    res = _get_client().get(f'{config.freshrss.freshrss_url}/token', headers=_get_headers(), timeout=10)
    res.raise_for_status()
    _edit_token = res.text
    return _edit_token


def _get_edit_token() -> str:
    """Get edit token, refreshing if necessary."""
    if _edit_token is None:
        return _refresh_edit_token()
    return _edit_token


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(FRESHRSS_RETRY_EXCEPTIONS),
    reraise=True,
)
def get_items(label: str) -> list[dict]:
    """Get RSS items from a specific label."""
    params = {'xt': 'user/-/state/com.google/read'}
    items = []
    while True:
        url = f'{config.freshrss.freshrss_url}/stream/contents/user/-/label/{label}'
        res = _get_client().get(url, headers=_get_headers(), params=params, timeout=10)
        res.raise_for_status()
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
    global _edit_token
    if not item_ids:
        return
    body = {
        'i': item_ids,
        'a': 'user/-/state/com.google/read',
        'T': _get_edit_token(),
    }

    res = _get_client().post(f'{config.freshrss.freshrss_url}/edit-tag', headers=_get_headers(), data=body, timeout=10)
    try:
        res.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            _edit_token = None
        raise
