# -*- coding: utf-8 -*-
"""Araç bazlı karbon — yakıt türü dikkate alınıyor mu?

Filo tek yakıtlı değil (smart_maintenance.json, 3.509 araç):
    MOTORIN 3.041 (%86,7) · CNG 348 (%9,9) · BİLİNMİYOR 119 · ELEKTRİK 1

Yani her 10 araçtan biri motorin yakmıyor. Rota önerilen aracın kapı numarası
canlı GPS'ten geliyor ve o araca ait marka/model/yakıt elimizde; "ortalama
otobüs" yerine gerçek aracın emisyonu verilebilir.

Bu testler o katmanın doğru çalıştığını ve **uydurma yapmadığını** korur.
"""
import pytest


def _kapi_bul(svc, yakit=None, cins=None):
    idx = (svc.PANEL_DATA or {}).get("_sm_idx") or {}
    for kapi, a in idx.items():
        if yakit and str(a.get("yakit_turu", "")).upper() != yakit:
            continue
        if cins and str(a.get("arac_cinsi", "")).upper() != cins:
            continue
        return kapi
    return None


def test_filoda_tek_yakit_yok(svc):
    """Varsayımın temeli: filo gerçekten karma. Tek yakıta düşerse bu
    katmanın gerekçesi kalmaz — o zaman testi değil kodu gözden geçir."""
    idx = (svc.PANEL_DATA or {}).get("_sm_idx") or {}
    assert idx, "filo indeksi yüklenmemiş"
    yakitlar = {str(a.get("yakit_turu", "")).upper() for a in idx.values()}
    assert "MOTORIN" in yakitlar
    assert "CNG" in yakitlar, "CNG araç kalmamış — karbon katmanını gözden geçir"


def test_bilinmeyen_arac_none_doner(svc):
    """Uydurma yok: filoda olmayan araç için tahmin üretilmez."""
    assert svc.arac_karbon_bilgisi("BOYLE_BIR_KAPI_YOK") is None
    assert svc.arac_karbon_bilgisi("") is None
    assert svc.arac_karbon_bilgisi(None) is None


def test_motorin_solo_taban_deger(svc):
    """Motorin solo = türetilmiş taban (800). Yakıt çarpanı 1,00."""
    kapi = _kapi_bul(svc, "MOTORIN", "SOLO")
    b = svc.arac_karbon_bilgisi(kapi)
    assert b["g_km"] == pytest.approx(svc.KARBON_SOLO_G_KM, abs=1)
    assert b["yakit"] == "MOTORIN"


def test_motorin_koruklu_taban_deger(svc):
    kapi = _kapi_bul(svc, "MOTORIN", "KORUKLU")
    b = svc.arac_karbon_bilgisi(kapi)
    assert b["g_km"] == pytest.approx(svc.KARBON_KORUKLU_G_KM, abs=1)


def test_cng_motorinden_temiz_ama_makul(svc):
    """CNG dizelden temiz olmalı — ama abartılı değil.

    IPCC enerji tabanlı oran 0,757; CNG motorunun verim kaybı (%17,5)
    uygulanınca net ~%11. Aradaki fark %5–20 bandının dışına çıkarsa
    varsayım kaymış demektir."""
    cng = svc.arac_karbon_bilgisi(_kapi_bul(svc, "CNG"))
    mot = svc.arac_karbon_bilgisi(_kapi_bul(svc, "MOTORIN", "SOLO"))
    assert cng["yakit"] == "CNG"
    assert cng["g_km"] < mot["g_km"], "CNG dizelden temiz çıkmıyor"
    fark = (mot["g_km"] - cng["g_km"]) / mot["g_km"] * 100
    assert 5 <= fark <= 20, "CNG/dizel farkı %%%.1f — varsayım kaymış" % fark


def test_elektrikli_sebeke_faktorunden(svc):
    """Elektrikli araç şebeke karbonundan hesaplanmalı, sıfır sayılmamalı.

    'Elektrikli = temiz' kestirmesi Türkiye şebekesi için yanlış:
    442 gCO₂e/kWh gerçek bir maliyet."""
    kapi = _kapi_bul(svc, "ELEKTRIK")
    if not kapi:
        pytest.skip("filoda elektrikli araç yok")
    b = svc.arac_karbon_bilgisi(kapi)
    beklenen = svc.KARBON_ELEKTRIK_KWH_KM * svc.KARBON["sebeke_g_kwh"]
    assert b["g_km"] == pytest.approx(beklenen, rel=0.01)
    assert b["g_km"] > 0, "elektrikli araç sıfır emisyon sayılmış"
    assert b["g_km"] < svc.KARBON_SOLO_G_KM, "elektrikli dizelden temiz olmalı"


def test_yakiti_bilinmeyen_arac_uydurmuyor(svc):
    """Yakıt alanı 'BİLİNMİYOR' olan araçta tahmin üretilmez, filo
    ortalamasına düşülür ve bu açıkça yazılır."""
    kapi = _kapi_bul(svc, "BILINMIYOR")
    if not kapi:
        pytest.skip("yakıtı bilinmeyen araç yok")
    b = svc.arac_karbon_bilgisi(kapi)
    assert b["yakit"] == "BİLİNMİYOR"
    assert "bilinmiyor" in b["kaynak"].lower()


def test_marka_model_tasiniyor(svc):
    """Yolcuya 'hangi araca biniyorsun' diyebilmek için marka/model gelmeli."""
    b = svc.arac_karbon_bilgisi(_kapi_bul(svc, "MOTORIN", "SOLO"))
    assert b["marka"], "marka bilgisi yok"
    assert b["model"], "model bilgisi yok"


def test_rota_karbonu_araci_kullaniyor(svc):
    """karbon_otobus_g, kapı numarası verilince o aracın yakıtını dikkate
    almalı. Aynı mesafede CNG araç, motorinden az CO₂ üretmeli."""
    cng = _kapi_bul(svc, "CNG")
    mot = _kapi_bul(svc, "MOTORIN", "SOLO")
    g_cng = svc.karbon_otobus_g(10.0, hat="34G", doluluk=0.4, kapi_no=cng)
    g_mot = svc.karbon_otobus_g(10.0, hat="34G", doluluk=0.4, kapi_no=mot)
    assert g_cng < g_mot, "kapı numarası karbon hesabına yansımıyor"


def test_kapisiz_cagri_eski_davranisi_koruyor(svc):
    """Araç bilinmiyorsa hesap eskisi gibi hat ortalamasından yürümeli —
    yeni katman mevcut davranışı bozmamalı."""
    a = svc.karbon_otobus_g(10.0, hat="34G", doluluk=0.4)
    b = svc.karbon_otobus_g(10.0, hat="34G", doluluk=0.4, kapi_no=None)
    assert a == pytest.approx(b)
    assert a > 0


def test_arac_ozellik_uydurmuyor(svc, monkeypatch):
    """Servis yanıt vermediğinde 'Dizel' uydurulmamalı.

    REGRESYON: eski hâli her araç için `yakit_tipi: "Dizel", kapasite: 90`
    döndürüyordu. `GetAracOzellikleriIETT_json` erişimimiz olmayan bir metot
    (her çağrıda HTTP 500), dolayısıyla o dal HER ZAMAN çalışıyordu — tüm
    filo "Dizel" görünüyordu, %9,9'u CNG olmasına rağmen.
    """
    monkeypatch.setattr(svc, "fetch_soap", lambda *a, **k: None)
    with svc._lock:
        svc.ARAC_OZELLIK_CACHE.pop("TEST_KAPI", None)

    o = svc.get_arac_ozellik("TEST_KAPI")
    assert o["veri_var"] is False, "bilinmeyen veri 'gerçek' olarak işaretlenmiş"
    assert o["yakit_tipi"] == "—", (
        "servis yanıt vermezken yakıt uyduruluyor: %r" % o["yakit_tipi"])
    assert o["kapasite"] is None, "kapasite uyduruluyor: %r" % o["kapasite"]
