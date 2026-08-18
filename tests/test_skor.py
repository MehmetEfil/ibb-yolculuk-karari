# -*- coding: utf-8 -*-
"""Güvenilirlik skoru — formülün ve normalizasyonun bozulmadığını korur.

Skor projenin adını taşıyan özellik. Ağırlıklar ve normalizasyon fikirle değil
ölçümle seçildi (dakiklik denendi, hatları ayırt etmediği için elendi); bir
refactor sırasında sessizce değişmemeli.
"""
from datetime import datetime, timedelta

import pytest

import skor


def _gorev(hat, plan, gercek_dk=None, durum="T"):
    """skor.ham_metrikler'in beklediği biçimde tek sefer kaydı.

    Alan adları arşiv servisinin kendi şeması: DTBASLAMAZAMANI (gerçek kalkış),
    DTBITISZAMANI (gerçek varış), DTPLANLANANBASLANGICZAMANI (plan).
    """
    kayit = {
        "SHATKODU": hat,
        "DTPLANLANANBASLANGICZAMANI": plan.strftime("%Y-%m-%d %H:%M:%S"),
        "SGOREVDURUM": durum,
    }
    if gercek_dk is not None:
        kayit["DTBASLAMAZAMANI"] = plan.strftime("%Y-%m-%d %H:%M:%S")
        kayit["DTBITISZAMANI"] = (
            plan + timedelta(minutes=gercek_dk)).strftime("%Y-%m-%d %H:%M:%S")
    return kayit


def test_agirliklar_45_30_25(svc=None):
    """Ağırlıklar toplamı 100 ve dağılım belgelenen değerde."""
    assert skor.AGIRLIK["sure"] == 45.0
    assert skor.AGIRLIK["gerceklesme"] == 30.0
    assert skor.AGIRLIK["duzenlilik"] == 25.0
    assert sum(skor.AGIRLIK.values()) == 100.0


def test_normalize_ucu_kirpiyor():
    """p5–p95 dışındaki uçlar kırpılmalı; tek aykırı hat ölçeği bozmamalı."""
    assert skor._normalize(0, 10, 90) == 0.0
    assert skor._normalize(100, 10, 90) == 1.0
    assert skor._normalize(50, 10, 90) == pytest.approx(0.5, abs=0.01)


def test_normalize_ters_yon():
    """Yayılım ve düzensizlik için büyük = kötü; ters=True bunu çevirir."""
    duz = skor._normalize(90, 10, 90, ters=True)
    kotu = skor._normalize(10, 10, 90, ters=True)
    assert duz == pytest.approx(0.0, abs=0.01)
    assert kotu == pytest.approx(1.0, abs=0.01)


def test_gerceklesme_iptali_yakaliyor():
    """Planlanan seferin yapılmaması gerçekleşme metriğine düşmeli."""
    t0 = datetime(2026, 7, 31, 8, 0)
    gorevler = []
    for i in range(10):
        p = t0 + timedelta(minutes=15 * i)
        # 10 seferin 3'ü iptal
        gorevler.append(_gorev("TEST1", p, 40 if i >= 3 else None,
                               durum="T" if i >= 3 else "I"))

    ham = skor.ham_metrikler(gorevler)
    assert "TEST1" in ham
    assert ham["TEST1"]["gerceklesme"] == pytest.approx(0.7, abs=0.01)


def test_duzenlilik_kumelenmeyi_yakaliyor():
    """Düzenlilik = ardışık kalkış aralıklarının σ/μ.

    Sefer SAYISI aynı olsa bile araçlar kümeleniyorsa yolcu boşuna bekler.
    Eşit aralıklı hat ile kümelenen hat aynı puanı ALMAMALI."""
    t0 = datetime(2026, 7, 31, 6, 0)

    duzenli = [_gorev("DUZENLI", t0 + timedelta(minutes=10 * i), 40)
               for i in range(12)]
    # aynı sefer sayısı, ama ikişerli kümelenmiş
    kumeli = []
    an = t0
    for i in range(12):
        kumeli.append(_gorev("KUMELI", an, 40))
        an += timedelta(minutes=2 if i % 2 == 0 else 18)

    h_duz = skor.ham_metrikler(duzenli)["DUZENLI"]
    h_kum = skor.ham_metrikler(kumeli)["KUMELI"]

    assert h_duz["duzensizlik"] == pytest.approx(0.0, abs=0.05)
    assert h_kum["duzensizlik"] > 0.4, "kümelenme yakalanmıyor"
    assert h_kum["duzensizlik"] > h_duz["duzensizlik"]


def test_skor_bilesenlerin_toplami(svc):
    """Toplam skor, üç bileşenin toplamına eşit olmalı — canlı veriyle.

    Formül parçalanıp yeniden birleştirildiğinde tutmuyorsa skor
    açıklanabilir değildir; ürünün 'sayı değil gerekçe' iddiası düşer."""
    import routes  # noqa: F401  (uç kaydı için gerekmez, sadece modül sağlığı)

    # diskteki arşivden hesaplanmış skorlar yerine formülün kendisini sına
    t0 = datetime(2026, 7, 31, 7, 0)
    gorevler = []
    for hat, aralik, sure in (("A1", 10, 30), ("B2", 25, 55), ("C3", 7, 20)):
        an = t0
        for i in range(15):
            gorevler.append(_gorev(hat, an, sure + (i % 5)))
            an += timedelta(minutes=aralik)

    sonuc = skor.skorla(gorevler)
    assert sonuc, "skorla() boş döndü"

    for hat, v in sonuc.items():
        k = v["kirilim"]
        toplam = (k["sure_tutarliligi"]["puan"]
                  + k["sefer_gerceklesme"]["puan"]
                  + k["duzenlilik"]["puan"])
        assert v["skor"] == pytest.approx(toplam, abs=0.15), (
            "%s: skor %.1f ama bileşenler %.1f" % (hat, v["skor"], toplam)
        )
        # hiçbir bileşen tavanını aşmamalı
        assert k["sure_tutarliligi"]["puan"] <= 45.001
        assert k["sefer_gerceklesme"]["puan"] <= 30.001
        assert k["duzenlilik"]["puan"] <= 25.001
        assert 0 <= v["skor"] <= 100


def test_harf_esikleri_monoton():
    """Yüksek skor daha iyi harf almalı."""
    sirali = [skor._harf(s) for s in (95, 80, 65, 50, 20)]
    assert sirali == sorted(sirali), "harf eşikleri monoton değil: %s" % sirali
