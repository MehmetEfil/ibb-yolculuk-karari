# -*- coding: utf-8 -*-
"""43 uc cagrisini (42 tekil yol) sinar — hangisi çalışıyor, hangisi patlıyor?

Demo sırasında bir ucun 500 dönmesi ya da boş kalması sessizce fark edilmez;
ekranda sadece "yükleniyor" kalır. Bu betik hepsini gerçekçi parametrelerle
çağırıp sonucu tablo hâlinde verir.

Kullanım:
    python scripts/uc_denetimi.py            # canlı servisle (kota harcar)
    python scripts/uc_denetimi.py --agsiz    # yalnız diskteki veriyle
"""
import io
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HERE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

AGSIZ = "--agsiz" in sys.argv
# --servis-yok: KOTA DOLMUŞ senaryosu. Gerçekte `fetch_soap` istisna atmaz,
# HTTP 500 görüp None döner. Uygulamanın o durumda ne yaptığını görmek,
# yapay bir istisnayla test etmekten çok daha anlamlı — demoda başımıza
# gelen tam olarak budur.
SERVIS_YOK = "--servis-yok" in sys.argv

# .env kosulsuz acilirsa temiz klon FileNotFoundError ile coker: dosya
# .gitignore'da, yani depoyu indiren kimsede yok. app.py ile ayni koruma.
_ENV = os.path.join(_HERE, ".env")
if os.path.exists(_ENV):
    for satir in open(_ENV, encoding="utf-8"):
        satir = satir.strip()
        if satir and "=" in satir and not satir.startswith("#"):
            k, _, v = satir.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
else:
    print("NOT: .env yok — kimlik isteyen servisler bos donecek. "
          "Diskteki veriyle sinamak icin: --agsiz")

import services as s  # noqa: E402


def veri_yukle():
    s.load_panel_data()
    s.load_hat_profil()
    s.sira_diskten_yukle()
    with open(os.path.join(_HERE, "memory_db.json"), encoding="utf-8") as f:
        s.MEMORY_DB.update({k: set(v) for k, v in json.load(f).items()})
    s.IS_DB_READY = True
    with open(os.path.join(_HERE, "durak_dict.json"), encoding="utf-8") as f:
        s.DURAK_DICT.update(json.load(f))
    s.build_durak_komsu()
    if AGSIZ:
        def yasak(*a, **k):
            raise RuntimeError("ağ kapalı (--agsiz)")
        s.fetch_soap = yasak
        s.fetch_soap_xml = yasak
    elif SERVIS_YOK:
        # Servisin gerçek arıza davranışı: yanıt yok, istisna yok.
        s.fetch_soap = lambda *a, **k: None
        s.fetch_soap_xml = lambda *a, **k: None


# Her uç için gerçekçi parametre. Boş dict = parametresiz çağrı.
UCLAR = [
    ("/api/en_yakin_durak", {"lat": 41.0082, "lon": 28.9784}),
    ("/api/rota_debug", {"nereden": "AVCILAR", "nereye": "TAKSIM"}),
    ("/api/karbon_rota", {"nereden": "AVCILAR", "nereye": "ZINCIRLIKUYU"}),
    ("/api/ispark", {}),
    ("/api/nasil_gidilir", {"nereden": "AVCILAR", "nereye": "ZINCIRLIKUYU"}),
    ("/api/profil", {}),
    ("/api/profil/seferler", {}),
    ("/api/profil/kurum_rapor", {}),
    ("/api/hat_skoru", {}),
    ("/api/hat_skoru", {"hat": "34G"}),
    ("/api/v1/dashboard", {}),
    ("/api/hat_detay", {"hat": "34G"}),
    ("/api/istatistik", {}),
    ("/api/durak_detay", {"kod": "123562"}),
    ("/api/canli_konum", {"hat": "34G"}),
    ("/api/bildirimler", {"hat": "34G"}),
    ("/api/radar", {}),
    ("/api/garajlar", {}),
    ("/api/kavsaklar", {}),
    ("/api/saatler", {"hat": "34G"}),
    ("/api/durak_ara", {"q": "avcilar"}),
    ("/api/motor_hat_bul", {"kodu": "123562"}),
    ("/api/durak_eta", {"hat": "34G", "lat": 41.0104, "lon": 28.8060, "yon": "G"}),
    ("/api/yolcu_analizi", {}),
    ("/api/gecikme_skoru", {"hat": "34G"}),
    ("/api/yogunluk", {}),
    ("/api/trafik_nokta", {"lat": 41.0082, "lon": 28.9784}),
    ("/api/trafik_isi", {}),
    ("/api/guzergah_trafik", {"hat": "34G"}),
    ("/api/guzergah_geo", {"hat": "34G"}),
    ("/api/arac_ozellik", {"kapi": "M3117"}),
    ("/api/operasyonel_ozet", {}),
    ("/api/kara_kutu_sefer", {"hat": "34G"}),
    ("/api/usulsuz_kart", {}),
    ("/api/metrobus_hazir", {}),
    ("/api/plaka_sorgula", {"plaka": "34FJA864"}),
    ("/api/durak_sefer_saati", {"durak": "123562"}),  # SOAP metodu kapali
    ("/api/yolcu_bilgilendirme", {"hat": "34G"}),
    ("/api/plan_basari", {}),
    ("/api/headway", {"hat": "34G"}),
    ("/api/hat_bilgi", {"hat": "34G"}),
    ("/api/kara_kutu", {}),
    ("/api/tani", {}),
]


def _dolu_mu(veri):
    """Yanıt 'işe yarar veri' taşıyor mu? Boş liste/sözlük = boş."""
    if veri is None:
        return False
    if isinstance(veri, list):
        return len(veri) > 0
    if isinstance(veri, dict):
        if not veri:
            return False
        # yalnızca durum/hata alanı varsa boş say
        anlamli = {k: v for k, v in veri.items()
                   if k not in ("durum", "hata", "mesaj", "veri_yasi_sn")}
        if not anlamli:
            return False
        for v in anlamli.values():
            if isinstance(v, (list, dict)) and len(v) > 0:
                return True
            if isinstance(v, (int, float)) and v:
                return True
            if isinstance(v, str) and v.strip():
                return True
        return False
    return True


def calistir():
    import routes
    from flask import Flask
    app = Flask(__name__, template_folder=os.path.join(_HERE, "templates"))
    routes.register_routes(app, None)
    c = app.test_client()

    print("=" * 78)
    print("UÇ DENETİMİ  (%s)" % ("ağsız — yalnız disk" if AGSIZ else
                             "SERVİS YOK — kota dolmuş senaryosu" if SERVIS_YOK else
                             "canlı servisle"))
    print("=" * 78)
    print("%-34s %-6s %8s  %s" % ("UÇ", "KOD", "SÜRE", "DURUM"))
    print("-" * 78)

    ozet = {"tamam": 0, "bos": 0, "hata": 0, "ag": 0}
    sorunlu = []

    for yol, par in UCLAR:
        t = time.perf_counter()
        try:
            r = c.get(yol, query_string=par)
            gecen = time.perf_counter() - t
            kod = r.status_code
            try:
                veri = r.get_json()
            except Exception:
                veri = None

            if kod != 200:
                durum, isaret = "HTTP %d" % kod, "hata"
            elif not _dolu_mu(veri):
                durum, isaret = "boş yanıt", "bos"
            else:
                durum, isaret = "ok", "tamam"
        except Exception as e:
            gecen = time.perf_counter() - t
            kod, durum, isaret = "-", "%s: %s" % (type(e).__name__, str(e)[:40]), "hata"

        # --agsiz modunda `fetch_soap` ISTISNA FIRLATIYOR. Uretimde bu asla
        # olmaz: gercek `fetch_soap` her istisnayi yutup None dondurur
        # (services.py:756). Yani buradaki HTTP 500'ler bir saglamlik acigi
        # degil, kancanin yapayligidir — "bu uc agi kullaniyor" demektir,
        # ki --agsiz modunun olcmek istedigi tam olarak budur.
        # Gercekci ariza senaryosu --servis-yok; orada 0 hata cikiyor.
        if AGSIZ and isaret == "hata":
            durum, isaret = "ağ istendi (agsiz modda beklenen)", "ag"

        ozet[isaret] += 1
        if isaret != "tamam":
            sorunlu.append((yol, par, durum))

        etiket = {"tamam": "✓", "bos": "◌", "hata": "✗", "ag": "⇢"}[isaret]
        ad = yol + ("?" + list(par)[0] if par else "")
        print("%-34s %-6s %7.0fms  %s %s" % (ad[:34], kod, gecen * 1000, etiket, durum))

    print("-" * 78)
    print("ÖZET: %d çalışıyor · %d boş · %d hatalı%s  (toplam %d)"
          % (ozet["tamam"], ozet["bos"], ozet["hata"],
             (" · %d ağ istedi" % ozet["ag"]) if ozet["ag"] else "",
             len(UCLAR)))

    if sorunlu:
        print("\nSORUNLULAR")
        for yol, par, durum in sorunlu:
            print("  %-32s %-28s %s" % (yol, json.dumps(par, ensure_ascii=False)[:28], durum))
    return ozet


if __name__ == "__main__":
    veri_yukle()
    calistir()
