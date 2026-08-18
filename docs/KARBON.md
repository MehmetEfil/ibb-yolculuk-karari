# Karbon Ayak İzi — Hesap Yöntemi ve Kaynaklar

> Bu doküman jüri sorusuna hazırlık içindir. Sunumda gösterilen her karbon
> sayısının nereden geldiği ve hangi girdilerin model varsayımı olduğu burada
> açıkça yazılıdır.

---

## 1. Katsayılar ve kaynakları

| Girdi | Değer | Kaynak |
|---|---|---|
| Dizel yakıt | **2,68 kg CO₂/litre** | IPCC 2006 Kılavuzu / US EPA standardı |
| Benzin | **2,27 kg CO₂/litre** | IPCC 2006 Kılavuzu |
| Türkiye elektrik şebekesi | **442 gCO₂e/kWh** | ETKB/EVÇED, 2022 |
| Metro enerji yoğunluğu | **0,10 kWh/yolcu-km** | Senaryo varsayımı ⚠️ |
| Marmaray enerji yoğunluğu | **0,06 kWh/yolcu-km** | Senaryo varsayımı ⚠️ |
| Tramvay/füniküler/teleferik | **Metro katsayısı vekil alınır** | İşletme enerji verisi yayımlanana kadar ⚠️ |
| **Otobüs** | **918 gCO₂/araç-km** | **İETT'nin kendi verisinden türetildi** — aşağıya bakın |
| Otomobil | **159 gCO₂/km** | 7,0 L/100km × 2,27 kg/L üzerinden türetildi ⚠️ |
| Yürüyüş | 0 | — |

---

## 2. Otobüs katsayısı nasıl türetildi

Genel bir "otobüs şu kadar kirletir" katsayısı kullanmak yerine **İETT'nin
kendi yakıt kayıtlarından** hesapladık:

```
Günlük yakıt tüketimi  :   356.979 litre   (GetAkarYakitToplamLitre_json)
Günlük araç-km         : 1.042.413 km      (arşivdeki tamamlanan seferler × hat uzunluğu)

918 gCO₂/araç-km = 356.979 L × 2,68 kg/L × 1000 ÷ 1.042.413 km
```

### Neden bu güvenilir — bağımsız doğrulama

Aynı iki sayı, tüketimi de veriyor:

```
356.979 L ÷ 1.042.413 km × 100 = 34,2 litre/100 km
```

Şehir otobüsünün tipik tüketimi **30–55 L/100km**. Çıkan değer bu aralığın
ortasında. Katsayı uydurulmuş olsaydı bu aralığa denk gelmesi tesadüf olurdu.

### Kişi başına çevirme

Otobüsün toplam emisyonu **araçtaki yolcu sayısına** bölünür — dolu otobüste
kişi başı emisyon düşer. Toplu taşımanın avantajı buradan gelir.

```
kişi_başı = 918 × km ÷ (hat_kapasitesi × doluluk)
```

**Doluluk canlı veriden okunur** (`/api/yogunluk`) — ölçüm anında örneğin
34A hattı %85, 130Ş %48. Ölçüm yoksa %40 varsayılıyor.

Ortaya çıkan değerler **25–28 gCO₂/yolcu-km** aralığında; yayımlanmış otobüs
figürleri (25–40) ile örtüşüyor. İkinci bağımsız doğrulama.

### Raylı sistem hesabı

GTFS paketi hat, istasyon ve planlı süreyi verir; trenlerin gerçek enerji
tüketimini vermez. Bu nedenle Metro için 0,10, Marmaray için 0,06
kWh/yolcu-km birer **senaryo varsayımıdır**. Şebeke katsayısıyla çarpılır:

```
Metro    = km × 0,10 kWh/yolcu-km × 442 gCO₂e/kWh
Marmaray = km × 0,06 kWh/yolcu-km × 442 gCO₂e/kWh
```

Arayüz bu sonucu “tahmini CO₂” olarak gösterir. Tramvay, füniküler ve
teleferikte ayrı işletme enerji verisi bulunmadığından Metro senaryosu vekil
alınır. İBB/Metro İstanbul veya TCDD işletme bazlı enerji verisi yayımladığında
bu varsayımlar değiştirilmelidir.

---

## 3. Araç süresi neden OSRM'in verdiği gibi değil

OSRM **serbest akış** süresi verir, trafiği bilmez. Ham kullanılsa Avcılar →
Kadıköy 37 dakika görünüyordu ve araba haksız yere cazip çıkıyordu.

Buna **mutlak tıkanıklık katsayısı** uyguluyoruz — ve bu da uydurulmadı,
440.000 gerçek İETT seferinden türetildi. Her saatin sefer süresi çarpanı,
günün en akıcı saatine (04:00) oranlandı:

```
04:00  1,00×  (serbest akış referansı)
08:00  1,22×
13:00  1,27×
17:00  1,42×  ← zirve
23:00  1,07×
```

Üstüne bir de anlık sapma (`_trafik_sapmasi`) çarpılıyor: o saat için trafik
normalden kötüyse ek yavaşlama.

**Sonuç:** araç ortalama hızı 38–42 km/s çıkıyor — İstanbul için gerçekçi.
Toplu taşıma 11–22 km/s.

> ⚠️ Bu katsayı otobüs verisinden türetildi. Otobüslerin bir kısmı özel şerit
> kullandığı için otomobil aslında daha fazla yavaşlar. Yani **1,42× muhafazakâr
> bir alt sınırdır**, arabayı olduğundan iyi gösterir — bizim aleyhimize hata.

---

## 4. Hibrit rota (park et — devam et)

### Otopark seçimi

İSPARK açık API'sinden otoparklar ve **anlık boş kapasite** alınıyor
(`api.ibb.gov.tr/ispark/Park`, kimlik gerekmez). Otopark ve boş yer sayısı
anlık değiştiği için arayüz sabit bir toplam iddiası taşımaz.

Aday filtresi:

- Resmî P+D tesisleri 5'ten az boş yeri varsa önerilmez.
- Normal İSPARK'lar da dinamik aktarma noktası olabilir; bunun için yol üstü
  olmaması, kapasitesinin en az 30 olması, en az 20 boş yer ve %30 boşluk
  oranı sağlaması gerekir.
- Dinamik adaydan toplu taşımaya başlangıç yürüyüşü 12 dakikayı geçemez.
- Otopark yolun **orta kısmında** olmalı: hedefe ilerleme oranı **0,25–0,70**
  arasında. Çok yakınsa araç bacağı işe yaramaz (yine baştan sona otobüs);
  çok uzaksa neredeyse hedefe kadar arabayla gidilir ve karbon avantajı kaybolur.
- Sapma sınırı: araç + toplu mesafesi, kuş uçuşunun **1,25 katını** geçemez

### Temsilî teşvik

MVP, İSPARK girişini 30 dakika içindeki İstanbulkart geçişiyle eşleşmiş gibi
gösterir. Teşvik yalnızca boşluğa göre verilmez:

```
teşvik puanı = %40 boş kapasite
              + %30 azaltılan araç kilometresi
              + %20 karbon farkı
              + %10 toplu taşımaya yakınlık
```

40–59 puan %10, 60–74 puan %20, 75–89 puan %30 ve 90+ puan %40 otopark
indirimi üretir. Buna sırasıyla 25, 50, 75 veya 100 mobilite puanı eşlik eder.
Bu yalnızca sunum akışıdır; ödeme ve bakiye hareketi üretmez.

### Dengeli puanlama

Süre, karbon ve doluluk riski aynı ölçeğe getirilerek birlikte değerlendirilir:

```
puan = 0,45 × (hibrit_süre / toplu_süre)
      + 0,35 × (hibrit_CO₂ / otomobil_CO₂)
      + 0,20 × (1 − boş_yer / kapasite)
```

### Hibrit her zaman gösterilmez

Yalnızca **gerçekten işe yarıyorsa** sunulur:

- Önce araca göre en az **%20 daha az karbonlu** olmalı; ayrıca
- Toplu taşımadan en az **%15 hızlı**, **veya** araca göre en az **%40 daha
  az karbonlu** olmalı.

Aksi hâlde kullanıcıyı boşuna arabaya bindirmiş oluruz. Erken sürümde sistem
Avcılar'da 6,6 km sürüp yine 149 dakika otobüs öneriyordu — toplam düz toplu
taşımadan kötüydü. Bu filtre onu engelliyor.

---

## 5. Doğrulama — 23 bağımsız kontrol

Aşağıdaki kontroller API çıktısındaki her sayıyı sıfırdan yeniden hesaplar.
⚠️ Bunları üreten `karbon_dogrula.py` betiği depoda **yok**; sayılar o günkü
çalıştırmadan alınmıştır. Kalıcı koruma `tests/test_karbon.py` ve
`tests/test_karbon_arac.py` dosyalarındadır (18 test, `pytest` ile koşar):

| Kontrol grubu | Sonuç |
|---|---|
| Katsayı türetmeleri yeniden üretiliyor mu | 3/3 ✓ |
| Araç CO₂ = km × 159 | ✓ |
| Araç süre = serbest × tıkanıklık | ✓ |
| Hibrit CO₂ = araç bacağı + toplu bacağı | ✓ |
| Hibrit km = bacakların toplamı | ✓ |
| Hibrit yalnızca işe yarıyorsa sunuluyor | ✓ |
| Kişi başı emisyon makul aralıkta | ✓ |
| Araç, toplu taşımadan kirli çıkıyor | ✓ |
| Sınır durumlar (boş girdi, geçersiz durak, aynı yer) | 4/4 ✓ |

**Toplam: 23 geçti / 0 kaldı**

Yanıt süresi: ortalama **4,4 saniye**.

---

## 6. Bilinen sınırlar — dürüstlük bölümü

Bunlar sunumda sorulursa cevabı hazır olsun:

1. **En zayıf halka: otomobil katsayısı.** 159 g/km, 7,0 L/100km varsayımına
   dayanıyor ve bu varsayımı resmî bir kaynaktan almadım. Türkiye filo
   ortalaması 6–9 L/100km aralığında olabilir → 136–204 g/km, yani **±%28**.
   Diğer her şey ölçüldü, bu tek girdi varsayım.
2. **CO₂ hesaplanıyor, CO₂e değil.** Metan ve N₂O dahil değil (birkaç yüzde).
3. **Tıkanıklık katsayısı otobüs verisinden**, otomobile özgü değil (muhafazakâr).
4. **Hibrit uygun P+D adaylarının 3'ünü deniyor** — ön puan filtresi sonrası. Küresel
   en iyi değil; her adayın ayrı rota hesabı gerektiği için performans sınırı.
5. **OSRM halka açık demo sunucusu** kullanılıyor. Sunum günü erişilemezse
   araç seçeneği düşer (kod kuş uçuşuna düşmüyor, seçeneği hiç göstermiyor).
6. **Hat ortalaması doluluk** kullanılıyor; binilen belirli otobüs boş ya da
   tıklım olabilir.

---

## 7. Uçlar

| Uç | Ne yapar |
|---|---|
| `/api/karbon_rota?nereden=&nereye=` | Üç seçenek: araç / toplu / hibrit — süre, km, CO₂ |
| `/api/ispark` | 252 otopark + anlık boş kapasite |
| `/api/ispark?lat=&lon=&n=` | Konuma en yakın otoparklar |

Yanıtta `kaynak` alanı katsayıları ve türetmelerini de döndürür — arayüz
bunu "bu sayı nereden?" bağlantısı olarak gösterebilir.

---

## 6. Araç bazlı emisyon — yakıt türüne göre

*(2 Ağustos 2026 eklendi)*

Yukarıdaki 918 / 800 / 1.120 değerleri filo ortalamasıdır ve yalnızca araç
**boyutunu** (solo/körüklü) ayırır. Oysa filo tek yakıtlı değil. Kendi
verimizde (`panel_data/smart_maintenance.json`, 3.509 araç):

| Yakıt | Araç | Pay |
|---|---|---|
| MOTORIN | 3.041 | %86,7 |
| **CNG** | **348** | **%9,9** |
| BİLİNMİYOR | 119 | %3,4 |
| ELEKTRİK | 1 | %0,03 |

Her 10 araçtan biri motorin yakmıyor. Veri ayrıca **marka ve model** taşıyor
(OTOKAR KENT 290LF, KARSAN AVANCITY CNG, MERCEDES CONECTO G…), yani önerilen
aracın ne olduğu biliniyor.

### Çarpanlar

Motorine göre oran, IPCC 2006 varsayılan CO₂ emisyon faktörlerinden
(enerji tabanlı):

```
motorin (gas/diesel oil)  74.100 kg CO₂/TJ
doğalgaz                  56.100 kg CO₂/TJ
                          56,1 / 74,1 = 0,757
```

⚠️ **Tek varsayım:** CNG motorları buji ateşlemeli; sıkıştırma ateşlemeli
dizele göre km başına daha çok enerji harcar. Yayımlanmış şehir otobüsü
karşılaştırmalarında bu fark **%15–20**. %17,5 alındı:

```
0,757 × 1,175 = 0,89   →  CNG otobüs, eşdeğer dizelden %11 daha az CO₂
```

Duyarlılık: enerji farkı %15 alınırsa çarpan 0,87 (dizelden %13 az),
%20 alınırsa 0,91 (%9 az). Yani sonuç bu varsayıma **zayıf** bağlı —
körüklü/solo 1,4 varsayımıyla aynı statüde.

**Elektrik:** şebeke faktörü 442 gCO₂e/kWh (ETKB/EVÇED 2022) × solo
e-otobüs tüketimi 1,2 kWh/km = **530 gCO₂/araç-km**. "Elektrikli = sıfır
emisyon" kestirmesi Türkiye şebekesi için yanlış olduğundan sıfır sayılmıyor.

Örnek (aynı boyut, solo):

| Araç | Yakıt | gCO₂/araç-km |
|---|---|---|
| AKIA ULTRA LF12 | MOTORIN | 800,0 |
| KARSAN AVANCITY CNG | CNG | 712,0 |
| MERCEDES CITARO 0530 | ELEKTRİK | 530,4 |

### ⚠️ Kapsam sınırı — dürüst rakam

Bakım veri seti **2025-H1** dönemine ait (`mevsim` alanı). Canlı filoyla
karşılaştırıldı: **6.911 canlı aracın yalnızca 397'si (%5,7)** bu sette var.
Yani araç bazlı hesap pratikte rotaların küçük bir kısmında devreye giriyor;
kalanında **doğrulanmış filo ortalaması** kullanılıyor.

Canlı alternatif denendi ve **kapalı**: `GetAracOzellikleriIETT_json`
erişimimiz olmayan 25 SOAP metodundan biri, her çağrıda HTTP 500 dönüyor.

**Bu sırada bulunan gerçek hata:** `get_arac_ozellik()` servis yanıt
vermediğinde `"yakit_tipi": "Dizel", "kapasite": 90` döndürüyordu — yani
uydurulmuş bir değeri gerçek veriymiş gibi sunuyordu. Servis her zaman 500
döndüğü için **her araç "Dizel" görünüyordu**, filonun %9,9'u CNG olmasına
rağmen. Artık bilinmeyen `"—"` olarak işaretleniyor ve `veri_var: False`
bayrağı ekleniyor; karbon hesabı bu uydurma değere değil, doğrulanmış filo
ortalamasına düşüyor.
