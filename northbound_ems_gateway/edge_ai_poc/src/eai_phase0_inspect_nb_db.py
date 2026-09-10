import sqlite3
import json
from pathlib import Path

DB_PATH = "/mnt/ems-logs/northbound_ems_gateway/nb_ems_gateway.db"

def print_line():
    print("=" * 100)

def safe_json_preview(value, max_len=1200):
    if value is None:
        return None
    text = str(value)
    if len(text) > max_len:
        return text[:max_len] + "...<TRUNCATED>"
    return text

def main():
    db = Path(DB_PATH)
    print("DB_PATH =", DB_PATH)
    print("DB_EXISTS =", db.exists())
    print("DB_SIZE_BYTES =", db.stat().st_size if db.exists() else None)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    print("TABLE_COUNT =", len(tables))

    for t in tables:
        table = t["name"]
        print_line()
        print("TABLE =", table)

        cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        col_names = [c["name"] for c in cols]
        print("COLUMNS =", col_names)

        try:
            count = conn.execute(f'SELECT COUNT(*) AS c FROM "{table}"').fetchone()["c"]
        except Exception as e:
            count = f"ERROR: {e}"
        print("ROW_COUNT =", count)

        # Try timestamp range if timestamp columns exist
        for ts_col in ["timestamp_utc", "timestamp_epoch_ms", "ts", "created_at", "updated_utc"]:
            if ts_col in col_names:
                try:
                    r = conn.execute(
                        f'SELECT MIN("{ts_col}") AS min_ts, MAX("{ts_col}") AS max_ts FROM "{table}"'
                    ).fetchone()
                    print(f"{ts_col}_RANGE =", dict(r))
                except Exception as e:
                    print(f"{ts_col}_RANGE_ERROR =", e)

        # Print latest/sample row
        try:
            order_col = None
            for candidate in ["timestamp_epoch_ms", "timestamp_utc", "ts", "id"]:
                if candidate in col_names:
                    order_col = candidate
                    break

            if order_col:
                row = conn.execute(
                    f'SELECT * FROM "{table}" ORDER BY "{order_col}" DESC LIMIT 1'
                ).fetchone()
            else:
                row = conn.execute(f'SELECT * FROM "{table}" LIMIT 1').fetchone()

            if row:
                d = dict(row)
                print("SAMPLE_ROW_PREVIEW =")
                for k, v in d.items():
                    print(f"  {k}: {safe_json_preview(v)}")
            else:
                print("SAMPLE_ROW_PREVIEW = EMPTY_TABLE")
        except Exception as e:
            print("SAMPLE_ROW_ERROR =", e)

    conn.close()

if __name__ == "__main__":
    main()
