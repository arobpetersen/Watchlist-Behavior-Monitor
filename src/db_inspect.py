from src.config import get_settings
from src.database import get_connection


def main():
    con = get_connection(str(get_settings().db_path))
    for t in ['watchlist_files','watchlist_candidates','intraday_bars_1m','entry_day_features','behavior_labels']:
        print(f"{t}: {con.execute(f'select count(*) from {t}').fetchone()[0]}")


if __name__ == '__main__':
    main()
