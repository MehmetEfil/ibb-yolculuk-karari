"""İBB GTFS verisinden planlı raylı sistem rota seçenekleri.

Bu modül canlı tren konumu üretmez. Hat sırası, istasyonlar arası planlı süre
ve sefer sıklığını kullanır; sonuçlarda veri niteliği açıkça belirtilir.
"""
from __future__ import annotations

import heapq
import json
import math
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "rayli_ag.json"
YURU_HIZ_KM_DK = 4.5 / 60.0
_AG = None


def _hav(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _yuru_dk(km):
    return max(1, int(round(km / YURU_HIZ_KM_DK)))


def _agi_yukle():
    global _AG
    if _AG is not None:
        return _AG
    try:
        veri = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        _AG = {"veri": {}, "dugumler": [], "kenarlar": {}}
        return _AG

    dugumler, kenarlar = [], {}
    for hat in veri.get("hatlar", []):
        onceki = None
        for sira, ist in enumerate(hat.get("istasyonlar", [])):
            idx = len(dugumler)
            dugumler.append({**ist, "hat": hat, "sira": sira})
            kenarlar[idx] = []
            if onceki is not None:
                sure = float(ist.get("onceki_dk") or 2.5)
                mesafe = _hav(dugumler[onceki]["lat"], dugumler[onceki]["lon"],
                              ist["lat"], ist["lon"])
                bilgi = {"tip": "rayli", "sure": sure, "mesafe_km": mesafe}
                kenarlar[onceki].append((idx, sure, bilgi))
                kenarlar[idx].append((onceki, sure, bilgi))
            onceki = idx

    # Aynı aktarma kompleksi içindeki yakın istasyon kayıtlarını yaya bağla.
    for i, a in enumerate(dugumler):
        for j in range(i + 1, len(dugumler)):
            b = dugumler[j]
            if a["hat"]["id"] == b["hat"]["id"]:
                continue
            if a["hat"]["mod"] == b["hat"]["mod"] == "marmaray":
                continue
            mesafe = _hav(a["lat"], a["lon"], b["lat"], b["lon"])
            if mesafe > 0.35:
                continue
            yuru = _yuru_dk(mesafe)
            # Hedef hatta geçişte ortalama yarım sefer aralığı beklenir.
            ab = yuru + max(1, round(b["hat"]["siklik_dk"] / 2))
            ba = yuru + max(1, round(a["hat"]["siklik_dk"] / 2))
            kenarlar[i].append((j, ab, {"tip": "aktarma", "yuru_dk": yuru,
                                        "mesafe_km": mesafe}))
            kenarlar[j].append((i, ba, {"tip": "aktarma", "yuru_dk": yuru,
                                        "mesafe_km": mesafe}))

    _AG = {"veri": veri, "dugumler": dugumler, "kenarlar": kenarlar}
    return _AG


def rayli_rota_alternatifleri(kaynak_lat, kaynak_lon, hedef_lat, hedef_lon,
                              max_yuru_km=1.8, limit=1):
    """Yürüme + raylı sistem (+ raylı aktarma) seçeneği döndürür."""
    if None in (kaynak_lat, kaynak_lon, hedef_lat, hedef_lon):
        return []
    ag = _agi_yukle()
    dugumler, kenarlar = ag["dugumler"], ag["kenarlar"]
    if not dugumler:
        return []

    baslar, bitisler = [], {}
    for i, d in enumerate(dugumler):
        a_km = _hav(kaynak_lat, kaynak_lon, d["lat"], d["lon"])
        b_km = _hav(hedef_lat, hedef_lon, d["lat"], d["lon"])
        if a_km <= max_yuru_km:
            bekleme = max(1, round(d["hat"]["siklik_dk"] / 2))
            baslar.append((i, _yuru_dk(a_km) + bekleme, a_km, bekleme))
        if b_km <= max_yuru_km:
            bitisler[i] = b_km
    if not baslar or not bitisler:
        return []

    uzaklik, onceki, kuyruk = {}, {}, []
    bas_bilgi = {}
    for i, maliyet, km, bekleme in baslar:
        durum = (i, False)  # False: henüz bir raylı segment kullanılmadı
        if maliyet < uzaklik.get(durum, float("inf")):
            uzaklik[durum] = maliyet
            bas_bilgi[durum] = (km, bekleme)
            heapq.heappush(kuyruk, (maliyet, i, False, i))

    secilen = None
    while kuyruk:
        maliyet, u, rayli_kullanildi, bas = heapq.heappop(kuyruk)
        durum = (u, rayli_kullanildi)
        if maliyet != uzaklik.get(durum):
            continue
        # Kısa F/TF hatlarında iki uç birbirine 1,8 km'den yakın olabilir.
        # Sadece yürüyüşlü yolun raylı seçeneği bastırmasına izin verme.
        if u in bitisler and rayli_kullanildi:
            secilen = (durum, bas, maliyet + _yuru_dk(bitisler[u]))
            break
        for v, agirlik, bilgi in kenarlar[u]:
            yeni = maliyet + agirlik
            yeni_rayli = rayli_kullanildi or bilgi["tip"] == "rayli"
            yeni_durum = (v, yeni_rayli)
            if yeni < uzaklik.get(yeni_durum, float("inf")):
                uzaklik[yeni_durum] = yeni
                onceki[yeni_durum] = (durum, bilgi)
                bas_bilgi[yeni_durum] = bas_bilgi.get(durum, bas_bilgi.get((bas, False)))
                heapq.heappush(kuyruk, (yeni, v, yeni_rayli, bas))
    if secilen is None:
        return []

    son_durum, bas, toplam = secilen
    son = son_durum[0]
    durum_yolu = [son_durum]
    kenar_yolu = []
    while durum_yolu[-1] != (bas, False):
        kayit = onceki.get(durum_yolu[-1])
        if not kayit:
            return []
        onceki_durum, bilgi = kayit
        kenar_yolu.append(bilgi)
        durum_yolu.append(onceki_durum)
    durum_yolu.reverse(); kenar_yolu.reverse()
    yol = [d[0] for d in durum_yolu]

    # Raylı kenarları aynı hat üzerinde yolculuk gruplarına ayır.
    gruplar, aktif = [], None
    aktarma_yuruyusleri = []
    for pos, bilgi in enumerate(kenar_yolu):
        u, v = yol[pos], yol[pos + 1]
        if bilgi["tip"] == "aktarma":
            if aktif:
                gruplar.append(aktif); aktif = None
            aktarma_yuruyusleri.append(int(bilgi["yuru_dk"]))
            continue
        hat = dugumler[u]["hat"]
        if aktif is None or aktif["hat"]["id"] != hat["id"]:
            if aktif:
                gruplar.append(aktif)
            aktif = {"hat": hat, "bas": u, "son": v, "sure": 0.0,
                     "km": 0.0, "koordinatlar": [[dugumler[u]["lat"], dugumler[u]["lon"]]]}
        aktif["son"] = v
        aktif["sure"] += float(bilgi["sure"])
        aktif["km"] += float(bilgi["mesafe_km"])
        aktif["koordinatlar"].append([dugumler[v]["lat"], dugumler[v]["lon"]])
    if aktif:
        gruplar.append(aktif)
    if not gruplar or len(gruplar) > 3:
        return []

    bas_km, ilk_bekleme = bas_bilgi.get(son_durum, bas_bilgi.get((bas, False), (0, 0)))
    son_km = bitisler[son]
    segmentler, adimlar, geometri = [], [], []
    for i, grup in enumerate(gruplar):
        h, b, s = grup["hat"], dugumler[grup["bas"]], dugumler[grup["son"]]
        bekleme = ilk_bekleme if i == 0 else max(1, round(h["siklik_dk"] / 2))
        segmentler.append({
            "tip": "sefer", "mod": h["mod"], "hat": h["kod"],
            "bekleme_dk": int(bekleme), "sefer_dk": max(1, int(round(grup["sure"]))),
            "bekleme_kaynak": "planli", "bekleme_detay": "İBB GTFS planlı sefer sıklığı",
            "mesafe_km": round(grup["km"], 2), "mesafe_kaynak": "gtfs_istasyon_zinciri",
            "trafik_gecikme_dk": 0,
        })
        adimlar.append({"tip": "bin", "hat": h["kod"], "mod": h["mod"],
                        "durak": b["id"], "lat": b["lat"], "lon": b["lon"]})
        geometri.append({"hat": h["kod"], "mod": h["mod"], "renk": h["renk"],
                         "koordinatlar": grup["koordinatlar"]})

    ilk, son_d = dugumler[gruplar[0]["bas"]], dugumler[gruplar[-1]["son"]]
    detay = {
        "baslangic_lat": kaynak_lat, "baslangic_lon": kaynak_lon,
        "bitis_lat": hedef_lat, "bitis_lon": hedef_lon,
        "b_kodu": ilk["id"], "b_durak": ilk["ad"], "b_lat": ilk["lat"], "b_lon": ilk["lon"],
        "i_kodu": son_d["id"], "i_durak": son_d["ad"], "i_lat": son_d["lat"], "i_lon": son_d["lon"],
    }
    for i in range(1, len(gruplar)):
        onceki_son = dugumler[gruplar[i - 1]["son"]]
        yeni_bas = dugumler[gruplar[i]["bas"]]
        pf = "a" if i == 1 else f"a{i}"
        detay.update({f"{pf}_kodu": yeni_bas["id"],
                      f"{pf}_durak": (onceki_son["ad"] if onceki_son["ad"] == yeni_bas["ad"]
                                        else f"{onceki_son['ad']} → {yeni_bas['ad']}"),
                      f"{pf}_lat": yeni_bas["lat"], f"{pf}_lon": yeni_bas["lon"]})

    hatlar = [g["hat"]["kod"] for g in gruplar]
    mod_adi = {"marmaray": "Marmaray", "metro": "Metro", "tramvay": "Tramvay",
               "funikuler": "Füniküler", "teleferik": "Teleferik"}
    mod_adlari = [mod_adi.get(g["hat"]["mod"], "Raylı sistem") for g in gruplar]
    aciklama = " → ".join(f"{m} {h}" for m, h in zip(mod_adlari, hatlar))
    rota = {
        "tip": "rayli" if len(gruplar) == 1 else "rayli_aktarma",
        "hatlar": hatlar, "modlar": [g["hat"]["mod"] for g in gruplar],
        "toplam_sure": int(round(toplam)), "aciklama": aciklama,
        "adimlar": adimlar, "detay": detay,
        "sure_kirilim": {"yuruyu_a_dk": _yuru_dk(bas_km), "yuruyu_b_dk": _yuru_dk(son_km),
                           "aktarma_yuruyu_dklar": aktarma_yuruyusleri,
                           "segmentler": segmentler},
        "canli": None, "planli": True, "erisim": [], "erisim_sorunlu": 0,
        "rayli_geometri": geometri,
        "rayli_kaynak": {"ad": ag["veri"].get("kaynak"),
                           "guncelleme": ag["veri"].get("metadata_guncelleme"),
                           "not": ag["veri"].get("not")},
    }
    return [rota][:limit]
