# -*- coding: utf-8 -*-
"""Rota hesabını profille — darboğaz nerede?

Kullanım:
    python scripts/profil_rota.py

Canlı servise çıkmaz: sadece diskteki veriyle çalışan saf hesap yolunu
ölçer. Amaç "yavaş" hissini sayıya çevirmek ve hangi fonksiyonun
zamanı yediğini görmek.
"""
import cProfile
import io as _io
import json
import os
import pstats
import sys
import time

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HERE)
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# .env kosulsuz acilirsa temiz klon FileNotFoundError ile coker: dosya
# .gitignore'da, yani depoyu indiren kimsede yok. app.py ile ayni koruma.
_ENV = os.path.join(_HERE, ".env")
if os.path.exists(_ENV):
    for satir in open(_ENV, encoding="utf-8"):
        satir = satir.strip()
        if satir and "=" in satir and not satir.startswith("#"):
            k, _, v = satir.partition("=")
            os.environ[k.strip()] = v.strip()

import services as s  # noqa: E402


def veri_yukle():
    t = time.perf_counter()
    s.load_panel_data()
    s.load_hat_profil()
    s.sira_diskten_yukle()
    with open(os.path.join(_HERE, "memory_db.json"), encoding="utf-8") as f:
        ham = json.load(f)
    with s._lock:
        s.MEMORY_DB.clear()
        s.MEMORY_DB.update({k: set(v) for k, v in ham.items()})
        s.IS_DB_READY = True
    with open(os.path.join(_HERE, "durak_dict.json"), encoding="utf-8") as f:
        s.DURAK_DICT.update(json.load(f))
    s.build_durak_komsu()
    print("veri yükleme: %.2f sn\n" % (time.perf_counter() - t))


def _ag_kapat():
    """Profil sırasında canlı çağrı olmasın — hem kota hem ölçüm gürültüsü."""
    def yasak(*a, **k):
        raise RuntimeError("ağ kapalı")
    s.fetch_soap = yasak
    s.fetch_soap_xml = yasak
    # trafik: sabit katsayı
    s.ibb_trafik_katsayi = lambda *a, **k: 1.0
    s.saat_trafik_katsayi = lambda *a, **k: 1.0


ROTALAR = [
    ("AVCILAR", "ZINCIRLIKUYU"),
    ("BAKIRKOY", "USKUDAR"),
    ("MECIDIYEKOY", "KADIKOY"),
    ("AKIK SITESI", "TAKSIM"),
]


def _koordinat(ad):
    """Durak adından koordinat — arama yolunu profilin dışında tut."""
    ad = ad.upper()
    for k, v in s.DURAK_DICT.items():
        if ad in str(v.get("ad", "")).upper():
            return v["lat"], v["lon"], v.get("ad")
    return None


def olc():
    import routes  # noqa: F401
    from flask import Flask
    app = Flask(__name__, template_folder=os.path.join(_HERE, "templates"))
    routes.register_routes(app, None)
    istemci = app.test_client()

    # ISINMA — durak arama indeksi ilk sorguda kuruluyor. Onu ölçüme
    # katmak yanıltıcı: gerçek kullanımda bir kez ödenir.
    t = time.perf_counter()
    istemci.get("/api/nasil_gidilir?nereden=AVCILAR&nereye=TAKSIM")
    print("ısınma (indeks kurulumu dahil): %.2f sn\n" % (time.perf_counter() - t))

    print("=== TEK TEK SÜRELER (ısınmış) ===")
    sureler = {}
    for a, b in ROTALAR:
        # her rota 3 kez, en iyisi alınır — ölçüm gürültüsünü kırpar
        en_iyi, adet = None, 0
        for _ in range(3):
            t = time.perf_counter()
            r = istemci.get("/api/nasil_gidilir?nereden=%s&nereye=%s" % (a, b))
            gecen = time.perf_counter() - t
            en_iyi = gecen if en_iyi is None else min(en_iyi, gecen)
        try:
            veri = r.get_json()
            adet = len(veri if isinstance(veri, list) else veri.get("rotalar", []))
        except Exception:
            pass
        sureler["%s→%s" % (a, b)] = en_iyi
        print("  %-26s %6.3f sn  (%d rota)" % ("%s→%s" % (a, b), en_iyi, adet))

    print("\n  toplam %.2f sn · ortalama %.3f sn · en yavaş %.3f sn"
          % (sum(sureler.values()), sum(sureler.values()) / len(sureler),
             max(sureler.values())))

    print("\n=== PROFİL (en pahalı 22 fonksiyon) ===")
    pr = cProfile.Profile()
    pr.enable()
    for a, b in ROTALAR:
        istemci.get("/api/nasil_gidilir?nereden=%s&nereye=%s" % (a, b))
    pr.disable()

    akis = _io.StringIO()
    pstats.Stats(pr, stream=akis).sort_stats("cumulative").print_stats(22)
    metin = akis.getvalue()
    bas = metin.find("ncalls")
    print(metin[bas:bas + 2600] if bas > 0 else metin[:2600])


if __name__ == "__main__":
    veri_yukle()
    _ag_kapat()
    olc()
