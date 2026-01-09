from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.web import javbus

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


@pytest.mark.asyncio
async def test_get_magnets_success() -> None:
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

    # Patch the client on the class
    with patch.object(javbus.client, 'get', mock_get):
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
async def test_get_magnets_no_variables() -> None:
    # HTML without the required variables
    mock_response_main = MagicMock()
    mock_response_main.text = '<html>No variables here</html>'
    mock_response_main.status_code = 200

    mock_get = AsyncMock(return_value=mock_response_main)

    with patch.object(javbus.client, 'get', mock_get):
        magnets = await javbus.get_magnets('TEST-002')
        assert magnets == []
        assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_scrape_one_page() -> None:
    # Sample HTML for a page with videos
    html = """
    <html>
        <a class="movie-box" href="https://www.javbus.com/VID-001"></a>
        <a class="movie-box" href="https://www.javbus.com/VID-002"></a>
        <a class="movie-box" href="https://www.javbus.com/VID-001"></a> <!-- Duplicate -->
    </html>
    """
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.status_code = 200
    mock_get = AsyncMock(return_value=mock_response)

    with patch.object(javbus.client, 'get', mock_get):
        ids = await javbus.scrape_one_page('ACTOR-1', 1)
        assert len(ids) == 2
        assert 'VID-001' in ids
        assert 'VID-002' in ids
        mock_get.assert_called_with(url=f'{javbus.host}/star/ACTOR-1/1')


@pytest.mark.asyncio
async def test_get_total_page() -> None:
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

    with patch.object(javbus.client, 'get', mock_get):
        total_page = await javbus.get_total_page('ACTOR-1')
        assert total_page == 3
        mock_get.assert_called_with(url=f'{javbus.host}/star/ACTOR-1')

    # Test single page (no links)
    mock_response.text = '<html></html>'
    with patch.object(javbus.client, 'get', mock_get):
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
