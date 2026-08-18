# -*- coding: utf-8 -*-
"""Performans regresyonu — yapılan hızlandırmalar geri gelmesin.

Eşikler bilerek GENİŞ tutuldu: amaç makineden makineye değişen mutlak süreyi
ölçmek değil, **algoritmik gerileme**yi yakalamak. Önbellek kaldırılırsa ya da
arama yeniden bütün durakları taramaya başlarsa bu testler saniyeler mertebesine
çıkıp kırmızı yanar; normal dalgalanmada yanmaz.

Ölçülen iki gerileme:
  1. `hat_ring_mi` önbelleksizdi — tek rota isteğinde 31.152 kez çağrılıp
     aynı hesabı tekrarlıyordu (2,1 sn / 11,8 sn).
  2. Durak araması her sorguda 15.112 durağı yeniden token'lara ayırıyordu —
     istek başına 241.800 `_tokenize` çağrısı, rota hesabının %50'si.
"""
import time

import pytest
from flask import Flask


def test_ring_tespiti_onbellekli(svc):
    """Aynı hat için tekrar tekrar sorulduğunda hesap tekrarlanmamalı."""
    hatlar = list(svc.HAT_DURAK_SIRA)[:50]

    # ilk tur: önbellek dolar
    for h in hatlar:
        svc.hat_ring_mi(h)

    t = time.perf_counter()
    for _ in range(200):
        for h in hatlar:
            svc.hat_ring_mi(h)
    gecen = time.perf_counter() - t

    # 10.000 çağrı; önbellekliyse milisaniyeler sürer, değilse saniyeler
    assert gecen < 0.5, (
        "hat_ring_mi önbelleği çalışmıyor gibi: 10.000 çağrı %.2f sn" % gecen)


def test_ring_onbellegi_dogru_cevap_veriyor(svc):
    """Hız için doğruluktan ödün verilmediğini kanıtla: önbellekli sonuç,
    önbelleksiz gövdenin sonucuyla aynı olmalı."""
    for h in list(svc.HAT_DURAK_SIRA)[:120]:
        assert svc.hat_ring_mi(h) == svc._hat_ring_mi_hesapla(h), (
            "%s hattında önbellek yanlış cevap veriyor" % h)


def test_durak_aramasi_indeksli(svc):
    """Arama indeksi kurulduktan sonra sorgular ucuz olmalı."""
    app = Flask(__name__, template_folder="templates")
    import routes
    routes.register_routes(app, None)
    istemci = app.test_client()

    istemci.get("/api/durak_ara?q=avcilar")      # ısınma: indeks kurulur

    sorgular = ["avcilar", "kadikoy", "taksim", "levent", "sisli",
                "besiktas", "bakirkoy", "uskudar", "pendik", "kartal"]
    t = time.perf_counter()
    for _ in range(5):
        for q in sorgular:
            istemci.get("/api/durak_ara?q=" + q)
    gecen = time.perf_counter() - t

    # 50 arama; indekssizken her biri 15.112 durağı tokenize ederdi
    assert gecen < 3.0, "50 durak araması %.2f sn — indeks devre dışı mı?" % gecen


@pytest.mark.slow
def test_rota_hesabi_butce_icinde(svc):
    """Uçtan uca bütçe. Şehir içi rota hızlı, şehir aşırı rota daha ağır
    (raylı + çok aktarmalı arama) ama ikisi de kullanılabilir olmalı."""
    app = Flask(__name__, template_folder="templates")
    import routes
    routes.register_routes(app, None)
    istemci = app.test_client()

    istemci.get("/api/nasil_gidilir?nereden=AVCILAR&nereye=TAKSIM")  # ısınma

    olcumler = {}
    for a, b, butce in (("AVCILAR", "ZINCIRLIKUYU", 2.0),
                        ("MECIDIYEKOY", "KADIKOY", 2.0),
                        ("BAKIRKOY", "USKUDAR", 6.0)):
        en_iyi = None
        for _ in range(2):
            t = time.perf_counter()
            r = istemci.get("/api/nasil_gidilir?nereden=%s&nereye=%s" % (a, b))
            gecen = time.perf_counter() - t
            en_iyi = gecen if en_iyi is None else min(en_iyi, gecen)
            assert r.status_code == 200
        olcumler["%s→%s" % (a, b)] = en_iyi
        assert en_iyi < butce, (
            "%s→%s %.2f sn (bütçe %.1f sn) — arama gerilemiş olabilir"
            % (a, b, en_iyi, butce))

    print("\n  " + " · ".join("%s %.0f ms" % (k, v * 1000)
                              for k, v in olcumler.items()))
