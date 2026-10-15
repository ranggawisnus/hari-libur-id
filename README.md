# Hari Libur Indonesia — REST API + Dataset

REST API hari libur nasional & cuti bersama Indonesia. Data resmi SKB 3 Menteri untuk tahun yang tersedia, sisanya hasil generator offline (ditandai jelas, tidak dicampur).

## Cara kerja (2 layer)

```
┌─ LAYER 1: GENERATOR OFFLINE (generator/engine.py) ────────────────┐
│  Tanpa jaringan, jalan untuk tahun berapa pun                       │
│  - tanggal tetap (1 Jan, 1 Mei, 1 Jun, 17 Agu, 25 Des) → rule      │
│  - Paskah + Wafat + Kenaikan → algoritma Anonymous Gregorian       │
│  - Imlek → lunardate (kalender Tionghoa)                            │
│  - hijri → hijridate (Idul Fitri, Idul Adha, 1 Muharram, dst)      │
│  - Waisak/Nyepi → perhitungan fase bulan (Meeus)                    │
└────────────────────────────────────────────────────────────────────┘
                              ▼ override
┌─ LAYER 2: TABEL RESMI (data/tanggal_resmi.json) ──────────────────┐
│  Dikutip dari SKB 3 Menteri. Tahun yang ada di sini = 100% persis   │
│  SKB. Saat ini terisi: 2024, 2025, 2026, 2027.                     │
└────────────────────────────────────────────────────────────────────┘
                              ▼ ingest
                        SQLite (data/holidays.db)
                              ▼
                    FastAPI (app/main.py)
```

Setiap baris punya field `origin`:
- `origin: "skb"` → tanggal persis dari SKB, aman dipakai produksi
- `origin: "computed"` → hasil generator, `is_official: false`, provisional

## Kenapa tabel resmi wajib ada (bukti empiris)

Library hijri offline TIDAK match keputusan pemerintah. Hasil pengujian langsung
`hijridate` vs SKB (12 event, 2025-2027): **7 di antaranya meleset -1 hari**.

| Event | Library | SKB |
|---|---|---|
| Idul Fitri 2025 | 30 Mar | **31 Mar** |
| Idul Fitri 2026 | 20 Mar | **21 Mar** |
| 1 Muharram 2025 | 26 Jun | **27 Jun** |
| Maulid 2025 | 4 Sep | **5 Sep** |

Pemerintah pakai sidang isbat + hisab sendiri, bukan Umm al-Qura. Jadi untuk
tahun resmi, tabel SKB menang; generator hanya jadi fallback untuk tahun
yang SKB-nya belum terbit — dan tetap ditandai `is_official: false`.

## Install & jalan

```bash
pip install -r requirements.txt

# 1. build SQLite (default 2024-2032, idempotent)
python -m ingest.ingest
python -m ingest.ingest 2020 2050        # rentang custom

# 2. verifikasi data vs SKB
python -m scripts.verify

# 3. test suite
pytest tests/ -v

# 4. jalanin API
uvicorn app.main:app --reload --port 8000
```

## API

| Endpoint | Keterangan |
|---|---|
| `GET /health` | status |
| `GET /holidays?year=2025&type=nasional&month=8` | list + filter |
| `GET /holidays/2025-08-17` | cek 1 tanggal |
| `GET /holidays/next?from_date=2026-10-15` | libur terdekat |
| `GET /years` | ringkasan per tahun + status resmi/computed |
| `POST /ingest?start=2024&end=2032` | regenerate DB |

Contoh:

```bash
curl "http://localhost:8000/holidays?year=2025&type=nasional"
curl "http://localhost:8000/holidays/2025-08-17"
curl "http://localhost:8000/holidays/next?from_date=2025-08-16"
```

## Deploy (Render free tier)

Repo ini siap deploy ke Render free tier (region singapore). Stateless by design:
DB di-generate saat image build DAN saat startup kalau kosong (ephemeral disk
free tier tidak masalah — ingest cuma ~0.06 detik, DB ~52KB).

Cara 1 — Blueprint (recommended):
  1. Login https://dashboard.render.com pakai akun GitHub lu
  2. New > Blueprint > pilih repo `ranggawisnus/hari-libur-id`
  3. render.yaml terbaca otomatis (web service, free plan, docker)
  4. Deploy — auto-deploy aktif setiap push ke main

Cara 2 — Manual:
  1. New > Web Service > connect repo
  2. Runtime: Docker, Region: Singapore, Plan: Free
  3. Health check path: /health

Test Docker lokal:
  docker build -t hari-libur-id .
  docker run -p 8000:8000 hari-libur-id

Catatan free tier: service sleep setelah 15 menit idle; cold start ~1 menit
(request pertama setelah idle akan lambat, sisanya normal).

## Update data tahun baru

Saat SKB tahun berikutnya terbit (biasanya Sep-Okt):

1. Tambahkan entri tahun tersebut ke `data/tanggal_resmi.json` (format sama)
2. `python -m ingest.ingest`
3. `python -m scripts.verify` → harus "SEMUA CEK LULUS"

JSON cuma sebagai PATCH — bukan input rutin. Generator tetap mengisi tahun
yang belum ada di tabel, ditandai provisional.

## Struktur

```
hari-libur-id/
├── data/
│   ├── tanggal_resmi.json   # tabel override SKB (source of truth untuk tahun resmi)
│   └── holidays.db          # hasil ingest (auto-generate)
├── generator/engine.py      # generator offline
├── ingest/ingest.py         # merge + build SQLite
├── app/main.py              # FastAPI
├── app/db.py                # query layer
├── scripts/verify.py        # verifikasi vs SKB + kualitas fallback
└── tests/test_api.py        # 20+ test
```

## Batasan yang diketahui (jujur)

- Tahun computed: hijri bisa ±1 hari, Nyepi/Waisak heuristik fase bulan → selalu cek `origin`/`is_official` sebelum dipakai
- Cuti bersama tidak pernah dihitung (murni keputusan SKB) — tahun computed tidak punya cuti bersama
- Libur daerah/lokal (Tahun Baru Saka Bali, hari jadi kota) di luar scope
- 2027: Isra Mikraj muncul 2x (Jan & Des) — ini benar sesuai SKB, generator juga menanganinya
