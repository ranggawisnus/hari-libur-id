"""Generator hari libur nasional Indonesia — offline murni.

Strategi:
- Tanggal tetap (UUD/UU)         -> rule, akurat untuk tahun berapa pun
- Paskah + turunan (Wafat/Kenaikan) -> algoritma Anonymous Gregorian, eksak
- Imlek                            -> lunardate (kalender Tionghoa), terverifikasi cocok dgn SKB
- Hijri (Idul Fitri, Idul Adha, 1 Muharram, Maulid, Isra Mikraj)
                                  -> hijridate; TERBUKTI meleset -1 hari di banyak tahun,
                                     jadi wajib di-override tabel resmi (lihat data/tanggal_resmi.json)
- Waisak                           -> purnama terakhir bulan Mei (WIB), heuristik
- Nyepi                            -> bulan baru Maret (WIB), heuristik
- Cuti bersama                     -> TIDAK dihitung; murni keputusan SKB (hanya dari tabel)

Hasil generator ditandai origin="computed"; hasil tabel resmi ditandai origin="skb".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from hijridate import Gregorian, Hijri
from lunardate import LunarDate

TIPE_NASIONAL = "nasional"
TIPE_CUTI_BERSAMA = "cuti_bersama"

# (key, bulan hijri, tanggal hijri, nama generik, jumlah hari beruntun)
HIJRI_EVENTS: list[tuple[str, int, int, str, int]] = [
    ("isra_mikraj", 7, 27, "Isra Mikraj Nabi Muhammad SAW", 1),
    ("idul_fitri", 10, 1, "Hari Raya Idul Fitri", 2),   # 1-2 Syawal (pola SKB 2024-2027)
    ("idul_adha", 12, 10, "Hari Raya Idul Adha", 1),
    ("tahun_baru_islam", 1, 1, "Tahun Baru Islam", 1),
    ("maulid", 3, 12, "Maulid Nabi Muhammad SAW", 1),
]

NAMA_GENERIK = {
    "tahun_baru_masehi": "Tahun Baru Masehi",
    "imlek": "Tahun Baru Imlek",
    "nyepi": "Hari Suci Nyepi",
    "idul_fitri": "Hari Raya Idul Fitri",
    "wafat_yesus": "Wafat Yesus Kristus",
    "paskah": "Kebangkitan Yesus Kristus (Paskah)",
    "hari_buruh": "Hari Buruh Internasional",
    "kenaikan_yesus": "Kenaikan Yesus Kristus",
    "idul_adha": "Hari Raya Idul Adha",
    "waisak": "Hari Raya Waisak",
    "pancasila": "Hari Lahir Pancasila",
    "tahun_baru_islam": "Tahun Baru Islam",
    "proklamasi": "Proklamasi Kemerdekaan",
    "maulid": "Maulid Nabi Muhammad SAW",
    "natal": "Kelahiran Yesus Kristus",
    "isra_mikraj": "Isra Mikraj Nabi Muhammad SAW",
}

WIB = timedelta(hours=7)


@dataclass(frozen=True)
class Holiday:
    key: str
    date: date
    name: str
    tipe: str
    origin: str  # "computed" | "skb"

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "key": self.key,
            "name": self.name,
            "type": self.tipe,
            "origin": self.origin,
            "is_official": self.origin == "skb",
            "weekday": self.date.strftime("%A"),
            "is_weekend": self.date.weekday() >= 5,
        }


# ---------------------------------------------------------------- kalender gerejawi

def easter_sunday(year: int) -> date:
    """Algoritma Anonymous Gregorian (Meeus). Paskah 1583-9999."""
    a, b, c = year % 19, year // 100, year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


# ---------------------------------------------------------------- fase bulan (Meeus bab 49)

def _phase_jde(k: float) -> float:
    """JDE (Ephemeris Time JD) fase bulan ke-k (k bulat = bulan baru, k+.5 = purnama)."""
    T = k / 1236.85
    E = 1 - 0.002516 * T - 0.0000074 * T * T
    M = math.radians(2.5534 + 29.10535670 * k - 0.0000014 * T * T - 0.00000011 * T**3)
    Mp = math.radians(201.5643 + 385.81693528 * k + 0.0107582 * T * T
                      + 0.00001238 * T**3 - 0.000000058 * T**4)
    F = math.radians(160.7108 + 390.67050284 * k - 0.0016118 * T * T
                     - 0.00000227 * T**3 + 0.000000011 * T**4)
    Om = math.radians(124.7746 - 1.56375588 * k + 0.0020672 * T * T + 0.00000215 * T**3)

    A = [
        math.radians(299.77 + 0.107408 * k - 0.009173 * T * T),
        math.radians(251.88 + 0.016321 * k),
        math.radians(251.83 + 26.651886 * k),
        math.radians(349.42 + 36.412478 * k),
        math.radians(84.66 + 18.206239 * k),
        math.radians(141.74 + 53.303771 * k),
        math.radians(207.14 + 2.453732 * k),
        math.radians(154.84 + 7.306860 * k),
        math.radians(34.52 + 27.261239 * k),
        math.radians(207.19 + 0.121824 * k),
        math.radians(291.34 + 1.844379 * k),
        math.radians(161.72 + 24.198154 * k),
        math.radians(239.56 + 25.513099 * k),
        math.radians(331.55 + 3.592518 * k),
    ]
    corr = (
        -0.40720 * math.sin(Mp) + 0.17241 * E * math.sin(M) + 0.01608 * math.sin(2 * Mp)
        + 0.01039 * math.sin(2 * F) + 0.00739 * E * math.sin(Mp - M)
        - 0.00514 * E * math.sin(Mp + M) + 0.00208 * E * E * math.sin(2 * M)
        - 0.00111 * math.sin(Mp - 2 * F) - 0.00057 * math.sin(Mp + 2 * F)
        + 0.00056 * E * math.sin(2 * Mp + M) - 0.00042 * math.sin(3 * Mp)
        + 0.00042 * E * math.sin(M + 2 * F) + 0.00038 * E * math.sin(M - 2 * F)
        - 0.00024 * E * math.sin(2 * Mp - M) - 0.00017 * math.sin(Om)
        - 0.00007 * math.sin(Mp + 2 * M)
        + 0.000325 * math.sin(A[0]) + 0.000165 * math.sin(A[1]) + 0.000164 * math.sin(A[2])
        + 0.000126 * math.sin(A[3]) + 0.000110 * math.sin(A[4]) + 0.000062 * math.sin(A[5])
        + 0.000060 * math.sin(A[6]) + 0.000056 * math.sin(A[7]) + 0.000047 * math.sin(A[8])
        + 0.000042 * math.sin(A[9]) + 0.000040 * math.sin(A[10]) + 0.000037 * math.sin(A[11])
        + 0.000035 * math.sin(A[12]) + 0.000023 * math.sin(A[13])
    )
    return (2451550.09766 + 29.530588861 * k + 0.00015437 * T * T
            - 0.000000150 * T**3 + 0.00000000073 * T**4 + corr)


def _jde_to_local(jde: float) -> datetime:
    return datetime(2000, 1, 1, 12, 0) + timedelta(days=jde - 2451545.0) + WIB


def moon_phases_in_year(year: int, phase: str) -> list[tuple[datetime, float]]:
    """Semua fase (new/full) dalam satu tahun Gregorian, waktu lokal WIB."""
    offset = 0.0 if phase == "new" else 0.5
    k0 = math.floor((year - 2000) * 12.3685) - 1
    out: list[tuple[datetime, float]] = []
    k = k0
    while k <= k0 + 15:
        jde = _phase_jde(k + offset)
        dt = _jde_to_local(jde)
        if dt.year > year + 1:
            break
        if dt.year == year:
            out.append((dt, k + offset))
        k += 1
    return out


def waisak_date(year: int) -> date:
    """Purnama TERAKHIR di bulan Mei (WIB). Cocok 4/4 vs SKB 2024-2027."""
    fulls = [dt.date() for dt, _ in moon_phases_in_year(year, "full") if dt.month == 5]
    return max(fulls) if fulls else date(year, 5, 15)


def nyepi_date(year: int) -> date:
    """Bulan baru di bulan Maret (WIB). Cocok 3/4 vs SKB 2024-2027 (2024 meleset -1 hari)."""
    news = [dt.date() for dt, _ in moon_phases_in_year(year, "new") if dt.month == 3]
    return max(news) if news else date(year, 3, 15)


# ---------------------------------------------------------------- hijri & imlek

def _hijri_event_dates_in_greg_year(g_year: int, h_month: int, h_day: int) -> list[date]:
    """Semua tanggal Gregorian dari event hijri (bulan/hari) yang jatuh di tahun Gregorian ini.
    Bisa >1 (contoh: Isra Mikraj 2027 terjadi dua kali: 5 Jan & 26 Des)."""
    found: list[date] = []
    for hy in range(g_year - 580, g_year - 577):
        try:
            g = Hijri(hy, h_month, h_day).to_gregorian()
        except Exception:
            continue
        if g.year == g_year:
            found.append(date(g.year, g.month, g.day))
    return sorted(found)


def imlek_date(year: int) -> date:
    """Tahun Baru Imlek = 1/1 kalender Tionghoa. Terverifikasi cocok SKB 2026 & 2027."""
    return LunarDate(year, 1, 1).to_solar_date()


# ---------------------------------------------------------------- generator utama

def generate(year: int) -> list[Holiday]:
    """Generate libur nasional (computed) untuk satu tahun Gregorian."""
    out: list[Holiday] = []

    def add(key: str, d: date, name: str) -> None:
        out.append(Holiday(key=key, date=d, name=name, tipe=TIPE_NASIONAL, origin="computed"))

    # tanggal tetap
    for key, (m, dd), nama in [
        ("tahun_baru_masehi", (1, 1), "Tahun Baru Masehi"),
        ("hari_buruh", (5, 1), "Hari Buruh Internasional"),
        ("pancasila", (6, 1), "Hari Lahir Pancasila"),
        ("proklamasi", (8, 17), "Proklamasi Kemerdekaan"),
        ("natal", (12, 25), "Kelahiran Yesus Kristus"),
    ]:
        add(key, date(year, m, dd), nama)

    # paskah & turunan
    easter = easter_sunday(year)
    add("paskah", easter, "Kebangkitan Yesus Kristus (Paskah)")
    add("wafat_yesus", easter - timedelta(days=2), "Wafat Yesus Kristus")
    add("kenaikan_yesus", easter + timedelta(days=39), "Kenaikan Yesus Kristus")

    # imlek
    add("imlek", imlek_date(year), "Tahun Baru Imlek")

    # hijri (fallback hitungan — wajib di-override tabel resmi kalau ada)
    for key, hm, hd, nama, span in HIJRI_EVENTS:
        occurrences = _hijri_event_dates_in_greg_year(year, hm, hd)
        for i, d in enumerate(occurrences):
            suffix = f"_{i + 1}" if len(occurrences) > 1 else ""
            if span > 1:
                for j in range(span):
                    add(f"{key}{suffix}_{j + 1}", d + timedelta(days=j), nama)
            else:
                add(f"{key}{suffix}", d, nama)

    # waisak & nyepi (heuristik fase bulan)
    add("waisak", waisak_date(year), "Hari Raya Waisak")
    add("nyepi", nyepi_date(year), "Hari Suci Nyepi")

    out.sort(key=lambda h: (h.date, h.key))
    return out
