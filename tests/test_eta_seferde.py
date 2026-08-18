# -*- coding: utf-8 -*-
"""Seferde OLMAYAN araç için "geliyor" denmemeli.

Kullanıcı bildirdi: rota sonucunda seferi olmayan bir araç için
"15 dk'ya gelecek" yazıyordu. Gelmeyecek araca süre vermek, süre
vermemekten kötüdür — yolcu durakta boşuna bekler.

Ölçüldü (canlı veri, 12 Ağu 2026):

    34G   M4852   garajda, hız 7, hareketsiz  →  "2 dk"
    500T  C-361   garajda, hız 0, hareketsiz  → "22 dk"

İKİ AYRI kod yolu vardı ve **ikisinde de** filtre yoktu:

  1. `/api/durak_eta`      → durak tıklanınca çıkan ETA listesi.
     Kodda "park hâlindeki otobüse güvenli ETA verilmez" yorumu vardı
     ama `hareketli` yalnızca yanıta alan olarak ekleniyor, filtre
     olarak hiç kullanılmıyordu.
  2. `_canli_eta_hesapla`  → ROTA KARTLARINDAKİ "● CANLI 15 dk" rozeti.
     Burada hareket/garaj kontrolü hiç yoktu. Kullanıcının gördüğü
     yer burasıydı.

Sınıflandırma `/api/canli_konum` ile aynı:
    garajda      garaj alanında + hareketsiz   → ELENİR
    garaj_cikis  garaj alanında + hareketli    → ELENİR
    duruyor      6 dk'da <150 m, garaj dışı    → ELENİR
    seferde      kalan                          → gösterilir

Canlı araç kalmazsa uygulama planlı sefer saatine düşer ve arayüz
"PLAN" rozeti gösterir — dürüst davranış budur.
"""
import inspect

import pytest
from flask import Flask


GARAJ = (41.0605, 28.7915)      # İkitelli garajı
YOLDA = (41.0100, 28.8000)      # güzergâh üstü


@pytest.fixture
def istemci(svc, monkeypatch):
    """Sahte filoyla, ağa çıkmadan çalışan bir test istemcisi."""
    import routes

    sahte = [
        {"KapiNo": "GARAJ1", "Enlem": str(GARAJ[0]), "Boylam": str(GARAJ[1]),
         "Hiz": "0", "Plaka": "34TEST01", "Operator": "İETT"},
        {"KapiNo": "DURAN1", "Enlem": str(YOLDA[0]), "Boylam": str(YOLDA[1]),
         "Hiz": "0", "Plaka": "34TEST02", "Operator": "İETT"},
        {"KapiNo": "YOLDA1", "Enlem": str(YOLDA[0]), "Boylam": str(YOLDA[1]),
         "Hiz": "42", "Plaka": "34TEST03", "Operator": "İETT"},
    ]

    def _filo(hat):
        return ([{"kapi": a["KapiNo"], "lat": float(a["Enlem"]),
                  "lon": float(a["Boylam"]), "hiz": float(a["Hiz"]),
                  "plaka": a["Plaka"], "op": "İETT", "yon": "G"}
                 for a in sahte], 0)

    monkeypatch.setattr(routes, "get_live_buses_cached", _filo)
    monkeypatch.setattr(routes, "tahmin_yon_terminal", lambda h, n: n)
    monkeypatch.setattr(routes, "arac_durak_yaklasiyor_mu",
                        lambda *a, **k: (True, 3))
    monkeypatch.setattr(routes, "arac_gercek_yon", lambda *a, **k: "G")
    # GARAJ1 garaj alanında, digerleri degil
    monkeypatch.setattr(
        routes, "garajda_mi",
        lambda la, lo: (("İkitelli", 40)
                        if la is not None and abs(la - GARAJ[0]) < 0.005
                        else (None, None)))
    # DURAN1 6 dk'dir hareketsiz; digerleri hareketli
    monkeypatch.setattr(
        routes, "arac_hareket_durumu",
        lambda kapi: ((False, 420, 20) if kapi == "DURAN1" else (True, 0, 900)))

    app = Flask(__name__)
    routes.register_routes(app, None)
    return app.test_client()


def _kapilar(istemci, yon=""):
    u = "/api/durak_eta?hat=34G&lat=%s&lon=%s" % (YOLDA[0] + 0.01, YOLDA[1])
    if yon:
        u += "&yon=" + yon
    d = istemci.get(u).get_json() or {}
    return [s.get("kapi") for s in (d.get("sonuclar") or [])], d.get("kaynak")


def test_garajdaki_arac_eta_listesine_girmez(istemci):
    """Garaj alanındaki araç gösterilmemeli — gelmeyecek."""
    kapilar, _ = _kapilar(istemci)
    assert "GARAJ1" not in kapilar, (
        "garajdaki araç yolcuya 'geliyor' diye gösteriliyor")


def test_hareketsiz_arac_eta_listesine_girmez(istemci):
    """6 dk'dır <150 m oynayan araç seferde sayılmaz."""
    kapilar, _ = _kapilar(istemci)
    assert "DURAN1" not in kapilar, (
        "6 dk'dır hareketsiz araca ETA veriliyor — yolcu boşuna bekler")


def test_seferdeki_arac_ELENMEZ(istemci):
    """Aşırı filtreleme koruması: çalışan araç listede kalmalı."""
    kapilar, kaynak = _kapilar(istemci)
    assert "YOLDA1" in kapilar, "seferdeki araç yanlışlıkla elendi"
    assert kaynak == "ram", "canlı araç varken planlı kaynağa düşülmüş"


def test_rota_karti_yolunda_da_filtre_var():
    """Rota kartlarını besleyen `_canli_eta_hesapla` ayrı bir kod yolu.

    `register_routes` içinde iç içe tanımlı olduğu için doğrudan
    çağrılamıyor; kaynağından doğruluyoruz. Asıl kullanıcı şikâyeti
    (rota kartında "CANLI 15 dk") bu fonksiyondan geliyordu ve
    `/api/durak_eta` düzeltilse bile burası açık kalabilir.
    """
    import routes
    kaynak = inspect.getsource(routes.register_routes)
    bas = kaynak.index("def _canli_eta_hesapla")
    # fonksiyonun govdesi: bir sonraki ayni girintili `def`e kadar
    son = kaynak.index("\n    def ", bas + 10)
    govde = kaynak[bas:son]
    assert "garajda_mi" in govde, (
        "_canli_eta_hesapla garaj kontrolü yapmıyor — garajdaki araç "
        "rota kartında 'CANLI' diye görünür")
    assert "arac_hareket_durumu" in govde, (
        "_canli_eta_hesapla hareket kontrolü yapmıyor")
