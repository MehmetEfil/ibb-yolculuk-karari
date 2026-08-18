import time
import os
import json as _json_mod
from datetime import datetime, timedelta
from collections import Counter
import random
import re
import requests
from rayli import rayli_rota_alternatifleri
from services import guncelle_kavsaklar
from flask import jsonify, request, render_template
from utils import *
from services import (
    _lock,
    PANEL_DATA,
    MEMORY_DB, DURAK_DICT,          # IS_DB_READY ICE AKTARILMAZ (bkz. api_motor_hat_bul)
    FILO_CACHE, LIVE_BUS_CACHE, OLAY_CACHE, API_RESPONSE_CACHE,
    HAFTALIK, ARSIV_CACHE, SAAT_CACHE,
    GECIKME_CACHE, YOGUNLUK_CACHE, ANALYSIS_CACHE,
    HAT_BILGI_CACHE, ARAC_KONUM_GECMIS, UZUN_DURUŞ_CACHE,
    ISTANBUL_PROFIL, _SAAT_DAGILIM_HIC, _SAAT_DAGILIM_HS,IETT_USER, IETT_PASS, trafik_seviye,
    get_live_buses_cached, tahmin_yon_terminal, fetch_soap,get_traffic_index_history,
    get_traffic_index_history_summary, fetch_soap_xml,
    olay_guncelle, get_arac_ozellik, get_trafik, saat_trafik_katsayi,
    build_haftalik, hesapla_analiz, hesapla_gecikme_skorlari, hesapla_yogunluk,
    guncelle_filo, guncelle_arsiv,
    get_hat_bilgi, hesapla_headway,
    _norm_hat_kodu, _duyuru_hata_ait_mi, _parse_aspnet_date,
    hat_skoru, arac_durak_yaklasiyor_mu, rota_mesafe_km, eta_hesapla,
    arac_gercek_yon, arac_hareket_durumu, segment_sure_tahmini,
    eta_araligi, guzergah_mesafe_km, guzergah_trafik_ort, guzergah_yon_gecerli,
    yon_sirali_gecerli, HAT_DURAK_SIRA, hat_ring_mi, durak_siralari,
    garaj_listesi,
    garajda_mi,
    hat_yon_durak_listesi,
    DURAK_KOMSU, YURU_HIZ_KMS,
    KARBON, karbon_otomobil_g, karbon_otobus_g, karbon_rayli_g, hat_doluluk,
    arac_karbon_bilgisi,
    osrm_rota, ispark_listesi, yol_tikaniklik_carpani,
    _trafik_sapmasi,
    URL_ANA, URL_IBB, URL_FILO, URL_IBB360, URL_SAAT,
    TOMTOM_KEY, guncelle_kavsaklar
)

# ── Kapasite modeli sabitleri (tüm bakım endpoint'leri bu değerleri kullanır) ──
_KAPASITE_ACIL_PCT  = 0.20   # %20 acil arıza rezervi
_KAPASITE_KAZA_PCT  = 0.10   # %10 kaza rezervi
_KAPASITE_NET_PCT   = 0.70   # %70 net bakım kapasitesi
_KAPASITE_GECE_BONUS = 2     # 01-05 gece penceresi: +2 ek slot

def register_routes(app, db):

    @app.route('/api/en_yakin_durak')
    def api_en_yakin_durak():
        lat = temiz_sayi(request.args.get('lat', '0'))
        lon = temiz_sayi(request.args.get('lon', '0'))
        if abs(lat) < 1 or abs(lon) < 1:
            return jsonify({"hata": "Geçersiz konum"})

        min_dist = 9999
        kodu = ""
        ad = ""

        with _lock:
            for k, d in DURAK_DICT.items():
                if d['lat'] > 0 and d['lon'] > 0:
                    dist = hav(lat, lon, d['lat'], d['lon'])
                    if dist < min_dist:
                        min_dist = dist
                        kodu = k
                        ad = d['ad']

        if kodu:
            return jsonify({"kodu": kodu, "ad": ad, "mesafe_m": int(min_dist * 1000)})

        return jsonify({"hata": "Yakınlarda durak bulunamadı."})

    TR_MAP = str.maketrans({
        'Ç':'C','Ğ':'G','İ':'I','I':'I','Ö':'O','Ş':'S','Ü':'U',
        'ç':'c','ğ':'g','ı':'i','i':'i','ö':'o','ş':'s','ü':'u',
    })
    STOP_KELIMELER = {
        'DURAK','DURAGI','DURAĞI','DURAGINDA','DURAGI','ISTASYON','ISTASYONU',
        'METRO','METROBUS','METROBÜS','ISKELE','ISKELESI','İSKELE','İSKELESİ',
        'MAH','MAHALLE','MAHALLESI','MAHALLESİ','MEYDAN','MEYDANI',
        'CAD','CADDE','CADDESI','CADDESİ','SK','SOK','SOKAK','SOKAĞI',
        'BULV','BLV','BULVARI','BUL','SITESI','SİTESİ','SITE',
        'YOLU','YOL','KÖPRÜ','KOPRU','GİŞELERİ','GISELERI',
        'ISTANBUL','İSTANBUL','TÜRKİYE','TURKIYE',
    }

    def _norm(s):
        """Türkçe karakter normalize + upper. Boş veya None için ''."""
        if not s: return ''
        return str(s).upper().translate(TR_MAP)

    def _tokenize(s):
        """Metni anlamlı token listesine çevir. Stopword filtresi uygular."""
        norm = re.sub(r'[^\wİıĞğÜüŞşÖöÇç]+', ' ', _norm(s))
        return [t for t in norm.split() if len(t) >= 2 and t not in STOP_KELIMELER]

    def _durak_skor(q_tokens, ad_tokens):
        """
        Sorgu tokenları ile durak adı tokenları arasındaki eşleşme skoru.
        Yüksek skor = daha iyi eşleşme. 0 = hiç eşleşme yok.
        """
        if not q_tokens or not ad_tokens: return 0
        skor = 0
        kullanilan = set()
        for qt in q_tokens:
            best_i, best_pts = -1, 0
            for i, at in enumerate(ad_tokens):
                if i in kullanilan: continue
                if qt == at:
                    pts = 100  # tam eşleşme
                elif len(qt) >= 3 and qt in at:
                    pts = 60 + min(30, len(qt) * 3)  # sorgu durakta substring
                elif len(at) >= 3 and at in qt:
                    pts = 40 + min(20, len(at) * 2)  # durak sorguda substring
                elif len(qt) >= 4 and len(at) >= 4 and qt[:4] == at[:4]:
                    pts = 30  # prefix eşleşmesi
                else:
                    pts = 0
                if pts > best_pts:
                    best_pts = pts; best_i = i
            if best_pts > 0:
                skor += best_pts
                kullanilan.add(best_i)
        # tüm sorgu tokenları eşleşirse büyük bonus
        if len(kullanilan) == len(q_tokens):
            skor += 50
        # durak adı çok kısaysa ve hepsi eşleşirse ek bonus
        if len(kullanilan) == len(ad_tokens):
            skor += 30
        return skor

    # ── Durak arama indeksi ───────────────────────────────────────────
    # ÖLÇÜM: arama, rota hesabının %50'sini yiyordu. Sebep, her sorguda
    # 15.112 durağın adının ve ilçesinin YENİDEN token'lara ayrılmasıydı —
    # tek istekte 241.800 `_tokenize` çağrısı. Durak adları değişmediği için
    # bu iş bir kez yapılıp saklanabilir.
    #
    # İki katman:
    #   1) token önbelleği  — {kod: (ad_tokens, ilce_tokens, ad)}
    #   2) trigram tersine indeksi — {3'lü harf: {kod}}
    #
    # (2) neden güvenli: skorlayıcı ancak şu durumlarda puan verir —
    # tam eşleşme, biri diğerini içerir (uzunluk ≥3), ya da ilk 4 harf aynı.
    # Üçü de en az bir ortak 3'lü harf dizisi gerektirir. Yani trigram
    # kesişimi olmayan bir durak zaten 0 puan alırdı; elemek sonucu
    # değiştirmez. 3'ten kısa token'lar (yalnız tam eşleşmeyle puan
    # alabilirler) ayrıca kendi adlarıyla indekslenir.
    _DURAK_IDX = {"boyut": -1, "token": {}, "trigram": {}}

    def _trigramlar(token):
        if len(token) < 3:
            return (token,)
        return tuple({token[i:i + 3] for i in range(len(token) - 2)})

    def _durak_index_kur(durak_sozlugu):
        """Durak sözlüğü değiştiyse indeksi yeniden kur."""
        if _DURAK_IDX["boyut"] == len(durak_sozlugu):
            return
        token, trigram = {}, {}
        for kod, d in durak_sozlugu.items():
            ad = d.get('ad', '')
            if not ad:
                continue
            ad_t = _tokenize(ad)
            ilce_t = _tokenize(d.get('ilce', ''))
            if not ad_t and not ilce_t:
                continue
            token[kod] = (ad_t, ilce_t, ad)
            for t in ad_t + ilce_t:
                for g in _trigramlar(t):
                    trigram.setdefault(g, set()).add(kod)
        _DURAK_IDX.update({"boyut": len(durak_sozlugu),
                           "token": token, "trigram": trigram})

    def _durak_adaylari(metin, durak_sozlugu, top_n=5, min_skor=80):
        """
        Token bazlı fuzzy arama. En iyi top_n adayı (kod, skor, ad) tuple olarak döndür.
        Hem durak adında hem ilçe alanında arama yapar.
        """
        if not metin: return []
        q_tokens = _tokenize(metin)
        if not q_tokens: return []
        metin_strip = _norm(metin).strip()
        if metin_strip in durak_sozlugu:
            d = durak_sozlugu[metin_strip]
            return [(metin_strip, 1000, d.get('ad', metin_strip))]

        _durak_index_kur(durak_sozlugu)
        idx_token = _DURAK_IDX["token"]
        idx_tri = _DURAK_IDX["trigram"]

        # Yalnızca sorguyla ortak trigramı olan duraklar puanlanır.
        # DURAK_ARAMA_INDEKSSIZ=1 ile daraltma kapatılabilir: indeksin
        # doğruluğu bozup bozmadığı ancak iki yol karşılaştırılarak
        # kanıtlanabilir (bkz. tests/test_durak_arama.py).
        if os.environ.get("DURAK_ARAMA_INDEKSSIZ") == "1":
            adaylar = set(idx_token)
        else:
            adaylar = set()
            for qt in q_tokens:
                for g in _trigramlar(qt):
                    s = idx_tri.get(g)
                    if s:
                        adaylar |= s

        # DİKKAT — sıra önemli. Aynı puanlı duraklar çok (örn. "AVCILAR" ve
        # "AVCILAR METROBÜS" ikisi de 270 alıyor) ve `sonuclar.sort` kararlı
        # olduğu için eşitliği GİRİŞ SIRASI bozar. Adaylar bir küme olduğundan
        # doğrudan küme üzerinde gezmek sırayı rastgeleleştiriyordu: aynı
        # sorgu çalıştırmadan çalıştırmaya farklı ilk sonuç veriyordu
        # (str hash'i süreç başına rastgele). Bu yüzden indeksin kendi
        # sırasında (= durak sözlüğünün sırası) gezip küme üyeliğine bakıyoruz;
        # üyelik testi ucuz, puanlama pahalıydı — kazanç korunuyor, sıra
        # eski davranışla birebir aynı kalıyor.
        sonuclar = []
        for kod, kayit in idx_token.items():
            if kod not in adaylar:
                continue
            ad_tokens, ilce_tokens, ad = kayit
            # Durak adı skoru
            sk_ad = _durak_skor(q_tokens, ad_tokens) if ad_tokens else 0
            # İlçe skoru: ilçe yalnız bir kelime — daha düşük katsayı
            sk_ilce = _durak_skor(q_tokens, ilce_tokens) // 2 if ilce_tokens else 0
            # Eşleşmeyen tokenları durakla birleşik dene (ilçe + ad)
            if sk_ad > 0 and sk_ilce > 0:
                # Hem ad hem ilçe katkıda bulunuyor → güçlü eşleşme
                sk = sk_ad + sk_ilce
            else:
                sk = max(sk_ad, sk_ilce)
            if sk >= min_skor:
                sonuclar.append((kod, sk, ad))
        sonuclar.sort(key=lambda x: x[1], reverse=True)
        return sonuclar[:top_n]

    def _durak_kodu_bul(metin, durak_sozlugu):
        """En iyi tek aday — geri uyumluluk için."""
        adaylar = _durak_adaylari(metin, durak_sozlugu, top_n=1)
        return adaylar[0][0] if adaylar else None

    def _geocode_nominatim(metin):
        """Nominatim ile adres/yer → (lat, lon, display_name). None döner hatada."""
        try:
            url="https://nominatim.openstreetmap.org/search"
            params={"q":f"{metin}, İstanbul, Türkiye","format":"json","limit":1,
                    "addressdetails":0,"viewbox":"28.5,41.3,29.5,40.8","bounded":1}
            r=requests.get(url,params=params,timeout=6,headers={"User-Agent":"UKOME-Portal/1.0"})
            data=r.json()
            if data:
                return float(data[0]["lat"]),float(data[0]["lon"]),data[0].get("display_name","")
            # bounded başarısızsa İstanbul kısıtsız dene
            params2={"q":f"{metin}, İstanbul","format":"json","limit":1}
            r2=requests.get(url,params=params2,timeout=6,headers={"User-Agent":"UKOME-Portal/1.0"})
            data2=r2.json()
            if data2:
                lat,lon=float(data2[0]["lat"]),float(data2[0]["lon"])
                if 40.5<=lat<=41.5 and 27.5<=lon<=30.0:
                    return lat,lon,data2[0].get("display_name","")
        except Exception:
            pass
        return None

    def _parse_koordinat(metin):
        m=re.match(r'^(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)$',metin.strip())
        if m:
            lat,lon=float(m.group(1)),float(m.group(2))
            if 40.0<=lat<=42.0 and 27.0<=lon<=31.0: return lat,lon
        return None

    def _en_yakin_durak_koordinat(lat,lon,snap_durak,max_km=2.0):
        en_iyi=None; en_dist=max_km
        for kod,d in snap_durak.items():
            dlat=d.get('lat',0); dlon=d.get('lon',0)
            if not dlat or not dlon: continue
            dist=hav(lat,lon,dlat,dlon)
            if dist<en_dist: en_dist=dist; en_iyi=kod
        return en_iyi, en_dist

    def _bekleme_hesapla(hat, durak_lat, durak_lon, canli_eta_liste=None,
                         varis_gecikmesi_dk=0):
        """
        Durakta o hattın aracını bekleme süresi (dk).

        `varis_gecikmesi_dk`: kullanıcının o durağa VARMASI için geçecek süre
        (yürüyüş, önceki segment vb.). Bundan önce geçecek araçlar kaçırılmış
        sayılır — aksi hâlde "6 dk yürü, 2 dk sonra gelen otobüse bin" gibi
        imkânsız bir tarif üretilirdi.

        1. Canlı ETA varsa: kullanıcı vardıktan SONRA gelen ilk araç
        2. Yoksa: hat headway / 2 (rastgele varış)
        3. Headway de yoksa: 8 dk varsayılan
        Returns: (bekleme_dk, kaynak: 'canli'|'headway'|'varsayilan', detay_str)
        """
        if canli_eta_liste is None:
            canli_eta_liste = _canli_eta_hesapla(hat, durak_lat, durak_lon)
        if canli_eta_liste:
            pay = max(0, int(varis_gecikmesi_dk))
            # Kullanıcı durağa varmadan geçecek araçları ele
            yakalanabilir = [e for e in canli_eta_liste if e.get('eta_min', 0) >= pay]
            if yakalanabilir:
                ilk = yakalanabilir[0]['eta_min']
                bek = max(1, ilk - pay)
                if pay > 0 and len(yakalanabilir) < len(canli_eta_liste):
                    kacan = len(canli_eta_liste) - len(yakalanabilir)
                    return bek, 'canli', f"Sonraki yakalanabilir araç {bek} dk sonra ({kacan} araç siz varmadan geçiyor)"
                return bek, 'canli', f"Sonraki araç {bek} dk içinde"
            # Görünen araçların hepsi kullanıcı varmadan geçiyor → headway'e düş
        # Headway tahmini
        try:
            with _lock:
                yc = YOGUNLUK_CACHE.get(hat, {})
            arac = yc.get('arac_sayisi', 0)
            if arac > 0:
                # Sefer süresi: kapasite_saat'ten geri hesap, yoksa hatlar uzunluğuna göre
                kapasite_saat = yc.get('kapasite_saat', 0)
                hat_kap = yc.get('arac_kapasite', 90)
                if kapasite_saat and hat_kap:
                    sefer_saat = kapasite_saat / hat_kap / arac
                    headway = max(2, 60 / max(sefer_saat, 0.5))
                else:
                    headway = max(3, 60 / arac)  # kabaca 1 saatte arac sayısı kadar geçer
                bek = max(2, round(headway / 2))
                return bek, 'headway', f"~{int(headway)} dk aralık · ortalama bekleme"
        except Exception:
            pass
        return 8, 'varsayilan', "Tipik bekleme süresi"

    def _canli_eta_hesapla(hat, durak_lat, durak_lon, max_eta=60):
        """
        Bir hattın o durağa yaklaşan canlı otobüslerini bulup ETA listesini döndürür.
        Format: [{kapi, plaka, eta_min, dist_km, hiz}, ...] sıralı.
        """
        try:
            normalized, _ = get_live_buses_cached(hat)
        except Exception:
            return []
        if not normalized: return []
        try:
            normalized = tahmin_yon_terminal(hat, normalized)
        except Exception:
            pass
        # Hat durak listesini al (varsa)
        cache_key = f"durak_detay_{hat}"
        with _lock: cached_durak = API_RESPONSE_CACHE.get(cache_key)
        hat_duraklar = cached_durak.get("duraklar", []) if cached_durak else []

        sonuclar = []
        for b in normalized:
            try:
                blat, blon = b.get("lat"), b.get("lon")
                if not blat or not blon: continue
                arac_yonu = b.get("yon")
                dist_km = hav(blat, blon, durak_lat, durak_lon)
                if dist_km > 15: continue  # 15km'den uzaktakini hesaplama
                # Yön kontrolü (varsa) - yaklaşmıyorsa atla
                yaklasiyor, sira_farki = arac_durak_yaklasiyor_mu(
                    blat, blon, arac_yonu, durak_lat, durak_lon, hat_duraklar,
                    hat_kodu=hat)
                # NOT: eskiden filtre yalnizca `hat_duraklar` doluysa
                # uygulaniyordu; onbellek bossa uzaklasan araca da ETA
                # veriliyordu. Artik SIRANO yedegi oldugu icin sart kalkti.
                if not yaklasiyor: continue

                # ── SEFERDE OLMAYAN ARAÇ ETA'YA GİRMEZ ──────────────────
                # Bu fonksiyon ROTA KARTLARINI besliyor ("● CANLI 15 dk").
                # `/api/durak_eta` ucundan AYRI bir kod yolu ve burada
                # hareket/garaj kontrolu HIC yoktu. Sonuc: garajda park
                # etmis otobus yolcuya "gelecek" diye gosteriliyordu.
                # Olculdu (canli veri): 34G M4852 garajda -> "2 dk",
                # 500T C-361 garajda, hiz 0 -> "22 dk".
                # Gelmeyecek arac icin sure vermek, sure vermemekten
                # kotudur — yolcu durakta bosuna bekler. Canli arac
                # kalmazsa cagiran zaten planli saate dusuyor (PLAN rozeti).
                try:
                    _hrk, _drs_sn, _drs_m = arac_hareket_durumu(b.get("kapi"))
                except Exception:
                    _hrk = True
                try:
                    _garaj_ad, _garaj_m = garajda_mi(blat, blon)
                except Exception:
                    _garaj_ad = None
                if _garaj_ad or not _hrk:
                    continue

                trafik = get_trafik(blat, blon)
                kats = trafik.get("katsayi", 1.0)
                if hat_duraklar:
                    route_km = rota_mesafe_km(blat, blon, durak_lat, durak_lon, arac_yonu, hat_duraklar)
                else:
                    route_km = dist_km * 1.4  # düz çizgi → kabaca yol mesafesi

                spd_raw = float(b.get("hiz", 0) or 0)
                # Durak temelli model (hat profili varsa), yoksa mesafe temelli
                eta_ham, serbest_dk, gecikme_dk, efektif_hiz = eta_hesapla(
                    route_km, spd_raw, kats,
                    kalan_durak=(sira_farki if hat_duraklar else None), hat=hat)
                eta_min = max(1, round(eta_ham))
                if eta_min > max_eta: continue

                sonuclar.append({
                    "kapi": b.get("kapi", "—"),
                    "plaka": b.get("plaka", "—"),
                    "eta_min": eta_min,
                    "dist_km": round(dist_km, 2),
                    "hiz": int(spd_raw),
                    "trafik": trafik.get("seviye", ""),
                })
            except Exception:
                continue
        sonuclar.sort(key=lambda x: x["eta_min"])
        return sonuclar

    def _coz_giris(girdi, snap_durak):
        """
        Girdiyi çöz: durak (fuzzy) → koordinat → adres (Nominatim).
        Returns: (durak_kodu, display_name, lat, lon, tip, oneriler)
        tip: 'durak' | 'koordinat' | 'adres' | 'koordinat_yok' | 'adres_yok' | None
        oneriler: [{kodu, ad, lat, lon, skor}, ...] eşleşme zayıfsa öneriler.
        """
        bos = (None, None, None, None, None, [])
        if not girdi: return bos
        metin=girdi.strip()

        # 1. Koordinat
        koord=_parse_koordinat(metin)
        if koord:
            lat,lon=koord
            kod,dist=_en_yakin_durak_koordinat(lat,lon,snap_durak)
            if kod:
                ad=snap_durak[kod].get('ad',kod)
                return kod, f"Konuma en yakın: {ad} ({dist:.2f} km)", lat, lon, 'koordinat', []
            return None, None, lat, lon, 'koordinat_yok', []

        # 2. Fuzzy durak araması — top 5 aday
        adaylar = _durak_adaylari(metin, snap_durak, top_n=5)
        if adaylar:
            top_kod, top_skor, top_ad = adaylar[0]
            d = snap_durak[top_kod]
            # Skor çok yüksek (>=200) → kesin → öneri listesi boş
            # Skor orta (80-200) → kabul et ama alternatifler de göster
            oneriler = []
            if top_skor < 200 and len(adaylar) > 1:
                for kod, sk, ad in adaylar[1:4]:
                    dd = snap_durak[kod]
                    oneriler.append({'kodu':kod,'ad':ad,'lat':dd.get('lat',0),
                                     'lon':dd.get('lon',0),'skor':sk,
                                     'ilce':dd.get('ilce','')})
            return top_kod, d.get('ad',top_kod), d.get('lat',0), d.get('lon',0), 'durak', oneriler

        # 3. Nominatim geocoding
        sonuc=_geocode_nominatim(metin)
        if sonuc:
            lat,lon,display=sonuc
            kod,dist=_en_yakin_durak_koordinat(lat,lon,snap_durak)
            if kod:
                ad=snap_durak[kod].get('ad',kod)
                return kod, f"🗺️ {display[:60]} → {ad}", lat, lon, 'adres', []
            return None, display, lat, lon, 'adres_yok', []

        return bos
    

    @app.route('/api/rota_debug')
    def api_rota_debug():
        a=request.args.get('a','').upper(); b=request.args.get('b','').upper()
        with _lock: snap_db=dict(MEMORY_DB); snap_durak=dict(DURAK_DICT)
        durak_a,_,_,_,_,_=_coz_giris(a, snap_durak)
        durak_b,_,_,_,_,_=_coz_giris(b, snap_durak)
        if not durak_a or not durak_b: return jsonify({"hata":"durak çözülemedi","a":durak_a,"b":durak_b})
        hatlar_a=set(snap_db.get(durak_a,[])); hatlar_b=set(snap_db.get(durak_b,[]))
        # hat → duraklar
        hat_to_duraklar={}
        for d_k,h_lst in snap_db.items():
            for h in h_lst: hat_to_duraklar.setdefault(h,[]).append(d_k)
        hatlar_a_komsu=set()
        for h in hatlar_a:
            for d in hat_to_duraklar.get(h,[]):
                for hh in snap_db.get(d,[]):
                    if hh not in hatlar_a: hatlar_a_komsu.add(hh)
        hatlar_b_komsu=set()
        for h in hatlar_b:
            for d in hat_to_duraklar.get(h,[]):
                for hh in snap_db.get(d,[]):
                    if hh not in hatlar_b: hatlar_b_komsu.add(hh)
        orta=hatlar_a_komsu&hatlar_b_komsu
        return jsonify({
            "durak_a":durak_a,"durak_b":durak_b,
            "hatlar_a":sorted(list(hatlar_a)),"hatlar_b":sorted(list(hatlar_b)),
            "memory_db_durak_n":len(snap_db),"hat_n":len(hat_to_duraklar),
            "hatlar_a_komsu_n":len(hatlar_a_komsu),"hatlar_b_komsu_n":len(hatlar_b_komsu),
            "orta_hat_n":len(orta),"orta_ornek":sorted(list(orta))[:30],
            "hatlar_a_komsu_ornek":sorted(list(hatlar_a_komsu))[:30],
        })


    # ══════════════════════════════════════════════════════
    # KARBON AYAK İZİ + HİBRİT ROTA
    # ══════════════════════════════════════════════════════
    def _toplu_karbon(rota):
        """Bir toplu taşıma rotasının kişi başı CO2 (gram) ve km toplamı.

        ARAÇ BAZLI HASSASİYET — filoda araçların %9,9'u CNG, biri elektrikli.
        Rotanın ilk bacağı için canlı GPS aracın KAPI NUMARASINI veriyor ve
        o aracın yakıt türü/markası/modeli elimizde. O bacakta "ortalama
        otobüs" yerine gerçek aracın emisyonu kullanılıyor; kalan bacaklarda
        hangi aracın geleceği belli olmadığı için hat ortalaması kalıyor.
        """
        g = 0.0
        km = 0.0
        kapi = ((rota.get('canli') or {}).get('kapi') or '').strip()
        if kapi in ('—', '-', ''):
            kapi = None
        ilk_otobus = True
        for s in (rota.get('sure_kirilim', {}) or {}).get('segmentler', []):
            m = s.get('mesafe_km') or 0
            km += m
            if s.get('mod') in ('metro', 'marmaray', 'tramvay', 'funikuler', 'teleferik'):
                g += karbon_rayli_g(m, mod=s.get('mod'))
            else:
                g += karbon_otobus_g(m, hat=s.get('hat'),
                                     kapi_no=kapi if ilk_otobus else None)
                ilk_otobus = False
        return g, km

    @app.route('/api/karbon_rota')
    def api_karbon_rota():
        """Uc secenegi yan yana: arac / toplu tasima / hibrit. Sure, km, CO2."""
        a = request.args.get('nereden', '').strip()
        b = request.args.get('nereye', '').strip()
        if not a or not b:
            return jsonify({"durum": "hata", "mesaj": "nereden ve nereye gerekli"})

        tr = _rota_hesapla(a, b)
        if tr.get('durum') != 'tamam' or not tr.get('rotalar'):
            return jsonify({"durum": "hata", "mesaj": tr.get('mesaj', 'Rota bulunamadi'),
                            "oneriler_a": tr.get('oneriler_a', []),
                            "oneriler_b": tr.get('oneriler_b', [])})

        en_iyi = tr['rotalar'][0]
        det = en_iyi.get('detay', {})
        o_lat = det.get('baslangic_lat') or det.get('b_lat')
        o_lon = det.get('baslangic_lon') or det.get('b_lon')
        h_lat = det.get('bitis_lat') or det.get('i_lat')
        h_lon = det.get('bitis_lon') or det.get('i_lon')

        t_g, t_km = _toplu_karbon(en_iyi)

        # Gelen aracın kendi yakıt bilgisi — varsa yolcuya gösterilir.
        # "Otobüs ortalama şu kadar kirletir" yerine "SENİN bineceğin araç
        # CNG, eşdeğer dizelden %11 temiz" diyebilmek için.
        _kapi = ((en_iyi.get('canli') or {}).get('kapi') or '').strip()
        _arac_karbon = arac_karbon_bilgisi(_kapi) if _kapi not in ('', '—', '-') else None

        secenekler = [{
            "tip": "toplu", "ad": "Toplu taşıma",
            "sure_dk": en_iyi.get('toplam_sure'),
            "km": round(t_km, 2),
            "co2_g": round(t_g),
            "hatlar": en_iyi.get('hatlar', []),
            "detay": "%d aktarma" % max(0, len(en_iyi.get('hatlar', [])) - 1),
            # Gelen aracın markası/modeli/yakıtı ve o araca özel emisyon
            "arac_karbon": _arac_karbon,
            # Arayuz ayni adim-adim paneli ve haritayi cizebilsin diye TAM rota
            "rota": en_iyi,
        }]

        # OSRM SERBEST AKIS suresi verir — trafigi bilmez. Ham haliyle kullanmak
        # arabayi haksiz yere cazip gosterirdi (Avcilar-Kadikoy 37 dk gibi).
        # Toplu tasimada kullandigimiz ayni trafik sapmasini araca da uyguluyoruz;
        # boylece iki secenek AYNI trafik varsayimiyla karsilastiriliyor.
        arac = osrm_rota(o_lat, o_lon, h_lat, h_lon) if (o_lat and h_lat) else None
        _t_sapma, _t_simdi, _t_norm = _trafik_sapmasi()
        _tikaniklik = yol_tikaniklik_carpani()      # saatin MUTLAK yavaslamasi
        if arac:
            a_km, a_dk_ham = arac
            # serbest akis x saatin tikanikligi x anlik sapma
            a_dk = a_dk_ham * _tikaniklik * max(1.0, _t_sapma)
            secenekler.append({
                "tip": "arac", "ad": "Araçla",
                "sure_dk": round(a_dk), "km": round(a_km, 2),
                "sure_serbest_dk": round(a_dk_ham),
                "tikaniklik_carpani": round(_tikaniklik, 2),
                "co2_g": round(karbon_otomobil_g(a_km)),
                "detay": "Tek kişi, benzinli · trafik dahil",
                # Harita cizimi icin ucdan uca koordinat
                "baslangic": {"lat": o_lat, "lon": o_lon},
                "hedef": {"lat": h_lat, "lon": h_lon},
            })

        hibrit = None
        ispark_ag = {"toplam": 0, "resmi": 0, "dinamik": 0}
        try:
            parklar = ispark_listesi()
            if parklar and o_lat and h_lat:
                toplam_kus = hav(o_lat, o_lon, h_lat, h_lon)
                adaylar = []
                for p in parklar:
                    # Resmî P+D tesisleri sürekli adaydır. Normal İSPARK'lar ise
                    # yalnızca kapasitesi gerçekten boşsa "dinamik aktarma"
                    # noktası olabilir; yol üstü parkları bu modele dahil edilmez.
                    kapasite = max(1.0, float(p.get('kapasite') or 0))
                    bos_orani = min(1.0, float(p.get('bos') or 0) / kapasite)
                    resmi_pd = bool(p.get('park_et_devam_et'))
                    yol_ustu = 'YOL ÜSTÜ' in str(p.get('tip') or '').upper()
                    if not p['acik']:
                        continue
                    if resmi_pd:
                        if p['bos'] < 5:
                            continue
                    elif (yol_ustu or kapasite < 30 or p['bos'] < 20
                          or bos_orani < 0.30):
                        continue
                    d_o = hav(o_lat, o_lon, p['lat'], p['lon'])
                    d_h = hav(p['lat'], p['lon'], h_lat, h_lon)
                    if d_o < 1.0 or d_h < 1.0:
                        continue
                    # DOLAMBAC: otopark yol uzerinde olmali.
                    # 1,6 fazla gevsekti — olculdu, Pendik→Taksim'de otopark
                    # baslangica 33,3 km, hedef ise 28,4 km uzaktaydi: yolcu
                    # HEDEFI GECIP geri donuyordu. Arac bacagi 45,3 km cikip
                    # duz surusun (35,3 km) uzerine ciktigi icin hibrit
                    # arabadan daha KIRLI oluyordu.
                    if d_o + d_h > toplam_kus * 1.25:
                        continue
                    if d_o > toplam_kus:      # hedeften uzaga surmek yok
                        continue
                    # PARK-AND-RIDE MANTIGI: otopark yolun ORTA kismindа olmali.
                    # Cok yakinsa arac bacagi ise yaramaz (yine bastan sona otobus),
                    # cok uzaksa neredeyse hedefe kadar arabayla gidilir ve karbon
                    # avantaji kaybolur. Ilerleme oranini 0.25-0.70 araligina sikistiriyoruz.
                    ilerleme = 1.0 - (d_h / max(0.1, toplam_kus))
                    if not (0.25 <= ilerleme <= 0.70):
                        continue
                    # İlk eleme yalnızca konuma göre değil, dolambaç ve güncel
                    # doluluk oranına göre yapılır. Mutlak boş yer sayısı büyük
                    # otoparkları haksız biçimde öne çıkarmamalı.
                    musaitlik_riski = 1.0 - min(1.0, float(p['bos']) / kapasite)
                    dolambac = (d_o + d_h) / max(0.1, toplam_kus)
                    ilerleme_sapmasi = abs(ilerleme - 0.45) / 0.25
                    on_puan = (0.45 * ilerleme_sapmasi
                               + 0.30 * musaitlik_riski
                               + 0.25 * max(0.0, dolambac - 1.0) / 0.25
                               + (0.08 if not resmi_pd else 0.0))
                    adaylar.append((on_puan, ilerleme, d_o, d_h, p, resmi_pd))
                adaylar.sort(key=lambda x: x[0])
                ispark_ag = {
                    "toplam": len(adaylar),
                    "resmi": sum(1 for x in adaylar if x[5]),
                    "dinamik": sum(1 for x in adaylar if not x[5]),
                }
                # Resmî ve dinamik tesislerin birlikte yarışabilmesi için en iyi
                # altı adayda gerçek araç + toplu taşıma rotası kurulur.
                for _on_puan, _ilerleme, d_o, d_h, p, resmi_pd in adaylar[:6]:
                    ar = osrm_rota(o_lat, o_lon, p['lat'], p['lon'])
                    if not ar:
                        continue
                    ar_km, ar_dk_ham = ar
                    ar_dk = ar_dk_ham * _tikaniklik * max(1.0, _t_sapma)
                    tr2 = _rota_hesapla("%.5f,%.5f" % (p['lat'], p['lon']), b)
                    if tr2.get('durum') != 'tamam' or not tr2.get('rotalar'):
                        continue
                    r2 = tr2['rotalar'][0]
                    # Normal İSPARK ancak toplu taşımaya gerçekten yakınsa
                    # dinamik aktarma noktasıdır. Uzak durağa yürütmek yok.
                    if not resmi_pd and int(r2.get('_yuru_a') or 0) > 12:
                        continue
                    g2, km2 = _toplu_karbon(r2)
                    toplam_dk = round(ar_dk + (r2.get('toplam_sure') or 0))
                    toplam_g = karbon_otomobil_g(ar_km) + g2
                    bos_orani = min(1.0, float(p['bos']) / max(1.0, float(p.get('kapasite') or 0)))
                    aday = {
                        "tip": "hibrit", "ad": "Hibrit (araç + toplu taşıma)",
                        "sure_dk": toplam_dk,
                        "km": round(ar_km + km2, 2),
                        "co2_g": round(toplam_g),
                        "hatlar": r2.get('hatlar', []),
                        "ispark": {"ad": p['ad'], "bos": p['bos'], "kapasite": p['kapasite'],
                                   "lat": p['lat'], "lon": p['lon'], "ilce": p['ilce'],
                                   "ucretsiz_dk": p['ucretsiz_dk'],
                                   "park_et_devam_et": resmi_pd,
                                   "aktarma_tipi": "resmi" if resmi_pd else "dinamik",
                                   "bos_orani": round(bos_orani * 100),
                                   "yerel_rezerv": max(5, round(float(p['kapasite']) * 0.20))},
                        "arac_bacagi": {"km": round(ar_km, 2), "dk": round(ar_dk),
                                        "co2_g": round(karbon_otomobil_g(ar_km))},
                        "toplu_bacagi": {"km": round(km2, 2), "dk": r2.get('toplam_sure'),
                                         "co2_g": round(g2)},
                        # Hibritin toplu bacagi da toplu tasima kadar DETAYLI
                        # gosterilebilsin: hat/bekleme/trafik kirilimi burada.
                        "toplu_rota": r2,
                        "baslangic": {"lat": o_lat, "lon": o_lon},
                        "hedef": {"lat": h_lat, "lon": h_lon},
                        "detay": "%s · %s (şu an %d yer boş)" % (
                            p['ad'],
                            "resmî Park Et Devam Et" if resmi_pd else "dinamik aktarma noktası",
                            p['bos']),
                    }
                    # Boyutları karşılaştırılabilir hâle getir: dakika ve gramı
                    # doğrudan toplamak yerine referans yolculuklara oranla.
                    _toplu_ref = max(1.0, float(en_iyi.get('toplam_sure') or toplam_dk))
                    _arac_ref = next((x for x in secenekler if x['tip'] == 'arac'), None)
                    if not _arac_ref or not _arac_ref.get('co2_g'):
                        continue
                    # DİNAMİK TEŞVİK: yalnızca boşluğa bakmak yerine kamu
                    # faydasını birlikte ölç. Böylece hedefe kadar araçla gidip
                    # boş otopark indirimi alma davranışı ödüllendirilmez.
                    dogrudan_arac_km = max(0.1, float(_arac_ref.get('km') or ar_km))
                    arac_km_azaltma = max(0.0, min(1.0, 1.0 - ar_km / dogrudan_arac_km))
                    karbon_azaltma = max(0.0, min(
                        1.0, 1.0 - toplam_g / float(_arac_ref['co2_g'])))
                    yurume_dk = max(0.0, float(r2.get('_yuru_a') or 0))
                    toplu_yakinlik = max(0.0, min(1.0, 1.0 - yurume_dk / 12.0))
                    tesvik_puani = round(100 * (
                        0.40 * bos_orani
                        + 0.30 * arac_km_azaltma
                        + 0.20 * karbon_azaltma
                        + 0.10 * toplu_yakinlik
                    ))
                    if tesvik_puani >= 90:
                        indirim_yuzde = 40
                    elif tesvik_puani >= 75:
                        indirim_yuzde = 30
                    elif tesvik_puani >= 60:
                        indirim_yuzde = 20
                    elif tesvik_puani >= 40:
                        indirim_yuzde = 10
                    else:
                        indirim_yuzde = 0
                    mobilite_puani = {0: 0, 10: 25, 20: 50, 30: 75, 40: 100}[indirim_yuzde]
                    aday["tesvik"] = {
                        "demo": True,
                        "puan": tesvik_puani,
                        "indirim_yuzde": indirim_yuzde,
                        "mobilite_puani": mobilite_puani,
                        "dogrulama_dk": 30,
                        "kosul": "İSPARK girişinden sonra İstanbulkart ile toplu taşımaya binin",
                        "bilesenler": {
                            "bos_kapasite": round(bos_orani * 100),
                            "azalan_arac_km": round(arac_km_azaltma * 100),
                            "karbon_farki": round(karbon_azaltma * 100),
                            "toplu_yakinlik": round(toplu_yakinlik * 100),
                        },
                    }
                    kapasite = max(1.0, float(p.get('kapasite') or 0))
                    musaitlik_riski = 1.0 - min(1.0, float(p['bos']) / kapasite)
                    aday["_puan"] = (
                        0.45 * min(2.0, toplam_dk / _toplu_ref)
                        + 0.35 * min(2.0, toplam_g / float(_arac_ref['co2_g']))
                        + 0.20 * musaitlik_riski
                    )
                    if hibrit is None or aday["_puan"] < hibrit["_puan"]:
                        hibrit = aday
        except Exception as e:
            print("[KARBON] hibrit hatasi:", e)

        # Hibrit yalnızca gerçek bir park-et-devam-et faydası üretiyorsa sunulur.
        # Önce özel araca göre çevresel fayda şartı aranır; ardından ya toplu
        # taşımaya göre anlamlı süre kazancı ya da çok güçlü karbon kazancı gerekir.
        if hibrit:
            hibrit.pop("_puan", None)
            _toplu = secenekler[0]
            _arac = next((x for x in secenekler if x["tip"] == "arac"), None)
            _karbon_kapisi = bool(_arac) and hibrit["co2_g"] <= _arac["co2_g"] * 0.80
            _hizli = hibrit["sure_dk"] <= (_toplu["sure_dk"] or 9999) * 0.85
            _cok_temiz = bool(_arac) and hibrit["co2_g"] <= _arac["co2_g"] * 0.60
            if _karbon_kapisi and (_hizli or _cok_temiz):
                _p = []
                _fark = (_toplu["sure_dk"] or 0) - hibrit["sure_dk"]
                if _fark > 0:
                    _p.append("Toplu taşımadan %d dk hızlı" % _fark)
                if _arac and _arac["co2_g"]:
                    _yuzde = round((1 - hibrit["co2_g"] / _arac["co2_g"]) * 100)
                    if _yuzde > 0:
                        _p.append("araca göre %d%% daha az karbon" % _yuzde)
                _tip = (hibrit.get('ispark') or {}).get('aktarma_tipi')
                if _tip == 'dinamik':
                    _p.insert(0, "Boş kapasite dinamik aktarmaya uygun")
                hibrit["neden"] = " · ".join(_p) or "Park et, devamı toplu taşıma"
                secenekler.append(hibrit)
            else:
                hibrit = None

        if secenekler:
            en_az = min(secenekler, key=lambda x: x["co2_g"])
            arac_s = next((x for x in secenekler if x["tip"] == "arac"), None)
            for s in secenekler:
                s["en_temiz"] = (s is en_az)
                if arac_s and s["tip"] != "arac" and arac_s["co2_g"] > 0:
                    s["tasarruf_g"] = max(0, arac_s["co2_g"] - s["co2_g"])
                    s["tasarruf_yuzde"] = round(
                        max(0, arac_s["co2_g"] - s["co2_g"]) / arac_s["co2_g"] * 100)

        return jsonify({
            "durum": "tamam",
            "nereden": tr.get('a_label'), "nereye": tr.get('b_label'),
            "secenekler": secenekler,
            "ispark_ag": ispark_ag,
            "kaynak": {
                "otobus_g_arac_km": KARBON["otobus_g_arac_km"],
                "otobus_kaynak": "IETT gunluk yakit / arac-km (356.979 L x 2,68 kg / 1.042.413 km)",
                # Arac tipine ayrim + kendini dogrulama — sunumda savunulabilir
                # olmasi icin turetmenin her halkasi disari veriliyor.
                "solo_g_arac_km": 800,
                "koruklu_g_arac_km": 1120,
                "filo_solo_pct": 63.6,
                "filo_koruklu_pct": 36.4,
                "filo_arac_sayisi": 3509,
                "yakit_orani_varsayim": 1.4,
                "harman_g_arac_km": 916.6,
                "harman_fark_pct": 0.16,
                "varsayilan_doluluk_pct": 40,
                "canli_doluluk_kapsam_pct": 6.3,
                "basabas_doluluk_pct": 5.4,
                "otomobil_g_km": KARBON["otomobil_g_km"],
                "otomobil_kaynak": "7,0 L/100km x 2,27 kg/L (IPCC benzin faktoru)",
                "dizel_kg_l": KARBON["dizel_kg_l"],
                "benzin_kg_l": KARBON["benzin_kg_l"],
            },
        })

    @app.route('/api/ispark')
    def api_ispark():
        """ISPARK otoparklari + anlik bos kapasite."""
        parklar = ispark_listesi()
        try:
            la = float(request.args.get('lat', 0))
            lo = float(request.args.get('lon', 0))
        except Exception:
            la = lo = 0
        if la and lo:
            # int() ciplak birakilinca ?n=abc HTTP 500 donduruyordu; utils.safe_int
            # zaten tam bu is icin var. Ust sinir bellek/CPU icin.
            n = max(1, min(200, safe_int(request.args.get('n'), 10)))
            sirali = sorted(parklar, key=lambda p: hav(la, lo, p['lat'], p['lon']))[:n]
            return jsonify({"parklar": [dict(p, mesafe_km=round(hav(la, lo, p['lat'], p['lon']), 2))
                                        for p in sirali], "toplam": len(parklar)})
        return jsonify({"parklar": parklar, "toplam": len(parklar),
                        "toplam_kapasite": sum(p['kapasite'] for p in parklar),
                        "toplam_bos": sum(p['bos'] for p in parklar)})

    def _rota_hesapla(girdi_a, girdi_b):
        """
        Rota bulma çekirdeği — hem /api/nasil_gidilir hem /api/karbon_rota kullanır.
        jsonify yerine düz sözlük döndürür ki başka uçlar da çağırabilsin.
        """
        with _lock: snap_db=dict(MEMORY_DB); snap_durak=dict(DURAK_DICT)
        if not snap_durak:
            return ({"durum":"bekle","mesaj":"Durak veritabanı henüz hazır değil. Lütfen 1-2 dakika bekleyin."})

        durak_a, label_a, lat_a, lon_a, tip_a, oner_a = _coz_giris(girdi_a, snap_durak)
        durak_b, label_b, lat_b, lon_b, tip_b, oner_b = _coz_giris(girdi_b, snap_durak)

        # Hiç çözülemediyse: fuzzy önerileri "bunu mu kastettin" olarak göster
        if tip_a is None:
            ad_oner=_durak_adaylari(girdi_a, snap_durak, top_n=5, min_skor=40)
            return ({"durum":"hata",
                            "mesaj":f"'{girdi_a}' için eşleşme bulunamadı.",
                            "oneriler_a":[{"kodu":k,"ad":a,"skor":s,
                                           "lat":snap_durak[k].get('lat',0),
                                           "lon":snap_durak[k].get('lon',0),
                                           "ilce":snap_durak[k].get('ilce','')}
                                          for k,s,a in ad_oner]})
        if tip_b is None:
            ad_oner=_durak_adaylari(girdi_b, snap_durak, top_n=5, min_skor=40)
            return ({"durum":"hata",
                            "mesaj":f"'{girdi_b}' için eşleşme bulunamadı.",
                            "oneriler_b":[{"kodu":k,"ad":a,"skor":s,
                                           "lat":snap_durak[k].get('lat',0),
                                           "lon":snap_durak[k].get('lon',0),
                                           "ilce":snap_durak[k].get('ilce','')}
                                          for k,s,a in ad_oner]})
        if tip_a=='koordinat_yok':
            return ({"durum":"hata","mesaj":f"Koordinat alındı ama 2km içinde IETT durağı bulunamadı."})
        if tip_b=='koordinat_yok':
            return ({"durum":"hata","mesaj":f"Koordinat alındı ama 2km içinde IETT durağı bulunamadı."})
        if tip_a=='adres_yok':
            return ({"durum":"hata","mesaj":f"'{girdi_a}' adresi bulundu ama yakında IETT durağı yok."})
        if tip_b=='adres_yok':
            return ({"durum":"hata","mesaj":f"'{girdi_b}' adresi bulundu ama yakında IETT durağı yok."})
        if not durak_a:
            return ({"durum":"hata","mesaj":f"Nereden '{girdi_a}' bulunamadı. Durak adı, kodu, koordinat (41.01,28.97) veya adres girebilirsiniz."})
        if not durak_b:
            return ({"durum":"hata","mesaj":f"Nereye '{girdi_b}' bulunamadı. Durak adı, kodu, koordinat veya adres girebilirsiniz."})

        # ── Yakın durak havuzu (250m içindeki tüm IETT durakları) ──
        # Aynı isim/lokasyondaki birden çok durak kodu için hatlar birleştirilir.
        # Bu sayede 79KM (klasik) "MECİDİYEKÖY" durağında, H-2 "MECİDİYEKÖY METROBÜS" durağında
        # durmuş olsa bile, hedef MECİDİYEKÖY METROBÜS için yakındaki MECİDİYEKÖY durağı da
        # iniş noktası olarak kabul edilir.
        # 250 m çok dardı: metrobüs istasyonları aynı adı taşıyan klasik duraktan
        # 700–800 m uzakta (ölçüldü: AVCILAR ↔ AVCILAR MRK.ÜNV.KMP 810 m,
        # MECİDİYEKÖY DEREYOLU ↔ MECİDİYEKÖY METROBÜS 715 m). Bu yüzden rota
        # planlayıcı metrobüsü hiç aday göremiyordu.
        # Yürüyüş süresi zaten toplama ekleniyor, dolayısıyla uzak aday ancak
        # gerçekten zaman kazandırıyorsa öne çıkar — genişletmek güvenli.
        YAKIN_KM = 0.80
        # ── İKİ KADEMELİ YARIÇAP ────────────────────────────────────────
        # Tek eşik metrobüsü dışarıda bırakıyordu: ölçüldü, AVCILAR durağından
        # en yakın metrobüs istasyonu 0,81 km — eşik 0,80 idi, ON METRE farkla
        # kaçıyordu. Sonuç: "AVCILAR → ZİNCİRLİKUYU" sorgusunda hattın adı
        # birebir "AVCILAR-ZİNCİRLİKUYU" (34) olmasına rağmen metrobüs hiç
        # aday olamıyor, 121 dk'lık 3 aktarmalı rotalar öneriliyordu.
        #
        # Yarıçapı topluca büyütmek pahalı: 1,5 km'de Mecidiyeköy havuzu
        # 48 → 140 durağa çıkıyor. Bunun yerine yalnızca YÜKSEK KAPASİTELİ
        # hatlar için genişletiyoruz — şehirde toplam 90 metrobüs durağı var,
        # maliyeti yok.
        #
        # "Yüksek kapasiteli" hat kodu gömülü değil, VERİDEN türetiliyor:
        # hat_kapasite.json'da kapasite >= 160 olan 8 hat tam olarak metrobüs
        # ailesidir (34, 34A, 34AS, 34B, 34BZ, 34C, 34G, 34Z) — körüklü araç.
        # Yanlış pozitif yok; sonraki en yüksek sıradan hat 152.
        #
        # Yürüyüş süresi zaten toplama ekleniyor, dolayısıyla uzaktaki
        # metrobüs ancak GERÇEKTEN zaman kazandırıyorsa öne çıkar.
        YUKSEK_KAP_KM  = 1.50
        YUKSEK_KAP_ESIK = 160
        # NOT: `from services import HAT_KAPASITE` YAPMA — services onu
        # load_panel_data() içinde YENİDEN ATIYOR, dolayısıyla doğrudan içe
        # aktarılan ad boş sözlüğe bağlı kalır. PANEL_DATA ise yerinde
        # değiştirildiği için üzerinden okumak güvenli.
        _kapasiteler = PANEL_DATA.get('hat_kapasite') or {}
        _yuksek_hatlar = {str(h).upper() for h, kap in _kapasiteler.items()
                          if isinstance(kap, (int, float)) and kap >= YUKSEK_KAP_ESIK}

        def _yakin_durak_havuzu(merkez_durak):
            m = snap_durak.get(merkez_durak, {})
            mlat, mlon = m.get('lat',0), m.get('lon',0)
            if not mlat or not mlon: return {merkez_durak}
            havuz = {merkez_durak}
            for k, d in snap_durak.items():
                dlat, dlon = d.get('lat',0), d.get('lon',0)
                if not dlat or not dlon: continue
                uz = hav(mlat, mlon, dlat, dlon)
                if uz <= YAKIN_KM:
                    havuz.add(k)
                elif uz <= YUKSEK_KAP_KM and _yuksek_hatlar:
                    # Yalnızca yüksek kapasiteli hat barındıran duraklar
                    if any(str(h).upper() in _yuksek_hatlar for h in snap_db.get(k, [])):
                        havuz.add(k)
            return havuz
        # ── BASLANGIC = HEDEF ise otobus onerme ─────────────────────────
        # Olculdu: USKUDAR -> USKUDAR sorgusunda a_kod ve b_kod ayni
        # (204931) oldugu halde 9 otobus rotasi uretiliyordu — "12A ile
        # 5 dk". Yolcu zaten orada; onu otobuse bindirmek sacma.
        # Tek tek rotalarda `b_kod == i_kod` korumasi vardi ama BASLANGIC
        # ile HEDEFIN ayni olmasi hic kontrol edilmiyordu: havuzdaki
        # komsu duraklar farkli oldugu icin rota "gecerli" gorunuyordu.
        # Esik 350 m = DURAK_KOMSU yurume esigi (yaklasik 4 dk).
        _a_i = snap_durak.get(durak_a); _b_i = snap_durak.get(durak_b)
        if _a_i and _b_i:
            _ayni_km = hav(_a_i['lat'], _a_i['lon'], _b_i['lat'], _b_i['lon'])
            if durak_a == durak_b or _ayni_km <= 0.35:
                _dk = max(1, int((_ayni_km / 4.8) * 60))
                return ({"durum": "ayni_yer",
                         "rotalar": [],
                         "a_kod": durak_a, "b_kod": durak_b,
                         "a_label": _a_i.get('ad'), "b_label": _b_i.get('ad'),
                         "mesafe_km": round(_ayni_km, 2),
                         "yuruyus_dk": _dk,
                         "mesaj": ("Zaten oradasınız — başlangıç ve hedef aynı durak."
                                   if durak_a == durak_b else
                                   "Başlangıç ve hedef çok yakın: yaklaşık %d dk yürüyüş."
                                   % _dk)})

        havuz_a = _yakin_durak_havuzu(durak_a)
        havuz_b = _yakin_durak_havuzu(durak_b)
        # Hat → o hattı barındıran havuz_a durağı (en yakın orijinal A'ya)
        # Bu sayede biniş durağını doğru seçeriz.
        d_a_info = snap_durak[durak_a]; d_b_info = snap_durak[durak_b]
        hat_binis = {}  # hat → durak_kodu (A havuzundan)
        hat_inis  = {}  # hat → durak_kodu (B havuzundan)
        for d_k in havuz_a:
            for h in snap_db.get(d_k, []):
                if h not in hat_binis:
                    hat_binis[h] = d_k
                else:
                    # Daha yakın olanı tercih et
                    cur = snap_durak[hat_binis[h]]
                    yeni = snap_durak[d_k]
                    if hav(d_a_info['lat'], d_a_info['lon'], yeni['lat'], yeni['lon']) < \
                       hav(d_a_info['lat'], d_a_info['lon'], cur['lat'], cur['lon']):
                        hat_binis[h] = d_k
        for d_k in havuz_b:
            for h in snap_db.get(d_k, []):
                if h not in hat_inis:
                    hat_inis[h] = d_k
                else:
                    cur = snap_durak[hat_inis[h]]
                    yeni = snap_durak[d_k]
                    if hav(d_b_info['lat'], d_b_info['lon'], yeni['lat'], yeni['lon']) < \
                       hav(d_b_info['lat'], d_b_info['lon'], cur['lat'], cur['lon']):
                        hat_inis[h] = d_k

        # ── PERON DÜZELTMESİ: biniş/iniş AYNI YÖNDE olmalı ───────────────
        # Yukarıdaki seçim "en yakın durak"a bakıyor, YÖNE bakmıyor. Metrobüs
        # istasyonlarının her yönü AYRI durak kaydı (İNCİRLİ: 900221=D,
        # 900222=G) ve iki peron 20–50 m arayla. Sonuç: planlayıcı DÖNÜŞ
        # peronunda bindirip GİDİŞ peronunda indiriyordu — fiziksel olarak
        # imkânsız bir rota (Bakırköy→Üsküdar'da 34G tam bunu yapıyordu).
        #
        # Servisin YON+SIRANO verisiyle doğru peron çifti seçiliyor: aynı
        # yönde sıra_biniş < sıra_iniş olan, toplam yürüyüşü en az kombinasyon.
        def _peron_duzelt():
            a_aday, b_aday = {}, {}
            for d_k in havuz_a:
                for h in snap_db.get(d_k, []):
                    a_aday.setdefault(h, []).append(d_k)
            for d_k in havuz_b:
                for h in snap_db.get(d_k, []):
                    b_aday.setdefault(h, []).append(d_k)

            duzeltilen = 0
            for h in list(hat_binis):
                if h not in hat_inis:
                    continue
                try:
                    ok, _ = yon_sirali_gecerli(h, hat_binis[h], hat_inis[h])
                except Exception:
                    continue
                if ok is not False:
                    continue          # gecerli ya da veri yok — dokunma
                # Gecersiz: ayni yonde gecerli en yakin cifti ara
                en_iyi, en_maliyet = None, None
                for bk in a_aday.get(h, []):
                    bi = snap_durak.get(bk) or {}
                    if not bi.get('lat'):
                        continue
                    for ik in b_aday.get(h, []):
                        ii = snap_durak.get(ik) or {}
                        if not ii.get('lat'):
                            continue
                        try:
                            ok2, _ = yon_sirali_gecerli(h, bk, ik)
                        except Exception:
                            ok2 = None
                        if ok2 is not True:
                            continue
                        mal = (hav(d_a_info['lat'], d_a_info['lon'], bi['lat'], bi['lon'])
                               + hav(d_b_info['lat'], d_b_info['lon'], ii['lat'], ii['lon']))
                        if en_maliyet is None or mal < en_maliyet:
                            en_maliyet, en_iyi = mal, (bk, ik)
                if en_iyi:
                    hat_binis[h], hat_inis[h] = en_iyi
                    duzeltilen += 1
                else:
                    # Bu hat bu iki nokta arasinda hicbir yonde islemiyor
                    hat_binis.pop(h, None)
                    hat_inis.pop(h, None)
            return duzeltilen

        try:
            _peron_duzelt()
        except Exception:
            pass

        hatlar_a = set(hat_binis.keys())
        hatlar_b = set(hat_inis.keys())
        rotalar=[]
        saat=datetime.now().hour; hici=datetime.now().weekday()<5
        th,ts=ISTANBUL_PROFIL.get(saat,(0.75,0.75))
        genel_kats=th if hici else ts
        # Aday sıralaması artık kalibre modelle yapılıyor (hat karakteri dahil).
        # Eski sabit hız (13–22 km/s) hangi hattın yavaş olduğunu bilmediği için
        # 139 dakikalık 72T gibi hatları "kısa" sanıp öne çıkarıyordu.
        # Trafik sapması döngü başına bir kez hesaplanır.
        _sapma, _, _ = _trafik_sapmasi()
        otobus_hizi_kmh = 13.0 + (22.0 - 13.0) * max(0.0, min(1.0, genel_kats))  # yedek
        for hat in sorted(list(hatlar_a.intersection(hatlar_b))):
            b_kod = hat_binis[hat]; i_kod = hat_inis[hat]
            b_info = snap_durak[b_kod]; i_info = snap_durak[i_kod]
            if b_kod == i_kod: continue  # aynı durakta direkt rota mantıksız
            mesafe_km=hav(b_info['lat'],b_info['lon'],i_info['lat'],i_info['lon'])
            seyahat_dk=int(segment_sure_tahmini(hat, mesafe_km, sapma=_sapma)[0])
            toplam_sure=seyahat_dk+10
            # A/B asıl durağa yürüme bilgisi (havuzdan farklı durak seçildiyse)
            yuruyu_a_ek = hav(d_a_info['lat'],d_a_info['lon'],b_info['lat'],b_info['lon'])
            yuruyu_b_ek = hav(d_b_info['lat'],d_b_info['lon'],i_info['lat'],i_info['lon'])
            yuruyu_a_ek_dk = max(0, int((yuruyu_a_ek/4.8)*60)) if yuruyu_a_ek > 0.03 else 0
            yuruyu_b_ek_dk = max(0, int((yuruyu_b_ek/4.8)*60)) if yuruyu_b_ek > 0.03 else 0
            rotalar.append({"tip":"direkt","hatlar":[hat],"toplam_sure":toplam_sure,
                            "aciklama":f"<b>{b_info['ad']}</b> durağından <b>{hat}</b> hattına binin.",
                            "puan": max(1, 100 - seyahat_dk),
                            "adimlar":[
                                {"tip":"yuru","mesaj":f"📍 <b>{b_info['ad']}</b> durağına gidin."},
                                {"tip":"bin","mesaj":f"🚌 <b>{hat}</b> numaralı araca binin.","hat":hat,"durak":b_kod,"lat":b_info['lat'],"lon":b_info['lon']},
                                {"tip":"in","mesaj":f"🏁 <b>{i_info['ad']}</b> durağında inin. ({seyahat_dk} dk)"}
                            ],
                            "detay":{"b_kodu":b_kod,"b_durak":b_info['ad'],"b_lat":b_info['lat'],"b_lon":b_info['lon'],
                                     "i_kodu":i_kod,"i_durak":i_info['ad'],"i_lat":i_info['lat'],"i_lon":i_info['lon']}})
        if len(rotalar)<3:
            transferler=[]
            for durak_c,hatlar_c in snap_db.items():
                if durak_c in havuz_a or durak_c in havuz_b: continue
                kesisim_ac=hatlar_a.intersection(hatlar_c); kesisim_cb=hatlar_b.intersection(hatlar_c)
                if kesisim_ac and kesisim_cb:
                    h1 = max(kesisim_ac, key=hat_skoru)
                    h2 = max(kesisim_cb, key=hat_skoru)
                    if h1!=h2:
                        dc_info=snap_durak.get(durak_c,{})
                        if not dc_info.get('lat',0): continue
                        # Iki bacak da YON olarak gecerli olmali:
                        # h1 ile binis→aktarma, h2 ile aktarma→inis.
                        try:
                            if (yon_sirali_gecerli(h1, hat_binis[h1], durak_c)[0] is False
                                or yon_sirali_gecerli(h2, durak_c, hat_inis[h2])[0] is False):
                                continue
                        except Exception:
                            pass
                        durak_c_ad=dc_info.get('ad',durak_c)
                        b_kod=hat_binis[h1]; i_kod=hat_inis[h2]
                        b_info=snap_durak[b_kod]; i_info=snap_durak[i_kod]
                        mesafe1=hav(b_info['lat'],b_info['lon'],dc_info['lat'],dc_info['lon'])
                        mesafe2=hav(dc_info['lat'],dc_info['lon'],i_info['lat'],i_info['lon'])
                        seyahat_dk=int(segment_sure_tahmini(h1, mesafe1, sapma=_sapma)[0]
                                       + segment_sure_tahmini(h2, mesafe2, sapma=_sapma)[0])
                        toplam_sure=seyahat_dk+20
                        transferler.append({"_maliyet":toplam_sure,"tip":"aktarmali","hatlar":[h1,h2],"toplam_sure":toplam_sure,
                                            "aciklama":f"<b>{h1}</b> ile <b>{durak_c_ad}</b>'da <b>{h2}</b>'ye aktarma.",
                                            "puan": max(1, 50 - seyahat_dk),
                                            "adimlar":[
                                                {"tip":"yuru","mesaj":f"📍 <b>{b_info['ad']}</b> durağına gidin."},
                                                {"tip":"bin","mesaj":f"🚌 <b>{h1}</b> numaralı araca binin.","hat":h1,"durak":b_kod,"lat":b_info['lat'],"lon":b_info['lon']},
                                                {"tip":"in","mesaj":f"🔄 <b>{durak_c_ad}</b> durağında inin."},
                                                {"tip":"bin","mesaj":f"🚌 <b>{h2}</b> hattına aktarma yapın.","hat":h2,"durak":durak_c,"lat":dc_info['lat'],"lon":dc_info['lon']},
                                                {"tip":"in","mesaj":f"🏁 <b>{i_info['ad']}</b> durağında inin."}
                                            ],
                                            "detay":{"b_kodu":b_kod,"b_durak":b_info['ad'],"b_lat":b_info['lat'],"b_lon":b_info['lon'],
                                                     "a_kodu":durak_c,"a_durak":durak_c_ad,"a_lat":dc_info['lat'],"a_lon":dc_info['lon'],
                                                     "i_kodu":i_kod,"i_durak":i_info['ad'],"i_lat":i_info['lat'],"i_lon":i_info['lon']}})
                        if len(transferler)>400: break
            # ONEMLI: eskiden burada `len(transferler)>30 -> break` vardi ve
            # aday listesi HIC SIRALANMADAN ilk 5'i aliniyordu. snap_db bir
            # sozluk oldugu icin bu "sozlukte ilk rastlanan 30 aktarma duragi"
            # demekti — kalite degil, rastlanti. Mecidiyekoy→Kadikoy'de 132
            # gecerli 1-aktarmali kombinasyon varken ilk 30'dan seciliyordu.
            transferler.sort(key=lambda t: t.get("_maliyet", 9999))
            seen=set()
            for t in transferler:
                combo=f"{t['hatlar'][0]}-{t['hatlar'][1]}"
                if combo not in seen:
                    seen.add(combo); t.pop("_maliyet", None); rotalar.append(t)
                    if len(rotalar)>=5: break

            # ── BFS ÇOKLU AKTARMA (1-aktarmalı yetersizse, max 4 aktarma) ──
            if len(rotalar) < 2 and hatlar_a and hatlar_b:
                # Hat → durak indeksi
                hat_to_duraklar = {}
                for d_k, h_listesi in snap_db.items():
                    if not snap_durak.get(d_k, {}).get('lat'): continue
                    for h in h_listesi:
                        hat_to_duraklar.setdefault(h, []).append(d_k)

                # ── MALIYET-DUYARLI ARAMA (hat dugum, aktarma duragi kenar) ──
                #
                # NEDEN DEGISTI: onceki surum duz BFS idi ve GLOBAL bir
                # `visited` kullaniyordu. Bir hat hangi yoldan ILK goruldiyse
                # ebeveyni sonsuza dek o kaliyordu; dolayisiyla bulunan butun
                # yollar ayni oneki paylasiyordu. Olculdu: Bakirkoy→Uskudar'da
                # dokuz onerinin dokuzu da "72YT → 30D → 129T" ile basliyor,
                # yalnizca son bacak degisiyordu — yani kullaniciya dokuz
                # secenek gibi gorunen sey tek bir rotanin varyasyonlariydi.
                #
                # Ikinci kusur: BFS SUREYI degil AKTARMA SAYISINI azaltiyordu.
                # Ucuncusu: iki hatti birlestiren durak olarak sozlukte ILK
                # rastlanan durak seciliyordu, en uygunu degil.
                #
                # Simdi: oncelik kuyrugu ile tahmini DAKIKA maliyeti uzerinden
                # genisliyoruz, aktarma cezasi arama sirasinda da sayiliyor ve
                # iki hat arasindaki EN IYI aktarma duragi seciliyor.
                import heapq
                MAX_AKTARMA = 4
                AKTARMA_CEZASI = 8.0      # dk — bekleme + yurume karsiligi
                MAKS_GENISLEME = 1500     # hat sayisi ~800, fazlasiyla yeter

                hedef_hatlar = set(hatlar_b)
                kuyruk = []
                for h in hatlar_a:
                    bk = hat_binis.get(h)
                    if bk and snap_durak.get(bk, {}).get('lat'):
                        heapq.heappush(kuyruk, (0.0, h, bk, (h,), ()))
                en_ucuz = {h: 0.0 for h in hatlar_a}
                bulunan_yollar = []
                genisleme = 0

                while kuyruk and genisleme < MAKS_GENISLEME and len(bulunan_yollar) < 40:
                    maliyet, h_cur, giris, hat_yolu, akt_yolu = heapq.heappop(kuyruk)
                    if maliyet > en_ucuz.get(h_cur, 9e9) + 0.01:
                        continue                      # daha ucuzu zaten islendi
                    if h_cur in hedef_hatlar and len(hat_yolu) >= 2:
                        bulunan_yollar.append((list(hat_yolu), list(akt_yolu),
                                               len(hat_yolu) - 1))
                        continue                      # hedefe vardik, dallanma
                    if len(hat_yolu) > MAX_AKTARMA:
                        continue
                    genisleme += 1
                    g_info = snap_durak.get(giris) or {}
                    if not g_info.get('lat'):
                        continue

                    # Komsu hat basina YALNIZCA en iyi aktarma duragini tut —
                    # aksi hâlde her genislemede yuzlerce kuyruk kaydi olurdu.
                    en_iyi_gecis = {}
                    for d_k in hat_to_duraklar.get(h_cur, []):
                        if d_k == giris or d_k in (durak_a, durak_b):
                            continue
                        d_info = snap_durak.get(d_k)
                        if not d_info or not d_info.get('lat'):
                            continue
                        bacak_km = hav(g_info['lat'], g_info['lon'],
                                       d_info['lat'], d_info['lon'])
                        if bacak_km < 0.15:
                            continue
                        # YON GECERLILIGI — bu bacagi URETMEDEN once bak.
                        # Olculdu: 40 sorgunun 2'sinde birinci siradaki rota
                        # fiziksel olarak imkansiz bir bacak iceriyordu
                        # (hat 139: binis sira 16, inis sira 9 — otobus inis
                        # duragindan ONCE geciyor). Peron duzeltmesi bunlari
                        # onaramiyor cunku gecerli alternatif peron YOK; tek
                        # dogru davranis bacagi hic uretmemek.
                        try:
                            if yon_sirali_gecerli(h_cur, giris, d_k)[0] is False:
                                continue
                        except Exception:
                            pass
                        yeni = (maliyet
                                + segment_sure_tahmini(h_cur, bacak_km, sapma=_sapma)[0]
                                + AKTARMA_CEZASI)
                        # (a) Ayni durakta aktarma — yurume yok
                        for h_next in snap_db.get(d_k, []):
                            if h_next == h_cur or h_next in hat_yolu:
                                continue
                            onceki = en_iyi_gecis.get(h_next)
                            if onceki is None or yeni < onceki[0]:
                                en_iyi_gecis[h_next] = (yeni, d_k)
                        # (b) YURUYEREK aktarma — yakindaki duraklarin hatlari
                        #     Metrobus istasyonlari ayri durak kaydi oldugu icin
                        #     bu olmadan metrobuse hic aktarma yapilamiyordu.
                        for k2, yuru_km in DURAK_KOMSU.get(d_k, ()):
                            yuru_dk = (yuru_km / YURU_HIZ_KMS) * 60
                            yeni2 = yeni + yuru_dk
                            for h_next in snap_db.get(k2, []):
                                if h_next == h_cur or h_next in hat_yolu:
                                    continue
                                onceki = en_iyi_gecis.get(h_next)
                                if onceki is None or yeni2 < onceki[0]:
                                    en_iyi_gecis[h_next] = (yeni2, d_k)

                    for h_next, (yeni, d_k) in en_iyi_gecis.items():
                        if yeni >= en_ucuz.get(h_next, 9e9):
                            continue
                        en_ucuz[h_next] = yeni
                        heapq.heappush(kuyruk, (yeni, h_next, d_k,
                                                hat_yolu + (h_next,),
                                                akt_yolu + (d_k,)))

                # BFS "herhangi bir yol" buluyor, kalite sırasına göre değil.
                # Detaylı hesaba (canlı ETA → API çağrısı) sokmadan ÖNCE ucuz
                # kalibre tahminle sırala; böylece en iyi adaylar seçilir ve
                # kota tüketimi artmaz (detaya giren aday sayısı yine 5).
                _adaylar = []
                for _hy, _ay, _na in bulunan_yollar:
                    _bk = hat_binis.get(_hy[0], durak_a)
                    _ik = hat_inis.get(_hy[-1], durak_b)
                    _yd = [_bk] + _ay + [_ik]
                    _tah = 0.0
                    _gecerli = True
                    for _i in range(len(_yd) - 1):
                        _d1 = snap_durak.get(_yd[_i], {}); _d2 = snap_durak.get(_yd[_i+1], {})
                        if not _d1.get('lat') or not _d2.get('lat'):
                            _gecerli = False; break
                        _mm = hav(_d1['lat'], _d1['lon'], _d2['lat'], _d2['lon'])
                        _hh = _hy[_i] if _i < len(_hy) else _hy[-1]
                        _tah += segment_sure_tahmini(_hh, _mm, sapma=_sapma)[0]
                    if not _gecerli:
                        continue
                    _adaylar.append((_tah + (_na + 1) * 8, _hy, _ay, _na))
                _adaylar.sort(key=lambda x: x[0])

                # CESITLILIK: ayni ilk-iki-hat onekinden en fazla 2 oneri.
                # Aksi hâlde liste, tek bir rotanin son bacagi degisen
                # kopyalariyla doluyor ve kullaniciya secenek sunulmus olmuyor.
                _secilen, _onek_say, _hat_kumeleri = [], {}, set()
                for _a in _adaylar:
                    _hy = _a[1]
                    _kume = frozenset(_hy)
                    if _kume in _hat_kumeleri:
                        continue                      # ayni hat kumesi tekrari
                    _onek = tuple(_hy[:2])
                    if _onek_say.get(_onek, 0) >= 2:
                        continue
                    _onek_say[_onek] = _onek_say.get(_onek, 0) + 1
                    _hat_kumeleri.add(_kume)
                    _secilen.append(_a)
                    if len(_secilen) >= 9:
                        break

                # Bulunan yollardan rota objelerine dönüştür
                for _skor, hat_yolu, aktarma_yolu, n_akt in _secilen:
                    # Havuzdan en uygun biniş ve iniş durakları
                    binis_kodu = hat_binis.get(hat_yolu[0], durak_a)
                    inis_kodu = hat_inis.get(hat_yolu[-1], durak_b)
                    b_info = snap_durak[binis_kodu]; i_info = snap_durak[inis_kodu]
                    # Toplam mesafe
                    # AKTARMA = iniş durağı. Sonraki hattın BİNİŞ durağı aynı
                    # durak olmayabilir (metrobüs istasyonu ayrı kayıt) —
                    # o hatta hizmet veren en yakın durağı türetip aradaki
                    # yürüyüşü süreye ekliyoruz.
                    def _binis_duragi(aktarma_kodu, hat_kodu):
                        if hat_kodu in snap_db.get(aktarma_kodu, []):
                            return aktarma_kodu, 0.0
                        en_k, en_d = aktarma_kodu, None
                        for k2, uz in DURAK_KOMSU.get(aktarma_kodu, ()):
                            if hat_kodu in snap_db.get(k2, []):
                                if en_d is None or uz < en_d:
                                    en_k, en_d = k2, uz
                        return en_k, (en_d or 0.0)

                    bin_noktalari = [binis_kodu]
                    in_noktalari  = []
                    aktarma_yuru_dk = []
                    for _i, _akt in enumerate(aktarma_yolu):
                        in_noktalari.append(_akt)
                        _bk, _uz = _binis_duragi(_akt, hat_yolu[_i + 1])
                        bin_noktalari.append(_bk)
                        aktarma_yuru_dk.append(int(round((_uz / 4.8) * 60)))
                    in_noktalari.append(inis_kodu)

                    toplam_mes = 0
                    seyahat_dk = 0
                    valid = True
                    for i in range(len(hat_yolu)):
                        d1 = snap_durak.get(bin_noktalari[i], {})
                        d2 = snap_durak.get(in_noktalari[i], {})
                        if not d1.get('lat') or not d2.get('lat'): valid = False; break
                        _m = hav(d1['lat'], d1['lon'], d2['lat'], d2['lon'])
                        toplam_mes += _m
                        seyahat_dk += segment_sure_tahmini(hat_yolu[i], _m, sapma=_sapma)[0]
                    if not valid: continue
                    if toplam_mes > 120: continue  # 120km üstü atla
                    seyahat_dk = int(seyahat_dk)
                    toplam_sure = (seyahat_dk + (n_akt + 1) * 8
                                   + sum(aktarma_yuru_dk))

                    # Tip etiketi
                    if n_akt == 2: tip = 'iki_aktarma'; tip_ad = '2 AKTARMA'
                    elif n_akt == 3: tip = 'uc_aktarma'; tip_ad = '3 AKTARMA'
                    else: tip = f'{n_akt}_aktarma'; tip_ad = f'{n_akt} AKTARMA'

                    # Açıklama
                    parcalar = [f"<b>{hat_yolu[0]}</b>"]
                    for i, ad in enumerate(aktarma_yolu):
                        ad_info = snap_durak.get(ad, {})
                        parcalar.append(f"<b>{ad_info.get('ad', ad)}</b>'da <b>{hat_yolu[i+1]}</b>")
                    aciklama = " → ".join(parcalar) + f" ({n_akt} aktarma)"

                    # Adımlar
                    adimlar = [{"tip":"yuru","mesaj":f"📍 <b>{b_info['ad']}</b> durağına gidin."}]
                    for i, h in enumerate(hat_yolu):
                        bk = bin_noktalari[i]
                        bk_info = snap_durak[bk]
                        adimlar.append({"tip":"bin","mesaj":f"🚌 <b>{h}</b> hattına binin.",
                                       "hat":h,"durak":bk,
                                       "lat":bk_info['lat'],"lon":bk_info['lon']})
                        if i < len(hat_yolu) - 1:
                            akt_info = snap_durak[aktarma_yolu[i]]
                            adimlar.append({"tip":"in","mesaj":f"🔄 <b>{akt_info['ad']}</b> durağında <b>{hat_yolu[i+1]}</b>'e aktarma."})
                        else:
                            adimlar.append({"tip":"in","mesaj":f"🏁 <b>{i_info['ad']}</b> durağında inin."})

                    # Detay (a, a2, a3, a4 olarak aktarmalar)
                    detay = {
                        "b_kodu":binis_kodu,"b_durak":b_info['ad'],"b_lat":b_info['lat'],"b_lon":b_info['lon'],
                        "i_kodu":inis_kodu,"i_durak":i_info['ad'],"i_lat":i_info['lat'],"i_lon":i_info['lon'],
                    }
                    for idx, ad in enumerate(aktarma_yolu):
                        ad_info = snap_durak[ad]
                        prefix = 'a' if idx == 0 else f'a{idx+1}'
                        detay[f'{prefix}_kodu'] = ad
                        detay[f'{prefix}_durak'] = ad_info['ad']
                        detay[f'{prefix}_lat'] = ad_info['lat']
                        detay[f'{prefix}_lon'] = ad_info['lon']

                    rotalar.append({
                        "tip": tip, "hatlar": hat_yolu, "toplam_sure": toplam_sure,
                        "aciklama": aciklama,
                        "puan": max(1, 60 - seyahat_dk // 3 - n_akt * 8),
                        "adimlar": adimlar, "detay": detay
                    })
        # Yürüyüş mesafesi rota başına (havuzdan farklı durak seçilebilir)
        YURUME_HIZI_KMH = 4.8
        for r in rotalar:
            det = r["detay"]
            b_lat_r = det.get("b_lat"); b_lon_r = det.get("b_lon")
            i_lat_r = det.get("i_lat"); i_lon_r = det.get("i_lon")
            # Başlangıç → biniş durağı yürüme
            kaynak_lat = lat_a if lat_a is not None else (snap_durak[durak_a]["lat"] if durak_a else None)
            kaynak_lon = lon_a if lon_a is not None else (snap_durak[durak_a]["lon"] if durak_a else None)
            hedef_lat = lat_b if lat_b is not None else (snap_durak[durak_b]["lat"] if durak_b else None)
            hedef_lon = lon_b if lon_b is not None else (snap_durak[durak_b]["lon"] if durak_b else None)
            yuruyu_a_dk = 0; yuruyu_b_dk = 0
            if kaynak_lat and b_lat_r:
                d = hav(kaynak_lat, kaynak_lon, b_lat_r, b_lon_r)
                if d > 0.03: yuruyu_a_dk = max(1, int((d / YURUME_HIZI_KMH) * 60))
            if hedef_lat and i_lat_r:
                d = hav(hedef_lat, hedef_lon, i_lat_r, i_lon_r)
                if d > 0.03: yuruyu_b_dk = max(1, int((d / YURUME_HIZI_KMH) * 60))
            r["_yuru_a"] = yuruyu_a_dk; r["_yuru_b"] = yuruyu_b_dk
            adimlar = r["adimlar"]
            if yuruyu_a_dk > 0:
                adimlar.insert(0, {"tip":"yuru","mesaj":f"🚶 Başlangıçtan <b>{yuruyu_a_dk} dk</b> yürüyerek <b>{det.get('b_durak','biniş')}</b> durağına gidin."})
            if yuruyu_b_dk > 0:
                adimlar.append({"tip":"yuru","mesaj":f"🚶 <b>{det.get('i_durak','iniş')}</b> durağından <b>{yuruyu_b_dk} dk</b> yürüyerek hedefinize ulaşın."})
            r["toplam_sure"] = r.get("toplam_sure",0) + yuruyu_a_dk + yuruyu_b_dk
            if lat_a is not None and lon_a is not None:
                det["baslangic_lat"]=lat_a; det["baslangic_lon"]=lon_a
            if lat_b is not None and lon_b is not None:
                det["bitis_lat"]=lat_b; det["bitis_lon"]=lon_b
        rotalar.sort(key=lambda x:x["puan"],reverse=True)

        # ── PERON ZİNCİRİ: her bacakta doğru yön peronunu seç ────────────
        # `_peron_duzelt` yalnızca A/B havuzu uçlarını düzeltiyor; ARA aktarma
        # durakları aramadan geliyor ve orada peron seçimi hâlâ yönsüzdü.
        # Metrobüs istasyonlarının her yönü ayrı durak kaydı olduğu için
        # (İNCİRLİ 900221=D, 900222=G) rota "dönüş peronunda bin, gidiş
        # peronunda in" diyebiliyordu — fiziksel olarak imkânsız.
        #
        # Burada rotanın TÜM bacak zinciri gezilir; geçersiz bir bacak
        # bulunursa biniş ve/veya iniş durağı, aynı hattı taşıyan ve YÖN
        # olarak geçerli olan en yakın komşu durakla değiştirilir (≤350 m,
        # `DURAK_KOMSU`). Değişiklik hem `adimlar` hem `detay` alanlarına
        # yazılır ki detaylı süre hesabı doğru noktalardan ölçsün.
        def _peron_zinciri_duzelt(r):
            hatlar_r = r.get('hatlar') or []
            adimlar_r = r.get('adimlar') or []
            det = r.get('detay') or {}
            if not hatlar_r or not det:
                return False

            bin_adim = [a for a in adimlar_r if a.get('tip') == 'bin']
            if len(bin_adim) != len(hatlar_r):
                return False
            in_alan = []
            for idx in range(1, len(hatlar_r)):
                in_alan.append('a' if idx == 1 else f'a{idx}')
            in_alan.append('i')

            def _adaylar(kod, hat):
                """Kod + <=350 m komsulari icinde hatti tasiyanlar."""
                out = []
                if kod and hat in (snap_db.get(kod) or []):
                    out.append((kod, 0.0))
                for k2, uz in (DURAK_KOMSU.get(kod) or ()):
                    if hat in (snap_db.get(k2) or []):
                        out.append((k2, uz))
                return out

            degisti = False
            for j, h in enumerate(hatlar_r):
                bk = bin_adim[j].get('durak')
                alan = in_alan[j]
                ik = det.get(f'{alan}_kodu')
                if not bk or not ik:
                    continue
                try:
                    ok, _ = yon_sirali_gecerli(h, bk, ik)
                except Exception:
                    continue
                if ok is not False:
                    continue                      # gecerli ya da veri yok

                en_iyi, en_mal = None, None
                for bk2, ub in _adaylar(bk, h):
                    for ik2, ui in _adaylar(ik, h):
                        try:
                            ok2, _ = yon_sirali_gecerli(h, bk2, ik2)
                        except Exception:
                            ok2 = None
                        if ok2 is not True:
                            continue
                        mal = ub + ui
                        if en_mal is None or mal < en_mal:
                            en_mal, en_iyi = mal, (bk2, ik2)
                if not en_iyi:
                    continue
                bk2, ik2 = en_iyi
                if bk2 != bk:
                    bi = snap_durak.get(bk2) or {}
                    if bi.get('lat'):
                        bin_adim[j]['durak'] = bk2
                        bin_adim[j]['lat'] = bi['lat']
                        bin_adim[j]['lon'] = bi['lon']
                        if j == 0:
                            det['b_kodu'] = bk2; det['b_durak'] = bi.get('ad', bk2)
                            det['b_lat'] = bi['lat']; det['b_lon'] = bi['lon']
                        degisti = True
                if ik2 != ik:
                    ii = snap_durak.get(ik2) or {}
                    if ii.get('lat'):
                        det[f'{alan}_kodu'] = ik2
                        det[f'{alan}_durak'] = ii.get('ad', ik2)
                        det[f'{alan}_lat'] = ii['lat']; det[f'{alan}_lon'] = ii['lon']
                        degisti = True
            return degisti

        for _r in rotalar:
            try:
                _peron_zinciri_duzelt(_r)
            except Exception:
                pass

        # Her rota için detaylı süre kırılımı + canlı bekleme tahmini
        rotalar = rotalar[:9]
        for r in rotalar:
            det = r.get('detay', {})
            hatlar_r = r.get('hatlar', [])

            # Her segment için biniş koordinatı: b → a → a2 → a3 → a4 ...
            # Her segment için iniş koordinatı: bir sonraki aktarma veya i
            # İNİŞ noktaları: aktarma durakları, sonuncusu hedef
            inis_noktalari = []
            for idx in range(1, len(hatlar_r)):
                prefix = 'a' if idx == 1 else f'a{idx}'
                inis_noktalari.append((det.get(f'{prefix}_lat'), det.get(f'{prefix}_lon')))
            inis_noktalari.append((det.get('i_lat'), det.get('i_lon')))

            # BİNİŞ noktaları adımlardan okunur — aktarma durağıyla AYNI
            # olmayabilir. Metrobüs istasyonu ayrı durak kaydı olduğu için
            # yolcu inip 50–350 m yürüyerek istasyona geçiyor. Eskiden burada
            # `a_lat` (İNİŞ durağı) biniş noktası sayılıyordu; hem o yürüyüş
            # süreye hiç girmiyor hem de ikinci bacağın mesafesi yanlış
            # noktadan ölçülüyordu.
            _bin_adim = [(a.get('lat'), a.get('lon'))
                         for a in (r.get('adimlar') or []) if a.get('tip') == 'bin'
                         and a.get('lat')]
            if len(_bin_adim) == len(hatlar_r):
                binis_noktalari = _bin_adim
            else:                                  # yedek: eski davranış
                binis_noktalari = [(det.get('b_lat'), det.get('b_lon'))]
                for idx in range(1, len(hatlar_r)):
                    prefix = 'a' if idx == 1 else f'a{idx}'
                    binis_noktalari.append((det.get(f'{prefix}_lat'),
                                            det.get(f'{prefix}_lon')))

            # Aktarma yürüyüşü: iniş noktasından bir sonraki biniş noktasına
            _akt_yuru = []
            for idx in range(len(hatlar_r) - 1):
                (ila, ilo) = inis_noktalari[idx]
                (bla, blo) = binis_noktalari[idx + 1]
                if ila and bla:
                    _km = hav(ila, ilo, bla, blo)
                    _akt_yuru.append(max(0, int(round((_km / 4.8) * 60))))
                else:
                    _akt_yuru.append(0)

            # ── ERİŞİLEBİLİRLİK ────────────────────────────────────────
            # `durak_dict` her durak için `engelli` (erişilebilir mi) ve
            # `tip` (AÇIK / KAPALI / FULL KAPALI korunak) tutuyor.
            # Rotanın binilecek/inilecek duraklarının durumunu yanıta
            # ekliyoruz. INTENT bölüm 6: uyarı verilir, rota ELENMEZ —
            # erişilemez durak da olsa yolcunun seçme hakkı var.
            _eris = []
            _bk_ad = [(a.get('durak'), a.get('hat')) for a in (r.get('adimlar') or [])
                      if a.get('tip') == 'bin']
            _in_kod = []
            for _i in range(1, len(hatlar_r)):
                _p = 'a' if _i == 1 else f'a{_i}'
                _in_kod.append(det.get(f'{_p}_kodu'))
            _in_kod.append(det.get('i_kodu'))
            for _idx, (_kod, _hat) in enumerate(_bk_ad):
                for _tip, _k in (('biniş', _kod),
                                 ('iniş', _in_kod[_idx] if _idx < len(_in_kod) else None)):
                    if not _k:
                        continue
                    _d = snap_durak.get(_k) or {}
                    _eris.append({
                        'rol': _tip, 'kod': _k, 'ad': _d.get('ad', _k),
                        'hat': _hat,
                        'engelli': bool(_d.get('engelli')),
                        'korunak': _d.get('tip') or 'AÇIK',
                        'akilli': bool(_d.get('akilli')),
                    })
            r['erisim'] = _eris
            r['erisim_sorunlu'] = sum(1 for x in _eris if not x['engelli'])

            r['canli'] = None
            kirilim = {
                'yuruyu_a_dk': r.get('_yuru_a', 0),
                'yuruyu_b_dk': r.get('_yuru_b', 0),
                'aktarma_yuruyu_dklar': _akt_yuru,
                'segmentler': []
            }

            for i, h in enumerate(hatlar_r):
                bin_lat, bin_lon = binis_noktalari[i]
                in_lat, in_lon = inis_noktalari[i]
                if not bin_lat or not in_lat:
                    continue
                # Canlı ETA yalnızca İLK segment için çekilir.
                #
                # İki sebep:
                # 1) DOĞRULUK — kullanıcı ikinci araca 40 dakika sonra binecek.
                #    Şu anki otobüs konumları o an için anlamsız; headway
                #    (sefer sıklığı) çok daha doğru bir tahmin.
                # 2) KOTA — Filo servisi saatte 100 istekle sınırlı ve her
                #    hat için ayrı çağrı gerekiyor. Ölçüldü: tüm segmentlere
                #    canlı veri çekilince tek rota sorgusu 14 hat tüketiyordu,
                #    yani saatte ~7 sorgu. İlk segmentle sınırlayınca bu
                #    sayı rota başına 1'e iniyor.
                if i == 0:
                    try:
                        eta_liste = _canli_eta_hesapla(h, bin_lat, bin_lon)
                    except Exception:
                        eta_liste = []
                else:
                    eta_liste = []
                # Kullanıcı bu durağa ne zaman varır? İlk segmentte yürüyüş,
                # sonrakilerde önceki segmentlerin toplamı.
                if i == 0:
                    varis_gecikmesi = kirilim['yuruyu_a_dk']
                else:
                    varis_gecikmesi = kirilim['yuruyu_a_dk'] + sum(
                        s['bekleme_dk'] + s['sefer_dk'] for s in kirilim['segmentler'])
                bek, kaynak, bek_detay = _bekleme_hesapla(
                    h, bin_lat, bin_lon, eta_liste, varis_gecikmesi_dk=varis_gecikmesi)
                # Segment trafiği — tek nokta yerine GÜZERGÂH BOYUNCA ortalama
                try:
                    seg_trafik = guzergah_trafik_ort(h, bin_lat, bin_lon, in_lat, in_lon)
                except Exception:
                    try:
                        seg_trafik = get_trafik(bin_lat, bin_lon)
                    except Exception:
                        seg_trafik = {}
                seg_kats = seg_trafik.get('katsayi', genel_kats)
                seg_seviye = seg_trafik.get('seviye', '')
                seg_renk = seg_trafik.get('renk', '#94a3b8')
                seg_kaynak = seg_trafik.get('kaynak', 'profil')
                mes_seg = hav(bin_lat, bin_lon, in_lat, in_lon)
                # Kuş uçuşu değil, güzergâh çizgisi üzerinden GERÇEK yol mesafesi
                _gercek_km = None
                try:
                    _gercek_km = guzergah_mesafe_km(h, bin_lat, bin_lon, in_lat, in_lon)
                except Exception:
                    _gercek_km = None
                # Kalibre model: hattın durak yoğunluğu + hat katsayısı + trafik sapması.
                # Eski sabit formül (hav*1.4 / 13–22 km/s) 575 hatta ölçüldü:
                # ortalama hata 18,2 dk idi, bu model 1,8 dk.
                _s, _serb, _gec = segment_sure_tahmini(h, mes_seg, seg_kats, gercek_yol_km=_gercek_km)
                sefer_dk = max(1, int(round(_s)))
                sefer_serbest_dk = max(1, int(round(_serb)))
                gecikme_dk = max(0, sefer_dk - sefer_serbest_dk)
                kirilim['segmentler'].append({
                    'tip':'sefer','hat':h,'bekleme_dk':bek,'sefer_dk':sefer_dk,
                    'bekleme_kaynak':kaynak,'bekleme_detay':bek_detay,'mesafe_km':round(_gercek_km if _gercek_km else mes_seg*1.4,2),'mesafe_kaynak':('guzergah' if _gercek_km else 'tahmin'),
                    'trafik_seviye': seg_seviye, 'trafik_renk': seg_renk,
                    'trafik_kats': round(seg_kats, 2), 'trafik_gecikme_dk': gecikme_dk,
                    'trafik_kaynak': seg_kaynak, 'sefer_serbest_dk': sefer_serbest_dk,
                })
                # İlk segment için canlı ETA badge
                if i == 0 and eta_liste:
                    ilk = eta_liste[0]
                    r['canli'] = {
                        'hat': h, 'eta_min': ilk['eta_min'],
                        'kapi': ilk['kapi'], 'plaka': ilk.get('plaka','—'),
                        'sonraki': [e['eta_min'] for e in eta_liste[1:3]],
                        'arac_sayisi': len(eta_liste),
                    }

            # Toplam süreyi kırılımdan yeniden hesapla
            toplam = kirilim['yuruyu_a_dk'] + kirilim['yuruyu_b_dk'] + sum(kirilim['aktarma_yuruyu_dklar'])
            for s in kirilim['segmentler']:
                toplam += s['bekleme_dk'] + s['sefer_dk']
            r['toplam_sure'] = toplam
            r['sure_kirilim'] = kirilim

        # Detaylı hesap toplam süreyi yeniden yazdığı için sıralama BURADA
        # yenilenmeli. Aksi hâlde liste kaba ön-tahmine göre sıralı kalıyor ve
        # en hızlı rota ikinci/üçüncü sırada görünüyordu (ölçüldü: 81/65/137).
        rotalar.sort(key=lambda x: x.get('toplam_sure') or 9999)

        # ── YÖN GEÇERLİLİĞİ: "ters yöne binme" önerilerini geri plana at ──
        # Durak-hat eşlemesi hangi YÖNDE geçildiğini söylemiyor; arama iki
        # durağı da taşıyan bir hattı bulunca aracın gerçekte ters yönde
        # gittiği durumu ayırt edemiyordu. Denetimde 10 rota çiftinde 9 böyle
        # segment çıktı. Geometriden karar verilebiliyorsa bu rotalar sona
        # atılır — hepsi sorunluysa yine gösterilir, kullanıcı rotasız kalmasın.
        def _yon_sorunlu(r):
            """
            "Bu rotada ters yöne bindiriliyor mu?"

            ÖNCE KESİN VERİ: servis her durak için YON (G=gidiş / D=dönüş) ve
            SIRANO (o yöndeki sıra) döndürüyor; `yon_sirali_gecerli()` bunu
            kullanıp çıkarımsız cevap veriyor. Geometriden çıkarım yalnızca
            sıra verisi olmayan hatlarda yedek olarak devreye giriyor —
            böylece geometrisi bozuk/eksik 24 hat da doğru değerlendiriliyor.
            """
            det = r.get('detay') or {}
            hatlar_r = r.get('hatlar') or []

            # Biniş durak KODLARI adımlardan (aktarmada yürüme olabilir)
            bin_kod = [a.get('durak') for a in (r.get('adimlar') or [])
                       if a.get('tip') == 'bin']
            in_kod, noktalar_in = [], []
            for idx in range(1, len(hatlar_r)):
                p = 'a' if idx == 1 else f'a{idx}'
                in_kod.append(det.get(f'{p}_kodu'))
                noktalar_in.append((det.get(f'{p}_lat'), det.get(f'{p}_lon')))
            in_kod.append(det.get('i_kodu'))
            noktalar_in.append((det.get('i_lat'), det.get('i_lon')))

            bin_nokta = [(a.get('lat'), a.get('lon')) for a in (r.get('adimlar') or [])
                         if a.get('tip') == 'bin']

            for i, h in enumerate(hatlar_r):
                if i >= len(in_kod):
                    break
                bk = bin_kod[i] if i < len(bin_kod) else det.get('b_kodu')
                ik = in_kod[i]
                # 1) KESIN: sira verisi
                if bk and ik:
                    try:
                        ok, _y = yon_sirali_gecerli(h, bk, ik)
                    except Exception:
                        ok = None
                    if ok is False:
                        return True
                    if ok is True:
                        continue
                # 2) YEDEK: geometriden cikarim
                if i < len(bin_nokta) and i < len(noktalar_in):
                    (la1, lo1), (la2, lo2) = bin_nokta[i], noktalar_in[i]
                    if la1 and la2:
                        try:
                            if guzergah_yon_gecerli(h, la1, lo1, la2, lo2) is False:
                                return True
                        except Exception:
                            pass
            return False

        try:
            _sorunlu_idx = {i for i, r in enumerate(rotalar) if _yon_sorunlu(r)}
            # Sorunlu olanlar HER HALUKARDA isaretlenir. Onceki surumde
            # "hepsi sorunluysa dokunma" dali isareti de atlıyordu; kullanici
            # gecersiz rotayi uyarisiz goruyordu.
            for i in _sorunlu_idx:
                rotalar[i]['yon_supheli'] = True
            _saglam = [r for i, r in enumerate(rotalar) if i not in _sorunlu_idx]
            if _saglam:
                _sorunlu = [r for i, r in enumerate(rotalar) if i in _sorunlu_idx]
                rotalar = _saglam + _sorunlu
        except Exception:
            pass

        # Raylı sistemler, mevcut otobüs motorundan ayrı bir GTFS ağı üzerinde
        # hesaplanır. Böylece İETT'nin canlı araç verisi raylı sistem için
        # yanlışlıkla "canlı" gibi sunulmaz. Yalnızca istasyona/istasyondan
        # makul yürüme mesafesinde gerçek bir seçenek varsa listeye eklenir.
        try:
            _kaynak_lat = lat_a if lat_a is not None else snap_durak[durak_a].get('lat')
            _kaynak_lon = lon_a if lon_a is not None else snap_durak[durak_a].get('lon')
            _hedef_lat = lat_b if lat_b is not None else snap_durak[durak_b].get('lat')
            _hedef_lon = lon_b if lon_b is not None else snap_durak[durak_b].get('lon')
            _rayli = rayli_rota_alternatifleri(
                _kaynak_lat, _kaynak_lon, _hedef_lat, _hedef_lon,
                max_yuru_km=1.8, limit=1)
            if _rayli:
                rotalar.extend(_rayli)
                rotalar.sort(key=lambda x: (bool(x.get('yon_supheli')),
                                            x.get('toplam_sure') or 9999))
                # Kart sayısını sınırlarken bulunan raylı seçeneği kaybetme.
                if len(rotalar) > 9:
                    rayli_rota = _rayli[0]
                    rotalar = rotalar[:9]
                    if rayli_rota not in rotalar:
                        rotalar[-1] = rayli_rota
                        rotalar.sort(key=lambda x: (bool(x.get('yon_supheli')),
                                                    x.get('toplam_sure') or 9999))
        except Exception as exc:
            print(f"[RAYLI] Rota hesaplanamadı: {exc}")

        # Her kart kendi emisyonunu taşır. Aksi halde kullanıcı ikinci bir
        # tramvay/metro kartını açtığında ilk sıradaki rotanın CO2 değeri
        # yanlışlıkla detay panelinde görünüyordu.
        for _rota in rotalar:
            try:
                _co2, _km = _toplu_karbon(_rota)
                _rota['karbon_g'] = round(_co2)
                _rota['toplu_km'] = round(_km, 2)
            except Exception:
                pass

        if rotalar:
            return ({"durum":"tamam","rotalar":rotalar,"a_kod":durak_a,"b_kod":durak_b,
                            "a_label":label_a or snap_durak.get(durak_a,{}).get("ad",girdi_a),
                            "b_label":label_b or snap_durak.get(durak_b,{}).get("ad",girdi_b),
                            "a_tip":tip_a,"b_tip":tip_b,
                            "oneriler_a":oner_a,"oneriler_b":oner_b})
        return ({"durum":"hata","mesaj":"Bu iki durak arasında uygun rota bulunamadı. Farklı durak adı, koordinat veya adres deneyin."})


    @app.route('/api/nasil_gidilir')
    def api_nasil_gidilir():
        return jsonify(_rota_hesapla(request.args.get('nereden', '').strip(),
                                     request.args.get('nereye', '').strip()))

    # ══════════════════════════════════════════════════════════════════
    # TERCİHLER + YOLCULUK GERİ BİLDİRİMİ (KONSEPT / mock veri)
    # Gerçek İstanbulkart entegrasyonu yok; ürün mantığını çalışır gösterir.
    # ══════════════════════════════════════════════════════════════════
    @app.route('/api/profil')
    def api_profil():
        import profil as _pf
        if not _pf.DURUM.get("profil"):
            with _lock:
                mdb = {k: list(v) for k, v in MEMORY_DB.items()}
                ddict = dict(DURAK_DICT)
            _pf.profil_kur(mdb, ddict, PANEL_DATA.get('hat_kapasite') or {},
                           kart_tipi=request.args.get('kart', 'tam'))
        return jsonify({"durum": "tamam", **_pf.ozet(),
                        "anket_semasi": _pf.ANKET_SEMASI,
                        "sorun_yerleri": _pf.SORUN_YERLERI,
                        "sorun_kategorileri": _pf.SORUN_KATEGORILERI})

    @app.route('/api/profil/seferler')
    def api_profil_seferler():
        import profil as _pf
        if not _pf.DURUM.get("profil"):
            api_profil()
        return jsonify({"durum": "tamam", "seferler": _pf.seferleri_ozetli()})

    @app.route('/api/profil/degerlendir', methods=['POST', 'GET'])
    def api_profil_degerlendir():
        import profil as _pf
        if request.method == 'POST':
            veri = request.get_json(silent=True) or {}
        else:
            # json.loads ciplak birakilinca ?puanlar=abc HTTP 500 donduruyordu
            try:
                _puanlar = _json_mod.loads(request.args.get("puanlar") or "{}")
                if not isinstance(_puanlar, dict):
                    _puanlar = {}
            except (ValueError, TypeError):
                _puanlar = {}
            veri = {"sefer_id": request.args.get("sefer_id"),
                    "puanlar": _puanlar,
                    "yorum": request.args.get("yorum", "")}
        return jsonify(_pf.degerlendirme_ekle(veri.get("sefer_id"),
                                              veri.get("puanlar") or {},
                                              veri.get("yorum") or ""))

    @app.route('/api/profil/yolculuk_bildir', methods=['POST'])
    def api_profil_yolculuk_bildir():
        import profil as _pf
        if not _pf.DURUM.get("profil"):
            api_profil()
        veri = request.get_json(silent=True) or {}
        return jsonify(_pf.bildirim_ekle(
            sefer_id=veri.get("sefer_id"), durum=veri.get("durum"),
            yer=veri.get("yer"), kategori=veri.get("kategori"),
            aciklama=veri.get("aciklama") or "", baglam=veri.get("baglam") or None,
            bacak=veri.get("bacak") or None))

    @app.route('/api/profil/kurum_rapor')
    def api_profil_kurum_rapor():
        import profil as _pf
        return jsonify({"durum": "tamam", **_pf.kurum_raporu()})

    @app.route('/api/profil/sifirla')
    def api_profil_sifirla():
        import profil as _pf
        with _lock:
            mdb = {k: list(v) for k, v in MEMORY_DB.items()}
            ddict = dict(DURAK_DICT)
        _pf.profil_kur(mdb, ddict, PANEL_DATA.get('hat_kapasite') or {},
                       kart_tipi=request.args.get('kart', 'tam'))
        return jsonify({"durum": "tamam", **_pf.ozet()})

    # ══════════════════════════════════════════════════════════════════
    # GÜVENİLİRLİK SKORU + HAT KARNESİ
    # Kaynak: GetIettArsivGorev_json (kotasız). Hesap pahalı olduğu için
    # 6 saat önbelleklenir — arşiv zaten günde bir kez güncelleniyor.
    # ══════════════════════════════════════════════════════════════════
    _SKOR_CACHE = {"ts": 0, "skorlar": {}, "ozet": {}, "tarih": ""}

    def _skorlari_al(force=False):
        import skor as _sk
        now = time.time()
        if not force and _SKOR_CACHE["skorlar"] and now - _SKOR_CACHE["ts"] < 21600:
            return _SKOR_CACHE
        gorevler, tarih = _arsiv_gorev_cek_guvenli()
        if not gorevler:
            return _SKOR_CACHE
        sk = _sk.skorla(gorevler, PANEL_DATA.get('hat_master'))
        _SKOR_CACHE.update({"ts": now, "skorlar": sk,
                            "ozet": _sk.sebeke_ozeti(sk), "tarih": tarih})
        return _SKOR_CACHE

    def _arsiv_gorev_cek_guvenli():
        try:
            from services import _arsiv_gorev_cek as _cek
            return _cek(max_gun=6)
        except Exception as e:
            print("[SKOR] arsiv cekilemedi:", e)
            return [], ""

    @app.route('/api/hat_skoru')
    def api_hat_skoru():
        c = _skorlari_al(request.args.get('force') == '1')
        if not c["skorlar"]:
            return jsonify({"durum": "hata", "mesaj": "Arşiv verisi alınamadı"})
        hat = (request.args.get('hat') or '').strip().upper()
        if hat:
            v = c["skorlar"].get(hat)
            if not v:
                return jsonify({"durum": "hata",
                                "mesaj": "%s için yeterli sefer kaydı yok" % hat})
            # Sıralamadaki yeri
            sirali = sorted(c["skorlar"].values(), key=lambda x: -x["skor"])
            sira = next((i + 1 for i, x in enumerate(sirali) if x["hat"] == hat), None)
            return jsonify({"durum": "tamam", "karne": v, "sira": sira,
                            "toplam_hat": len(sirali), "tarih": c["tarih"],
                            "ozet": c["ozet"]})
        # Liste görünümü — ?n=abc eskiden HTTP 500 donduruyordu
        n = max(1, min(1000, safe_int(request.args.get('n'), 25)))
        sirali = sorted(c["skorlar"].values(), key=lambda x: -x["skor"])
        return jsonify({"durum": "tamam", "tarih": c["tarih"], "ozet": c["ozet"],
                        "en_iyi": sirali[:n],
                        "en_kotu": list(reversed(sirali[-n:]))})

    @app.route('/api/v1/dashboard')
    def api_dashboard():
        with _lock:
            data = dict(ANALYSIS_CACHE)
        return jsonify(data)

    @app.route('/api/hat_detay')
    def api_hat_detay():
        hat=request.args.get('hat','').upper()
        res=fetch_soap(URL_ANA,'GetHat_json',
                       f'<GetHat_json xmlns="http://tempuri.org/"><HatKodu>{hat}</HatKodu></GetHat_json>')
        return jsonify(res or [])

    @app.route('/api/istatistik')
    def api_istatistik():
        hat=request.args.get('hat','').upper()
        with _lock:
            hi=HAFTALIK.get("haftaici",{}).get(hat,0)
            hs=HAFTALIK.get("haftasonu",{}).get(hat,0)
            gorev=ARSIV_CACHE.get("hat_gorev",{}).get(hat,0)
        if hi>0:
            return jsonify({"dunku_yolcu":f"HİÇ:{hi:,} | HS:{hs:,}".replace(',','.'),"bugunku_gorev_sayisi":gorev,"kaynak":"ram"})
        yolcu_str="Veri Yok"
        for off in [1,2,3]:
            t=(datetime.now()-timedelta(days=off)).strftime("%Y-%m-%d")
            g=(datetime.now()-timedelta(days=off)).strftime("%d/%m")
            body=f'<GetIettYolculukHat_json xmlns="http://tempuri.org/"><Tarih>{t}</Tarih></GetIettYolculukHat_json>'
            res=fetch_soap(URL_IBB360,'GetIettYolculukHat_json',body,use_auth=False,timeout_sec=8)
            if isinstance(res,list):
                for y in res:
                    y_hat = temiz_str(alan_oku(y, 'Hat', 'HAT', 'HatKodu', 'HATKODU')).upper()
                    if y_hat == hat:
                        try:
                            yolcu_val = int(temiz_sayi(alan_oku(y, 'Yolculuk', 'YOLCULUK', 'Yolcu', 'YOLCU', varsayilan=0)))
                            yolcu_str = f"{yolcu_val:,}".replace(',', '.')
                        except Exception:
                            pass
                        break
            if yolcu_str!="Veri Yok": break
        return jsonify({"dunku_yolcu":yolcu_str,"bugunku_gorev_sayisi":gorev,"kaynak":"api"})



    @app.route('/api/durak_detay')
    def api_durak_detay():
        hat=request.args.get('hat','').upper()
        cache_key=f"durak_detay_{hat}"
        with _lock:
            cached = API_RESPONSE_CACHE.get(cache_key)
        if cached:
            return jsonify(cached)
        body=f'<DurakDetay_GYY_wYonAdi xmlns="http://tempuri.org/"><hat_kodu>{hat}</hat_kodu></DurakDetay_GYY_wYonAdi>'
        root=fetch_soap_xml(URL_IBB,'DurakDetay_GYY_wYonAdi',body,timeout_sec=10)
        if root is None: return jsonify({"duraklar":[],"terminaller":{"G":"Gidiş","D":"Dönüş"}})
        data=[]; api_yon={"G":None,"D":None}
        with _lock: snap=dict(DURAK_DICT)
        for tbl in root.iter():
            if not tbl.tag.endswith('Table'): continue
            d={c.tag.split('}')[-1].upper():c.text for c in tbl}
            if 'YKOORDINATI' not in d or 'XKOORDINATI' not in d: continue
            yv=yon_cozucu(d.get('YON')); dkod=d.get('DURAKKODU','')
            inf=snap.get(dkod,{'akilli':False,'engelli':False,'tip':'AÇIK'})
            lat=temiz_sayi(d.get('YKOORDINATI','0')); lon=temiz_sayi(d.get('XKOORDINATI','0'))
            data.append({"sira":int(d.get('SIRANO',0) or 0),"ad":temiz_str(d.get('DURAKADI'),'Durak'),
                         "lat":lat,"lon":lon,"yon":yv,"kodu":dkod,
                         "akilli":inf.get('akilli',False),"engelli":inf.get('engelli',False),"tip":inf.get('tip','AÇIK')})
            yon_adi=temiz_str(d.get('YONADI') or d.get('YON_ADI'))
            if yon_adi and not api_yon[yv]: api_yon[yv]=yon_adi
        data.sort(key=lambda x:x['sira'])
        gi=[x for x in data if x['yon']=='G']; do=[x for x in data if x['yon']=='D']
        terms={"G":api_yon["G"] or (gi[-1]['ad'] if gi else "Gidiş"),
               "D":api_yon["D"] or (do[-1]['ad'] if do else "Dönüş")}
        sonuc={"duraklar":data,"terminaller":terms}
        with _lock:
            API_RESPONSE_CACHE[cache_key]=sonuc
        return jsonify(sonuc)

    @app.route('/api/canli_konum')
    def api_canli_konum():
        hat = request.args.get('hat', '').upper().strip()
        force = request.args.get('force', '0').strip() == '1'

        if not hat:
            return jsonify({"araclar": [], "veri_yasi_sn": 0, "arac_sayisi": 0})

        normalized, raw = get_live_buses_cached(hat, force_refresh=force)

        if normalized:
            normalized = tahmin_yon_terminal(hat, normalized)
            # ── ARAÇ DURUMU: seferde / duruyor / garajda ─────────────────
            # `arac_hareket_durumu` yalnızca ETA ucunda kullanılıyordu;
            # harita her aracı hizmetteymiş gibi çiziyordu. Garajda park
            # etmiş otobüs de yön okuyla görünüyor, kullanıcı onu gelecek
            # sanıyordu. Artık işaretleniyor.
            for _a in normalized:
                try:
                    _g_ad, _g_m = garajda_mi(_a.get("lat"), _a.get("lon"))
                except Exception:
                    _g_ad, _g_m = None, None
                try:
                    _hrk, _drs_sn, _drs_m = arac_hareket_durumu(_a.get("kapi"))
                except Exception:
                    _hrk, _drs_sn = True, 0
                _a["garaj_ad"] = _g_ad
                _a["garaj_m"] = _g_m
                _a["hareketli"] = bool(_hrk)
                _a["durus_dk"] = int((_drs_sn or 0) / 60)
                if _g_ad and not _hrk:
                    _a["durum"] = "garajda"
                elif _g_ad:
                    _a["durum"] = "garaj_cikis"
                elif not _hrk:
                    _a["durum"] = "duruyor"
                else:
                    _a["durum"] = "seferde"

        now = time.time()

        with _lock:
            live_entry = LIVE_BUS_CACHE.get(hat, {})
            live_ts = live_entry.get("ts", 0)

        veri_yasi = int(now - live_ts) if live_ts else 0

        # Verinin NE KADAR TAZE olduğunu ve nereden geldiğini açıkça söyle.
        # Kota dolduğunda uygulama son bilinen veriyi göstermeye devam
        # ediyor; yolcunun bunu bilmeye hakkı var. "Canlı" etiketiyle 40
        # dakikalık veri göstermek yanıltıcı olurdu.
        if veri_yasi <= 180:
            kaynak, kaynak_ad = "canli", "canlı"
        elif veri_yasi <= 1800:
            kaynak, kaynak_ad = "gecikmeli", "%d dk önceki veri" % (veri_yasi // 60)
        else:
            kaynak, kaynak_ad = "eski", "%d dk önceki veri — servis yanıt vermiyor" % (veri_yasi // 60)

        return jsonify({
            "araclar": normalized,
            "veri_yasi_sn": veri_yasi,
            "arac_sayisi": len(normalized),
            "kaynak": kaynak,
            "kaynak_ad": kaynak_ad,
            "force_used": force
        })

    # ★ FIX: Tek /api/bildirimler endpoint — çift tanım silindi
    @app.route('/api/bildirimler')
    def api_bildirimler():
        hat = request.args.get('hat', '').upper().strip()
        duyuru = olay_guncelle("duyuru")
        sonuclar = {"kaza": [], "ariza": [], "duyuru": []}

        for d in duyuru:
            if not d or not isinstance(d, dict):
                continue

            hk = temiz_str(alan_oku(d,'HAT','HATKODU','HatKodu','SHATKODU','Hat','HATLAR','Hatlar','ILGILIHATLAR','SHATLAR')).upper().strip()
            baslik = temiz_str(alan_oku(d,'BASLIK','Baslik','SDUYURUBASLIK'))
            msg = temiz_str(alan_oku(d,'MESAJ','Mesaj','SDUYURUMETNI','ACIKLAMA','Aciklama','ICERIK','Icerik'))
            tip = temiz_str(alan_oku(d,'TIP','Tip','STIP','KATEGORI','Kategori'),'DUYURU')
            if not (baslik or msg):
                continue

            if hat:
                if not _duyuru_hata_ait_mi(d, hat):
                    continue
                genel = False
            else:
                genel = not bool(_norm_hat_kodu(hk))

            sonuclar["duyuru"].append({
                "tip": "📢 " + tip,
                "mesaj": (f"<b>{baslik}</b><br>" if baslik else "") + msg,
                "lat": 0,
                "lon": 0,
                "kapi": "",
                "hat": hk,
                "genel": genel
            })

        return jsonify(sonuclar)

    @app.route('/api/radar')
    def api_radar():
        kaza=olay_guncelle("kaza"); ariza=olay_guncelle("ariza")
        with _lock: kapi_map=dict(FILO_CACHE["kapi_map"])
        cleaned=[]
        for k in kaza:
            if not k or not isinstance(k,dict): continue
            lat=temiz_sayi(alan_oku(k,'ENLEM','NENLEM','enlem',varsayilan=0))
            lon=temiz_sayi(alan_oku(k,'BOYLAM','NBOYLAM','boylam',varsayilan=0))
            if lat>0 and lon>0:
                raw=k.get('KAZASAAT',k.get('DTOLAYBASLANGICZAMANI',''))
                saat="Bilinmiyor"
                if raw and '/Date(' in str(raw):
                    try: saat=datetime.fromtimestamp(int(re.search(r'\d+',str(raw)).group())/1000).strftime('%H:%M')
                    except Exception:
                        pass
                cleaned.append({"enlem":lat,"boylam":lon,"saat":saat,
                                "tur":temiz_str(alan_oku(k, 'Tur', 'TUR', 'KAZA_TURU', varsayilan='Kaza')),"tip":"KAZA"})
        for y in ariza:
            if not y or not isinstance(y,dict): continue
            lat=temiz_sayi(alan_oku(y,'NENLEM','Enlem','enlem',varsayilan=0))
            lon=temiz_sayi(alan_oku(y,'NBOYLAM','Boylam','boylam',varsayilan=0))
            kapi=temiz_str(alan_oku(y,'SKAPINUMARASI','KapiNo'))
            msg=temiz_str(alan_oku(y,'SMESAJMETNI','MESAJ','Mesaj'))
            if (lat==0 or lon==0) and kapi in kapi_map:
                lat=kapi_map[kapi].get('lat',0); lon=kapi_map[kapi].get('lon',0)
            if lat>0 and lon>0:
                lat+=random.uniform(-0.0003,0.0003); lon+=random.uniform(-0.0003,0.0003)
                cleaned.append({"enlem":lat,"boylam":lon,"saat":kapi,"tur":msg,"tip":"ARIZA"})
        return jsonify(cleaned)

    @app.route('/api/garajlar')
    def api_garajlar():
        """
        İETT garajları — CANLI `GetGaraj_json` servisinden (86 garaj).

        Önceki sürümde burada ELLE YAZILMIŞ 27 kayıtlık statik liste vardı;
        yorumu "GetGaraj_json HTTP 500 döndürüyor" diyordu. Tekrar denendi:
        servis çalışıyor. Statik listenin sapmaları ölçüldü —
        İkitelli 0,82 km · Avcılar 0,59 km · **Tuzla 6,57 km**, ayrıca
        "Sarıyer Garajı" gerçekte hiç yok. Haritada garajlar bu yüzden
        yanlış yerde görünüyordu.

        Servis erişilemezse önbellekteki son liste döner (garajlar yer
        değiştirmediği için 24 saat TTL fazlasıyla yeterli).
        """
        g = garaj_listesi(force=request.args.get('force') == '1')
        # Arayüz eski alan adlarını bekliyor — uyumluluk için ikisi de veriliyor
        return jsonify([{"SGARAJADI": x["ad"], "NENLEM": x["lat"], "NBOYLAM": x["lon"],
                         "ad": x["ad"], "kod": x["kod"],
                         "lat": x["lat"], "lon": x["lon"]} for x in g])
    @app.route('/api/kavsaklar')
    def api_kavsaklar():
        # Eğer en üstte import etmediysen burada da edebilirsin:
        from services import guncelle_kavsaklar 
        
        ilce = request.args.get('ilce', '').upper()
        durum = request.args.get('durum', '').upper()
        force = request.args.get('force', '0') == '1'

        veri = guncelle_kavsaklar(force=force)

        # Filtreleme (İsteğe bağlı)
        if ilce:
            veri = [k for k in veri if k.get("ilce") == ilce]
        if durum:
            veri = [k for k in veri if k.get("durum") == durum]

        return jsonify({
            "adet": len(veri),
            "kavsaklar": veri,
            "kaynak": "isbak_soap"
        })

    @app.route('/api/saatler')
    def api_saatler():
        hat=request.args.get('hat','').upper()
        with _lock: 
            cached=SAAT_CACHE.get(hat)
        if cached: return jsonify(cached)
        body=f'<GetPlanlananSeferSaati_json xmlns="http://tempuri.org/"><HatKodu>{hat}</HatKodu></GetPlanlananSeferSaati_json>'
        res=fetch_soap(URL_SAAT,'GetPlanlananSeferSaati_json',body,timeout_sec=8)
        if res:
            with _lock: SAAT_CACHE[hat]=res
        return jsonify(res or [])

    @app.route('/api/durak_ara')
    def api_durak_ara():
        q_raw = request.args.get('q', '').strip()
        if len(q_raw) < 2: return jsonify([])
        with _lock: snap_d = dict(DURAK_DICT)
        q_up = q_raw.upper()
        if q_up in snap_d:
            d = snap_d[q_up]
            return jsonify([{'ad':d.get('ad',''),'kodu':q_up,'lat':d.get('lat',0),
                             'lon':d.get('lon',0),'ilce':d.get('ilce',''),
                             'akilli':d.get('akilli',False),'engelli':d.get('engelli',False),
                             'tip':d.get('tip','AÇIK'),'skor':1000}])
        adaylar = _durak_adaylari(q_raw, snap_d, top_n=40, min_skor=50)
        matched = []
        for kod, sk, ad in adaylar:
            d = snap_d[kod]
            matched.append({'ad':d.get('ad',''),'kodu':kod,'lat':d.get('lat',0),
                            'lon':d.get('lon',0),'ilce':d.get('ilce',''),
                            'akilli':d.get('akilli',False),'engelli':d.get('engelli',False),
                            'tip':d.get('tip','AÇIK'),'skor':sk})
        return jsonify(matched)

    @app.route('/api/motor_hat_bul')
    def api_motor_hat_bul():
        durak_kodu = request.args.get('kodu', '').strip()
        if not durak_kodu:
            return jsonify({"durum": "yok"})

        with _lock:
            # `IS_DB_READY` ICE AKTARILMAZ — services.py onu `global` ile
            # YENIDEN ATIYOR, dolayisiyla `from services import IS_DB_READY`
            # ile alinan ad sonsuza dek False kalir. Bu, MUHENDISLIK_NOTLARI.md'de
            # belgelenen HAT_KAPASITE tuzaginin aynisiydi: DB dolu olsa bile
            # olmayan durak sorgusu "yok" yerine "bekle" donuyordu
            # (canli dogrulandi: 13.388 durak varken bile "bekle").
            # MEMORY_DB yerinde guncellendigi icin dolulugu guvenilir isarettir.
            hatlar = list(MEMORY_DB.get(durak_kodu, []))
            ready = bool(MEMORY_DB)

        # 1. Hafıza DB (disk cache) hazır ve bu durak var → en hızlı yol
        if hatlar:
            return jsonify({"durum": "tamam", "hatlar": sorted(hatlar), "kaynak": "db"})

        # 2. DB henüz yüklenmediyse bekle mesajı ver
        if not ready:
            return jsonify({"durum": "bekle"})

        # 3. DB hazır ama bu durak kayıtlarda yok
        return jsonify({"durum": "yok"})

    # ★ FIX: ETA — araç yön ve geçmiş kontrolü eklendi
    @app.route('/api/durak_eta')
    def api_durak_eta():
        hat=request.args.get('hat','').upper()
        durak_lat=temiz_sayi(request.args.get('lat','0'))
        durak_lon=temiz_sayi(request.args.get('lon','0'))
        istenen_yon=request.args.get('yon','').strip().upper()

        # ── Yön verilmemişse DURAĞIN KENDİ yönünden türet ────────────────
        # Metrobüs istasyonlarında her yön AYRI durak kaydı (İNCİRLİ
        # 900221=D, 900222=G). G peronunda bekleyen yolcuya D yönündeki
        # araçları göstermek yanlış — o araç bu perona hiç uğramıyor.
        # Sorgulanan koordinata en yakın, bu hattı taşıyan durağı bulup
        # onun yönünü kullanıyoruz.
        if istenen_yon not in ('G', 'D') and hat:
            try:
                _en_k, _en_d = None, 9e9
                for _y in ('G', 'D'):
                    for _st in hat_yon_durak_listesi(hat, _y):
                        _m = hav(durak_lat, durak_lon, _st['lat'], _st['lon'])
                        if _m < _en_d:
                            _en_d, _en_k = _m, _y
                if _en_k and _en_d <= 0.25:      # 250 m içinde net eşleşme
                    istenen_yon = _en_k
            except Exception:
                pass
        if not hat or abs(durak_lat) < 1 or abs(durak_lon) < 1:
            return jsonify({"hata":"hat, lat, lon gerekli"})

        with _lock:
            saat_c=SAAT_CACHE.get(hat); filo_ts=FILO_CACHE["ts"]

        # Durak listesini al (yön kontrolü için)
        cache_key=f"durak_detay_{hat}"
        with _lock: cached_durak=API_RESPONSE_CACHE.get(cache_key)
        hat_duraklar=cached_durak.get("duraklar",[]) if cached_durak else []

        normalized,_=get_live_buses_cached(hat)
        if normalized:
            normalized=tahmin_yon_terminal(hat,normalized)
            sonuclar=[]
            with _lock: kapi_map=dict(FILO_CACHE["kapi_map"])
            for b in normalized:
                # Yön: önce HAREKETTEN türet, etiket yalnızca yedek.
                # GetHatOtoKonum_json'un 'yon' alanı güvenilmez (saha ölçümünde
                # 34AS'te etiketli araçların ~yarısı ters yönde ilerliyordu).
                # ÖNCELİK SAHA ÖLÇÜMÜYLE DEĞİŞTİ (31 Tem 2026).
                #
                # Eski kod hareketten türetilen yönü etiketin ÜSTÜNE yazıyordu;
                # gerekçe "34AS'te etiketli araçların yarısı ters yönde" idi.
                # O ölçüm YANLIŞ ALANI karşılaştırmış: `GetHatOtoKonum_json`ın
                # `yon` alanı G/D değil TERMİNAL ADI ('B.SONDURAK',
                # 'SÖĞÜTLÜÇEŞME'). Gerçek yön `guzergahkodu`da ('34G_D_D0').
                #
                # 4 hatta 87 araç izlenerek ölçüldü: guzergahkodu'ndan okunan
                # yön, aracın SIRANO ilerlemesiyle **86/87 = %98,9** uyumlu.
                # Terminal adı ↔ yön eşlemesi de %100 tutarlı.
                # Bu yüzden ETİKET ÖNCELİKLİ; hareketten türetme yalnızca
                # etiket yoksa devreye giriyor (o da nadiren, çünkü
                # guzergahkodu 51.972 seferin %100'ünde dolu).
                etiket_yon = b.get("yon")
                if etiket_yon in ("G", "D"):
                    arac_yonu, yon_kaynak = etiket_yon, "guzergah_kodu"
                else:
                    gercek_yon = arac_gercek_yon(b.get("kapi"), hat_duraklar,
                                                 etiket_yon, hat_kodu=hat)
                    arac_yonu  = gercek_yon
                    yon_kaynak = "hareket" if gercek_yon else "yok"

                if istenen_yon in ('G','D'):
                    if arac_yonu is None:
                        continue          # yönü bilinmiyorsa listeleme — yanlış ETA'dan iyidir
                    if arac_yonu != istenen_yon:
                        continue

                # ── SEFERDE OLMAYAN ARAÇ ETA'YA GİRMEZ ──────────────────────
                # Bu yorum eskiden de buradaydı ("park hâlindeki otobüse
                # güvenli ETA verilmez") ama `hareketli` YALNIZCA yanıta alan
                # olarak ekleniyordu, filtre olarak HİÇ kullanılmıyordu.
                # `garajda_mi` ise bu uçta hiç çağrılmıyordu. Sonuç: garajda
                # park etmiş otobüs yolcuya "2 dakikaya geliyor" diye
                # gösteriliyordu.
                #
                # Ölçüldü (12 Ağu, canlı veri):
                #   34G  M4852  garajda, hız 7, hareketsiz →  "2 dk"
                #   500T C-361  garajda, hız 0, hareketsiz → "22 dk"
                # Arayüz `hareketli` alanını hiç okumuyor, yani kullanıcı
                # yalnızca süreyi görüyordu. Gelmeyecek araç için süre vermek,
                # süre vermemekten kötüdür — yolcu durakta bekler.
                #
                # `/api/canli_konum` ile AYNI sınıflandırma (routes.py:1983):
                #   garajda      = garaj alanında + hareketsiz  → ELENİR
                #   garaj_cikis  = garaj alanında + hareketli    → ELENİR
                #                  (henüz güzergâha girmemiş; ETA'sı güvenilmez)
                #   duruyor      = 6 dk'da <150 m, garaj dışı    → ELENİR
                #   seferde      = kalan                          → gösterilir
                hareketli, durus_sn, durus_m = arac_hareket_durumu(b.get("kapi"))
                try:
                    _garaj_ad, _garaj_m = garajda_mi(b.get("lat"), b.get("lon"))
                except Exception:
                    _garaj_ad, _garaj_m = None, None
                if _garaj_ad or not hareketli:
                    continue

                try:
                    blat,blon=b["lat"],b["lon"]
                    spd_raw = float(b.get("hiz",0) or 0)
                    dist_km=hav(blat,blon,durak_lat,durak_lon)

                    yaklasiyor,sira_farki=arac_durak_yaklasiyor_mu(
                        blat,blon,arac_yonu,durak_lat,durak_lon,hat_duraklar,
                        hat_kodu=hat)
                    if not yaklasiyor:
                        continue

                    trafik=get_trafik(blat,blon)
                    kats=trafik.get("katsayi",1.0)
                    route_km = rota_mesafe_km(blat, blon, durak_lat, durak_lon, arac_yonu, hat_duraklar)

                    # Durak temelli model: kalan durak sayısı artık tahmine giriyor.
                    # eta_baz = bu hattın olağan süresi, gecikme = normalden sapma.
                    eta_ham, eta_baz, gecikme_ham, efektif_hiz = eta_hesapla(
                        route_km, spd_raw, kats, kalan_durak=sira_farki, hat=hat)
                    gecikme_dk = round(gecikme_ham, 1)
                    eta_min    = max(1, round(eta_ham))
                    _alt, _ust = eta_araligi(hat, eta_min)
                    if eta_min>75: continue

                    sonuclar.append({
                        "kapi":b["kapi"],"plaka":b.get("plaka","—"),
                        "operator":b.get("op","İETT"),
                        "hiz":int(spd_raw),"eta_min":eta_min,
                        "eta_baz_min": round(eta_baz),
                        "gecikme_dk": gecikme_dk,
                        "dist_km":round(dist_km,2),"route_km":round(route_km,2),
                        "veri_yasi":int(time.time()-filo_ts) if filo_ts else 0,
                        "kaynak":"ram","trafik_sev":trafik.get("seviye",""),
                        "trafik_renk":trafik.get("renk","#94a3b8"),"trafik_kats":kats,
                        "trafik_kaynak": trafik.get("kaynak","profil"),
                        "yaklasiyor":True,"sira_farki":sira_farki,
                        "yon":arac_yonu,"yon_kaynak":yon_kaynak,
                        "hareketli":hareketli,"durus_sn":durus_sn,"durus_m":durus_m,
                        "eta_alt":_alt,"eta_ust":_ust,
                    })
                except Exception: 
                    continue
            sonuclar.sort(key=lambda x:x['eta_min'])
            if sonuclar:
                return jsonify({"sonuclar":sonuclar[:5],"kaynak":"ram","arac_sayisi":len(normalized)})

        # Sefer saatinden tahmin
        if not saat_c:
            body=f'<GetPlanlananSeferSaati_json xmlns="http://tempuri.org/"><HatKodu>{hat}</HatKodu></GetPlanlananSeferSaati_json>'
            saat_c=fetch_soap(URL_SAAT,'GetPlanlananSeferSaati_json',body,timeout_sec=8) or []
            if saat_c:
                with _lock: SAAT_CACHE[hat]=saat_c

        if saat_c:
            simdi_dk=datetime.now().hour*60+datetime.now().minute
            gun_idx=datetime.now().weekday()
            gt='P' if gun_idx==6 else ('C' if gun_idx==5 else 'I')
            trafik=get_trafik(durak_lat,durak_lon); kats=trafik.get("katsayi",1.0)
            gelecek=[]
            for s in saat_c:
                gun_tipi = temiz_str(s.get('SGUNTIPI') or s.get('GunTipi')).upper()
                if gun_tipi != gt:
                    continue
                saat_yon=str(s.get('SYON',s.get('Yon','G'))).upper().strip()
                if saat_yon=='1': saat_yon='G'
                elif saat_yon in ('0','2'): saat_yon='D'
                if istenen_yon in ('G','D') and saat_yon!=istenen_yon: continue
                t=s.get('DT','')
                if not t: continue
                try:
                    p=t.split(':'); t_dk=int(p[0])*60+int(p[1])
                    fark=t_dk-simdi_dk
                    if fark<-5: continue  # Geçmiş seferler (5dk tolerans)
                    gecikme_oran = max(0.0, 1.0 - kats)
                    gecikme_dk_ek = round(max(0, fark) * gecikme_oran * 0.5, 1)
                    gec_dk=max(1,round(fark + gecikme_dk_ek))
                    if 0<gec_dk<90: gelecek.append({"saat":t,"dk":gec_dk,"planlanan_dk":fark,"gecikme_dk":gecikme_dk_ek})
                except Exception:
                    pass
            gelecek.sort(key=lambda x:x['dk'])
            if gelecek:
                return jsonify({"sonuclar":[{"eta_min":g["dk"],"saat":g["saat"],"planlanan_dk":g["planlanan_dk"],
                                              "gecikme_dk": g.get("gecikme_dk", 0),
                                              "kaynak":"sefer_saati","kapi":"-","plaka":"-","operator":"Planlı",
                                              "hiz":0,"dist_km":0,"route_km":0,"veri_yasi":0,
                                              "trafik_sev":trafik.get("seviye",""),
                                              "trafik_renk":trafik.get("renk","#94a3b8"),"trafik_kats":kats,
                                              "trafik_kaynak": trafik.get("kaynak","profil")}
                                             for g in gelecek[:3]],
                                "kaynak":"sefer_saati","arac_sayisi":0})

        return jsonify({"sonuclar":[],"kaynak":"yok","arac_sayisi":0})

    @app.route('/api/yolcu_analizi')
    def api_yolcu_analizi():
        hat=request.args.get('hat','').upper()
        if not hat: return jsonify({"hata":"Hat kodu gerekli"})
        with _lock:
            hi=HAFTALIK.get("haftaici",{}).get(hat,0)
            hs=HAFTALIK.get("haftasonu",{}).get(hat,0)
        if hi>0:
            return jsonify({"hat":hat,"tarihler":["HaftaİçiOrt","HaftaSonuOrt"],
                            "yolcular":[hi,hs],"kaynak":"haftalik_ram"})
        tarihler=[]; yolcular=[]
        for off in [3,2,1]:
            t_str=(datetime.now()-timedelta(days=off)).strftime("%Y-%m-%d")
            g_str=(datetime.now()-timedelta(days=off)).strftime("%d/%m")
            body=f'<GetIettYolculukHat_json xmlns="http://tempuri.org/"><Tarih>{t_str}</Tarih></GetIettYolculukHat_json>'
            yolcu=0
            res=fetch_soap(URL_IBB360,'GetIettYolculukHat_json',body,use_auth=False,timeout_sec=8)
            if isinstance(res,list):
                for y in res:
                    y_hat = temiz_str(alan_oku(y, 'Hat', 'HAT', 'HatKodu', 'HATKODU')).upper()
                    if y_hat == hat:
                        try:
                            yolcu = int(temiz_sayi(alan_oku(y, 'Yolculuk', 'YOLCULUK', 'Yolcu', 'YOLCU', varsayilan=0)))
                        except Exception:
                            pass
                        break
            tarihler.append(g_str); yolcular.append(yolcu)
        return jsonify({"hat":hat,"tarihler":tarihler,"yolcular":yolcular,"kaynak":"api"})

    @app.route('/api/gecikme_skoru')
    def api_gecikme_skoru():
        hat=request.args.get('hat','').upper()
        with _lock: gc=dict(GECIKME_CACHE)
        if hat:
            veri=gc.get(hat)
            if not veri:
                saat=datetime.now().hour; hici=datetime.now().weekday()<5
                th,ts=ISTANBUL_PROFIL.get(saat,(0.75,0.75)); kats=th if hici else ts
                seed_val=sum(ord(c) for c in hat)%100; varyasyon=(seed_val-50)*0.003
                hat_kats=max(0.25,min(1.0,kats+varyasyon)); sev,renk=trafik_seviye(hat_kats)
                veri={"skor":int((1.0-hat_kats)*100),"seviye":sev,"renk":renk,
                      "ortalama_hiz":round(28.0*hat_kats,1),"beklenen_hiz":28.0,"arac_sayisi":0,"tahmin":True}
            return jsonify(veri)
        top=sorted(gc.items(),key=lambda x:x[1].get("skor",0),reverse=True)
        return jsonify({"hatlar":[{"hat":h,**v} for h,v in top],"toplam":len(top)})

    @app.route('/api/yogunluk')
    def api_yogunluk():
        hat=request.args.get('hat','').upper()
        with _lock: yc=dict(YOGUNLUK_CACHE)
        if hat:
            veri=yc.get(hat)
            if not veri: return jsonify({"hata":"Bu hat için yoğunluk verisi yok"})
            return jsonify({"hat":hat,**veri})
        simdi=datetime.now().hour; hici=datetime.now().weekday()<5
        sirali=sorted([(h,v["profil_hi"][simdi] if hici else v["profil_hs"][simdi],
                        v.get("kaynak_arac","—"),v.get("arac_sayisi",0))
                       for h,v in yc.items()],key=lambda x:x[1],reverse=True)[:20]
        return jsonify({"en_yogun":[{"hat":h,"doluluk":d,"kaynak":k,"arac":a} for h,d,k,a in sirali],
                        "saat":simdi,"gun_tipi":"HİÇ" if hici else "HS"})

    @app.route('/api/trafik_nokta')
    def api_trafik_nokta():
        lat=temiz_sayi(request.args.get('lat','0')); lon=temiz_sayi(request.args.get('lon','0'))
        if abs(lat) < 1 or abs(lon) < 1: return jsonify({"hata":"lat/lon gerekli"})
        return jsonify(get_trafik(lat,lon))

    @app.route('/api/trafik_isi')
    def api_trafik_isi():
        """
        Harita ısı katmanı için trafik yoğunluk noktaları.
        Önce IBB TrafficIndex → yoksa saat profili ile İstanbul koridor noktaları üretilir.
        Dönen format: {noktalar:[{lat,lon,yogunluk}], kaynak, ibb_index}
        """
        from services import get_traffic_index_history_summary, saat_trafik_katsayi, KORIDOR_AGIRLIKLARI

        # İstanbul'u kapsayan ızgara noktaları (lat, lon)
        GRID = [
            (41.0781, 28.9784), (41.0500, 28.9900), (41.0200, 29.0100),
            (41.0050, 28.9500), (40.9900, 28.8700), (41.0300, 28.7800),
            (41.1050, 29.0300), (41.0650, 29.0600), (41.0450, 29.1000),
            (40.9750, 29.0100), (40.9600, 29.1200), (41.1300, 28.9900),
            (41.1500, 29.0500), (41.0850, 28.8500), (41.0100, 28.8200),
            (40.9950, 28.7500), (41.0600, 28.6800), (41.1200, 28.7200),
            (41.0300, 29.0500), (41.0750, 29.1500), (40.9500, 28.9800),
            (40.9300, 29.0600), (41.1700, 29.0200), (41.0950, 28.7800),
        ]

        ibb_index = None
        kaynak = "profil"

        # 1. IBB TrafficIndex
        try:
            ozet = get_traffic_index_history_summary(period="5M")
            values = ozet.get("values", [])
            if values:
                ibb_index = values[-1]
                kaynak = "ibb_traffic_index"
        except Exception:
            pass

        noktalar = []
        for lat, lon in GRID:
            if ibb_index is not None:
                # IBB indeksi tüm şehir için geçerli; koridor ağırlıklarıyla nokta bazlı varyasyon ekle
                kor_kats = saat_trafik_katsayi(lat, lon)
                base_yogunluk = float(ibb_index)
                # Koridor yoğunluğu yüksekse indeksi biraz artır
                yogunluk = round(min(100, base_yogunluk * (2.0 - kor_kats)), 1)
            else:
                # Saat profili → yoğunluk = (1 - katsayi) * 100
                kats = saat_trafik_katsayi(lat, lon)
                yogunluk = round((1.0 - kats) * 100, 1)

            noktalar.append({"lat": lat, "lon": lon, "yogunluk": yogunluk})

        return jsonify({
            "noktalar": noktalar,
            "kaynak": kaynak,
            "ibb_index": ibb_index,
            "adet": len(noktalar)
        })

    # ── YENİ ENDPOINTLERİ ──────────────────────────────────────

    @app.route('/api/guzergah_trafik')
    def api_guzergah_trafik():
        """
        Hat güzergahını trafik renkli segmentlere böler.
        Döner: {segmentler:[{lat1,lon1,lat2,lon2,renk,seviye,katsayi}], hat, yon}
        Frontend bu listeyi alıp her segmenti ayrı polyline olarak çizer.
        """
        hat = request.args.get('hat','').upper()
        yon = request.args.get('yon','G').upper()
        if not hat:
            return jsonify({"hata": "hat gerekli"})

        # Durak listesini cache'den veya API'den al
        cache_key = f"durak_detay_{hat}"
        with _lock:
            cached = API_RESPONSE_CACHE.get(cache_key)

        if not cached:
            body = f'<DurakDetay_GYY_wYonAdi xmlns="http://tempuri.org/"><hat_kodu>{hat}</hat_kodu></DurakDetay_GYY_wYonAdi>'
            root = fetch_soap_xml(URL_IBB, 'DurakDetay_GYY_wYonAdi', body, timeout_sec=10)
            if root is None:
                return jsonify({"hata": "Durak verisi alınamadı", "segmentler": []})
            from utils import xml_findall_local, xml_child_text, safe_int, temiz_str, temiz_sayi
            duraklar_raw = xml_findall_local(root, "DurakDetay_GYY_wYonAdiResult") or xml_findall_local(root, "Table")
            duraklar = []
            for item in duraklar_raw:
                d = {
                    "kodu": xml_child_text(item, "SDURAKKODU", ""),
                    "ad":   xml_child_text(item, "SDURAKADI", ""),
                    "yon":  xml_child_text(item, "SYON", "G").upper(),
                    "sira": safe_int(xml_child_text(item, "SSIRA", "0")),
                    "lat":  temiz_sayi(xml_child_text(item, "ENLEM", "0")),
                    "lon":  temiz_sayi(xml_child_text(item, "BOYLAM", "0")),
                }
                if d["lat"] and d["lon"]:
                    duraklar.append(d)
            with _lock:
                API_RESPONSE_CACHE[cache_key] = {"duraklar": duraklar}
        else:
            duraklar = cached.get("duraklar", [])

        # Seçili yönü filtrele ve sırala
        pts = sorted(
            [d for d in duraklar if d.get("yon") == yon and d.get("lat") and d.get("lon")],
            key=lambda x: x.get("sira", 0)
        )

        if len(pts) < 2:
            return jsonify({"segmentler": [], "hat": hat, "yon": yon, "mesaj": "Yeterli durak yok"})

        # Her ardışık durak çifti için trafik sorgula → segment oluştur
        segmentler = []
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i+1]
            # Segment orta noktasında trafik sorgula (performans için)
            mid_lat = (p1["lat"] + p2["lat"]) / 2
            mid_lon = (p1["lon"] + p2["lon"]) / 2
            trafik = get_trafik(mid_lat, mid_lon)
            seg = {
                "lat1": p1["lat"], "lon1": p1["lon"],
                "lat2": p2["lat"], "lon2": p2["lon"],
                "durak1": p1.get("ad", ""), "durak2": p2.get("ad", ""),
                "renk":    trafik.get("renk", "#0ea5e9"),
                "seviye":  trafik.get("seviye", "bilinmiyor"),
                "katsayi": trafik.get("katsayi", 1.0),
                "trafik_kaynak": trafik.get("kaynak", "profil"),
            }
            if "ibb_index" in trafik:
                seg["ibb_index"] = trafik["ibb_index"]
            segmentler.append(seg)

        return jsonify({
            "segmentler": segmentler,
            "hat": hat,
            "yon": yon,
            "durak_sayisi": len(pts),
        })

    @app.route('/api/guzergah_geo')
    def api_guzergah_geo():
        """
        Gerçek yol geometrisi: hat_guzergah_geo.json'dan [[lat,lon],...] döner.
        ?hat=76A&yon=G (G=gidiş, D=dönüş, boş=her ikisi)
        """
        hat = request.args.get('hat', '').upper().strip()
        yon = request.args.get('yon', '').upper().strip()
        if not hat:
            return jsonify({"hata": "hat gerekli"})

        geo = PANEL_DATA.get('hat_guzergah_geo', {})
        hat_data = geo.get(hat)
        if not hat_data:
            return jsonify({"hat": hat, "G": [], "D": []})

        if yon in ('G', 'D'):
            return jsonify({"hat": hat, yon: hat_data.get(yon, [])})
        return jsonify({"hat": hat, "G": hat_data.get('G', []), "D": hat_data.get('D', [])})




    @app.route('/api/arac_ozellik')
    def api_arac_ozellik():
        kapi=request.args.get('kapi','').strip()
        if not kapi: return jsonify({"hata":"kapi gerekli"})
        return jsonify(get_arac_ozellik(kapi))

    @app.route('/api/operasyonel_ozet')
    def api_operasyonel_ozet():
        with _lock:
            return jsonify({
                "ariza_aktif": len(OLAY_CACHE["ariza"]["veri"]),
                "duyuru_sayisi": len(OLAY_CACHE["duyuru"]["veri"]),
                "guncelleme_ts": datetime.now().isoformat()
            })

    @app.route('/api/kara_kutu_sefer')
    def api_kara_kutu_sefer():
        """GetKaraKutuSeferBilgileri_json — Tarih bazlı kara kutu sefer bilgileri"""
        tarih=request.args.get('tarih',datetime.now().strftime("%Y-%m-%d"))
        body=f'<GetKaraKutuSeferBilgileri_json xmlns="http://tempuri.org/"><Tarih>{tarih}</Tarih></GetKaraKutuSeferBilgileri_json>'
        res=fetch_soap(URL_FILO,'GetKaraKutuSeferBilgileri_json',body,timeout_sec=10,use_auth=True)
        return jsonify(res or [])

    @app.route('/api/usulsuz_kart')
    def api_usulsuz_kart():
        """GetUzulsuzKartKullanim_json — Saate göre usulsüz kart kullanımı"""
        saat=request.args.get('saat',str(datetime.now().hour))
        try: saat_int=int(saat)
        except: saat_int=datetime.now().hour
        body=f'<GetUzulsuzKartKullanim_json xmlns="http://tempuri.org/"><saat>{saat_int}</saat></GetUzulsuzKartKullanim_json>'
        res=fetch_soap(URL_FILO,'GetUzulsuzKartKullanim_json',body,timeout_sec=8,use_auth=True)
        return jsonify(res or [])

    @app.route('/api/metrobus_hazir')
    def api_metrobus_hazir():
        """GetKaraKutu_ServiseHazirAracMetrobus_json — Metrobüste servise hazır araçlar"""
        body='<GetKaraKutu_ServiseHazirAracMetrobus_json xmlns="http://tempuri.org/" />'
        res=fetch_soap(URL_FILO,'GetKaraKutu_ServiseHazirAracMetrobus_json',body,timeout_sec=8,use_auth=True)
        return jsonify(res or [])

    @app.route('/api/plaka_sorgula')
    def api_plaka_sorgula():
        """IETTPlakaServisi_Json — KapiNo ile plaka sorgula (ibb.asmx)"""
        kapi=request.args.get('kapi','').strip()
        if not kapi: return jsonify({"hata":"kapi gerekli"})
        body=f'<IETTPlakaServisi_Json xmlns="http://tempuri.org/"><KapiNo>{kapi}</KapiNo></IETTPlakaServisi_Json>'
        res=fetch_soap(URL_IBB,'IETTPlakaServisi_Json',body,timeout_sec=8,use_auth=True)
        return jsonify(res or [])

    @app.route('/api/durak_sefer_saati')
    def api_durak_sefer_saati():
        """GetPlanlananSeferSaatiAraDurak_json — Durak kodu ile sefer saati"""
        durak=request.args.get('durak','').strip()
        if not durak: return jsonify({"hata":"durak gerekli"})
        body=f'<GetPlanlananSeferSaatiAraDurak_json xmlns="http://tempuri.org/"><DurakKodu>{durak}</DurakKodu></GetPlanlananSeferSaatiAraDurak_json>'
        res=fetch_soap(URL_SAAT,'GetPlanlananSeferSaatiAraDurak_json',body,timeout_sec=8,use_auth=True)
        return jsonify(res or [])

    @app.route('/api/yolcu_bilgilendirme')
    def api_yolcu_bilgilendirme():
        """GetYolcuBilgilendirme_json — Yolcu bilgilendirme mesajları"""
        body='<GetYolcuBilgilendirme_json xmlns="http://tempuri.org/" />'
        res=fetch_soap(URL_FILO,'GetYolcuBilgilendirme_json',body,timeout_sec=8,use_auth=True)
        return jsonify(res or [])





    @app.route('/api/plan_basari')
    def api_plan_basari():
        """
        Tüm ağ veya belirli hat için sefer tamamlanma oranı.
        SGOREVDURUM: T=Tamamlandı, YK=Yarım Kaldı, P=Planlı
        ?hat=79T → sadece o hat
        """
        hat_filtre = request.args.get('hat', '').strip().upper()

        with _lock:
            hat_tamamlanma = dict(ARSIV_CACHE.get("hat_tamamlanma", {}))
            ozet_genel     = dict(ARSIV_CACHE.get("tamamlanma_ozet", {}))
            veri_tarihi    = ARSIV_CACHE.get("veri_tarihi", "")

        if hat_filtre:
            hat_veri = hat_tamamlanma.get(hat_filtre, {})
            return jsonify({
                "hat":       hat_filtre,
                "veri":      hat_veri,
                "tarih":     veri_tarihi,
                "kaynak":    "arsiv_gorev",
            })

        # Tüm ağ — en düşük tamamlanma oranlı 20 hat öne al
        sirali = sorted(
            hat_tamamlanma.items(),
            key=lambda x: x[1].get("oran_yuzde", 100)
        )[:20]

        return jsonify({
            "ozet":    ozet_genel,
            "en_dusuk": [{"hat": h, **v} for h, v in sirali],
            "tarih":   veri_tarihi,
            "kaynak":  "arsiv_gorev",
        })


    @app.route('/api/headway')
    def api_headway():
        """
        Hat için sefer sıklığı (headway) analizi.
        GetPlanlananSeferSaati_json → bugünün saatlerinden hesaplar.
        ?hat=79T → zorunlu
        """
        hat = request.args.get('hat', '').strip().upper()
        if not hat:
            return jsonify({"hata": "hat parametresi gerekli"})

        # SAAT_CACHE'de varsa direkt kullan
        with _lock:
            saat_c = SAAT_CACHE.get(hat)

        sonuc = hesapla_headway(hat)
        if not sonuc:
            return jsonify({"hata": f"{hat} için sefer saati verisi alınamadı"})

        # Hat uzunluğu ekle (headway × hat_uzunlugu → km/saat verimlilik)
        hb = get_hat_bilgi(hat)
        sonuc["hat_uzunlugu_km"]  = hb.get("hat_uzunlugu_km")
        sonuc["sefer_suresi_dk"]  = hb.get("sefer_suresi_dk")
        sonuc["hat_adi"]          = hb.get("hat_adi", hat)

        # Headway yorumu
        hw = sonuc.get("headway_ort")
        if hw is not None:
            if hw <= 5:
                sonuc["headway_yorum"] = "Çok sık — yüksek kapasite hattı"
            elif hw <= 10:
                sonuc["headway_yorum"] = "Sık — yeterli frekans"
            elif hw <= 20:
                sonuc["headway_yorum"] = "Orta — bekleme süresi kabul edilebilir"
            else:
                sonuc["headway_yorum"] = "Seyrek — bekleme süresi uzun"

        return jsonify(sonuc)


    @app.route('/api/hat_bilgi')
    def api_hat_bilgi():
        """
        GetHat_json'dan SEFER_SURESI, HAT_UZUNLUGU, tarife bilgisi.
        Tek hat veya boş (tüm ağ özeti).
        ?hat=79T
        """
        hat = request.args.get('hat', '').strip().upper()

        if hat:
            sonuc = get_hat_bilgi(hat)
            if not sonuc:
                return jsonify({"hata": f"{hat} için hat bilgisi alınamadı"})

            # Tamamlanma ve headway ekle
            with _lock:
                tamamlanma = dict(ARSIV_CACHE.get("hat_tamamlanma", {}).get(hat, {}))
            sonuc["tamamlanma"] = tamamlanma
            return jsonify(sonuc)

        # Tüm cache'i döndür (hat listesi için)
        with _lock:
            snap = dict(HAT_BILGI_CACHE)
        return jsonify({
            "hat_sayisi": len(snap),
            "hatlar":     list(snap.keys()),
            "kaynak":     "hat_bilgi_cache",
        })


    @app.route('/api/kara_kutu')
    def api_kara_kutu():
        """GetKaraKutu_json — Hat/araç bazlı kara kutu verisi"""
        hat=request.args.get('hat','').upper()
        kapi=request.args.get('kapi','')
        tarih=request.args.get('tarih',datetime.now().strftime("%Y-%m-%d"))
        body=(f'<GetKaraKutu_json xmlns="http://tempuri.org/">'
              f'<tarih>{tarih}</tarih><KapiNo>{kapi}</KapiNo><HatKodu>{hat}</HatKodu>'
              f'</GetKaraKutu_json>')
        res = fetch_soap(URL_FILO, 'GetKaraKutu_json', body, timeout_sec=10, use_auth=True)
        return jsonify(res or [])

    # ══════════════════════════════════════════════════════════
    # ★ ML VERİ SİSTEMİ — SQL kolonlarına dayalı akıllı simülasyon
    # Kolonlar: transition_date, transition_hour, transport_type_id, road_type,
    #           line, transfer_type, number_of_passage, number_of_passenger,
    #           product_kind, transaction_type_desc, town, line_name
    # ══════════════════════════════════════════════════════════

    # İstanbul gerçek ilçe dağılımı (IETT hizmet ağına göre ağırlıklı)
    # ══════════════════════════════════════════════════════════
    # ★ GERÇEK SQL VERİ ANALİTİĞİ (Dashboard Grafikleri İçin)
    # ══════════════════════════════════════════════════════════

    @app.route('/api/tani')
    def api_tani():
        with _lock:
            snap_live={h:data["normalized"] for h,data in LIVE_BUS_CACHE.items()
                       if isinstance(data,dict) and data.get("normalized")}
            ornek_arac=FILO_CACHE["liste"][0] if FILO_CACHE["liste"] else None
            ornek_normalized = None
            if snap_live:
                ilk_liste = next(iter(snap_live.values()), [])
                if ilk_liste:
                    ornek_normalized = ilk_liste[0]
        return jsonify({
            "zaman":datetime.now().isoformat(),
            "filo_cache_yas_sn":int(time.time()-FILO_CACHE["ts"]) if FILO_CACHE["ts"] else -1,
            "filo_kapi_map":len(FILO_CACHE["kapi_map"]),
            "live_cache_hatlar":list(snap_live.keys())[:10],
            "live_cache_arac_toplam":sum(len(v) for v in snap_live.values()),
            "memory_db_durak":len(MEMORY_DB),"durak_dict":len(DURAK_DICT),
            "gecikme_cache":len(GECIKME_CACHE),"yogunluk_cache":len(YOGUNLUK_CACHE),
            "duyuru_sayisi":len(OLAY_CACHE["duyuru"]["veri"]),
            "ornek_ham_kayit":ornek_arac,"ornek_normalized":ornek_normalized,
        })
    # ──────────────────────────────────────────────────────────
    # ★ YENİ: SQL'DEN GERÇEK VERİ İLE YIĞILMA VE AKTARMA TAHMİNİ
    # ──────────────────────────────────────────────────────────
