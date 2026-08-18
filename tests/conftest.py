# -*- coding: utf-8 -*-
"""Test altyapısı — veriyi DİSKTEN yükler, canlı servise hiç dokunmaz.

Neden bu kadar dikkatli: `FiloDurum` saatte 100 istekle sınırlı ve aşılınca
tüm şebeke veri alamıyor. Testler her çalıştırıldığında kota harcasaydı
kullanılamaz olurlardı. Bu yüzden:

  * `services` modülü import edilir ama `start_background_threads()` ÇAĞRILMAZ
    (o, canlı çekim yapan iş parçacıklarını başlatır),
  * `build_memory_db()` / `build_durak_dict()` yerine JSON'lar doğrudan
    modül global'lerine yazılır — çünkü o fonksiyonlar diskten okuduktan
    sonra arka planda `_grafik_onar` iş parçacığını başlatıyor ve o ağa çıkıyor,
  * ağ çağrısı yapan her giriş noktası `_ag_kapali` fixture'ıyla bloke edilir;
    bir test yanlışlıkla ağa çıkmaya kalkarsa test HATA verir, sessizce
    yavaşlamaz.
"""
import io
import json
import os
import sys

import pytest

PROJE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJE not in sys.path:
    sys.path.insert(0, PROJE)

# Windows konsolu cp1254 kullanıyor; services.py'nin ✅/⚠️ içeren log
# satırları `pytest -s` ile doğrudan konsola yazılınca UnicodeEncodeError
# atıyor. app.py aynı korumayı kendi içinde yapıyor, testlerde de gerekli.
if (getattr(sys.stdout, "encoding", "") or "").lower() != "utf-8":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                                      errors="replace")
    except Exception:
        pass


def _json_oku(ad):
    yol = os.path.join(PROJE, ad)
    with open(yol, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def svc():
    """services modülü, diskteki veriyle tam yüklenmiş hâlde."""
    import services as s

    s.load_panel_data()
    s.load_hat_profil()
    s.sira_diskten_yukle()

    # MEMORY_DB: {durak_kodu: set(hat)} — build_memory_db() arka plan
    # iş parçacığı başlattığı için elle dolduruluyor.
    ham = _json_oku("memory_db.json")
    with s._lock:
        s.MEMORY_DB.clear()
        s.MEMORY_DB.update({k: set(v) for k, v in ham.items()})
        s.IS_DB_READY = True

    dd = _json_oku("durak_dict.json")
    with s._lock:
        s.DURAK_DICT.clear()
        s.DURAK_DICT.update(dd)

    s.build_durak_komsu()
    return s


@pytest.fixture(autouse=True)
def _ag_kapali(monkeypatch):
    """Testler ağa çıkamaz. Çıkmaya kalkan test açıkça patlar."""
    def _yasak(*a, **k):
        raise AssertionError(
            "Test canlı servise çıkmaya çalıştı. Testler diskteki veriyle "
            "çalışmalı — canlı çağrı saatlik kotayı harcar."
        )

    import services as s
    for ad in ("fetch_soap", "fetch_soap_xml"):
        if hasattr(s, ad):
            monkeypatch.setattr(s, ad, _yasak)

    import requests
    monkeypatch.setattr(requests, "get", _yasak)
    monkeypatch.setattr(requests, "post", _yasak)
