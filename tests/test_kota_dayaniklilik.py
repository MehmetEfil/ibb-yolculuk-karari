# -*- coding: utf-8 -*-
"""Kota dayanıklılığı — servis düştüğünde ne oluyor, düzelince ne oluyor?

`FiloDurum` saatte 100 istekle sınırlı; kota dolması ANORMAL DEĞİL, normal
işletme koşulu. Uygulamanın buna göre davranması gerekiyor:

  1. Kota doluyken son bilinen veri gösterilmeye devam etmeli (boş ekran yok).
  2. Uygulama YENİDEN BAŞLATILSA bile veri kaybolmamalı (disk anlık görüntüsü).
  3. Gösterilen verinin YAŞI dürüstçe belirtilmeli ("canlı" diye 40 dakikalık
     veri göstermek yanıltıcı).
  4. **Kota açılınca canlı veri ANINDA devralmalı** — eski görüntü yapışıp
     kalmamalı. Bu dosyanın asıl sınadığı madde budur.
"""
import json
import os
import time

import pytest


@pytest.fixture
def temiz_filo(svc, monkeypatch, tmp_path):
    """Her testten önce filo önbelleğini bilinen bir duruma getir.

    `_HERE` HER testte geçici klasöre çevriliyor: aksi hâlde `guncelle_filo`
    başarılı olunca gerçek proje klasöründeki `filo_anlik.json`'ın üzerine
    sahte test verisi yazılıyor. (Bir kez yaşandı: uygulama açılışta
    "3 araç diskten" yükledi.)
    """
    monkeypatch.setattr(svc, "_HERE", str(tmp_path))
    with svc._lock:
        eski = dict(svc.FILO_CACHE)
        svc.FILO_CACHE["ts"] = 0
        svc.FILO_CACHE["liste"] = []
        svc.FILO_CACHE["kapi_map"] = {}
    yield svc
    with svc._lock:
        svc.FILO_CACHE.update(eski)


def _sahte_filo(n=600):
    return [{"KapiNo": "T%04d" % i, "Enlem": "41.0%d" % i, "Boylam": "28.9%d" % i,
             "Plaka": "34TEST%02d" % i, "Operator": "İETT", "Garaj": "Test"}
            for i in range(n)]


def test_cekim_basarisizsa_eldeki_veri_silinmiyor(temiz_filo, monkeypatch):
    """Kota dolduğunda önbellek TEMİZLENMEMELİ — boş ekran yerine son
    bilinen durum gösterilmeye devam etmeli."""
    svc = temiz_filo
    monkeypatch.setattr(svc, "fetch_soap", lambda *a, **k: _sahte_filo())
    monkeypatch.setattr(svc, "_konum_guncelle", lambda *a, **k: None)
    monkeypatch.setattr(svc, "hesapla_uzun_duruş", lambda *a, **k: None)
    assert svc.guncelle_filo(zorunlu=True) is True
    with svc._lock:
        onceki_adet = len(svc.FILO_CACHE["liste"])
    assert onceki_adet == 600

    # şimdi servis düşsün
    monkeypatch.setattr(svc, "fetch_soap", lambda *a, **k: None)
    monkeypatch.setattr(svc, "time", svc.time)
    sonuc = svc.guncelle_filo(zorunlu=True)

    assert sonuc is False, "başarısız çekim True dönmemeli"
    with svc._lock:
        assert len(svc.FILO_CACHE["liste"]) == onceki_adet, (
            "çekim başarısız olunca eldeki veri silinmiş — ekran boş kalır")


def test_veri_yasi_dogru_hesaplaniyor(temiz_filo):
    """Yaş, verinin GERÇEK çekilme anından ölçülmeli."""
    svc = temiz_filo
    assert svc.filo_veri_yasi_sn() is None, "veri yokken yaş None olmalı"

    with svc._lock:
        svc.FILO_CACHE["ts"] = time.time() - 600      # 10 dk önce
        svc.FILO_CACHE["liste"] = _sahte_filo()
    yas = svc.filo_veri_yasi_sn()
    assert 590 <= yas <= 610, "yaş yanlış: %s" % yas


def test_anlik_goruntu_diske_yazilip_geri_yukleniyor(temiz_filo, tmp_path):
    """Yeniden başlatma senaryosu: disk anlık görüntüsü veriyi kurtarmalı."""
    svc = temiz_filo

    ts = time.time() - 900        # 15 dk önceki veri
    with svc._lock:
        svc.FILO_CACHE["ts"] = ts
        svc.FILO_CACHE["liste"] = _sahte_filo(600)
        svc.FILO_CACHE["kapi_map"] = {"T0000": {"plaka": "34TEST00"}}

    assert svc._filo_anlik_kaydet(zorla=True) is True
    assert (tmp_path / svc.FILO_ANLIK_DOSYA).exists()

    # "yeniden başlatma": bellek boşalıyor
    with svc._lock:
        svc.FILO_CACHE["ts"] = 0
        svc.FILO_CACHE["liste"] = []
        svc.FILO_CACHE["kapi_map"] = {}

    assert svc.filo_anlik_yukle() is True
    with svc._lock:
        assert len(svc.FILO_CACHE["liste"]) == 600, "anlık görüntü geri yüklenmedi"
        # ts ORİJİNAL kalmalı — "şimdi çekilmiş" gibi göstermek yalan olur
        assert abs(svc.FILO_CACHE["ts"] - ts) < 2, (
            "geri yüklenen veri taze gibi işaretlenmiş — yaş yalan söyler")
    assert svc.filo_veri_yasi_sn() >= 890


def test_canli_veri_gelince_ANINDA_devraliyor(temiz_filo, monkeypatch, tmp_path):
    """★ ASIL SORU: kota açılınca eski görüntü yapışıp kalıyor mu?

    Senaryo: eski anlık görüntü yüklü → servis geri geliyor → ilk başarılı
    çekimde hem bellek hem disk tazelenmeli, yaş sıfırlanmalı.
    """
    svc = temiz_filo
    monkeypatch.setattr(svc, "_konum_guncelle", lambda *a, **k: None)
    monkeypatch.setattr(svc, "hesapla_uzun_duruş", lambda *a, **k: None)

    # 1) elimizde 40 dakikalık eski veri var
    eski_ts = time.time() - 2400
    with svc._lock:
        svc.FILO_CACHE["ts"] = eski_ts
        svc.FILO_CACHE["liste"] = _sahte_filo(600)
        svc.FILO_CACHE["kapi_map"] = {}
    assert svc.filo_veri_yasi_sn() > 2000

    # 2) servis geri geliyor
    monkeypatch.setattr(svc, "fetch_soap", lambda *a, **k: _sahte_filo(700))
    svc._filo_anlik_son_yazma = 0        # yazma kısıtını bu test için aç
    assert svc.guncelle_filo(zorunlu=True) is True

    # 3) bellek TAZE olmalı
    with svc._lock:
        assert len(svc.FILO_CACHE["liste"]) == 700, "canlı veri belleğe yazılmadı"
    yas = svc.filo_veri_yasi_sn()
    assert yas < 5, "canlı veri geldiği hâlde yaş hâlâ eski: %s sn" % yas

    # 4) disk de tazelenmiş olmalı — sonraki yeniden başlatma eskiyi almasın
    yol = tmp_path / svc.FILO_ANLIK_DOSYA
    assert yol.exists()
    paket = json.loads(yol.read_text(encoding="utf-8"))
    assert len(paket["liste"]) == 700, "disk anlık görüntüsü tazelenmemiş"
    assert paket["ts"] > eski_ts + 1000, "diskteki zaman damgası eski kalmış"


def test_yarim_dosya_birakmiyor(temiz_filo, tmp_path):
    """Yazma sırasında çökme olursa yarım dosya kalmamalı: önce .tmp'ye
    yazılıp sonra taşınıyor. Yarım JSON, boş ekrandan beterdir."""
    svc = temiz_filo
    with svc._lock:
        svc.FILO_CACHE["ts"] = time.time()
        svc.FILO_CACHE["liste"] = _sahte_filo(600)
    svc._filo_anlik_kaydet(zorla=True)

    assert not (tmp_path / (svc.FILO_ANLIK_DOSYA + ".tmp")).exists(), \
        "geçici dosya temizlenmemiş"
    # yazılan dosya geçerli JSON olmalı
    json.loads((tmp_path / svc.FILO_ANLIK_DOSYA).read_text(encoding="utf-8"))


def test_bozuk_anlik_goruntu_cokmeye_yol_acmiyor(temiz_filo, tmp_path):
    """Disk dosyası bozuksa uygulama çökmemeli, sadece False dönmeli."""
    svc = temiz_filo
    (tmp_path / svc.FILO_ANLIK_DOSYA).write_text("{bozuk json", encoding="utf-8")
    assert svc.filo_anlik_yukle() is False


def test_guvenilmez_kucuk_goruntu_yok_sayiliyor(temiz_filo, tmp_path):
    """Şebeke ~6.900 araç. Bir avuç araçlık görüntü ya yarım yazılmış ya da
    artıktır; haritada 3 otobüs gösterip 'işte şebeke' demek boş ekrandan
    daha yanıltıcıdır.

    REGRESYON: testler bir kez gerçek `filo_anlik.json`'a 3 sahte araç yazdı
    ve uygulama açılışta onu yükledi ("💾 3 araç diskten").
    """
    svc = temiz_filo
    with svc._lock:
        svc.FILO_CACHE["ts"] = time.time()
        svc.FILO_CACHE["liste"] = _sahte_filo(3)
    svc._filo_anlik_kaydet(zorla=True)

    with svc._lock:
        svc.FILO_CACHE["ts"] = 0
        svc.FILO_CACHE["liste"] = []

    assert svc.filo_anlik_yukle() is False, "güvenilmez görüntü yüklendi"
    with svc._lock:
        assert not svc.FILO_CACHE["liste"], "çöp veri belleğe girdi"
