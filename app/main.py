"""FastAPI app — REST API hari libur nasional Indonesia.

Jalankan:
    uvicorn app.main:app --reload
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import sys

from fastapi import FastAPI, HTTPException, Query

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import connect, holidays_on, list_holidays, next_holiday, year_summary  # noqa: E402
from ingest.ingest import run as ingest_run  # noqa: E402

app = FastAPI(
    title="Hari Libur Indonesia API",
    description="Libur nasional + cuti bersama Indonesia. Data resmi SKB (origin=skb) "
                "untuk tahun yang tersedia; sisanya hasil generator offline (origin=computed).",
    version="1.0.0",
)


def _enrich(row: dict) -> dict:
    """Tambah field turunan (weekday, is_weekend, is_official) ke baris DB."""
    d = date.fromisoformat(row["date"])
    return {
        **row,
        "weekday": d.strftime("%A"),
        "is_weekend": d.weekday() >= 5,
        "is_official": row["origin"] == "skb",
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/holidays")
def get_holidays(
    year: int | None = Query(default=None, ge=1900, le=2200),
    month: int | None = Query(default=None, ge=1, le=12),
    type: str | None = Query(default=None, pattern="^(nasional|cuti_bersama)$"),
) -> dict:
    conn = connect()
    try:
        items = [_enrich(r) for r in list_holidays(conn, year=year, month=month, tipe=type)]
        counts = {
            "total": len(items),
            "nasional": sum(1 for i in items if i["type"] == "nasional"),
            "cuti_bersama": sum(1 for i in items if i["type"] == "cuti_bersama"),
        }
        return {"filters": {"year": year, "month": month, "type": type}, **counts, "items": items}
    finally:
        conn.close()


@app.get("/holidays/next")
def get_next_holiday(
    from_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> dict:
    d = from_date or date.today().isoformat()
    conn = connect()
    try:
        nxt = next_holiday(conn, d)
        if not nxt:
            return {"from_date": d, "next": None}
        days_until = (date.fromisoformat(nxt["date"]) - date.fromisoformat(d)).days
        return {"from_date": d, "days_until": days_until, "next": _enrich(nxt)}
    finally:
        conn.close()


@app.get("/holidays/{date_str}")
def get_holiday_by_date(date_str: str) -> dict:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise HTTPException(status_code=400, detail="Format tanggal harus YYYY-MM-DD")
    conn = connect()
    try:
        items = [_enrich(r) for r in holidays_on(conn, date_str)]
        return {
            "date": date_str,
            "is_holiday": bool(items),
            "is_nasional_holiday": any(i["type"] == "nasional" for i in items),
            "items": items,
        }
    finally:
        conn.close()


@app.get("/years")
def get_years() -> dict:
    conn = connect()
    try:
        return {"years": year_summary(conn)}
    finally:
        conn.close()


@app.post("/ingest", status_code=200)
def refresh(
    start: int = Query(default=2024, ge=1900, le=2200),
    end: int = Query(default=2032, ge=1900, le=2200),
) -> dict:
    """Regenerate SQLite dari dataset. Aman dipanggil berkali-kali (idempotent)."""
    return ingest_run(start, end)
