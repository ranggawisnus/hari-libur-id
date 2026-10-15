"""Ingest: merge tabel resmi (SKB) dengan hasil generator -> SQLite.

Aturan merge:
- Tahun ada di data/tanggal_resmi.json  -> pakai tanggal SKB apa adanya (origin="skb")
- Tahun tidak ada                      -> pakai hasil generator (origin="computed")
- Cuti bersama                         -> hanya dari tabel resmi (tidak pernah dihitung)

Usage:
    python -m ingest.ingest                 # default 2024-2032
    python -m ingest.ingest 2020 2040       # rentang custom
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import connect, rebuild  # noqa: E402
from generator.engine import Holiday, generate  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "tanggal_resmi.json"

DEFAULT_START, DEFAULT_END = 2024, 2032


def load_official(data_file: Path = DATA_FILE) -> dict[str, dict]:
    if not data_file.exists():
        return {}
    return json.loads(data_file.read_text(encoding="utf-8")).get("years", {})


def official_to_holidays(year_data: dict) -> list[Holiday]:
    return [
        Holiday(
            key=e["key"],
            date=date.fromisoformat(e["date"]),
            name=e["name"],
            tipe=e["type"],
            origin="skb",
        )
        for e in year_data["entries"]
    ]


def build_year(year: int, official: dict[str, dict]) -> tuple[list[Holiday], str]:
    """Return (holidays, mode)."""
    year_data = official.get(str(year))
    if year_data:
        return official_to_holidays(year_data), "skb"
    return generate(year), "computed"


def run(start: int = DEFAULT_START, end: int = DEFAULT_END, data_file: Path = DATA_FILE) -> dict:
    official = load_official(data_file)
    holidays: list[Holiday] = []
    per_year: dict[int, str] = {}
    for year in range(start, end + 1):
        items, mode = build_year(year, official)
        holidays.extend(items)
        per_year[year] = mode

    conn = connect()
    n = rebuild(conn, holidays, meta={
        "generated_at": date.today().isoformat(),
        "years_range": f"{start}-{end}",
        "official_years": ",".join(str(y) for y, m in sorted(per_year.items()) if m == "skb"),
        "computed_years": ",".join(str(y) for y, m in sorted(per_year.items()) if m == "computed"),
        "source": "data/tanggal_resmi.json + generator/engine.py",
    })
    conn.close()
    return {"rows": n, "per_year": per_year, "official_years": sorted(
        int(y) for y, m in per_year.items() if m == "skb")}


if __name__ == "__main__":
    s = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_START
    e = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_END
    result = run(s, e)
    print(f"Ingest selesai: {result['rows']} baris untuk {s}-{e}")
    print(f"  tahun resmi (SKB) : {result['official_years']}")
    print(f"  tahun computed     : {[y for y, m in result['per_year'].items() if m == 'computed']}")
