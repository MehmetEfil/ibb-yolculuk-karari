# ETA Modeli — Teşhis, Düzeltmeler, Etki Faktörleri

> Son güncelleme: 27 Temmuz 2026
> Tüm ölçümler canlı İBB/İETT servislerinden ve saha gözleminden alınmıştır.

## 1. Neden bu doküman

Kullanıcı "Otobüsüm Nerede" ile karşılaştırıp panelimizin ETA'larının hatalı
olduğunu tespit etti. Sistematik inceleme sonucu **beş ayrı hata** bulundu;
beşi de düzeltildi (aşağıda H1–H5).

---

## 2. Bulunan hatalar

### H1 — Trafik iki kez sayılıyordu ✅ düzeltildi

```python
profil_hiz = max(12.0, 24.0 * kats)          # trafik hıza girmiş
gecikme    = eta_baz * (1 - kats) * 0.6      # trafik İKİNCİ kez eklenmiş
eta        = eta_baz + gecikme
```

Trafik katsayısı 0,5 iken hız 24→12'ye düşüyor **ve** üstüne %30 daha ekleniyordu.

**Düzeltme:** `services.eta_hesapla()` — tek fonksiyon, tanım gereği
`gecikme = trafikli_süre − serbest_akış_süresi`. Çift sayım matematiksel
olarak imkânsız hâle geldi.

**Etki:** yoğun trafikte tahmin %11–31 arası şişiyordu.

| Trafik | Eski | Yeni |
|---|---|---|
| akıcı | 10,5 dk | 9,4 dk |
| yoğun | 15,5 dk | 12,5 dk |
| tıkanık | 20,4 dk | 15,0 dk |
| dur-kalk | 21,8 dk | 15,0 dk |

Doğrulama: 9/9 kural, 324 parametre kombinasyonu.

---

### H2 — Durak sayısı tahmine hiç girmiyordu ✅ düzeltildi

Kod `sira_farki`'nı (araçla durak arasındaki durak sayısı) hesaplıyor,
cevapta döndürüyor, ama ETA matematiğinde **kullanmıyordu**. Model saf
mesafe/hız idi.

Sonuç: aynı mesafedeki iki otobüsten biri 2, diğeri 12 durak ötedeyse
ikisine de aynı süre veriliyordu. Gerçek fark ~10 dakika.

**Düzeltme — veriden kalibre edilmiş model:**

```
süre = km / 42,1 km/s  +  durak_sayısı × 0,50 dk  ×  hat_katsayısı
```

Kalibrasyon kümesi: **575 hat × 10 gün = 443.000 gerçek sefer**.

Yol boyunca bir tuzak: kısıtsız regresyon "seyir hızı 123 km/s" verdi —
km ile durak sayısı eş-doğrusal olduğu için model ikisini ayıramadı.
Fiziksel kısıt konarak yeniden çözüldü.

**Holdout doğrulama** (23 Temmuz'da öğren → 25 Temmuz'da test):

| Model | ±%20 içinde | ±%30 içinde |
|---|---|---|
| Eski (mesafe ÷ 24 km/s) | %46,2 | %62,1 |
| Yeni global | %63,5 | %78,8 |
| **Yeni + hat katsayısı** | **%89,4** | **%97,2** |

Eğitim gününde %100, test gününde %89,4 → model ezberlemiyor, genelleşiyor.

Çıktı: `data/hat_profil.json` (735 hat, hafta içi/hafta sonu ayrı katsayı).
GTFS'ten durak sayısı + arşivden gerçek süre. Statik dosya, ayda bir tazelenir.

---

### H3 — "Şu anki trafik" 24 saat eskiydi ✅ düzeltildi

İBB trafik geçmişi servisi kayıtları **en yeni başta** döndürüyor.
Panel `values[-1]` alıyordu — o listenin **en eski** kaydı:

```
listenin başı : 2026-07-27T22:34  index 20   ← gerçek şu an
listenin sonu : 2026-07-26T22:39  index 36   ← kodun aldığı
```

Yani panel bir yıldır "şu anki trafik" diye dünkü aynı saatin değerini
kullanıyormuş. Haritadaki trafik katmanı, gecikme skorları, ETA — trafiğe
dokunan her şey etkileniyordu. Orijinal staj panelinden miras.

**Düzeltme:** `get_traffic_index_history_summary()` artık veriyi kronolojik
sıraya çeviriyor. Grafikler de soldan sağa doğru akıyor.

**Ek düzeltme:** trafik referansı "24 saat ortalaması" yerine
**"aynı saatin 7 günlük normali"** oldu. 24 saatlik ortalama gecenin ölü
saatlerini içerdiği için gündüzü sürekli "normalden kötü" gösteriyordu.

Ölçülen saatlik normal profil (7 gün):

```
04:00 →  1,8      12:00 → 39,4      18:00 → 59,4
07:00 → 28,2      15:00 → 47,8      21:00 → 28,5
08:00 → 38,2      17:00 → 56,3      23:00 → 23,6
```

**Etki (aynı 4 saha ölçümünde):** ortalama mutlak hata **2,4 dk → 0,51 dk**.

---

### H4 — Yön etiketi güvenilmez ✅ düzeltildi, sahada doğrulandı

En ciddi hata bu. `GetHatOtoKonum_json`'un `yon` alanı yanlış.

Saha ölçümü (34AS, 27 Temmuz 23:10, `yon=G` etiketli 4 araç):

```
O5100   G_indeks:  1 → 1 → 2 → 2 → 3    ✓ artıyor, etiket doğru
M3180   G_indeks: 20 → 21 → 21 → 21 → 22 ✓ artıyor, etiket doğru
M4652   G_indeks: 26 → 26 → 26 → 26 → 25 ✗ AZALIYOR, ters yönde
O5062   G_indeks: 22 → 21 → 21 → 21 → 20 ✗ AZALIYOR, ters yönde
```

Örneklemde etiketli araçların **yarısı** ters yönde ilerliyordu.

Sonucu: `/api/durak_eta` durağa **hiç gelmeyecek** otobüsler için ETA veriyor.
Sahada görüldü — "1 dk" denen otobüs 374 m'den 2.167 m'ye uzaklaştı.

Yaklaşma filtresinin kendi mantığı doğru (indeks karşılaştırması sağlam);
sorun girdi verisinde.

**Düzeltme:** `services.arac_gercek_yon()` — yönü etiketten değil
**hareketten** türetir. Aracın geçmiş konumları hem G hem D durak dizisinde
indekslenir; hangi yönde indeks tutarlı artıyorsa fiili yön odur.
Karar verilemezse araç listelenmez (yanlış ETA'dan iyidir).

Altyapı hazırdı: `ARAC_KONUM_GECMIS` zaten her araç için 11 dakikalık
konum geçmişi tutuyordu (uzun duruş tespiti için).

Yanıta `yon_kaynak` alanı eklendi: `hareket` | `etiket` | `yok`.

**Saha doğrulaması (34AS, TOPKAPI durağı):**

| | Düzeltme öncesi | Düzeltme sonrası |
|---|---|---|
| Listelenen araç | 5 | 5 |
| Gerçekten durağa varan | 1 | **5** |
| Hiç yaklaşmadan uzaklaşan | 4 | **0** |

Öncesi (araçlar hiç yaklaşmadan uzaklaşıyor):
```
M3079   374m → 727 → 1831 → 2167
M3239  4267m → 4817 → 5299 → 6423
O5103  5224m → 6034 → 6653 → 6957
M4607  8269m → 9053 → 9751 → 10246
```

Sonrası (hepsi durağa varıp ayrılıyor):
```
A5082    98m'ye kadar geldi      O5031   620m → 141m
O5030    28m'ye kadar geldi      O5110  2044m → 244m
M3215   233m → 112m
```

Beş aracın beşinde de `yon_kaynak = hareket` — karar etiketten değil
gözlemden geldi.

> **Test aracı uyarısı:** ilk değerlendirmede "ilk konum vs son konum"
> karşılaştırması kullanıldı; varıp giden otobüs bu ölçüte göre "uzaklaştı"
> görünüyor ve sonuç %20 isabet gibi okunuyordu. Doğru ölçüt, gözlem
> penceresindeki **en yakın mesafe**. Ölçüt düzeltildi.

---

### H5 — Hareketsiz araca güvenli ETA veriliyordu ✅ düzeltildi

500T saha ölçümünde park hâlindeki bir araca 33 dakikalık ETA verildiği
görüldü: C-342, altı dakikada 60 metre. Duran otobüs için kesin tahmin
üretmek kullanıcıyı yanıltır.

**Düzeltme:** `services.arac_hareket_durumu()` — son 6 dakikada 150 m'den az
yer değiştiren araç `hareketli=False` olarak işaretlenir. Yanıta
`hareketli`, `durus_sn`, `durus_m` alanları eklendi.

Doğrulama (500T, MEHMET ALİ TUNGA CAMİ):

```
C-346   247 sn'de    4 m  →  hareketli=HAYIR   yon_kaynak=etiket
C-342   247 sn'de  921 m  →  hareketli=EVET    yon_kaynak=hareket
C-380   247 sn'de 2508 m  →  hareketli=EVET    yon_kaynak=hareket
```

Park hâlindeki tek araç, yön çıkarımının karar veremediği tek araçla aynı.
İki mekanizma birbirini doğruluyor.

Bu bilgi aynı zamanda **mazeret katmanının girdisi**: "bu otobüs 6 dakikadır
hareketsiz" cümlesi kullanıcı için tahmin kadar değerli.

---

## 3. ETA'yı etkileyen tüm faktörler

Hangi faktör için ne veriye sahibiz, ne kadarını kullanıyoruz:

| # | Faktör | Etki | Veri | Durum |
|---|---|---|---|---|
| 1 | Kalan mesafe | Büyük | `rota_mesafe_km` + güzergâh çizgisi | ✅ kullanılıyor |
| 2 | Kalan durak sayısı | **Büyük** | `sira_farki`, GTFS durak dizisi | ✅ yeni eklendi |
| 3 | Yön / yaklaşıyor mu | **Kritik** | Konum geçmişinden türetim | ✅ yeni eklendi |
| 4 | Hat karakteri | Büyük | 735 hat katsayısı (arşiv) | ✅ yeni eklendi |
| 5 | Gün tipi (hafta içi/sonu) | Orta | Ayrı katsayı, oran 0,92 | ✅ kullanılıyor |
| 6 | Trafik (şehir geneli) | Büyük | İBB TrafficIndex, 5 dk | ✅ düzeltildi |
| 7 | Saat dilimi | Büyük | Saatlik normal profil ölçüldü | ⚠️ trafikte var, hat katsayısında yok |
| 8 | Aracın kendi hızı | Orta | `ARAC_KONUM_GECMIS` son 11 dk | ⚠️ ham hız var, trend yok |
| 9 | Durak beklemesi | Orta | Sabit 0,50 dk | ⚠️ ölçülebilir ama sabit |
| 10 | Yolcu yoğunluğu | Orta | `GetIettYolculukHat` günlük hat toplamı | ⚠️ saat kırılımı yok |
| 11 | Uzun duruş / arıza | Orta | `hesapla_uzun_duruş()` — 60 m'de 120 sn+ | ❌ ETA'ya bağlı değil |
| 12 | Sefer iptali | **Kritik** | `SGOREVDURUM='I'`, %3,97 | ❌ kullanılmıyor |
| 13 | Duyurular (yol kapalı) | Değişken | `GetDuyurular_json`, 72 aktif | ❌ ETA'ya bağlı değil |
| 14 | Kaza | Nadir/büyük | `GetKazaLokasyon_json`, 1–10/gün | ❌ ETA'ya bağlı değil |
| 15 | Trafik (nokta bazlı) | Büyük | TomTom (anahtar gerek) | ❌ yok — İBB tek sayı veriyor |
| 16 | Hava durumu | Orta | OpenWeather ücretsiz | ❌ entegre değil |
| 17 | İşletmeci (ÖHO/İETT) | Küçük | `SSERVISTIPI` | ❌ kullanılmıyor |
| 18 | Okul dönemi / tatil | Orta | Takvimden türetilebilir | ❌ yok |
| 19 | Maç / etkinlik | Nadir/büyük | İBB etkinlik takvimi | ❌ yok |
| 20 | Yol çalışması | Değişken | `GetBozukSatih_json` (kimlik gerek) | ❌ kullanılmıyor |

**Özet:** 20 faktörden 6'sı tam kullanımda, 4'ü kısmi, 10'u hiç kullanılmıyor.

---

## 4. Hedef model — mazeret katmanıyla birlikte

```
ETA = normal_beklenti × trafik_sapması + Δ_araç + Δ_yoğunluk + Δ_olay

normal_beklenti = (km/42,1 × 60 + durak × 0,50) × hat_katsayısı(gün tipi, saat)
trafik_sapması  = o saatin normali ÷ şu anki trafik
Δ_araç          = aracın son 10 dk hızı, hattın normuna göre sapma
Δ_yoğunluk      = son duraklarda ölçülen bekleme, normale göre fazlası
Δ_olay          = güzergâhta kaza/duyuru varsa ek süre
```

Modelin değeri şurada: **her terim ayrı ölçüldüğü için mazeret cümlesi
kendiliğinden çıkıyor.**

```
Normal beklenti     8 dk   (6 durak × 1,3 dk)
+ Trafik           +3 dk   İBB indeksi 71, bu saatin normali 52
+ Araç yavaş       +2 dk   bu otobüs son 10 dk'da hattın %60 hızında
+ Durak beklemesi  +2 dk   son 3 durakta ortalamanın 2 katı bekledi
─────────────────────────
Tahmin             15 dk
```

Ekranda: **"15 dk. Normalde 8 dk sürerdi — 3 dk trafik, 2 dk aracın
yavaşlığı, 2 dk yoğun duraklar."**

Dört rakamın dördü de ölçülen veriden geliyor; jüri sorduğunda kaynağı
gösterilebilir. MOBİETT'in yapamadığı tam olarak bu.

**Ek öneri — güven aralığı.** Arşivdeki süre yayılımı zaten ölçülü.
"15 dk" yerine **"15 dk (12–21 arası)"** demek hem daha dürüst, hem
tahmin tutmadığında kullanıcıyı kaybetmiyor.

---

## 5. Bilinen sınırlar

- Saha doğrulaması **4 ölçüm, tek hat, gece saati**. Aynı veriyle hem hata
  bulundu hem düzeltme doğrulandı — bu döngüsel; bağımsız test gerekli.
- Hat katsayısı günlük medyan, **saat kırılımı yok**. Sabah/akşam zirvesi için
  ayrı katsayı gerekiyor. Veri hazır (arşivde saat bilgisi var).
- Durak beklemesi **sabit 0,50 dk**. Yolcu yoğunluğuna göre değişmeli.
- İBB TrafficIndex **şehir geneli tek sayı**. Kadıköy'deki ve Beylikdüzü'ndeki
  otobüs neredeyse aynı katsayıyı alıyor. Nokta bazlı trafik için TomTom
  anahtarı gerekiyor (ücretsiz katman 2.500 istek/gün).
- Test aracının örnekleme boşluğu: 50 sn'de bir yoklama, metrobüs 50 sn'de
  500–970 m gidiyor → 150 m'lik varış penceresi atlanabiliyor.

---

## 6. Kritik operasyonel uyarı

`FiloDurum/SeferGerceklesme.asmx` **saatte 100 istek** ile sınırlı (dokümante).
Aşılınca çalışan metotlar da `Policy Falsified` döner — yetki hatasıyla
**aynı mesaj**, karıştırmak kolay.

Panelin 120 saniyelik yoklaması tek başına saatte 30 istek. Sunum günü
birkaç kişi haritayı kurcalarsa canlı otobüsler kaybolur.

**Mimari kural: kullanıcı başına canlı çağrı yapılmaz.** Tek merkezi
yoklayıcı çeker, herkes cache'ten okur. Böylece 3 kişi de 300 kişi de
aynı kotayı tüketir.
