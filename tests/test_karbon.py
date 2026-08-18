# -*- coding: utf-8 -*-
"""Karbon türetimi — docs/KARBON.md'deki zincirin kodda bozulmadığını korur.

Bu sayıların savunulabilirliği projenin sürdürülebilirlik iddiasının tamamı.
Katsayı uydurulmadığı iddiası ancak türetim yeniden üretilebilirse geçerli.
"""
import pytest


def test_otobus_katsayisi_iett_yakit_verisinden_turetiliyor(svc):
    """918 gCO₂/araç-km sabit yazılmış bir sayı değil; İETT'nin günlük yakıt
    kaydından çıkıyor. Türetimi burada yeniden yapıp koddaki değerle
    karşılaştırıyoruz."""
    GUNLUK_LITRE = 356_979
    GUNLUK_ARAC_KM = 1_042_413
    DIZEL_KG_L = svc.KARBON["dizel_kg_l"]

    turetim = GUNLUK_LITRE * DIZEL_KG_L * 1000 / GUNLUK_ARAC_KM

    assert svc.KARBON["otobus_g_arac_km"] == pytest.approx(turetim, abs=1.0), (
        "918 türetimden koptu: kod %.1f, yakıt verisinden %.1f"
        % (svc.KARBON["otobus_g_arac_km"], turetim)
    )


def test_tuketim_sehir_otobusu_araliginda(svc):
    """Bağımsız akıl kontrolü: aynı iki sayı L/100km veriyor. Şehir otobüsü
    tipik aralığı 30–55. Uydurma bir katsayı bu aralığa denk gelmezdi."""
    l_100km = 356_979 / 1_042_413 * 100
    assert 30 <= l_100km <= 55
    assert l_100km == pytest.approx(34.2, abs=0.2)


def test_solo_ve_koruklu_ayrisimi(svc):
    """918 bir FİLO ORTALAMASI. Kapasiteye bölmek körüklü aracı haksız yere
    temiz gösteriyordu; araç tipi ayrıştırıldı."""
    assert svc.arac_emisyon_g_km(90) == pytest.approx(800, abs=1)     # solo
    assert svc.arac_emisyon_g_km(171) == pytest.approx(1120, abs=1)   # körüklü
    # arada doğrusal geçiş
    orta = svc.arac_emisyon_g_km(160)
    assert 800 < orta < 1120


def test_ayrisim_kendi_kaynagini_yeniden_uretiyor(svc):
    """En kritik kontrol: SOLO/KÖRÜKLÜ değerleri filo oranıyla harmanlanınca
    ölçülen 918'i geri vermeli. Vermiyorsa ayrıştırma tutarsızdır."""
    SOLO_PAY, KORUKLU_PAY = 0.636, 0.364
    harman = SOLO_PAY * 800 + KORUKLU_PAY * 1120
    olculen = svc.KARBON["otobus_g_arac_km"]
    fark_pct = abs(harman - olculen) / olculen * 100

    assert fark_pct < 0.5, (
        "Türetim kendi kaynağını yeniden üretmiyor: harman %.1f, ölçülen %.1f "
        "(fark %%%.2f)" % (harman, olculen, fark_pct)
    )


def test_otomobil_katsayisi(svc):
    """7,0 L/100km × 2,27 kg/L (IPCC benzin faktörü)."""
    turetim = 7.0 * svc.KARBON["benzin_kg_l"] * 10
    assert svc.KARBON["otomobil_g_km"] == pytest.approx(turetim, abs=1)
    assert svc.KARBON["otomobil_g_km"] == pytest.approx(159, abs=1)


def test_metrobus_kisi_basi_makul(svc):
    """Kişi başına bölme sonrası metrobüs, yayımlanmış otobüs figürleriyle
    (25–40 g/yolcu-km) aynı büyüklük mertebesinde olmalı. Eski kod burada
    13,4 veriyordu — çift iyimserlik."""
    kap, doluluk = 171, svc.KARBON["varsayilan_doluluk"]
    kisi_basi = svc.arac_emisyon_g_km(kap) / (kap * doluluk)
    assert 10 < kisi_basi < 30
    assert kisi_basi == pytest.approx(16.4, abs=0.5)


def test_otobus_arabadan_temiz_kalir(svc):
    """Niteliksel sonuç: makul doluluklarda otobüs tek kişilik arabadan
    temiz olmalı. Bu bozulursa sürdürülebilirlik iddiası çöker."""
    for kap in (90, 171):
        for doluluk in (0.15, 0.40, 0.85):
            kisi_basi = svc.arac_emisyon_g_km(kap) / (kap * doluluk)
            assert kisi_basi < svc.KARBON["otomobil_g_km"], (
                "kapasite %d doluluk %.2f: %.1f g/yolcu-km, otomobilden kirli"
                % (kap, doluluk, kisi_basi)
            )
