from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from src.utils import freshrss


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request('POST', 'http://example.test/edit-tag')
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError('bad status', request=request, response=response)


def test_read_items_refreshes_stale_edit_token(monkeypatch: pytest.MonkeyPatch) -> None:
    fresh_value = 'fresh-value'
    tokens = []

    token_response = SimpleNamespace(text=fresh_value, raise_for_status=Mock())
    first_post = SimpleNamespace(raise_for_status=Mock(side_effect=_status_error(401)))
    second_post = SimpleNamespace(raise_for_status=Mock())
    client = SimpleNamespace(get=Mock(return_value=token_response), post=Mock(side_effect=[first_post, second_post]))
    monkeypatch.setattr(freshrss, '_client', client)
    monkeypatch.setattr(freshrss, '_edit_token', 'stale-token')
    monkeypatch.setattr(freshrss.read_items.retry, 'sleep', lambda _seconds: None)
    post_responses = [first_post, second_post]

    def capture_post(*_args: object, **kwargs: object) -> SimpleNamespace:
        data = kwargs['data']
        assert isinstance(data, dict)
        tokens.append(data['T'])
        return post_responses.pop(0)

    client.post = Mock(side_effect=capture_post)

    freshrss.read_items(['item-1'])

    assert tokens == ['stale-token', fresh_value]
    assert freshrss._edit_token == fresh_value  # noqa: SLF001


def test_get_items_raises_for_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_response = SimpleNamespace(raise_for_status=Mock(side_effect=_status_error(500)))
    client = SimpleNamespace(get=Mock(return_value=bad_response))
    monkeypatch.setattr(freshrss, '_client', client)
    monkeypatch.setattr(freshrss.get_items.retry, 'sleep', lambda _seconds: None)

    with pytest.raises(httpx.HTTPStatusError):
        freshrss.get_items('Actor')

    assert client.get.call_count == 3
