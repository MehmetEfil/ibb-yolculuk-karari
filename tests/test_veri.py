# -*- coding: utf-8 -*-
"""Veri bütünlüğü — sunumda ve arayüzde geçen sayıların dayanağı.

Bu testler "veri hâlâ orada mı, hâlâ aynı mı" sorusunu yanıtlar. Bir JSON
yenilendiğinde sessizce bozulursa arayüz boş ekran gösterir ama hata vermez;
o sessiz bozulmayı burada yakalıyoruz.
"""
import pytest

# İstanbul'un kabaca sınırları — koordinat doğrulaması için
ENLEM = (40.75, 41.65)
BOYLAM = (27.90, 29.95)


def test_durak_sayisi(svc):
    assert len(svc.DURAK_DICT) == 15112, (
        "durak sayısı değişti: %d" % len(svc.DURAK_DICT))


def test_durak_koordinatlari_istanbul_icinde(svc):
    disarida = [k for k, v in svc.DURAK_DICT.items()
                if not (ENLEM[0] <= v.get("lat", 0) <= ENLEM[1]
                        and BOYLAM[0] <= v.get("lon", 0) <= BOYLAM[1])]
    assert not disarida, (
        "%d durağın koordinatı İstanbul dışında: %s"
        % (len(disarida), disarida[:5]))


def test_duraklarin_adi_var(svc):
    adsiz = [k for k, v in svc.DURAK_DICT.items() if not str(v.get("ad", "")).strip()]
    assert not adsiz, "%d durağın adı boş" % len(adsiz)


def test_erisilebilir_durak_orani(svc):
    """Ürünün kapsayıcılık iddiasının dayanağı: 853 / 15.112 = %5,6.

    Bu oran değişirse sunumdaki rakam da değişmeli — testin görevi
    sessizce kaymasını engellemek."""
    toplam = len(svc.DURAK_DICT)
    erisilebilir = sum(1 for v in svc.DURAK_DICT.values()
                       if str(v.get("engelli", "")).upper() == "TRUE")
    oran = erisilebilir / toplam * 100

    assert erisilebilir == 853, "erişilebilir durak sayısı değişti: %d" % erisilebilir
    assert oran == pytest.approx(5.6, abs=0.1), "oran %%%.2f" % oran


def test_hat_durak_grafigi_dolu(svc):
    assert len(svc.MEMORY_DB) > 13000, (
        "hat-durak grafiği eksik: %d durak" % len(svc.MEMORY_DB))


def test_yuruyerek_aktarma_indeksi_kuruldu(svc):
    """Metrobüsün grafikte 'ada' kalmasını çözen indeks. Kurulmazsa
    metrobüs ara aktarma olarak asla çıkamaz."""
    komsu = getattr(svc, "DURAK_KOMSU", None)
    assert komsu, "DURAK_KOMSU boş — yürüyerek aktarma indeksi kurulmamış"
    assert len(komsu) > 5000, "komşuluk indeksi beklenenden küçük: %d" % len(komsu)


def test_guzergah_geometrisi_yuklu(svc):
    geo = (svc.PANEL_DATA or {}).get("hat_guzergah_geo")
    assert geo, "güzergâh geometrisi yüklenmedi"
    assert len(geo) > 700, "güzergâh sayısı düşük: %d" % len(geo)


def test_hat_profili_yuklu(svc):
    """ETA modelinin kalibrasyon tablosu."""
    assert len(svc.HAT_PROFIL) > 700, (
        "hat profili eksik: %d hat" % len(svc.HAT_PROFIL))


def test_kapasite_verisi_metrobusu_ayirt_ediyor(svc):
    """Yüksek kapasiteli hat tespiti koda gömülü değil, veriden geliyor:
    kapasite >= 160 olan hatlar metrobüs ailesi. Bu bozulursa metrobüs
    iki kademeli havuzdan düşer ve rotalarda yine kaybolur."""
    kap = svc.HAT_KAPASITE or {}
    assert kap, "HAT_KAPASITE boş"
    yuksek = [h for h, v in kap.items() if (v or 0) >= 160]
    assert 3 <= len(yuksek) <= 20, (
        "yüksek kapasiteli hat sayısı beklenmedik: %d (%s)"
        % (len(yuksek), yuksek[:10]))


def test_rayli_ag_yuklu():
    """Raylı sistem GTFS ağı — otobüs dışı alternatifin kaynağı."""
    import json
    import os
    yol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "rayli_ag.json")
    with open(yol, encoding="utf-8") as f:
        d = json.load(f)
    hatlar = d.get("hatlar") or []
    assert len(hatlar) >= 20, "raylı servis sayısı düşük: %d" % len(hatlar)

    # hatlar bir liste: her eleman bir servis kaydı
    kayitlar = hatlar if isinstance(hatlar, list) else list(hatlar.values())
    istasyon = sum(len(k.get("istasyonlar", [])) for k in kayitlar)
    assert istasyon > 200, "istasyon sayısı düşük: %d" % istasyon
