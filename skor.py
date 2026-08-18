# -*- coding: utf-8 -*-
"""
GÜVENİLİRLİK SKORU + HAT KARNESİ

Projenin adını taşıyan özellik. Kaynak: `GetIettArsivGorev_json` (kotasız,
T+2 gün gecikmeli, günlük ~44.000 sefer).

    Skor = 45 × süre_tutarlılığı + 30 × sefer_gerçekleşme + 25 × düzenlilik

NEDEN BU ÜÇÜ — ölçüldü, uydurulmadı
------------------------------------
Plan dökümanındaki ilk formül "dakiklik ×0,4 + iptal ×0,3" idi. Ölçtük:
kalkış dakikliği ±3 dk toleransta şebeke genelinde **%91,5** ve hatlar
birbirinden ayrışmıyor — o formül herkese aynı puanı verirdi. Kullandığımız
üç metrik ise geniş aralıkta dağılıyor, yani gerçekten ayırt ediyor:

  süre yayılımı (p90−p10)/medyan : %7,9 – %258,0   (medyan %43,9)
  sefer gerçekleşmeme            : %0   – %58,3    (şebeke %4,03)
  headway düzensizliği σ/μ       : medyan 0,50

(30 Tem 2026 arşivi, 51.932 sefer, 732 hat üzerinde ölçüldü. Daha önce
belgelerde yazan %9,8-197,9 / 0,23 değerleri eski bir günden kalmıştı;
formül seçimi değişmiyor — dakiklik hâlâ düz, yayılım hâlâ ayırt ediyor.)

NORMALİZASYON
-------------
Her metrik şebekenin kendi p5–p95 aralığına göre 0–1'e çekiliyor (uçları
kırparak). Böylece "iyi/kötü" mutlak bir eşikle değil, İstanbul şebekesinin
gerçek dağılımıyla tanımlanıyor. Tek bir aykırı hat tüm ölçeği bozmuyor.
"""
import math
import re
import statistics
from collections import defaultdict
from datetime import datetime

AGIRLIK = {"sure": 45.0, "gerceklesme": 30.0, "duzenlilik": 25.0}
MIN_SEFER = 8          # bu sayıdan az seferi olan hat puanlanmaz


def _dt(s):
    if not s:
        return None
    m = re.search(r'-?\d{10,}', str(s))
    if m:
        return datetime.fromtimestamp(int(m.group()) / 1000.0)
    try:
        return datetime.fromisoformat(str(s)[:19])
    except Exception:
        return None


def _yuzdelik(sirali, q):
    if not sirali:
        return None
    i = min(len(sirali) - 1, max(0, int(round(q * (len(sirali) - 1)))))
    return sirali[i]


def _normalize(deger, p5, p95, ters=False):
    """
    Metriği 0–1'e çeker. `ters=True` ise küçük olan iyidir.
    p5/p95 dışına taşanlar kırpılır — tek aykırı hat ölçeği bozmasın.
    """
    if deger is None or p95 is None or p5 is None or p95 <= p5:
        return 0.5
    x = (deger - p5) / (p95 - p5)
    x = max(0.0, min(1.0, x))
    return (1.0 - x) if ters else x


def ham_metrikler(gorevler):
    """Arşiv kayıtlarından hat başına ham metrikler."""
    hat = defaultdict(lambda: {"sureler": [], "kalkislar": [],
                               "toplam": 0, "tamam": 0, "iptal": 0, "yarim": 0})
    for g in gorevler or []:
        h = str(g.get("SHATKODU") or "").strip().upper()
        if not h:
            continue
        d = hat[h]
        d["toplam"] += 1
        durum = str(g.get("SGOREVDURUM") or "").strip().upper()
        if durum == "I":
            d["iptal"] += 1
        elif durum == "YK":
            d["yarim"] += 1
        else:
            d["tamam"] += 1

        b = _dt(g.get("DTBASLAMAZAMANI"))
        s = _dt(g.get("DTBITISZAMANI"))
        if b and s:
            sure = (s - b).total_seconds() / 60.0
            if 8 <= sure <= 300:
                d["sureler"].append(sure)
        # Kalkış — YALNIZCA gerçekleşen seferler düzenlilik serisine girer.
        #
        # Eskiden `b or DTPLANLANANBASLANGICZAMANI` yazıyordu: iptal edilen
        # seferin PLANLANAN kalkışı seriye giriyordu. Ölçüldü — 10 dk aralıklı
        # 12 seferin ortadaki 4'ü iptal edildiğinde düzensizlik hâlâ 0,000
        # çıkıyordu, oysa yolcunun gördüğü aralık 4 yerde 20 dakikaya çıkıyor.
        # Yani düzenlilik bileşeni gerçekleşmeyi değil PLANI ölçüyordu ve
        # iptal, hattı düzensiz göstermek yerine hiç görünmüyordu.
        #
        # Planlanan saat yalnızca sefer gerçekleştiği hâlde başlama damgası
        # eksikse yedek olarak kullanılır.
        if durum != "I":
            k = b or _dt(g.get("DTPLANLANANBASLANGICZAMANI"))
            if k:
                d["kalkislar"].append(k)

    out = {}
    for h, d in hat.items():
        if d["toplam"] < MIN_SEFER:
            continue
        kayit = {"sefer": d["toplam"], "tamam": d["tamam"],
                 "iptal": d["iptal"], "yarim": d["yarim"]}

        # 1) Süre yayılımı
        sr = sorted(d["sureler"])
        if len(sr) >= 5:
            med = statistics.median(sr)
            p10, p90 = _yuzdelik(sr, 0.10), _yuzdelik(sr, 0.90)
            kayit["medyan_sure_dk"] = round(med, 1)
            kayit["yayilim"] = round((p90 - p10) / med, 3) if med > 0 else None
            kayit["p10_dk"] = round(p10, 1)
            kayit["p90_dk"] = round(p90, 1)
        else:
            kayit["yayilim"] = None

        # 2) Gerçekleşme
        kayit["gerceklesme"] = round(d["tamam"] / d["toplam"], 4)

        # 3) Headway düzensizliği (ardışık kalkış aralıklarının σ/μ)
        ks = sorted(d["kalkislar"])
        aralik = [(ks[i + 1] - ks[i]).total_seconds() / 60.0
                  for i in range(len(ks) - 1)]
        aralik = [a for a in aralik if 1 <= a <= 180]
        if len(aralik) >= 5:
            mu = statistics.mean(aralik)
            sd = statistics.pstdev(aralik)
            kayit["headway_dk"] = round(mu, 1)
            kayit["duzensizlik"] = round(sd / mu, 3) if mu > 0 else None
        else:
            kayit["duzensizlik"] = None

        out[h] = kayit
    return out


def skorla(gorevler, hat_master=None):
    """
    Tüm hatları puanlar. Döner: {hat: {skor, alt kırılım, açıklama}}
    """
    ham = ham_metrikler(gorevler)
    if not ham:
        return {}

    yay = sorted(v["yayilim"] for v in ham.values() if v.get("yayilim") is not None)
    ger = sorted(v["gerceklesme"] for v in ham.values() if v.get("gerceklesme") is not None)
    duz = sorted(v["duzensizlik"] for v in ham.values() if v.get("duzensizlik") is not None)

    esik = {
        "yay_p5": _yuzdelik(yay, 0.05), "yay_p95": _yuzdelik(yay, 0.95),
        "ger_p5": _yuzdelik(ger, 0.05), "ger_p95": _yuzdelik(ger, 0.95),
        "duz_p5": _yuzdelik(duz, 0.05), "duz_p95": _yuzdelik(duz, 0.95),
    }

    adlar = {}
    for h in (hat_master or []):
        k = str(h.get("HATKODU") or "").strip().upper()
        if k:
            adlar[k] = h.get("hatadi") or h.get("HATADI") or ""

    sonuc = {}
    for h, v in ham.items():
        n_yay = _normalize(v.get("yayilim"), esik["yay_p5"], esik["yay_p95"], ters=True)
        n_ger = _normalize(v.get("gerceklesme"), esik["ger_p5"], esik["ger_p95"])
        n_duz = _normalize(v.get("duzensizlik"), esik["duz_p5"], esik["duz_p95"], ters=True)

        p_sure = AGIRLIK["sure"] * n_yay
        p_ger = AGIRLIK["gerceklesme"] * n_ger
        p_duz = AGIRLIK["duzenlilik"] * n_duz

        # ── Eksik metrik BEDAVA PUAN OLMAMALI ───────────────────────────
        # `_normalize` ölçülemeyen metriğe 0,5 döndürüyor. Eskiden bu değer
        # doğrudan ağırlıkla çarpılıyordu, yani "sınava girmedi" cevabı
        # "orta düzeyde başarılı" diye puanlanıyordu: yayılımı hiç
        # hesaplanamayan hat 45 puanın 22,5'ini bedavaya alıyordu.
        # Ölçüldü — T2 (Taksim-Tünel) böylece 77,5 alıp **B** notuna
        # çıkıyordu, oysa süre tutarlılığı hakkında tek bir veri yok.
        #
        # Doğrusu: ölçülemeyen metriği puanlamamak. Skor YALNIZCA ölçülen
        # bileşenlerden hesaplanır, sonra 100'lük ölçeğe geri getirilir.
        # Böylece hat "elimizdeki veriye göre" değerlendirilmiş olur;
        # ölçemediğimiz şey ne ödül ne ceza getirir.
        olculen = []
        if v.get("yayilim") is not None:
            olculen.append((AGIRLIK["sure"], p_sure))
        if v.get("gerceklesme") is not None:
            olculen.append((AGIRLIK["gerceklesme"], p_ger))
        if v.get("duzensizlik") is not None:
            olculen.append((AGIRLIK["duzenlilik"], p_duz))

        if olculen:
            tavan = sum(a for a, _ in olculen)
            skor = sum(p for _, p in olculen) * (100.0 / tavan)
        else:
            # Üç metrik de yoksa puanlanacak bir şey kalmıyor.
            skor = 0.0

        # Eksik metrik varsa güven düşer
        eksik = sum(1 for x in ("yayilim", "gerceklesme", "duzensizlik")
                    if v.get(x) is None)
        guven = "yüksek" if eksik == 0 and v["sefer"] >= 30 else (
            "orta" if eksik <= 1 else "düşük")

        sonuc[h] = {
            "hat": h, "ad": adlar.get(h, ""),
            "skor": round(skor, 1),
            # Harf YUVARLANMIS puandan alinmali: ham skor kullanilinca
            # 54,96 ekranda "55,0" gorunup harf D oluyordu (esik >=55 = C).
            "harf": _harf(round(skor, 1)),
            "kirilim": {
                "sure_tutarliligi": {"puan": round(p_sure, 1), "tavan": AGIRLIK["sure"],
                                     "ham": v.get("yayilim"), "oran": round(n_yay, 3)},
                "sefer_gerceklesme": {"puan": round(p_ger, 1), "tavan": AGIRLIK["gerceklesme"],
                                      "ham": v.get("gerceklesme"), "oran": round(n_ger, 3)},
                "duzenlilik": {"puan": round(p_duz, 1), "tavan": AGIRLIK["duzenlilik"],
                               "ham": v.get("duzensizlik"), "oran": round(n_duz, 3)},
            },
            "olcum": v,
            "guven": guven,
            "aciklama": _aciklama(v, n_yay, n_ger, n_duz),
        }
    return sonuc


def _harf(skor):
    if skor >= 85: return "A"
    if skor >= 70: return "B"
    if skor >= 55: return "C"
    if skor >= 40: return "D"
    return "E"


def _aciklama(v, n_yay, n_ger, n_duz):
    """'Bu hat neden bu puanı aldı' — insan diliyle, sayıya dayalı."""
    p = []
    if v.get("yayilim") is not None:
        y = v["yayilim"]
        if n_yay >= 0.7:
            p.append("Sefer süresi tutarlı: aynı yolculuk %s–%s dk arasında değişiyor "
                     "(yayılım %%%d)." % (v.get("p10_dk"), v.get("p90_dk"), round(y * 100)))
        elif n_yay <= 0.3:
            p.append("Sefer süresi çok oynak: aynı yolculuk %s dk da sürebiliyor %s dk da "
                     "(yayılım %%%d). Yolcu ne zaman varacağını kestiremiyor."
                     % (v.get("p10_dk"), v.get("p90_dk"), round(y * 100)))
        else:
            p.append("Sefer süresi orta düzeyde oynak (yayılım %%%d)." % round(y * 100))

    if v.get("gerceklesme") is not None:
        kayip = v["sefer"] - v["tamam"]
        if n_ger >= 0.7:
            p.append("Planlanan seferlerin %%%.1f'i yapılmış." % (v["gerceklesme"] * 100))
        else:
            p.append("Planlanan %d seferin %d'i tamamlanmamış (%d iptal, %d yarım kaldı) — "
                     "durakta bekleyen yolcu boşuna bekliyor."
                     % (v["sefer"], kayip, v["iptal"], v["yarim"]))

    if v.get("duzensizlik") is not None:
        d = v["duzensizlik"]
        if n_duz >= 0.7:
            p.append("Araçlar düzenli aralıklarla geçiyor (ortalama %s dk, sapma %.2f)."
                     % (v.get("headway_dk"), d))
        elif n_duz <= 0.3:
            p.append("Araçlar kümeleniyor: ortalama %s dk aralık ama sapma %.2f — "
                     "üst üste iki araç sonra uzun boşluk."
                     % (v.get("headway_dk"), d))
    return " ".join(p)


def sebeke_ozeti(skorlar):
    if not skorlar:
        return {}
    sk = sorted(v["skor"] for v in skorlar.values())
    n = len(sk)
    dagilim = defaultdict(int)
    for v in skorlar.values():
        dagilim[v["harf"]] += 1
    return {
        "hat_sayisi": n,
        "ortalama": round(sum(sk) / n, 1),
        "medyan": round(sk[n // 2], 1),
        "en_dusuk": round(sk[0], 1),
        "en_yuksek": round(sk[-1], 1),
        "dagilim": dict(dagilim),
    }
