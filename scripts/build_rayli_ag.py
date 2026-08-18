#!/usr/bin/env python3
"""İBB Açık Veri GTFS dosyalarından küçük bir raylı sistem ağı üretir."""
from __future__ import annotations

import csv
import io
import json
import statistics
from collections import defaultdict
from pathlib import Path

import requests

PACKAGE_API = (
    "https://data.ibb.gov.tr/api/3/action/"
    "package_show?id=public-transport-gtfs-data"
)
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "rayli_ag.json"
RAIL_AGENCIES = {"4": "Marmaray", "11": "Metro İstanbul"}
METRO_ISTANBUL_MODLARI = {
    "0": "tramvay",
    "1": "metro",
    "6": "teleferik",
    "7": "funikuler",
}


def _indir(url: str) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": "IETT-Yolculuk-Karari/1.0"},
        timeout=45,
    )
    response.raise_for_status()
    return response.content


def _csv_oku(data: bytes):
    # Kaynak dosyalar Windows Türkçe kodlamasıyla yayımlanıyor.
    text = data.decode("cp1254", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _saniye(saat: str | None):
    if not saat:
        return None
    try:
        h, m, s = (int(x) for x in saat.split(":"))
        return h * 3600 + m * 60 + s
    except Exception:
        return None


def main():
    paket = json.loads(_indir(PACKAGE_API).decode("utf-8"))["result"]
    kaynaklar = {r["name"]: r["url"] for r in paket["resources"]}
    gerekli = ("agency", "routes", "trips", "stops", "stop_times", "frequencies")
    tablolar = {ad: _csv_oku(_indir(kaynaklar[ad])) for ad in gerekli}

    rotalar = {
        r["route_id"]: r for r in tablolar["routes"]
        if ((r.get("agency_id") == "4" and r.get("route_type") == "1")
            or (r.get("agency_id") == "11"
                and r.get("route_type") in METRO_ISTANBUL_MODLARI))
    }
    seferler = {t["trip_id"]: t for t in tablolar["trips"] if t.get("route_id") in rotalar}
    duraklar = {s["stop_id"]: s for s in tablolar["stops"]}

    sefer_duraklari = defaultdict(list)
    for st in tablolar["stop_times"]:
        if st.get("trip_id") not in seferler:
            continue
        try:
            sira = int(st.get("stop_sequence") or 0)
        except Exception:
            sira = 0
        sefer_duraklari[st["trip_id"]].append((sira, st))

    hat_seferleri = defaultdict(list)
    for trip_id, trip in seferler.items():
        hat_seferleri[trip["route_id"]].append(trip_id)

    frekanslar = defaultdict(list)
    for f in tablolar["frequencies"]:
        trip = seferler.get(f.get("trip_id"))
        if not trip:
            continue
        try:
            saniye = int(float(f.get("headway_secs") or 0))
        except Exception:
            saniye = 0
        if 120 <= saniye <= 3600:
            frekanslar[trip["route_id"]].append(saniye)

    cikti_hatlar = []
    kullanilan_duraklar = set()
    for route_id, route in sorted(rotalar.items(), key=lambda x: x[1].get("route_short_name", "")):
        adaylar = []
        for trip_id in hat_seferleri[route_id]:
            sirali = sorted(sefer_duraklari.get(trip_id, []), key=lambda x: x[0])
            benzersiz = []
            gorulen = set()
            for _, st in sirali:
                if st.get("stop_id") not in gorulen:
                    gorulen.add(st.get("stop_id")); benzersiz.append(st)
            adaylar.append((len(benzersiz), trip_id, benzersiz))
        if not adaylar:
            continue
        _, trip_id, secilen = max(adaylar, key=lambda x: x[0])
        if len(secilen) < 2:
            continue

        istasyonlar = []
        onceki_zaman = None
        for index, st in enumerate(secilen):
            stop = duraklar.get(st.get("stop_id"))
            if not stop:
                continue
            try:
                lat, lon = float(stop["stop_lat"]), float(stop["stop_lon"])
            except Exception:
                continue
            zaman = _saniye(st.get("departure_time") or st.get("arrival_time"))
            onceki_dk = None
            if onceki_zaman is not None and zaman is not None:
                fark = (zaman - onceki_zaman) / 60
                if 0.5 <= fark <= 15:
                    onceki_dk = round(fark, 1)
            onceki_zaman = zaman
            istasyonlar.append({
                "id": stop["stop_id"],
                "ad": stop.get("stop_name") or stop["stop_id"],
                "lat": round(lat, 6), "lon": round(lon, 6),
                "erisilebilir": stop.get("wheelchair_boarding") == "1",
                "onceki_dk": onceki_dk,
            })
            kullanilan_duraklar.add(stop["stop_id"])
        if len(istasyonlar) < 2:
            continue

        # Eksik zamanlarda istasyonlar arası muhafazakâr varsayım.
        for i in range(1, len(istasyonlar)):
            if istasyonlar[i]["onceki_dk"] is None:
                istasyonlar[i]["onceki_dk"] = 2.5

        freq = frekanslar.get(route_id) or []
        route_type = route.get("route_type")
        mod = ("marmaray" if route.get("agency_id") == "4"
               else METRO_ISTANBUL_MODLARI[route_type])
        varsayilan = 480 if mod == "marmaray" else (600 if mod in ("funikuler", "teleferik") else 360)
        headway = int(round(statistics.median(freq))) if freq else varsayilan
        cikti_hatlar.append({
            "id": route_id,
            # GTFS'teki Marmaray1/Marmaray2 adları servis varyantıdır; yolcuya
            # ürün markası olan tek "Marmaray" adı gösterilir.
            "kod": ("Marmaray" if route.get("agency_id") == "4"
                    else (route.get("route_short_name") or route_id)),
            "ad": route.get("route_long_name") or route.get("route_short_name") or route_id,
            "isletmeci": RAIL_AGENCIES[route["agency_id"]],
            "mod": mod,
            "renk": "#%s" % (route.get("route_color") or ("7b1f3a" if route["agency_id"] == "4" else "163b65")),
            "siklik_dk": max(2, min(30, round(headway / 60))),
            "istasyonlar": istasyonlar,
        })

    sonuc = {
        "surum": 2,
        "kaynak": "İBB Açık Veri · Toplu Ulaşım GTFS Verisi",
        "kaynak_url": "https://data.ibb.gov.tr/en/dataset/public-transport-gtfs-data",
        "metadata_guncelleme": paket.get("metadata_modified"),
        "not": "Planlı/statik raylı sistem verisidir; canlı araç konumu değildir.",
        "hatlar": cikti_hatlar,
    }
    OUTPUT.write_text(json.dumps(sonuc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{OUTPUT}: {len(cikti_hatlar)} hat, {len(kullanilan_duraklar)} istasyon kaydı")


if __name__ == "__main__":
    main()
