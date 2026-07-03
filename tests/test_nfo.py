from pathlib import Path

from src.utils.nfo import NfoOld


def test_nfo_runtime_element_takes_precedence(tmp_path: Path) -> None:
    nfo_path = tmp_path / 'movie.nfo'
    nfo_path.write_text(
        '<movie><premiered>2025-01-01</premiered><runtime>120</runtime><duration>90</duration></movie>',
        encoding='utf-8',
    )

    nfo = NfoOld(nfo_path)

    assert nfo.date == '2025-01-01'
    assert nfo.duration == 120
