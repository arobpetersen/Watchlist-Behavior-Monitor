from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.backwatch_source import (
    canonical_filename,
    infer_setup_date,
    list_source_files,
    normalize_backwatch_file,
    process_new_source_files,
    resolve_source_dir,
    save_canonical_watchlist,
    scan_source_files,
)
from src.database import get_connection


@pytest.mark.parametrize(
    ('name', 'expected'),
    [
        ('2026-04-30_backwatch.xlsx', '2026-04-30'),
        ('2026-04-30.xlsx', '2026-04-30'),
        ('backwatch_2026-04-30.xlsx', '2026-04-30'),
        ('TC2000_2026-04-30.xlsx', '2026-04-30'),
        ('2026_04_30_backwatch.csv', '2026-04-30'),
        ('20260430_backwatch.csv', '2026-04-30'),
        ('04-30-2026_backwatch.xlsx', '2026-04-30'),
        ('4-30-26_backwatch.xlsx', '2026-04-30'),
        ('backwatch_without_date.xlsx', None),
    ],
)
def test_infer_setup_date_patterns(name, expected):
    assert infer_setup_date(name) == expected


def test_list_source_files_filters_supported_files(tmp_path: Path):
    (tmp_path / '2026-04-30_backwatch.csv').write_text('ticker\nAAPL\n')
    (tmp_path / '2026-05-01_backwatch.xlsx').write_text('placeholder')
    (tmp_path / '2026-05-02_backwatch.xls').write_text('placeholder')
    (tmp_path / 'notes.txt').write_text('skip')

    files = list_source_files(tmp_path)

    assert {f.name for f in files} == {
        '2026-04-30_backwatch.csv',
        '2026-05-01_backwatch.xlsx',
        '2026-05-02_backwatch.xls',
    }


def test_resolve_source_dir_falls_back_to_parent_tc2000(tmp_path: Path):
    app_root = tmp_path / 'Watchlist-Behavior-Monitor'
    app_root.mkdir()
    parent_source = tmp_path / 'tc2000'
    parent_source.mkdir()

    assert resolve_source_dir(Path('tc2000'), app_root) == parent_source


def test_normalize_maps_symbol_column_and_missing_optional_fields(tmp_path: Path):
    source = tmp_path / '2026-04-30_backwatch.csv'
    source.write_text('Symbol,Other\n aapl ,x\nMSFT,y\nAAPL,z\n')

    df = normalize_backwatch_file(source)

    assert df.columns.tolist() == ['ticker', 'rating', 'setup', 'focus', 'key_level']
    assert df['ticker'].tolist() == ['AAPL', 'MSFT']
    assert df[['rating', 'setup', 'focus', 'key_level']].fillna('').eq('').all().all()


def test_normalize_maps_tc2000_symbols_header(tmp_path: Path):
    source = tmp_path / '2026-04-30_backwatch.xlsx'
    pd.DataFrame({'Symbols from TC2000': [' atom ', 'usar', 'LWLG']}).to_excel(source, index=False)

    df = normalize_backwatch_file(source)

    assert df.columns.tolist() == ['ticker', 'rating', 'setup', 'focus', 'key_level']
    assert df['ticker'].tolist() == ['ATOM', 'USAR', 'LWLG']
    assert df[['rating', 'setup', 'focus', 'key_level']].fillna('').eq('').all().all()


def test_normalize_uses_first_column_when_symbol_like(tmp_path: Path):
    source = tmp_path / '2026-04-30_backwatch.csv'
    source.write_text('Name,setup\nNVDA,breakout\nTSLA,base\n')

    df = normalize_backwatch_file(source)

    assert df['ticker'].tolist() == ['NVDA', 'TSLA']
    assert df['setup'].tolist() == ['breakout', 'base']


def test_save_canonical_watchlist(tmp_path: Path):
    source = tmp_path / 'TC2000_2026-04-30.csv'
    source.write_text('Ticker,rating\nAAPL,5\n')
    output_dir = tmp_path / 'watchlists'

    output_path, df = save_canonical_watchlist(source, '2026-04-30', output_dir)

    assert output_path.name == canonical_filename('2026-04-30', 'TC2000_2026-04-30')
    assert output_path.read_text().startswith('ticker,rating,setup,focus,key_level')
    assert df['ticker'].tolist() == ['AAPL']


def test_scan_source_files_mixed_statuses(tmp_path: Path):
    source_dir = tmp_path / 'tc2000'
    watchlists_dir = tmp_path / 'watchlists'
    source_dir.mkdir()
    watchlists_dir.mkdir()
    (source_dir / '2026-04-30_backwatch.csv').write_text('Symbols from TC2000\nAAPL\nMSFT\n')
    (source_dir / '2026-05-01_backwatch.csv').write_text('ticker\nNVDA\n')
    (watchlists_dir / canonical_filename('2026-05-01', '2026-05-01_backwatch')).write_text('ticker,rating,setup,focus,key_level\nNVDA,,,,\n')
    (source_dir / 'backwatch_without_date.csv').write_text('ticker\nTSLA\n')
    (source_dir / '2026-05-02_backwatch.csv').write_text('ticker\nnot a symbol?\n')
    con = get_connection(':memory:')

    rows = scan_source_files(source_dir, watchlists_dir, con)
    by_file = {r.source_file: r for r in rows}

    assert by_file['2026-04-30_backwatch.csv'].status == 'New'
    assert by_file['2026-04-30_backwatch.csv'].ticker_count == 2
    assert by_file['2026-05-01_backwatch.csv'].status == 'Already Processed'
    assert by_file['backwatch_without_date.csv'].status == 'Missing Date'
    assert by_file['2026-05-02_backwatch.csv'].status == 'No Valid Tickers'


def test_process_new_source_files_saves_only_new_files(tmp_path: Path):
    source_dir = tmp_path / 'tc2000'
    watchlists_dir = tmp_path / 'watchlists'
    source_dir.mkdir()
    watchlists_dir.mkdir()
    (source_dir / '2026-04-30_backwatch.csv').write_text('Symbols from TC2000\nAAPL\nMSFT\n')
    (source_dir / '2026-05-01_backwatch.csv').write_text('ticker\nNVDA\n')
    (watchlists_dir / canonical_filename('2026-05-01', '2026-05-01_backwatch')).write_text('ticker,rating,setup,focus,key_level\nNVDA,,,,\n')
    con = get_connection(':memory:')

    rows, saved = process_new_source_files(source_dir, watchlists_dir, con)

    assert [p.name for p in saved] == [canonical_filename('2026-04-30', '2026-04-30_backwatch')]
    assert (watchlists_dir / canonical_filename('2026-04-30', '2026-04-30_backwatch')).exists()
    assert {r.source_file: r.status for r in rows} == {
        '2026-04-30_backwatch.csv': 'Processed',
        '2026-05-01_backwatch.csv': 'Already Processed',
    }
