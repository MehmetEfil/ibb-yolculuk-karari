# -*- coding: utf-8 -*-
"""Geçmiş yolculuklardan bağlamsal geri bildirim üreten konsept modülü.

Gerçek İstanbulkart entegrasyonu yoktur; yolculuklar temsilîdir. Bildirimler
otomatik iş emrine dönüşmez. Tekrarlanan sinyaller saha ve operasyon ekipleri
için doğrulanacak birer iyileştirme adayı üretir.
"""
import json
import os as _os
import random
import time
from datetime import datetime, timedelta

_HERE = _os.path.dirname(_os.path.abspath(__file__))

# ── Kalite ve kümeleme kuralları ────────────────────────────────────────
DEGERLENDIRME_ASGARI_SORU = 3       # kısa ve tamamlanabilir geri bildirim
TEKRAR_ESIGI              = 3       # aynı konuda 3 sinyal → inceleme adayı

SORUN_YERLERI = {
    "arac": "Araç içinde",
    "durak": "Durakta",
    "sefer": "Sefer düzeninde",
    "aktarma": "Aktarmada",
    "bilgi": "Yolcu bilgilendirmesinde",
}

SORUN_KATEGORILERI = {
    "temizlik": "Temizlik",
    "yogunluk": "Yoğunluk",
    "iklimlendirme": "Isıtma / klima",
    "erisilebilirlik": "Erişilebilirlik",
    "bilgilendirme": "Bilgilendirme",
    "bekleme": "Bekleme süresi",
    "ekipman": "Ekipman arızası",
    "personel": "Personel davranışı",
    "guvenlik": "Güvenlik",
    "diger": "Diğer",
}

# ── Anket şeması — hepsi AYRI puanlanır (INTENT kararı) ────────────────
ANKET_SEMASI = [
    {"alan": "hat", "baslik": "Hat", "ikon": "", "renk": "#163b65",
     "sorular": [
         {"kod": "sefer_sikligi", "metin": "Sefer sıklığı yeterli miydi?"},
         {"kod": "kalabalik",     "metin": "Araç içi yoğunluk uygun muydu?"},
         {"kod": "saat_uyum",     "metin": "İlan edilen saate uyuldu mu?"},
     ]},
    {"alan": "arac", "baslik": "Araç", "ikon": "", "renk": "#163b65",
     "sorular": [
         {"kod": "temizlik",   "metin": "Araç temizliği"},
         {"kod": "klima",      "metin": "Isıtma / klima"},
         {"kod": "erisim",     "metin": "Engelli erişimi (rampa, alan)"},
     ]},
    {"alan": "durak", "baslik": "Durak", "ikon": "", "renk": "#a51c30",
     "sorular": [
         {"kod": "bekleme_alani", "metin": "Bekleme alanı ve korunak"},
         {"kod": "bilgi_ekrani",  "metin": "Bilgilendirme ekranı"},
         {"kod": "durak_erisim",  "metin": "Durağa erişim (rampa, kaldırım)"},
     ]},
    {"alan": "sofor", "baslik": "Sürücü", "ikon": "", "renk": "#28745a",
     "sorular": [
         {"kod": "surus",     "metin": "Sürüş güvenliği"},
         {"kod": "iletisim",  "metin": "İletişim ve yardımseverlik"},
         {"kod": "duraga_yanasma", "metin": "Durağa düzgün yanaşma"},
     ]},
]

KART_TIPLERI = {
    "tam":     {"ad": "Tam", "ikon": "", "engelli": False},
    "ogrenci": {"ad": "Öğrenci", "ikon": "", "engelli": False},
    "65":      {"ad": "65+ Ücretsiz", "ikon": "", "engelli": False},
    "engelli": {"ad": "Engelli Ücretsiz", "ikon": "", "engelli": True},
}

# ── Durum (bellekte; gerçek sistemde veritabanı olurdu) ─────────────────
DURUM = {
    "profil": None,
    "seferler": [],           # [{id, tarih, hat, binis, inis, kapi, sure_dk, degerlendirildi}]
    "degerlendirmeler": [],   # [{sefer_id, puanlar, yorum, gecerli, ts}]
    "odul": {"kazanilan": 0, "kullanilan": 0},
}


def _rasgele_sefer_uret(memory_db, durak_dict, hat_kapasite, adet=24):
    """Gercek hat ve durak verisinden inandirici mock sefer gecmisi."""
    rnd = random.Random(42)          # tekrarlanabilir demo

    def _fallback_seferler():
        """Canli/disk veri henüz hazır değilse konsept ekranı boş bırakma."""
        rotalar = [
            ("34G", "Avcılar Merkez", "Zincirlikuyu"),
            ("500T", "Tuzla Şifa Mahallesi", "Cevizlibağ"),
            ("129T", "Bostancı", "Taksim"),
        ]
        araclar = {
            "34G": ["M3412", "M3486"],
            "500T": ["O5004", "O5071"],
            "129T": ["C1292", "C1298"],
        }
        simdi = datetime.now()
        sonuc = []
        for i in range(adet):
            hat, binis, inis = rotalar[i % len(rotalar)]
            if i % 2:
                binis, inis = inis, binis
            t = simdi - timedelta(days=i % 12, hours=(i * 2) % 11,
                                  minutes=(i * 7) % 60)
            sonuc.append({
                "id": "S%03d" % (i + 1),
                "tarih": t.strftime("%Y-%m-%d %H:%M"),
                "gun": t.strftime("%d.%m.%Y"),
                "saat": t.strftime("%H:%M"),
                "hat": hat,
                "binis_kodu": "", "binis": binis,
                "inis_kodu": "", "inis": inis,
                "kapi": araclar[hat][i % 2],
                "sure_dk": 24 + (i * 5) % 33,
                "ucret_tl": [17.85, 17.85, 8.96, 0.0][i % 4],
                "degerlendirildi": False,
            })
        sonuc.sort(key=lambda x: x["tarih"], reverse=True)
        return sonuc

    if not memory_db or not durak_dict:
        return _fallback_seferler()

    # Yolcu sayisi yuksek, tanidik hatlar
    aday_hatlar = [h for h in ("34AS", "34G", "500T", "129T", "15F", "12A",
                               "76D", "50B", "14R", "36A")
                   if any(h in v for v in memory_db.values())]
    if not aday_hatlar:
        aday_hatlar = list({h for v in list(memory_db.values())[:400] for h in v})[:10]

    hat_durak = {}
    for kod, hatlar in memory_db.items():
        m = durak_dict.get(kod)
        if not m or not m.get("ad"):
            continue
        for h in hatlar:
            if h in aday_hatlar:
                hat_durak.setdefault(h, []).append((kod, m["ad"]))

    # ── GERCEKCI DESEN: yolcu rastgele gezmiyor ────────────────────────
    # Duzenli bir yolcunun gecmisi birkac SABIT hat, SABIT durak cifti ve
    # kucuk bir arac havuzundan olusur (ayni hatta ayni araclar doner).
    # Rastgele uretim hem gercek disi olur hem de "tekrarlayan sikayet"
    # mantigi hic tetiklenmez — cunku her sikayet baska araca gider.
    duzenli = [h for h in aday_hatlar if len(hat_durak.get(h, [])) >= 2][:3]
    if not duzenli:
        return _fallback_seferler()
    rota_havuzu = {}
    arac_havuzu = {}
    for h in duzenli:
        ds = hat_durak[h]
        rota_havuzu[h] = rnd.sample(ds, 2)
        # Hat basina 2 arac: biri sorunlu, biri normal
        arac_havuzu[h] = ["%s%04d" % (rnd.choice("MOC"), rnd.randint(1000, 9999))
                          for _ in range(2)]

    seferler = []
    simdi = datetime.now()
    for i in range(adet):
        h = rnd.choice(duzenli)
        ds = hat_durak.get(h) or []
        if len(ds) < 2:
            continue
        b, inis = rota_havuzu[h]
        if rnd.random() < 0.5:            # donus yonu
            b, inis = inis, b
        t = simdi - timedelta(days=rnd.randint(0, 13),
                              hours=rnd.randint(0, 12), minutes=rnd.randint(0, 59))
        seferler.append({
            "id": "S%03d" % (i + 1),
            "tarih": t.strftime("%Y-%m-%d %H:%M"),
            "gun": t.strftime("%d.%m.%Y"),
            "saat": t.strftime("%H:%M"),
            "hat": h,
            "binis_kodu": b[0], "binis": b[1],
            "inis_kodu": inis[0], "inis": inis[1],
            "kapi": rnd.choice(arac_havuzu[h]),
            "sure_dk": rnd.randint(12, 58),
            "ucret_tl": rnd.choice([17.85, 17.85, 8.96, 0.0]),
            "degerlendirildi": False,
        })
    seferler.sort(key=lambda x: x["tarih"], reverse=True)
    return seferler


def profil_kur(memory_db, durak_dict, hat_kapasite, kart_tipi="tam"):
    """Demo profili olusturur (kart tanimli kullanici)."""
    kt = KART_TIPLERI.get(kart_tipi, KART_TIPLERI["tam"])
    # Önce seferleri üret: veri henüz hazır değilse profil nesnesini yarım
    # bırakıp sonraki isteklerin boş ekran göstermesini önler.
    seferler = _rasgele_sefer_uret(memory_db, durak_dict, hat_kapasite)
    DURUM["profil"] = {
        "ad": "Demo Kullanıcı",
        "kart_no": "1234 **** **** 5678",
        "kart_tipi": kart_tipi,
        "kart_tipi_ad": kt["ad"],
        "kart_ikon": kt["ikon"],
        "engelli": kt["engelli"],
        "bakiye_tl": 142.50,
        "uye_tarih": "2024-03-11",
    }
    DURUM["seferler"] = seferler
    DURUM["degerlendirmeler"] = _demo_sinyalleri(seferler)
    degerlendirilen = {d["sefer_id"] for d in DURUM["degerlendirmeler"]
                       if d.get("sefer_id")}
    for sefer in DURUM["seferler"]:
        if sefer["id"] in degerlendirilen:
            sefer["degerlendirildi"] = True
    DURUM["odul"] = {"kazanilan": 0, "kullanilan": 0}
    return DURUM["profil"]


def _demo_sinyalleri(seferler):
    """Sunumda kümeleme mantığını görünür kılan, açıkça temsilî kayıtlar."""
    if not seferler:
        return []
    hedef = seferler[0]
    kayitlar = []
    desen = [
        ("sorun", "arac", "iklimlendirme"),
        ("sorun", "arac", "iklimlendirme"),
        ("sorun", "arac", "iklimlendirme"),
        ("sorun", "arac", "temizlik"),
    ] + [("sorunsuz", None, None)] * 16
    for i, (durum, yer, kategori) in enumerate(desen):
        sefer = seferler[i % len(seferler)]
        if durum == "sorun":
            sefer = dict(sefer, kapi=hedef["kapi"], hat=hedef["hat"])
        kayitlar.append(_bildirim_kaydi(
            sefer, durum, yer, kategori,
            "Sunum için temsilî geçmiş kayıt" if durum == "sorun" else "",
            kaynak="demo_gecmis"))
    return kayitlar


# ── Bağlamsal bildirim ─────────────────────────────────────────────────
def _hedef_belirle(sefer, yer):
    if yer == "arac":
        kapi = str(sefer.get("kapi") or "")
        if not kapi or "sefer" in kapi.lower() or "bağlam" in kapi.lower():
            return "hat", sefer.get("hat") or "Bilinmeyen hat"
        return "arac", kapi
    if yer == "durak":
        return "durak", sefer.get("binis") or "Bilinmeyen durak"
    return "hat", sefer.get("hat") or "Bilinmeyen hat"


def _bildirim_kaydi(sefer, durum, yer=None, kategori=None, aciklama="", kaynak="yolcu"):
    konular = []
    if durum == "sorun":
        alan, hedef = _hedef_belirle(sefer, yer)
        konular.append({
            "alan": alan, "hedef": hedef,
            "konu": SORUN_KATEGORILERI.get(kategori, kategori or "Diğer"),
            "kategori": kategori or "diger", "yer": yer or "sefer",
        })
    return {
        "sefer_id": sefer.get("id"), "hat": sefer.get("hat", "—"),
        "kapi": sefer.get("kapi", "—"), "durak": sefer.get("binis", "—"),
        "durum": durum, "yer": yer, "kategori": kategori,
        "yorum": str(aciklama).strip(), "gecerli": True, "sebepler": [],
        "konular": konular, "kaynak": kaynak, "ts": time.time(),
    }


def bildirim_ekle(sefer_id=None, durum="sorun", yer=None, kategori=None,
                  aciklama="", baglam=None, bacak=None):
    """Yıldız puanı yerine yolculuk bağlamına bağlı sonuç veya sorun kaydı."""
    sefer = next((s for s in DURUM["seferler"] if s["id"] == sefer_id), None)
    if not sefer and baglam:
        simdi = datetime.now()
        sefer = {
            "id": str(baglam.get("id") or "Y%d" % int(time.time() * 1000)),
            "tarih": simdi.strftime("%Y-%m-%d %H:%M"),
            "gun": simdi.strftime("%d.%m.%Y"), "saat": simdi.strftime("%H:%M"),
            "hat": str(baglam.get("hat") or "Toplu taşıma"),
            "binis": str(baglam.get("binis") or "Başlangıç"),
            "inis": str(baglam.get("inis") or "Hedef"),
            "kapi": str(baglam.get("kapi") or "Planlı sefer"),
            "sure_dk": int(baglam.get("sure_dk") or 0), "ucret_tl": 0.0,
            "degerlendirildi": False, "mod": str(baglam.get("mod") or "toplu"),
            "karbon_g": int(baglam.get("karbon_g") or 0),
        }
        DURUM["seferler"].insert(0, sefer)
    if not sefer:
        return {"durum": "hata", "mesaj": "Yolculuk bağlamı bulunamadı"}
    if sefer.get("degerlendirildi"):
        return {"durum": "hata", "mesaj": "Bu yolculuk için bildirim zaten kaydedildi"}
    durum = str(durum or "").strip().lower()
    if durum not in ("sorunsuz", "sorun"):
        return {"durum": "hata", "mesaj": "Yolculuk sonucu seçilmedi"}
    if durum == "sorun":
        if yer not in SORUN_YERLERI:
            return {"durum": "hata", "mesaj": "Sorunun yaşandığı yeri seçin"}
        if kategori not in SORUN_KATEGORILERI:
            return {"durum": "hata", "mesaj": "Sorun başlığını seçin"}
        if len(str(aciklama).strip()) < 8:
            return {"durum": "hata", "mesaj": "Sorunu en az 8 karakterle kısaca açıklayın"}
    bildirim_seferi = dict(sefer)
    if bacak:
        bildirim_seferi["hat"] = str(bacak.get("hat") or sefer.get("hat") or "Toplu taşıma")
        bildirim_seferi["kapi"] = str(bacak.get("kapi") or sefer.get("kapi") or "Planlı sefer")
    kayit = _bildirim_kaydi(bildirim_seferi, durum, yer, kategori, aciklama)
    if bacak:
        kayit["bacak"] = {"hat": bildirim_seferi["hat"], "kapi": bildirim_seferi["kapi"],
                           "mod": str(bacak.get("mod") or ""), "sira": bacak.get("sira")}
    DURUM["degerlendirmeler"].append(kayit)
    sefer["degerlendirildi"] = True
    return {
        "durum": "tamam", "sonuc": durum,
        "mesaj": ("Yolculuk sorunsuz tamamlandı olarak kaydedildi" if durum == "sorunsuz"
                   else "Bildiriminiz yolculuk bağlamıyla kaydedildi"),
        "inceleme_esigi": TEKRAR_ESIGI,
        "gecerli_toplam": sum(1 for d in DURUM["degerlendirmeler"] if d["gecerli"]),
    }


# ── Eski puanlama API'si için geriye dönük uyumluluk ───────────────────
def dogruluk_denetle(sefer, puanlar, yorum):
    """Asgari veri kalitesini denetler; görüşün içeriğini yargılamaz."""
    sebepler = []
    degerler = [v for v in puanlar.values() if isinstance(v, (int, float)) and v > 0]

    if len(degerler) < DEGERLENDIRME_ASGARI_SORU:
        sebepler.append("En az üç soru yanıtlanmalı")
    if len(str(yorum).strip()) > 0 and len(str(yorum).strip()) < 4:
        sebepler.append("Yorum çok kısa")

    return (len(sebepler) == 0), sebepler


def _konu_cikar(puanlar, sefer):
    """
    Düşük puanlanan başlıkları 'şikâyet konusu'na çevirir.
    Gerçek üründe bunu bir dil modeli sınıflandırırdı; burada kural tabanlı
    (INTENT: "AI sınıflandırma mock kalabilir").
    """
    etiket = {
        "sefer_sikligi": ("hat", "Sefer sıklığı yetersiz"),
        "kalabalik":     ("hat", "Aşırı yoğunluk"),
        "saat_uyum":     ("hat", "Saat uyumsuzluğu"),
        "temizlik":      ("arac", "Temizlik sorunu"),
        "klima":         ("arac", "Isıtma/klima arızası"),
        "erisim":        ("arac", "Engelli erişimi yetersiz"),
        "bekleme_alani": ("durak", "Bekleme alanı yetersiz"),
        "bilgi_ekrani":  ("durak", "Bilgi ekranı çalışmıyor"),
        "durak_erisim":  ("durak", "Durak erişimi engelli"),
        "surus":         ("sofor", "Sürüş güvenliği"),
        "iletisim":      ("sofor", "İletişim sorunu"),
        "duraga_yanasma": ("sofor", "Durağa yanaşmıyor"),
    }
    out = []
    for kod, puan in puanlar.items():
        if not isinstance(puan, (int, float)) or puan > 2:
            continue
        e = etiket.get(kod)
        if not e:
            continue
        alan, konu = e
        hedef = {"hat": sefer["hat"], "arac": sefer["kapi"],
                 "durak": sefer["binis"], "sofor": sefer["kapi"]}.get(alan, "")
        out.append({"alan": alan, "konu": konu, "hedef": hedef, "puan": puan})
    return out


def degerlendirme_ekle(sefer_id, puanlar, yorum):
    sefer = next((s for s in DURUM["seferler"] if s["id"] == sefer_id), None)
    if not sefer:
        return {"durum": "hata", "mesaj": "Sefer bulunamadı"}
    if sefer["degerlendirildi"]:
        return {"durum": "hata", "mesaj": "Bu sefer zaten değerlendirildi"}

    gecerli, sebepler = dogruluk_denetle(sefer, puanlar, yorum)
    kayit = {
        "sefer_id": sefer_id, "hat": sefer["hat"], "kapi": sefer["kapi"],
        "durak": sefer["binis"], "puanlar": puanlar, "yorum": str(yorum).strip(),
        "gecerli": gecerli, "sebepler": sebepler,
        "konular": _konu_cikar(puanlar, sefer) if gecerli else [],
        "ts": time.time(),
    }
    DURUM["degerlendirmeler"].append(kayit)
    sefer["degerlendirildi"] = True

    gecerli_say = sum(1 for d in DURUM["degerlendirmeler"] if d["gecerli"])
    return {
        "durum": "tamam", "gecerli": gecerli, "sebepler": sebepler,
        "gecerli_toplam": gecerli_say,
        "odul": DURUM["odul"],
        "yeni_odul": False,
    }


def kurum_raporu():
    """
    İETT tarafının göreceği görünüm: tekrarlayan bildirimler gruplanır,
    eşiği aşanlar için doğrulanacak inceleme adayı üretilir.
    """
    grup = {}
    for d in DURUM["degerlendirmeler"]:
        if not d["gecerli"]:
            continue
        for k in d["konular"]:
            anahtar = (k["alan"], k["hedef"], k["konu"])
            g = grup.setdefault(anahtar, {"alan": k["alan"], "hedef": k["hedef"],
                                          "konu": k["konu"], "adet": 0})
            g["adet"] += 1

    liste = sorted(grup.values(), key=lambda x: -x["adet"])
    bildirimler = []
    for g in liste:
        if g["adet"] >= TEKRAR_ESIGI:
            if g["alan"] in ("arac", "sofor"):
                bildirimler.append({
                    "tip": "arac_inceleme",
                    "baslik": "%s için araç inceleme adayı" % g["hedef"],
                    "detay": "%s — %d bildirim; saha doğrulaması gerekir" % (g["konu"], g["adet"]),
                    "hedef": g["hedef"],
                })
            elif g["alan"] == "durak":
                bildirimler.append({
                    "tip": "durak_inceleme",
                    "baslik": "%s için durak iyileştirme adayı" % g["hedef"],
                    "detay": "%s — %d bildirim; saha doğrulaması gerekir" % (g["konu"], g["adet"]),
                    "hedef": g["hedef"],
                })
            else:
                bildirimler.append({
                    "tip": "hat_inceleme",
                    "baslik": "%s için sefer planı inceleme adayı" % g["hedef"],
                    "detay": "%s — %d bildirim; operasyon doğrulaması gerekir" % (g["konu"], g["adet"]),
                    "hedef": g["hedef"],
                })

    # Erişilebilirlik: kart tipinden engellilik çıkarımı yapılmaz. Yalnızca
    # yolcunun açıkça verdiği durak erişimi geri bildirimleri gruplanır.
    erisim = []
    say = {}
    for d in DURUM["degerlendirmeler"]:
        if not d["gecerli"]:
            continue
        for k in d["konular"]:
            if k.get("kategori") == "erisilebilirlik" and k["alan"] == "durak":
                say[k["hedef"]] = say.get(k["hedef"], 0) + 1
    for durak, n in sorted(say.items(), key=lambda x: -x[1]):
        erisim.append({
            "durak": durak, "bildirim": n,
            "not": "Anonim erişim sinyali; yatırım kararı öncesi saha doğrulaması gerekir",
        })

    varlik = {}
    for g in liste:
        anahtar = (g["alan"], g["hedef"])
        v = varlik.setdefault(anahtar, {"alan": g["alan"], "hedef": g["hedef"],
                                        "toplam_sinyal": 0, "konular": []})
        v["toplam_sinyal"] += g["adet"]
        v["konular"].append({"konu": g["konu"], "adet": g["adet"],
                              "inceleme_adayi": g["adet"] >= TEKRAR_ESIGI})
    varliklar = sorted(varlik.values(), key=lambda x: -x["toplam_sinyal"])
    tamamlanan = sum(1 for d in DURUM["degerlendirmeler"] if d.get("gecerli"))
    sorunlu = sum(1 for d in DURUM["degerlendirmeler"]
                  if d.get("gecerli") and d.get("durum") == "sorun")
    return {"gruplar": liste, "bildirimler": bildirimler, "erisim": erisim,
            "varliklar": varliklar, "tamamlanan": tamamlanan,
            "sorunlu": sorunlu,
            "sorun_orani": round((100.0 * sorunlu / tamamlanan), 1) if tamamlanan else 0,
            "veri_notu": "Temsilî kayıtlar; kişisel açıklamalar bu özette gösterilmez"}


def seferleri_ozetli():
    """Yolcunun kendi gönderdiği bildirimi geçmiş kartında görünür kılar."""
    son = {}
    for kayit in DURUM["degerlendirmeler"]:
        if kayit.get("sefer_id"):
            son[kayit["sefer_id"]] = kayit
    sonuc = []
    for ham in DURUM["seferler"]:
        sefer = dict(ham)
        kayit = son.get(sefer["id"])
        if kayit:
            sorun = kayit.get("durum") == "sorun" or bool(kayit.get("konular"))
            sefer["bildirim_ozeti"] = {
                "durum": "sorun" if sorun else "sorunsuz",
                "yer": SORUN_YERLERI.get(kayit.get("yer"), ""),
                "kategori": SORUN_KATEGORILERI.get(kayit.get("kategori"), ""),
                "aciklama": ("" if kayit.get("kaynak") == "demo_gecmis"
                              else str(kayit.get("yorum") or "")[:180]),
                "kurum_durumu": ("Benzer anonim sinyallerle birlikte değerlendiriliyor"
                                  if sorun else "Sorunsuz yolculuk paydasına eklendi"),
            }
        sonuc.append(sefer)
    return sonuc


def ozet():
    gecerli = sum(1 for d in DURUM["degerlendirmeler"] if d["gecerli"])
    toplam = len(DURUM["degerlendirmeler"])
    return {
        "profil": DURUM["profil"],
        "sefer_sayisi": len(DURUM["seferler"]),
        "degerlendirilen": toplam,
        "gecerli": gecerli,
        "gecersiz": toplam - gecerli,
        "odul": DURUM["odul"],
        "inceleme_esigi": TEKRAR_ESIGI,
        "sorun_yerleri": SORUN_YERLERI,
        "sorun_kategorileri": SORUN_KATEGORILERI,
    }
