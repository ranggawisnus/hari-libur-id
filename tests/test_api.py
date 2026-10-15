"""Test suite: verifikasi API + integritas data + akurasi generator."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import connect  # noqa: E402
from app.main import app  # noqa: E402
from generator.engine import easter_sunday, generate, imlek_date  # noqa: E402
from ingest.ingest import load_official, run as ingest_run  # noqa: E402

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _fresh_db():
    ingest_run(2024, 2032)
    yield


# ------------------------------------------------------------------ API

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_holidays_2025_total():
    r = client.get("/holidays", params={"year": 2025})
    assert r.status_code == 200
    body = r.json()
    # SKB 2025: 17 nasional + 10 cuti bersama = 27
    assert body["total"] == 27
    assert body["nasional"] == 17
    assert body["cuti_bersama"] == 10


def test_filter_type_nasional():
    r = client.get("/holidays", params={"year": 2026, "type": "nasional"})
    body = r.json()
    assert body["total"] == 17  # SKB 2026
    assert all(i["type"] == "nasional" for i in body["items"])


def test_filter_month():
    r = client.get("/holidays", params={"year": 2025, "month": 4})
    items = r.json()["items"]
    assert items  # April 2025 penuh libur (Idul Fitri + Wafat + Paskah)
    assert all(i["date"].startswith("2025-04") for i in items)


def test_check_holiday_date():
    r = client.get("/holidays/2025-08-17")
    body = r.json()
    assert body["is_holiday"] is True
    assert body["is_nasional_holiday"] is True
    assert any("Proklamasi" in i["name"] for i in body["items"])


def test_check_non_holiday_date():
    r = client.get("/holidays/2025-08-18")
    body = r.json()
    assert body["is_holiday"] is False
    assert body["items"] == []


def test_bad_date_format():
    r = client.get("/holidays/17-08-2025")
    assert r.status_code == 400


def test_next_holiday():
    r = client.get("/holidays/next", params={"from_date": "2025-08-16"})
    body = r.json()
    assert body["next"]["date"] == "2025-08-17"
    assert body["days_until"] == 1


def test_years_endpoint():
    r = client.get("/years")
    years = {y["year"]: y for y in r.json()["years"]}
    assert "2025" in years and "2030" in years
    # 2025 resmi -> all_official=1; 2030 computed -> 0
    assert years["2025"]["all_official"] == 1
    assert years["2030"]["all_official"] == 0


def test_ingest_idempotent():
    before = client.get("/holidays", params={"year": 2025}).json()["total"]
    r = client.post("/ingest", params={"start": 2024, "end": 2032})
    assert r.status_code == 200
    after = client.get("/holidays", params={"year": 2025}).json()["total"]
    assert before == after == 27


# ------------------------------------------------------------------ Data resmi vs SKB

@pytest.mark.parametrize("year", ["2024", "2025", "2026", "2027"])
def test_db_matches_skb(year):
    """Tahun resmi harus 100% identik dengan tabel SKB."""
    official = load_official()
    skb = {(e["date"], e["key"], e["name"], e["type"]) for e in official[year]["entries"]}
    conn = connect()
    rows = conn.execute(
        "SELECT date, key, name, type FROM holidays WHERE substr(date,1,4)=?", (year,)
    ).fetchall()
    conn.close()
    db = {(r["date"], r["key"], r["name"], r["type"]) for r in rows}
    assert db == skb


def test_all_official_years_flagged():
    conn = connect()
    rows = conn.execute(
        "SELECT DISTINCT origin FROM holidays WHERE substr(date,1,4) IN "
        "('2024','2025','2026','2027')"
    ).fetchall()
    conn.close()
    assert [r["origin"] for r in rows] == ["skb"]


# ------------------------------------------------------------------ Generator (rule-based)

def test_easter_known_dates():
    assert easter_sunday(2025) == date(2025, 4, 20)  # cocok SKB 2025
    assert easter_sunday(2026) == date(2026, 4, 5)
    assert easter_sunday(2027) == date(2027, 3, 28)  # cocok SKB 2027


def test_easter_derived():
    e = easter_sunday(2025)
    gen = {h.key: h.date for h in generate(2025)}
    assert gen["wafat_yesus"] == e - timedelta(days=2)
    assert gen["kenaikan_yesus"] == e + timedelta(days=39)


def test_fixed_holidays_any_year():
    for year in (1999, 2035, 2099):
        dates = {h.key: h.date for h in generate(year)}
        assert dates["tahun_baru_masehi"] == date(year, 1, 1)
        assert dates["hari_buruh"] == date(year, 5, 1)
        assert dates["pancasila"] == date(year, 6, 1)
        assert dates["proklamasi"] == date(year, 8, 17)
        assert dates["natal"] == date(year, 12, 25)


def test_imlek_matches_skb():
    assert imlek_date(2026) == date(2026, 2, 17)  # cocok SKB 2026
    assert imlek_date(2027) == date(2027, 2, 6)   # cocok SKB 2027


def test_generator_no_duplicate_keys_per_date():
    for year in (2028, 2029, 2030):
        holidays = generate(year)
        seen = set()
        for h in holidays:
            k = (h.date, h.key)
            assert k not in seen, f"duplikat {k} di {year}"
            seen.add(k)


def test_generator_covers_all_event_types():
    holidays = generate(2030)
    keys = {h.key for h in holidays}
    for expected in ("tahun_baru_masehi", "imlek", "nyepi", "idul_fitri", "wafat_yesus",
                     "paskah", "hari_buruh", "kenaikan_yesus", "idul_adha", "waisak",
                     "pancasila", "tahun_baru_islam", "proklamasi", "maulid", "natal",
                     "isra_mikraj"):
        assert any(k == expected or k.startswith(expected + "_") for k in keys), \
            f"{expected} tidak ter-generate untuk 2030"


def test_computed_years_flagged_provisional():
    conn = connect()
    rows = conn.execute(
        "SELECT DISTINCT origin FROM holidays WHERE substr(date,1,4)='2030'"
    ).fetchall()
    conn.close()
    assert [r["origin"] for r in rows] == ["computed"]
