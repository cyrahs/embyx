import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.utils.web import JavBusPaginationError, javbus

# Sample HTML content simulating the main page
MAIN_PAGE_HTML = """
<html>
<script>
    var gid = 12345;
    var uc = 0;
    var img = '/pics/cover/sample.jpg';
</script>
</html>
"""

# Sample HTML content simulating the AJAX response (table row structure)
AJAX_RESPONSE_HTML = """
<html>
    <tr>
        <td width="70%">
            <a href="magnet:?xt=urn:btih:de439fca97a0365b47d9b087010115a94cad6853&dn=release1">release1</a>
        </td>
        <td style="text-align:center">
            <a href="magnet:?xt=urn:btih:de439fca97a0365b47d9b087010115a94cad6853&dn=release1">2.02GB</a>
        </td>
        <td style="text-align:center">
            <a href="magnet:?xt=urn:btih:de439fca97a0365b47d9b087010115a94cad6853&dn=release1">2025-01-01</a>
        </td>
    </tr>
    <tr>
        <td width="70%">
            <a href="magnet:?xt=urn:btih:a1b2c3d4e5f67890abcdef1234567890abcdef12&dn=release2">release2</a>
        </td>
        <td style="text-align:center">
            <a href="magnet:?xt=urn:btih:a1b2c3d4e5f67890abcdef1234567890abcdef12&dn=release2">1.5GB</a>
        </td>
        <td style="text-align:center">
            <a href="magnet:?xt=urn:btih:a1b2c3d4e5f67890abcdef1234567890abcdef12&dn=release2">2025-01-02</a>
        </td>
    </tr>
    <a href="http://other-link.com">Other Link</a>
</html>
"""


def set_javbus_client(monkeypatch: pytest.MonkeyPatch, mock_get: AsyncMock) -> SimpleNamespace:
    client = SimpleNamespace(get=mock_get, aclose=AsyncMock())
    monkeypatch.setattr(javbus, '_client', client)
    return client


@pytest.mark.asyncio
async def test_get_magnets_success(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock the client.get method
    mock_get = AsyncMock()

    # We expect two calls.
    # Side effects can be a list of return values
    mock_response_main = MagicMock()
    mock_response_main.text = MAIN_PAGE_HTML
    mock_response_main.status_code = 200

    mock_response_ajax = MagicMock()
    mock_response_ajax.text = AJAX_RESPONSE_HTML
    mock_response_ajax.status_code = 200

    mock_get.side_effect = [mock_response_main, mock_response_ajax]

    set_javbus_client(monkeypatch, mock_get)
    video_id = 'TEST-001'
    magnets = await javbus.get_magnets(video_id)

    assert len(magnets) == 2

    # Check first magnet
    magnet1 = next(m for m in magnets if 'de439fca97a0365b47d9b087010115a94cad6853' in m['magnet'])
    assert magnet1['magnet'] == f'magnet:?xt=urn:btih:de439fca97a0365b47d9b087010115a94cad6853&dn={video_id}'
    assert magnet1['size'] == '2.02GB'
    assert magnet1['size_int'] > 0

    # Check second magnet
    magnet2 = next(m for m in magnets if 'a1b2c3d4e5f67890abcdef1234567890abcdef12' in m['magnet'])
    assert magnet2['magnet'] == f'magnet:?xt=urn:btih:a1b2c3d4e5f67890abcdef1234567890abcdef12&dn={video_id}'
    assert magnet2['size'] == '1.5GB'
    assert magnet2['size_int'] > 0

    # Verify calls
    assert mock_get.call_count == 2

    # Check first call (Main page)
    args, _ = mock_get.call_args_list[0]
    assert str(args[0]).endswith(f'/{video_id}')

    # Check second call (AJAX)
    args, kwargs = mock_get.call_args_list[1]
    assert 'uncledatoolsbyajax.php' in str(args[0])
    assert 'gid=12345' in str(args[0])
    assert 'img=/pics/cover/sample.jpg' in str(args[0])
    assert kwargs['headers']['Referer'].endswith(f'/{video_id}')


@pytest.mark.asyncio
async def test_get_magnets_no_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    # HTML without the required variables
    mock_response_main = MagicMock()
    mock_response_main.text = '<html>No variables here</html>'
    mock_response_main.status_code = 200

    mock_get = AsyncMock(return_value=mock_response_main)

    set_javbus_client(monkeypatch, mock_get)
    magnets = await javbus.get_magnets('TEST-002')
    assert magnets == []
    assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_scrape_one_page(monkeypatch: pytest.MonkeyPatch) -> None:
    # Sample HTML for a page with videos
    html = """
    <html>
        <a class="movie-box featured" href="https://www.javbus.com/VID-001/"></a>
        <a class="movie-box" href="https://www.javbus.com/VID-002"></a>
        <a class="movie-box" href="https://www.javbus.com/VID-001"></a> <!-- Duplicate -->
    </html>
    """
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.status_code = 200
    mock_get = AsyncMock(return_value=mock_response)

    set_javbus_client(monkeypatch, mock_get)
    ids = await javbus.scrape_one_page('ACTOR-1', 1)
    assert len(ids) == 2
    assert 'VID-001' in ids
    assert 'VID-002' in ids
    mock_get.assert_called_once_with(url=f'{javbus.host}/star/ACTOR-1')

    mock_get.reset_mock()
    await javbus.scrape_one_page('ACTOR-1', 2)
    mock_get.assert_called_once_with(url=f'{javbus.host}/star/ACTOR-1/2')


@pytest.mark.asyncio
async def test_get_total_page(monkeypatch: pytest.MonkeyPatch) -> None:
    # Sample HTML with pagination
    html = """
    <html>
        <a href="/star/ACTOR-1/1">1</a>
        <a href="/star/ACTOR-1/2">2</a>
        <a href="/star/ACTOR-1/3">3</a>
    </html>
    """
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.status_code = 200
    mock_get = AsyncMock(return_value=mock_response)

    set_javbus_client(monkeypatch, mock_get)
    total_page = await javbus.get_total_page('ACTOR-1')
    assert total_page == 3
    mock_get.assert_any_call(url=f'{javbus.host}/star/ACTOR-1')
    mock_get.assert_any_call(url=f'{javbus.host}/star/ACTOR-1/4')

    # Test single page (no links)
    mock_response.text = '<html></html>'
    total_page = await javbus.get_total_page('ACTOR-1')
    assert total_page == 1


@pytest.mark.asyncio
async def test_scrape() -> None:
    # Mock helpers
    with (
        patch.object(javbus, 'get_total_page', new_callable=AsyncMock) as mock_get_total_page,
        patch.object(javbus, 'scrape_one_page', new_callable=AsyncMock) as mock_scrape_one_page,
    ):
        mock_get_total_page.return_value = 2
        mock_scrape_one_page.side_effect = [['A', 'B'], ['C']]

        ids = await javbus.scrape('ACTOR-1')

        # We expect flatten list from scrape_one_page results
        assert len(ids) == 3
        assert set(ids) == {'A', 'B', 'C'}

        mock_get_total_page.assert_called_once_with('ACTOR-1')
        assert mock_scrape_one_page.call_count == 2


@pytest.mark.asyncio
async def test_get_total_page_follows_sliding_windows_through_page_26(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = {
        1: range(1, 11),
        10: range(6, 16),
        15: range(11, 21),
        20: range(16, 26),
        25: range(17, 27),
        26: (),
    }
    requested: list[int] = []

    async def get(*, url: str) -> httpx.Response:
        page = 1 if url.endswith('/ACTOR-1') else int(url.rsplit('/', 1)[-1])
        requested.append(page)
        request = httpx.Request('GET', url)
        if page == 27:
            return httpx.Response(404, request=request)
        links = ''.join(f'<a href="/star/ACTOR-1/{number}">{number}</a>' for number in windows[page])
        return httpx.Response(
            200,
            text=f'<a class="movie-box" href="/{page:03d}"></a>{links}',
            request=request,
        )

    set_javbus_client(monkeypatch, AsyncMock(side_effect=get))

    assert await javbus.get_total_page('ACTOR-1') == 26
    assert requested == [1, 10, 15, 20, 25, 26, 27]


@pytest.mark.asyncio
async def test_scrape_reports_page_progress_and_globally_deduplicates() -> None:
    events: list[tuple[int, int | None, int | None]] = []

    async def progress(completed: int, total: int | None, current: int | None) -> None:
        events.append((completed, total, current))

    async def scrape_page(_actor_id: str, page: int) -> list[str]:
        await asyncio.sleep((4 - page) * 0.001)
        return {1: ['A', 'B'], 2: ['B', 'C'], 3: ['D']}[page]

    with (
        patch.object(javbus, 'get_total_page', new_callable=AsyncMock, return_value=3) as total,
        patch.object(javbus, 'scrape_one_page', new_callable=AsyncMock, side_effect=scrape_page),
    ):
        ids = await javbus.scrape('ACTOR-1', progress_callback=progress)

    assert ids == ['A', 'B', 'C', 'D']
    total.assert_awaited_once_with('ACTOR-1', progress_callback=progress)
    assert events[:2] == [(0, None, None), (0, 3, None)]
    assert [event[0] for event in events[2:]] == [1, 2, 3]
    assert {event[2] for event in events[2:]} == {1, 2, 3}


@pytest.mark.asyncio
async def test_terminal_404_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    url = f'{javbus.host}/star/ACTOR-1/2'
    response = httpx.Response(404, request=httpx.Request('GET', url))
    mock_get = AsyncMock(return_value=response)
    set_javbus_client(monkeypatch, mock_get)

    assert await javbus.scrape_one_page('ACTOR-1', 2) == []
    mock_get.assert_awaited_once_with(url=url)


@pytest.mark.asyncio
async def test_pagination_limit_fails_instead_of_returning_partial_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <a class="movie-box" href="/VID-001"></a>
    <a href="/star/ACTOR-1/3">3</a>
    """
    response = MagicMock(text=html, status_code=200)
    set_javbus_client(monkeypatch, AsyncMock(return_value=response))
    monkeypatch.setattr(javbus, 'max_actor_pages', 3)

    with pytest.raises(JavBusPaginationError, match='safety limit'):
        await javbus.get_total_page('ACTOR-1')


@pytest.mark.asyncio
async def test_scrape_rejects_an_empty_page_inside_discovered_range() -> None:
    async def scrape_page(_actor_id: str, page: int) -> list[str]:
        return {1: ['A'], 2: [], 3: ['C']}[page]

    with (
        patch.object(javbus, 'get_total_page', new_callable=AsyncMock, return_value=3),
        patch.object(javbus, 'scrape_one_page', new_callable=AsyncMock, side_effect=scrape_page),
        pytest.raises(JavBusPaginationError, match='empty page at 2'),
    ):
        await javbus.scrape('ACTOR-1')


@pytest.mark.asyncio
async def test_javbus_aclose_resets_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = set_javbus_client(monkeypatch, AsyncMock())

    await javbus.aclose()

    client.aclose.assert_awaited_once()
    assert javbus._client is None  # noqa: SLF001
