# Ekip Özeti — Nerede Kaldık, Ne Öneriyorum

*27 Temmuz Pazartesi · sunuma 5 gün*

---

## 1. Projenin şu anki hâli

Staj panelinden bağımsız bir kopya çıkardık. İçinde İETT'nin canlı
servislerine bağlı **38 uç** ve üç çalışan sayfa var:

- **Operasyon haritası** — canlı otobüs konumu, durak listesi, güzergâh,
  durağa varış tahmini, trafik katmanı, duyurular
- **Yol tarifi** — durak/adres/koordinattan rota; direkt ve 1–3 aktarmalı
  seçenekler, harita üzerinde çizim
- **Analiz** — planlanan vs gerçekleşen sefer süresi, hat gecikme skorları,
  filo yükü

Kimlik bilgileri koda gömülü değil, Datathon'un eski verileri temizlendi,
proje tek başına ayakta duruyor.

### Bu hafta ETA motorunda 5 hata bulup düzelttik

Mehmet "Otobüsüm Nerede" ile karşılaştırınca tahminlerimizin tutmadığını
fark etti. Kazınca beş ayrı hata çıktı:

1. **Trafik iki kez sayılıyordu** — yoğun saatte tahmin %31'e kadar şişiyordu
2. **Durak sayısı hesaba hiç girmiyordu** — 2 durak ötedeki ve 12 durak
   ötedeki otobüse aynı süre veriliyordu
3. **"Şu anki trafik" tam 24 saat eskiydi** — servis en yeni kaydı başta
   veriyor, kod sondakini alıyordu
4. **Otobüsün yön bilgisi yanlıştı** — ölçtük, etiketlerin yarısı hatalı.
   Durağa hiç gelmeyecek otobüsler için süre veriliyordu
5. **Park hâlindeki otobüse tahmin veriliyordu**

Sonuç, gerçek otobüsleri durağa varana kadar izleyerek ölçüldü:

| | Önce | Sonra |
|---|---|---|
| Tahmin doğruluğu | %46 | **%89** |
| Ortalama hata | 2,4 dk | **0,51 dk** |
| Durağa gerçekten varan otobüs oranı | 1/5 | **5/5** |

3 ve 4 numaralı hatalar staj panelinden miras kalmıştı — yani o panel de
uzun süredir yanlış veri gösteriyormuş.

### Ama ürünün kendisi henüz yok

Dürüst olalım: elimizde sağlam bir **altyapı** var, **ürün** yok.
Projenin adı "güvenilirlik" ama hâlâ "500T bu saatte %58 güvenilir" diyen
bir ekran mevcut değil. Hat karnesi, şehir paneli, güvenilirlik skoru —
hiçbiri yazılmadı. Kalan iki günün ana işi bu.

---

## 2. Elimizde ne var (hepsi test edildi, çalışıyor)

| Veri | Miktar |
|---|---|
| Canlı otobüs konumu | 6.911 araç, anlık |
| Sefer arşivi (planlanan vs gerçekleşen) | **44.000 sefer/gün** |
| Duraklar | **15.112** — koordinat, ilçe, erişilebilirlik, korunaklılık |
| Hatlar | 837 hat, 841 güzergâh çizgisi |
| Planlı sefer saatleri | GTFS, 135.000 sefer |
| Trafik indeksi | 5 dakikada bir, şehir geneli |
| Duyurular | Anlık, 72 aktif |
| İSPARK otoparkları | **252 otopark, canlı boş kapasite** |

Ayrıca ölçtüğümüz şeyler: her hattın gerçek sefer süresi, iptal oranı
(**şebeke geneli %4,03**, hat bazında %0–58,3), saatlik trafik normali.

---

## 3. Yeni fikir: Erişilebilirlik + Yolcu Geri Bildirimi

### Fikir

Herkeste İstanbulkart var. Uygulamada geçmiş yolculuklarını görsün,
oradan puanlasın: otobüs temiz miydi, şoför nasıldı, durak kullanılabilir
miydi. Şikâyet Şikayetvar'a değil **kuruma** gitsin. Kurum kusurunu
içeriden öğrensin, kamuoyunda karalanmasın.

*(Not: Akbil entegrasyonu Belbim'in izniyle olur, biz konsept olarak
mock veriyle göstereceğiz.)*

### Neden güçlü — üç sebep

**1. Sıfır sürtünme.** Kayıt yok, şifre yok. Kart zaten kimlik.

**2. Bağlamlı geri bildirim.** Şikayetvar'da insan boşlukta yazıyor.
Burada hangi hat, hangi durak, saat kaçta, ne kadar sürdü — hepsi belli.
Yani şikâyet **işlenebilir veri** oluyor.

**3. Hacim.** En yoğun 50 hatta günde **945.219 yolculuk** var (ölçtük).
Yolculukların sadece %1'i puanlasa:

> **günde 9.452 · yılda 3,4 milyon geri bildirim**

Bir anket firması yılda birkaç bin kişiye ulaşır. Kurum anket parası
ödemeden, sürekli ve bağlamlı veri toplar.

### Ve şu kısmı bugün gerçek veriyle yapabiliyoruz

Engelli erişimi için Akbil'e gerek yok — İETT bu veriyi zaten veriyor.
Ölçtük:

> **İstanbul'un 15.112 otobüs durağının sadece 853'ü (%5,6)
> engelli erişimine uygun.**

İlçelere göre:

```
Çekmeköy      %0,6          Fatih         %18,6
Sultanbeyli   %1,4          Beylikdüzü    %17,7
Sancaktepe    %1,5          Bayrampaşa    %15,0
Pendik        %2,1          Zeytinburnu   %13,5
Arnavutköy    %2,3          Eyüpsultan    %12,5
```

**Çekmeköy ile Fatih arasında 31 kat fark.**

Bunun neden önemli olduğunu özellikle söylemek istiyorum: güvenilirlik
skorlarında "eşitsizlik" hikâyesi **çıkmadı** — orada en kötü ilçeler
Fatih, Beyoğlu, Şişli çıktı, yani merkez. Sebebi trafik yoğunluğu,
ihmal değil. O yüzden "aynı vergi, farklı hizmet" cümlesini oradan
kuramayız, veri bizi yalanlar.

**Ama erişilebilirlikte o hikâye gerçek.** Çünkü durağa rampa yapmak
trafiğe bağlı değil, **bütçe kararına** bağlı. Ve dağılım tam da çeper
ilçelerin aleyhine.

Bonus veriler: durakların %44,1'i korunaklı (yağmur), sadece %6,4'ü ekranlı.

### Sunumdaki cümle

> Bugün nerede erişilebilir durak olduğunu biliyoruz — %5,6.
> Yolculuk verisiyle engelli bireylerin **nereye gitmeye çalıştığını** da
> bilirdik. İkisinin arasındaki fark, yenileme öncelik listesidir.

Birincisi gerçek veri, bugün gösterilebilir. İkincisi konsept.

---

## 4. Yeni fikir: Karbon Ayak İzi + Hibrit Rota

### Fikir

Yol tarifinde üç seçenek olsun:

```
🚗 Araçla        →  45 dk · 22 km · 2,9 kg CO₂
🚌 Toplu taşıma  →  62 dk · 24 km · 0,6 kg CO₂
🔀 Hibrit        →  51 dk · 24 km · 1,1 kg CO₂
     Evden Kozyatağı İSPARK'a araçla 18 dk
     (şu an 118 yer boş)
     4 dk yürü → 34 metrobüs → 29 dk
```

### Neden yapılabilir

Kontrol ettik, gerekli her şey hazır:

- **İSPARK API'si açık**, kimlik gerekmiyor: 252 otopark
- **Canlı boş kapasite veriyor** — şu an 81.366 kapasitede 35.597 boş.
  "Şu an 118 yer boş" diyebilmek, statik otopark listesinden bambaşka
- Araç rotası için OSRM zaten entegre
- Toplu taşıma rotası zaten çalışıyor

Yani sıfırdan bir şey yazmıyoruz, iki mevcut yeteneği zincirliyoruz.
Tahminimiz **1,5 gün**.

### Dikkat

Karbon katsayılarını uydurmayacağız, kaynağını slaytta göstereceğiz.
Türkiye'nin elektrik şebekesi Avrupa'dan daha karbon yoğun; metro için
AB rakamlarını kopyalamak yanlış olur. Jüri "bu sayı nereden?" diye sorar.

---

## 5. Önerim — kalan iki gün

```
SALI  sabah    ETA'yı bitir (iptal, duyuru, kaza katmanlarını bağla)
SALI  öğleden  GÜVENİLİRLİK SKORU + HAT KARNESİ    ← ürünün kalbi
SALI  akşam    Erişilebilirlik haritası (2 saat, veri hazır)
ÇARŞ  tam gün  Karbon + hibrit rota
PERŞ           Entegrasyon, uçtan uca test → FEATURE FREEZE
PERŞ  gece     Akbil vizyonu için mock ekranlar
CUMA           Slaytlar, yedek demo videosu, 2 kez prova
CMT            Sunum
```

**Şehir paneli (ilçe ısı haritası) roadmap slaydına gidiyor.** Verisi
hazır ama anlatısı riskli (yukarıda anlattığım eşitlik meselesi), ve
karbon fikri daha özgün.

### Tartışmak istediğim iki şey

1. **Güvenilirlik skoru olmadan sunuma gidemeyiz.** Projenin adı bu.
   Salı öğleden sonrası buna ayrılmalı, pazarlıksız.

2. **Karbon mu, şehir paneli mi?** İkisi birden olmaz. Ben karbondan
   yanayım: canlı otopark verisiyle desteklenen, kimsenin yapmadığı bir
   şey. Ama tartışalım.

---

## 6. Bir uyarı — teknik ama herkesi ilgilendiriyor

Canlı otobüs konumu veren servis **saatte 100 istekle** sınırlı.
Test yaparken bu sınırı biz doldurduk ve servis çalışmayı kesti.

Sunum günü salonda birkaç kişi haritayı kurcalarsa **canlı otobüsler
kaybolur.** Bunu önlemek için mimariyi şöyle kurmalıyız: tek merkezi
yoklayıcı veriyi çeker, herkes hafızadan okur. Böylece 3 kişi de
300 kişi de aynı kotayı tüketir.

Ayrıca **yedek demo videosu zorunlu.** Canlı demo çökerse elimizde
bir şey olsun.


---

# GÜNCELLEME — 31 Temmuz 2026 gecesi

Sunuma **1 gün** kaldı. Son durum:

## Biten işler

**🏅 Güvenilirlik skoru + Hat Karnesi — projenin adını taşıyan özellik artık var.**
`45 × süre_tutarlılığı + 30 × sefer_gerçekleşme + 25 × düzenlilik`.
732 hat puanlandı (ortalama 64,2 · aralık 5,4–100 · A=75 B=230 C=228 D=117 E=82).
Her hat için "bu hat neden bu puanı aldı" açıklaması sayılara dayalı yazılıyor.

**🚇 Metrobüs artık kullanılıyor.** İki sebepten hiç çıkmıyordu: havuz yarıçapı
metrobüs istasyonunu 10 metreyle kaçırıyordu (0,80 km eşik, istasyon 0,81 km)
ve metrobüs grafikte adaydı (istasyonların kendi durak kodu var, aktarma
kurulamıyordu). İkisi de düzeltildi:
Avcılar→Zincirlikuyu **121 → 55 dk**, Bakırköy→Üsküdar **160 → 81 dk**.

**🧭 Yön artık kesin.** Servisin `YON` + `SIRANO` verisini kullanıyoruz,
geometriden çıkarım yapmıyoruz. Bu, gerçek bir hatayı ortaya çıkardı:
planlayıcı metrobüste **dönüş peronunda bindirip gidiş peronunda indiriyordu**
(fiziksel olarak imkânsız). 837 hat kapsanıyor, eksik 0.

**🌱 Karbon.** Araç/toplu/hibrit karşılaştırması, İSPARK park-and-ride, moda
göre filtreli harita. Emisyon araç tipine göre ayrıştırıldı (solo 800 /
körüklü 1.120 gCO₂/araç-km) — filo oranıyla harmanlanınca ölçülen 918'i
%0,16 farkla veriyor.

**Profil + Geçmiş Seferler (konsept).** Temsilî yolculuklar bağlamıyla
değerlendirilir. Ücretsiz biniş vaadi yoktur; aynı hedef ve konuda en az üç
işlenebilir kayıt kurum görünümünde doğrulanacak inceleme adayı oluşturur.

**❌ Analiz sekmesi kaldırıldı** — ürün yönüyle uyumsuzdu.

## Sunumda dikkat

1. **Raylı sistem eklendi.** Metro, Marmaray, T1/T3/T4, F1/F2/F3 ve TF1/TF2
   planlı GTFS ağıyla hesaplanıyor; canlı raylı araç konumu gibi sunulmuyor.
   Kaynak paket yeni uzatmaların gerisinde kalabilir; bunu dürüstçe söyleyelim.
2. **Kota.** `FiloDurum` saatte 100 istek. Salonda birkaç kişi aynı anda
   kurcalarsa canlı araçlar kaybolur. Demo öncesi test sorgusu yapmayın.
3. **ETA doğruluğu %84**, eski belgede yazan %93,2 değil. 45.102 gerçek
   seferle yeniden ölçüldü, medyan oran 0,998 tutuyor ama ±%20 kapsaması
   %84 çıktı. Slaytta %84 yazalım.

## Doğrulama özeti

37/37 uç · 72/72 karbon kontrolü · ilk sıradaki rotalarda ters segment 0 ·
geometri ihlali 0 · 50 km/s üstü segment 0 · konsol temiz.
