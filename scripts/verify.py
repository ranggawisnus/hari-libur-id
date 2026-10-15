"""Verifikasi: bandingkan isi DB vs tabel SKB, dan kualitas fallback generator.

Usage:
    python -m scripts.verify
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import connect  # noqa: E402
from generator.engine import generate  # noqa: E402
from ingest.ingest import load_official  # noqa: E402

TIPE_NASIONAL = "nasional"


def main() -> int:
    official = load_official()
    conn = connect()
    ok = True

    print("=" * 72)
    print("1. CEK DB vs TABEL SKB (harus 100% identik untuk tahun resmi)")
    print("=" * 72)
    for year, data in sorted(official.items()):
        rows = conn.execute(
            "SELECT date, key, name, type, origin FROM holidays "
            "WHERE substr(date,1,4) = ? ORDER BY date, key", (year,)
        ).fetchall()
        db_set = {(r["date"], r["key"], r["name"], r["type"]) for r in rows}
        skb_set = {(e["date"], e["key"], e["name"], e["type"]) for e in data["entries"]}
        nasional_db = sum(1 for r in rows if r["type"] == TIPE_NASIONAL)
        cuti_db = len(rows) - nasional_db
        match = db_set == skb_set
        ok = ok and match
        print(f"  {year}: DB={len(rows)} (nasional={nasional_db}, cuti={cuti_db}) "
              f"SKB={len(skb_set)} -> {'COCOK' if match else 'BEDA!'}")
        if not match:
            for x in sorted(skb_set - db_set):
                print(f"      kurang di DB: {x}")
            for x in sorted(db_set - skb_set):
                print(f"      tidak ada di SKB: {x}")
        origins = {r["origin"] for r in rows}
        if origins != {"skb"}:
            print(f"      WARNING: origin bukan semua skb: {origins}")
            ok = False

    print()
    print("=" * 72)
    print("2. KUALITAS FALLBACK GENERATOR (tahun computed — bukan untuk dijadikan patokan)")
    print("=" * 72)
    total_match = total_miss = 0
    for year, data in sorted(official.items()):
        skb = {e["date"]: e["name"] for e in data["entries"] if e["type"] == TIPE_NASIONAL}
        gen = {h.date.isoformat(): h.name for h in generate(int(year)) if h.tipe == TIPE_NASIONAL}
        same_date = set(skb) & set(gen)
        miss = sorted(set(skb) - set(gen))
        extra = sorted(set(gen) - set(skb))
        total_match += len(same_date)
        total_miss += len(miss)
        print(f"  {year}: cocok {len(same_date)}/{len(skb)} tanggal", end="")
        if miss or extra:
            details = []
            for d in miss:
                # cek apakah generator punya tanggal ±1 hari (gejala hijri -1 hari)
                from datetime import date, timedelta
                d0 = date.fromisoformat(d)
                near = [g for g in gen if abs((date.fromisoformat(g) - d0).days) == 1]
                tag = f"(generator: {near[0]} = -1 hari)" if near else ""
                details.append(f"{d} {tag}")
            print(f" | beda: {'; '.join(details)}")
        else:
            print()
    print(f"  TOTAL fallback: {total_match} cocok, {total_miss} beda dari SKB")
    print("  Catatan: beda selalu gejala hijri -1 hari / nyepi, itu ALASAN tabel resmi ada.")

    print()
    print("=" * 72)
    print("3. RINGKASAN DB")
    print("=" * 72)
    for r in conn.execute(
        "SELECT substr(date,1,4) AS year, COUNT(*) AS total, "
        "MIN(is_official) AS all_official FROM holidays GROUP BY year ORDER BY year"
    ):
        tag = "resmi (SKB)" if r["all_official"] else "computed (provisional)"
        print(f"  {r['year']}: {r['total']} hari [{tag}]")

    conn.close()
    print()
    print("HASIL:", "SEMUA CEK LULUS" if ok else "ADA MASALAH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
