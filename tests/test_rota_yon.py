# -*- coding: utf-8 -*-
"""Rota ve yön — geçmişte en çok hata bu alandan çıktı, hepsi burada kilitli.

Korunan düzeltmeler (CLAUDE.md "Rota planlayıcı — düzeltilmiş 4 hata"):
  1. Kapalı tur mesafesi — hatların %45,6'sında G kolu gidiş+dönüşü birlikte
     tutuyor; tek "en yakın köşe" yaklaşımı 0,18 km'lik mesafeyi 29,96 km
     hesaplıyordu.
  2. Yön doğrulaması — durak-hat eşlemesi yönü söylemiyor; araç B→A giderken
     A→B önerilebiliyordu.
  3. Peron — metrobüste her yön AYRI durak kaydı; dönüş peronunda bindirip
     gidiş peronunda indirmek fiziksel olarak imkânsız bir rota üretiyordu.
  4. Ring hatları — bir durak aynı yönde iki kez geçebilir; tek değer tutmak
     ilk geçişi kaybediyordu.
"""
import pytest


# ── 1. Sıra verisi bütünlüğü ──────────────────────────────────────────

def test_sira_verisi_yuklendi(svc):
    """837 hat kapsanıyor, eksik 0. Bu veri yön doğrulamasının temeli."""
    assert len(svc.HAT_DURAK_SIRA) >= 800, (
        "sıra verisi eksik: %d hat" % len(svc.HAT_DURAK_SIRA))


def test_sirano_listesi_ring_icin_coklu_deger_tutuyor(svc):
    """Ring hattında bir durak aynı yönde birden fazla sıraya sahip olabilir.
    Yapı liste olmalı; tek değere düşerse ring tespiti çöker."""
    ornek = next(iter(svc.HAT_DURAK_SIRA.values()))
    yon = next(iter(ornek.values()))
    for kod, sira in yon.items():
        assert isinstance(sira, list), (
            "durak %s sıra değeri liste değil: %r" % (kod, sira))
        break


def test_ring_hatlari_tespit_ediliyor(svc):
    """Şebekede ring hattı var; hiç bulunamıyorsa tespit bozulmuştur."""
    ringler = [h for h in list(svc.HAT_DURAK_SIRA)[:400] if svc.hat_ring_mi(h)]
    assert len(ringler) > 0, "hiç ring hattı tespit edilemedi"


# ── 2. Yön doğrulaması ────────────────────────────────────────────────

def test_yon_veri_yok_ile_yanlis_yon_ayri(svc):
    """KRİTİK: 'veri yok' (None) ile 'farklı yönde' (False) karıştırılmamalı.

    Karıştığında peron düzeltmesi hiç devreye girmiyordu — çünkü kod
    'karar veremedim' sanıp geçiyordu."""
    sonuc, _ = svc.yon_sirali_gecerli("BOYLE_BIR_HAT_YOK", "1", "2")
    assert sonuc is None, "bilinmeyen hat için None dönmeli, %r döndü" % sonuc


def test_ayni_yonde_ileri_gidis_gecerli(svc):
    """Aynı yönde sırası küçük → büyük olan çift geçerli olmalı."""
    for hat, yonler in list(svc.HAT_DURAK_SIRA.items())[:200]:
        for yon, duraklar in yonler.items():
            sirali = sorted(duraklar.items(), key=lambda kv: min(kv[1]))
            if len(sirali) < 6:
                continue
            binis, inis = sirali[1][0], sirali[4][0]
            gecerli, _ = svc.yon_sirali_gecerli(hat, binis, inis)
            assert gecerli is True, (
                "%s hattında %s→%s ileri yönde ama geçersiz sayıldı"
                % (hat, binis, inis))
            return
    pytest.skip("uygun test hattı bulunamadı")


def test_ters_yon_reddediliyor(svc):
    """Sırası büyük → küçük olan çift, ring DEĞİLSE reddedilmeli."""
    for hat, yonler in list(svc.HAT_DURAK_SIRA.items())[:300]:
        if svc.hat_ring_mi(hat):
            continue
        for yon, duraklar in yonler.items():
            sirali = sorted(duraklar.items(), key=lambda kv: min(kv[1]))
            if len(sirali) < 8:
                continue
            gecerli, _ = svc.yon_sirali_gecerli(hat, sirali[6][0], sirali[1][0])
            assert gecerli is False, (
                "%s hattında ters yön geçerli sayıldı" % hat)
            return
    pytest.skip("uygun test hattı bulunamadı")


# ── 3. Güzergâh mesafesi ──────────────────────────────────────────────

def test_guzergah_mesafesi_kus_ucusundan_kucuk_degil(svc):
    """Geometri ihlali: yol mesafesi kuş uçuşundan kısa olamaz.

    Kapalı tur hatalarında tam olarak bu oluyordu — yanlış kol eşleşince
    mesafe saçmalıyordu."""
    ihlal = []
    bakilan = 0
    for hat, yonler in list(svc.HAT_DURAK_SIRA.items()):
        if bakilan >= 40:
            break
        for yon, duraklar in yonler.items():
            kodlar = [k for k in duraklar if k in svc.DURAK_DICT]
            if len(kodlar) < 10:
                continue
            a, b = svc.DURAK_DICT[kodlar[2]], svc.DURAK_DICT[kodlar[8]]
            yol = svc.guzergah_mesafe_km(hat, a["lat"], a["lon"],
                                         b["lat"], b["lon"])
            if not yol:
                continue
            kus = svc.mesafe_km(a["lat"], a["lon"], b["lat"], b["lon"]) \
                if hasattr(svc, "mesafe_km") else None
            bakilan += 1
            if kus and yol < kus * 0.95:
                ihlal.append((hat, round(yol, 2), round(kus, 2)))
            break
    assert not ihlal, "geometri ihlali (yol < kuş uçuşu): %s" % ihlal[:5]


def test_kapali_tur_yakin_duraklar_makul_mesafe(svc):
    """Yan yana iki durak arası mesafe birkaç km'yi geçmemeli.

    Regresyon: 88A hattında gerçek 0,18 km olan çift eski yöntemde
    29,96 km hesaplanıyordu."""
    kotu = []
    bakilan = 0
    for hat, yonler in list(svc.HAT_DURAK_SIRA.items()):
        if bakilan >= 30:
            break
        for yon, duraklar in yonler.items():
            sirali = sorted(((k, min(v)) for k, v in duraklar.items()),
                            key=lambda kv: kv[1])
            sirali = [(k, s) for k, s in sirali if k in svc.DURAK_DICT]
            if len(sirali) < 5:
                continue
            (k1, _), (k2, _) = sirali[2], sirali[3]   # ardışık iki durak
            a, b = svc.DURAK_DICT[k1], svc.DURAK_DICT[k2]
            yol = svc.guzergah_mesafe_km(hat, a["lat"], a["lon"],
                                         b["lat"], b["lon"])
            bakilan += 1
            if yol and yol > 8:
                kotu.append((hat, k1, k2, round(yol, 1)))
            break
    assert not kotu, (
        "ardışık duraklar arası mesafe patlamış (kapalı tur hatası?): %s"
        % kotu[:5])


# ── 4. Hız tavanı ─────────────────────────────────────────────────────

def test_segment_hizi_gercekci(svc):
    """Emniyet supabı: bozuk profil kaydı 106 km/s gibi süreler üretmişti.
    Şebekede 50 km/s üstü segment olmamalı."""
    hizli = []
    for hat in list(svc.HAT_DURAK_SIRA)[:60]:
        for km in (5.0, 12.0, 18.6):
            # kats=1.0 verilir: aksi hâlde canlı trafik indeksi çağrılır.
            # Döner: (sure_dk, serbest_dk, gecikme_dk)
            sure, _serbest, _gecikme = svc.segment_sure_tahmini(hat, km, kats=1.0)
            if not sure or sure <= 0:
                continue
            hiz = km / (sure / 60.0)
            if hiz > 50:
                hizli.append((hat, km, round(hiz, 1)))
    assert not hizli, "50 km/s üstü segment: %s" % hizli[:5]


# ── Baslangic = hedef ───────────────────────────────────────────────────
# Olculdu: USKUDAR -> USKUDAR sorgusunda a_kod ve b_kod ayni (204931)
# oldugu halde 9 otobus rotasi ureliyordu — "12A ile 5 dk". Yolcu zaten
# orada. Tek tek rotalarda `b_kod == i_kod` korumasi vardi ama BASLANGIC
# ile HEDEFIN ayni olmasi hic kontrol edilmiyordu; havuzdaki komsu
# duraklar farkli oldugu icin rota "gecerli" gorunuyordu.

def test_ayni_durak_icin_otobus_onerilmez(svc):
    """Başlangıç ve hedef aynı durakken rota listesi boş dönmeli."""
    import routes
    from flask import Flask
    app = Flask(__name__, template_folder="templates")
    routes.register_routes(app, None)
    c = app.test_client()

    d = c.get("/api/nasil_gidilir",
              query_string={"nereden": "USKUDAR", "nereye": "USKUDAR"}).get_json()
    assert d.get("durum") == "ayni_yer", (
        "aynı durak için normal rota akışı çalışmış: durum=%s" % d.get("durum"))
    assert not d.get("rotalar"), (
        "yolcu zaten oradayken %d otobüs rotası önerildi" % len(d.get("rotalar") or []))
    assert d.get("mesaj"), "kullanıcıya açıklama verilmemiş"


def test_farkli_duraklar_normal_calisiyor(svc):
    """Aşırı filtreleme koruması: gerçek rota isteği etkilenmemeli."""
    import routes
    from flask import Flask
    app = Flask(__name__, template_folder="templates")
    routes.register_routes(app, None)
    c = app.test_client()

    d = c.get("/api/nasil_gidilir",
              query_string={"nereden": "AVCILAR", "nereye": "ZINCIRLIKUYU"}).get_json()
    assert d.get("durum") == "tamam", "normal rota isteği bozuldu: %s" % d.get("durum")
    assert d.get("rotalar"), "gerçek rota isteğinde hiç rota dönmedi"
