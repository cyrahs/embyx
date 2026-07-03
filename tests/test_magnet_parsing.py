import pytest

from src.utils import magnet


def test_rss_magnet_skips_invalid_size() -> None:
    item = {
        'title': 'ABC-123',
        'summary': {
            'content': """
            <table><tbody>
              <tr>
                <td><a href="magnet:?xt=urn:btih:abc&dn=name">name</a></td>
                <td>unknown</td>
              </tr>
            </tbody></table>
            """,
        },
    }

    assert magnet.rss.get_magnet(item) is None


@pytest.mark.asyncio
async def test_sukebei_magnet_skips_invalid_size(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search(_keyword: str, **_kwargs) -> list[dict]:
        return [
            {'size': 'unknown', 'magnet': 'magnet:?xt=urn:btih:bad&dn=bad', 'type': 'trusted', 'name': 'bad'},
            {'size': '2 GiB', 'magnet': 'magnet:?xt=urn:btih:good&dn=good', 'type': 'regular', 'name': 'good'},
        ]

    class DummyMagnetLogger:
        def info(self, *_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr(magnet.sukebei, 'search', fake_search)
    monkeypatch.setattr(magnet, '_get_magnet_logger', lambda: DummyMagnetLogger())

    result = await magnet.sukebei.get_magnet('ABC-123')

    assert result == 'magnet:?xt=urn:btih:good&dn=ABC-123'
