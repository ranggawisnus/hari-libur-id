"""Jembatan antara dataset (generator + tabel resmi) dan SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "holidays.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS holidays (
    date       TEXT NOT NULL,
    key        TEXT NOT NULL,
    name       TEXT NOT NULL,
    type       TEXT NOT NULL CHECK (type IN ('nasional', 'cuti_bersama')),
    origin     TEXT NOT NULL CHECK (origin IN ('skb', 'computed')),
    is_official INTEGER NOT NULL,
    PRIMARY KEY (date, key)
);
CREATE INDEX IF NOT EXISTS idx_holidays_date ON holidays(date);
CREATE INDEX IF NOT EXISTS idx_holidays_year ON holidays(substr(date, 1, 4));
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def rebuild(conn: sqlite3.Connection, holidays: list, meta: dict[str, str]) -> int:
    """Ganti seluruh isi tabel holidays dengan daftar baru. Return jumlah baris."""
    with conn:
        conn.execute("DELETE FROM holidays")
        conn.executemany(
            "INSERT OR REPLACE INTO holidays (date, key, name, type, origin, is_official) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (h.date.isoformat(), h.key, h.name, h.tipe, h.origin, 1 if h.origin == "skb" else 0)
                for h in holidays
            ],
        )
        for k, v in meta.items():
            conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (k, str(v)))
    return len(holidays)


def list_holidays(
    conn: sqlite3.Connection,
    year: int | None = None,
    month: int | None = None,
    tipe: str | None = None,
) -> list[dict]:
    sql, params = "SELECT * FROM holidays WHERE 1=1", []
    if year is not None:
        sql += " AND substr(date, 1, 4) = ?"
        params.append(f"{year:04d}")
    if month is not None:
        sql += " AND CAST(substr(date, 6, 2) AS INTEGER) = ?"
        params.append(month)
    if tipe is not None:
        sql += " AND type = ?"
        params.append(tipe)
    sql += " ORDER BY date, key"
    return [dict(r) for r in conn.execute(sql, params)]


def holidays_on(conn: sqlite3.Connection, d: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM holidays WHERE date = ? ORDER BY key", (d,)
        )
    ]


def next_holiday(conn: sqlite3.Connection, from_date: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM holidays WHERE date >= ? ORDER BY date, key LIMIT 1",
        (from_date,),
    ).fetchone()
    return dict(row) if row else None


def year_summary(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT substr(date, 1, 4) AS year,
               COUNT(*) AS total,
               SUM(CASE WHEN type = 'nasional' THEN 1 ELSE 0 END) AS nasional,
               SUM(CASE WHEN type = 'cuti_bersama' THEN 1 ELSE 0 END) AS cuti_bersama,
               MIN(is_official) AS all_official
        FROM holidays GROUP BY year ORDER BY year
        """
    ).fetchall()
    return [dict(r) for r in rows]
