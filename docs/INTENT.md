# Erişilebilir İstanbul — İlk Ürün Notları

> **Arşiv notu:** Bu dosya ilk fikirleri ve geçmiş kararları korur. Kart
> türünden engellilik çıkarımı, otomatik iş emri ve biniş ödülü güncel üründen
> çıkarılmıştır. Uygulanan kararların tek kaynağı `URUN_MANTIGI.md` dosyasıdır.

**Bu proje ne, neden var, neye göre karar veriyoruz**

> Ad, ürünün en ayırt edici iddiasını taşıyor: erişilebilirlik.
> Hem fiziksel anlamda (engelli bireyler için kullanılabilir duraklar),
> hem bilgi anlamında (ne zaman geleceğini ve neden geciktiğini bilmek).

> Tech İstanbul İnovasyon Yaz Kampı · 4 kişilik ekip · Sunum: 1 Ağustos 2026
>
> Bu doküman projenin **pusulası**. Bir karar tartışmalı hâle gelirse buraya
> bakılır. Kod değişir, buradaki gerekçeler kalır.

---

## 1. Kimlik — bu ürün kimin, kime hitap ediyor

**İETT'nin vatandaş uygulaması.** Kurumun kendi resmî uygulaması olarak
konumlanır; MOBİETT / "Otobüsüm Nerede" yerine geçmeyi hedefler.

Bu karar dokümanın her satırını etkiliyor, o yüzden baştan net olsun:

- Uygulamada konuşan ses **kurumun sesi**. "Bize bildirin" diyoruz,
  "onlara iletiriz" demiyoruz.
- Geri bildirim doğrudan kuruma akar — çünkü uygulama zaten kurumun.
  Araya üçüncü bir taraf girmiyor.
- Erişilebilirlik bildirimi bir dış talep değil, **iç iş emri**.
- Bu yüzden "Şikayetvar'da karalanmak yerine kendi göbeğimizi kendimiz
  kesmek" cümlesi anlamlı: şikâyet kamuya değil, ilgili birime düşüyor.

---

## 2. Problem

İstanbullunun ulaşımdan beklentisi büyük vizyon değil, **öngörülebilirlik**.
Şikâyetler hep aynı yere çıkıyor:

> *"20 dakika bekledim gelmedi"* · *"1 dk diyor, 10 dk bekledik"*
> *"sefer iptal duyurusu gelmiyor"* · *"otobüs durakta durmadan geçti"*

İnsanlar otobüsün **nerede** olduğunu değil, **ne zaman geleceğini ve
neden gelmediğini** bilmek istiyor.

Mevcut resmî uygulamalar anlık konum yarışına girmiş ve kaybediyor.
Bunu varsaymadık, **ölçtük**: aynı altyapı üzerine kurulu bir panelde beş
ayrı hesap hatası bulduk. İkisi — 24 saat eski trafik verisi ve yanlış yön
etiketi — tahminleri sistematik olarak bozuyordu. Yani "nerede" sorusu
göründüğünden çok daha zor.

---

## 3. Ürünün tek cümlelik özü

> **Sana otobüsün nerede olduğunu değil, hattına güvenip
> güvenemeyeceğini ve neden güvenmediğini söylüyoruz.**

Dört farklılaşma ekseni:

| | |
|---|---|
| **Güvenilirlik** | Geçmişe dayalı, ölçülmüş skor |
| **Açıklanabilirlik** | Sayı değil, gerekçe |
| **Sürdürülebilirlik** | Karbon ayak izi + hibrit rota |
| **Kapsayıcılık** | Erişilebilirlik ve geri bildirim döngüsü |

---

## 4. ŞU AN ÇALIŞAN KISIM

Hepsi canlı İETT servislerine bağlı, test edildi.

### 4.1 Harita ve canlı takip
- Anlık araç konumları çekiliyor (6.911 araç, şebeke geneli)
- Durağa varış süresi (ETA) hesaplanıyor ve gösteriliyor
- Hareket saatleri, güzergâh çizgisi, trafik verisi yolcuya sunuluyor
- Duraklar ve garajlar haritada
- Duyurular anlık olarak yansıtılıyor

### 4.2 "Nasıl giderim"
Biniş ve iniş durağı girilince sistem hesaplıyor:
- Hangi otobüse binileceği
- Durakta kaç dakika bekleneceği
- Yolun trafik dahil kaç dakika süreceği
- Kaç aktarma yapılacağı
- İndikten sonra bir sonraki aracın kaç dakika bekleneceği

Direkt, 1, 2 ve 3 aktarmalı seçenekler üretiliyor; rota harita üzerinde
çiziliyor.

### 4.3 Analiz
- Planlanan vs gerçekleşen sefer süresi
- Hat bazlı gecikme skorları
- Filo yükü (araç başına çalışma süresi)

### 4.4 Bu hafta düzeltilen beş hata

ETA motoru "Otobüsüm Nerede" ile karşılaştırılınca tutmadığı görüldü.
Kazınca beş ayrı hata çıktı:

| # | Hata | Etki |
|---|---|---|
| 1 | Trafik iki kez sayılıyordu | Yoğun saatte tahmin %31'e kadar şişiyordu |
| 2 | Durak sayısı hesaba girmiyordu | 2 ve 12 durak ötedeki otobüse aynı süre |
| 3 | "Şu anki trafik" 24 saat eskiydi | Servis en yeniyi başta veriyor, kod sondakini alıyordu |
| 4 | Yön etiketi yanlıştı | Etiketlerin ~yarısı hatalı; gelmeyecek otobüse süre veriliyordu |
| 5 | Park hâlindeki araca tahmin | Duran otobüse "33 dk" deniyordu |

Gerçek otobüsler durağa varana kadar izlenerek ölçüldü:

```
Tahmin doğruluğu              %46  →  %89
Ortalama hata               2,4 dk →  0,51 dk
Durağa gerçekten varan oran   1/5  →  5/5
```

3 ve 4 numaralı hatalar staj panelinden mirastı — yani o panel de uzun
süredir yanlış veri gösteriyormuş.

### 4.5 Henüz yapılmamış olan

Dürüst olalım: sağlam bir **altyapı** var, **ürün** yok. Projenin adı
"güvenilirlik" ama hâlâ *"500T bu saatte %58 güvenilir"* diyen bir ekran
mevcut değil. Güvenilirlik skoru ve hat karnesi kalan işin başında.

---

## 5. MODÜL 1 — İSPARK + Hibrit Rota + Karbon Ayak İzi

### Ne yapar

Yol tarifine iki seçenek eklenir: **otobüs** ve **hibrit**.

**Otobüs seçilirse** sistem şu anki gibi çalışır, üstüne yolculuğun karbon
ayak izini gösterir.

**Hibrit seçilirse** yolcu aracıyla evinden yola çıkar:
1. Sistem gideceği yere en uygun İSPARK'ı önerir
2. Araçla kaç dakika süreceğini ve ne kadar karbon bırakacağını hesaplar
3. Oradan otobüse bindirir, o kısmın karbonunu da hesaplar
4. Ekranda toplamı gösterir: **kaç dakikada varır, kaç km gider, toplam
   ne kadar karbon bırakır**

```
🚗 Araçla        45 dk · 22 km · 2,9 kg CO₂
🚌 Toplu taşıma  62 dk · 24 km · 0,6 kg CO₂
🔀 Hibrit        51 dk · 24 km · 1,1 kg CO₂
     Evden Kozyatağı İSPARK'a araçla 18 dk (şu an 118 yer boş)
     4 dk yürü → 34 metrobüs → 29 dk
```

### "En uygun İSPARK" nasıl seçilir

**Dengeli puanlama:** süre + karbon + o anki boş yer birlikte değerlendirilir.
Yalnızca süreye bakmak yolcuyu neredeyse hedefe kadar araçla götürür ve
karbon mesajını boşa çıkarır; yalnızca karbona bakmak makul olmayan uzun
rotalar önerir. Üçünü birlikte puanlıyoruz — ve **dolu otoparkı asla
önermiyoruz**, canlı veri elimizde olduğu için buna gerek yok.

### Neden yapılabilir

| İhtiyaç | Durum |
|---|---|
| İSPARK konumları | ✅ Açık API, kimlik gerekmiyor — 252 otopark |
| Otopark doluluğu | ✅ **Canlı boş kapasite** — 81.366 kapasite, 35.597 boş |
| Araç rotası + süresi | ✅ OSRM zaten entegre |
| Toplu taşıma rotası | ✅ Rota motoru çalışıyor |

Sıfırdan bir şey yazmıyoruz; iki mevcut yeteneği zincirliyoruz.

### Kural: karbon sayısı uydurulmaz

Katsayıların kaynağı slaytta gösterilir. Türkiye'nin elektrik şebekesi
Avrupa'dan daha karbon yoğun — metro için AB rakamlarını kopyalamak
yanıltıcı olur. Jüri "bu sayı nereden?" diye sorar, cevabımız hazır olmalı.

---

## 6. MODÜL 2 — Erişilebilirlik ve Otomatik Durak Bildirimi

### Ne yapar

Sistem kullanıcının engelli birey olduğunu **İstanbulkart kart tipinden**
tanır. Kullanıcı hiçbir şey beyan etmez, hiçbir form doldurmaz —
İstanbulkart'ın zaten engelli/65+/öğrenci kart tipleri var, uygulama
bunu okur.

> Bu, "kayıt yok, kart zaten kimlik" ilkesinin doğal sonucu. Erişilebilirlik
> desteği için kullanıcıdan engelini beyan etmesini istemek hem sürtünme
> yaratır hem incitici olabilir. Kart tipi bunu ortadan kaldırıyor.

Sonra sistem iki iş yapar:

**A) Kullanıcıyı uyarır — ama rotadan çıkarmaz**

Durak erişilebilir değilse yolcuya uyarı gösterilir, o durak rotadan
silinmez.

> **Neden çıkarmıyoruz:** İstanbul'daki durakların yalnızca %5,6'sı
> erişilebilir. Erişilemez durakları rotadan elesek çoğu yolculuk
> **hiç sonuç vermezdi**. Kullanıcıyı seçeneksiz bırakmak, uyarmaktan
> kötüdür. Karar yolcunun: belki refakatçisi vardır, belki o durağı
> zaten biliyordur.

**B) Kuruma bildirir ve veriyi biriktirir**

Bildirim **İETT Bilgi İşlem Dairesi**'ne düşer ve **doğrudan orada işlenir**
— araya yönlendirme katmanı girmez. Ayrıca İETT bu veriyi kendi
veritabanında tutar: engelli bireylerin **sık kullandığı** duraklar
işaretlenir ve yenileme listesine alınır.

**Eşik:** bir durağı **günde 10+ farklı engelli birey** düzenli olarak
kullanıyorsa ve durak erişilebilir değilse, otomatik olarak yenileme
listesine girer.

> Eşiğin amacı gürültüyü elemek. Tek bir kullanıcının bir kez uğradığı
> durak için iş emri açmak listeyi anlamsızlaştırır. "Düzenli ve çok
> kişi" ölçütü, yenilemenin gerçekten karşılığı olan duraklara
> odaklanmayı sağlar.

Zamanla biriken veri **yenileme öncelik listesi** hâline gelir: engelli
bireylerin fiilen kullandığı ama erişilebilir olmayan duraklar, kullanım
yoğunluğuna göre sıralanır. Bugün böyle bir liste yok — hangi durağın
yenileneceği talebe göre değil, başka ölçütlere göre belirleniyor.

**Bu, ürünün en somut kurumsal katkısı:** bütçe zaten harcanıyor, biz
sadece *nereye* harcanacağını veriye bağlıyoruz.

### Veri zaten elimizde

İETT bu bilgiyi kendi servisinden veriyor. Ölçtük:

> **İstanbul'daki 15.112 otobüs durağının sadece 853'ü (%5,6)
> engelli erişimine uygun.**

```
Çekmeköy      %0,6          Fatih         %18,6
Sultanbeyli   %1,4          Beylikdüzü    %17,7
Sancaktepe    %1,5          Bayrampaşa    %15,0
Şile          %1,7          Zeytinburnu   %13,5
Pendik        %2,1          Eyüpsultan    %12,5
Arnavutköy    %2,3
```

**Çekmeköy ile Fatih arasında 31 kat fark.** Ortada gerçek bir sorun var
ve kimse ölçmüyor.

Yan veriler: durakların %44,1'i korunaklı (yağmur), sadece %6,4'ü ekranlı.

### Neden eşitlik anlatısı buraya taşındı

Bu, projenin en önemli editoryal kararı ve gerekçesi kaydedilmeli.

"Aynı belediye, aynı vergi, farklı kentli deneyimi" cümlesini önce
**güvenilirlik skorlarıyla** kurmayı denedik. Veri tam tersini söyledi:
en düşük skorlu ilçeler Fatih, Beyoğlu, Şişli çıktı — yani merkez.
Sebebi ihmal değil trafik yoğunluğu. O anlatıyı **bıraktık**.

**Erişilebilirlikte aynı iddia gerçek.** Çünkü durağa rampa yapmak
trafiğe bağlı değil, **bütçe kararına** bağlı. Ve dağılım tam da çeper
ilçelerin aleyhine.

---

## 7. MODÜL 3 — Geri Bildirim, Anket ve Teşvik

### Ne yapar

Yolcu geçmiş seferlerini görür ve oradan puanlar: otobüsün eksikleri
neydi, iyi yanları neydi. Veriyi kurum kendisi toplar.

**Neden değerli — üç sebep:**

**1. Sıfır sürtünme.** Herkeste zaten İstanbulkart var. Kayıt yok, şifre
yok, form yok. Kart kendisi kimlik.

**2. Bağlamlı geri bildirim.** Şikayetvar'da insan boşlukta yazıyor.
Burada hangi hat, hangi durak, saat kaçta, ne kadar sürdü — hepsi belli.
Şikâyet serbest metin olmaktan çıkıp **işlenebilir veri** oluyor.

**3. Hacim.** En yoğun 50 hatta günde **945.219 yolculuk** var (ölçüldü).
Yolculukların %1'i puanlasa:

> **günde 9.452 · yılda 3,4 milyon geri bildirim**

Bir anket firması yılda birkaç bin kişiye ulaşır. Kurum üçüncü şirketlere
anket parası ödemeden, sürekli ve bağlamlı veri toplar. Ve sorun kamuoyunda
karalanmadan **içeriden** öğrenilir.

### Ne puanlanır — dört ayrı hedef

Bir yolculukta dört farklı şey değerlendirilir, **ayrı ayrı**:

| Hedef | Örnek |
|---|---|
| **Hat** | Sefer sıklığı yetersiz, saatler tutmuyor |
| **Araç** | Klima çalışmıyor, temiz değil, kalabalık |
| **Durak** | Aydınlatma yok, korunaksız, erişilemez |
| **Şoför** | Durakta durmadı, agresif sürüş / nazikti, yardımcı oldu |

Ayrıca her biri için **serbest yorum** yazılabilir.

> **Neden ayrı:** araç kirliyse hattın puanı düşmemeli, şoför kabaysa
> durak suçlanmamalı. Tek bir "yolculuk puanı" hangi sorunun nerede
> olduğunu gizler — ve kurum için işe yaramaz hâle gelir.

### AI katmanı — hacmi anlamlı kılan şey

Serbest yorumları arka planda bir **yapay zekâ katmanı** işler:

1. **Sınıflandırır** — yorum hangi konuya ait (temizlik, klima, şoför
   davranışı, sefer sıklığı, durak fiziksel durumu, erişilebilirlik…)
2. **Gruplar** — aynı sorunu anlatan yüzlerce yorumu tek başlık altında
   toplar
3. **Önceliklendirir** — hacme ve tekrar sıklığına göre sıralar
4. **Kuruma bildirir** — İETT'ye özet rapor olarak düşer

**Bu katman fikrin işleyip işlememesini belirliyor.** Günde 9.452 geri
bildirim, yılda 3,4 milyon yorum demek. Hiçbir insan ekibi bunu okuyamaz —
okunamayan veri gürültüdür, veri değil. AI sınıflandırma olmadan hacim
avantaj değil yük olur.

Sınıflandırılmış hâliyle ise şu cümle kurulabilir:

> *"Bu ay 34 hattında 'klima çalışmıyor' konulu 1.240 bildirim geldi,
> %78'i M3xxx serisi araçlardan."*

Bu, bir anket raporunun asla veremeyeceği çözünürlükte bir bilgi.

### Sunumda nasıl gösterilecek — mock

AI sınıflandırma **mock ekran** olarak gösterilecek: hazırlanmış örnek
yorumlar ve bunların gruplanmış hâli, temsilî çıktı olarak sunulur.

**Neden mock:** kalan sürede güvenilirlik skoru, karbon/hibrit rota ve
erişilebilirlik katmanı yazılacak. Sınıflandırma motorunu canlıya almak
yarım gün daha götürürdü ve o süre skordan çalınırdı. Skor projenin adını
taşıyor, sınıflandırma ise fikrin destekleyici parçası.

Sunumda dürüst cümle: *"Bu ekran konsept — sınıflandırma mantığını
gösteriyoruz, motoru sonraki sürümde canlıya alıyoruz."*

### Teşvik

Katılımı artırmak için kampanya: **10 geçerli değerlendirme ver, 1 ücretsiz
biniş kazan.**

**Maliyeti kurum karşılar.** Ekonomik gerekçe savunulabilir: üçüncü
şirketlere ödenen anket bedeli ortadan kalkıyor, karşılığında ücretsiz
biniş veriliyor. Kurum aynı parayla, anketten kat kat fazla ve sürekli
veri topluyor — üstelik veri kurumun kendi elinde kalıyor.

### Tasarım notları (uygulanırken dikkat)

- **Seçilim yanlılığı:** sadece kızgın olan puan verir. Karşı önlem: tek
  dokunuşla puanlama, kapalı uçlu sorular, herkese sorulması.
- **Karşılık göster:** kullanıcı katkı verdiği veriden faydalanmalı —
  "senin hattın 68/100, 1.240 kişi puanladı".
- **Görünür sonuç:** "söyledin, şunu yaptık" döngüsü yoksa insanlar bırakır.
- **Teşvik suistimali:** ödül bildirim *sayısına* bağlıysa insanlar
  boş bildirim üretir. Ödül, **işlenebilir** bildirime bağlanmalı.

---

## 8. Tasarım ilkeleri

Bunlar süsleme değil. Her biri bu projede **yanlış çıkmış bir varsayımın**
sonucu olarak yazıldı.

### İlke 1 — Ölçmeden iddia etme
Her sayı canlı API'den ya da sefer arşivinden gelir.
*Neden:* İlk skor formülü dakiklik üzerine kuruluydu. Ölçtük — hatların
**%92,3'ü ±3 dk toleransta zamanında**. Formül bütün hatlara ~95 puan
verirdi, hiçbir şeyi ayırt etmezdi.

### İlke 2 — Veri anlatıyı belirler, anlatı veriyi değil
*Neden:* Bkz. bölüm 6 — eşitlik anlatısının taşınması.

### İlke 3 — Bilinmiyorsa gösterme
Emin olmadığımız bilgiyi kullanıcıya vermeyiz. Boş bırakmak, yanlış
söylemekten iyidir.
*Neden:* Yön etiketi güvenilmez çıktı; durağa hiç gelmeyecek otobüsler için
"1 dakika" yazıyorduk. Artık yön hareketten türetiliyor, karar verilemezse
**araç listelenmiyor**. Park hâlindeki araca kesin süre verilmiyor.

### İlke 4 — Tahminle birlikte gerekçe
```
Normal beklenti    8 dk
+ Trafik          +3 dk   İBB indeksi 71, bu saatin normali 52
+ Araç yavaş      +2 dk   son 10 dk'da hattın %60 hızında
+ Durak beklemesi +2 dk   son 3 durakta normalin 2 katı
─────────────────────────
Tahmin           15 dk
```
*Neden:* Memnuniyetsizliğin kaynağı gecikme değil **bilinmezlik**. Ayrıca
her terim ayrı ölçüldüğü için sayının arkasında durabiliyoruz.

### İlke 5 — Kullanıcıdan bilgi isteme, zaten bildiğini kullan
Engelli olduğunu sorma, kart tipinden anla. Hesap açtırma, kartı kimlik
say. Anket gönderme, yaptığı yolculuğu sor.

### İlke 6 — Dürüst sınıflandırma
Demoda gösterilen her şey üç kutudan birine girer ve bu **açıkça söylenir**:
çalışıyor / sınırlı / konsept.
*Neden:* "Her şey çalışıyor" demek, "mimari planlandı, MVP şu kadarını
gösteriyor, yol haritası net" demekten daha az ikna edici.

---

## 9. Sunum kapsamı — ne gerçek, ne konsept

> ⚠️ **Doğrulanacak:** Aşağıdaki dağılım son konuşmadan çıkarıldı;
> yalnızca "kurum paneli → mock" açıkça onaylandı. Diğerleri ekipçe
> teyit edilmeli.

| Modül | Sınıf | Not |
|---|---|---|
| Harita, canlı takip, ETA | **Çalışıyor** | Canlı veri |
| Nasıl giderim (rota) | **Çalışıyor** | Canlı veri |
| Karbon + hibrit rota | **Çalışıyor** *(hedef)* | İSPARK canlı verisi, ~1,5 gün |
| Erişilebilirlik haritası | **Çalışıyor** *(hedef)* | Veri hazır, ~2 saat |
| Güvenilirlik skoru + hat karnesi | **Çalışıyor** *(hedef)* | Formül hazır, yazılacak |
| Akbil geçmiş yolculuk + anket | **Konsept** | Mock ekran, temsilî veri |
| AI yorum sınıflandırma | **Konsept** | Mock ekran — motor sonraki sürümde |
| Kuruma giden bildirim paneli | **Konsept** | Mock ekran ✅ onaylandı |
| Teşvik kampanyası | **Konsept** | Mock ekran |
| Şehir paneli (ilçe ısı haritası) | **Roadmap** | Verisi hazır, anlatısı riskli |
| Tüm 837 hatta ML | **Roadmap** | — |

### Yapmayacaklarımız
- Anlık konum doğruluğunda MOBİETT ile yarışmak
- Ölçmediğimiz bir sayıyı sunumda kullanmak
- Kullanıcıdan İstanbulkart şifresi veya engel beyanı istemek
- Mock ekranı "çalışıyor" gibi göstermek

---

## 10. Kanıt defteri — hangi karar neye dayanıyor

| Karar | Ölçüm |
|---|---|
| Skor dakiklikten kurulmaz | ±3 dk'da %92,3 zamanında — ayırt etmiyor |
| Skor süre tutarlılığından kurulur | (p90−p10)/medyan: %9,8 – %197,9 arası dağılım |
| İptal skora girer | Şebeke %3,97, hat bazında %0 – %29,6 |
| ETA'da durak sayısı kullanılır | Doğruluk %46 → %89 (farklı günde test) |
| Trafik tek kez uygulanır | Çift sayım yoğun trafikte +%31 hata |
| Yön hareketten türetilir | Etiket örneklemde %50 hatalı; sahada 1/5 → 5/5 |
| Eşitlik anlatısı erişilebilirlikten kurulur | Çekmeköy %0,6 ↔ Fatih %18,6 (31 kat) |
| Karbon fikri şehir paneline tercih edilir | İSPARK 252 otopark, canlı boş kapasite |
| Geri bildirim hacmi anketi yener | Günde 945.219 yolculuk, %1'i = günde 9.452 |
| Kullanıcı başına canlı API çağrısı yapılmaz | Servis saatte 100 istek; testte kotayı doldurup servisi kestik |

---

## 11. Karara bağlananlar

| Soru | Karar |
|---|---|
| Ürün adı | **Erişilebilir İstanbul** |
| Ürünün muhatabı | İETT'nin resmî vatandaş uygulaması |
| Engelli tanıma | İstanbulkart **kart tipinden** — beyan istenmez |
| Erişilemez durak | **Uyarı verilir, rotadan çıkarılmaz** |
| Sık kullanılan erişilemez duraklar | İETT veritabanında tutulur, yenileme listesine alınır |
| Bildirim muhatabı | **İETT Bilgi İşlem Dairesi** |
| Puanlama hedefi | **Hat, araç, durak, şoför — dördü ayrı** + serbest yorum |
| Yorum işleme | **AI sınıflandırır, gruplar, önceliklendirir, kuruma bildirir** |
| Teşvik finansmanı | **Kurum karşılar** (anket bedelinden tasarruf) |
| Hibrit İSPARK seçimi | Dengeli: süre + karbon + canlı boş yer |
| Bildirim akışı | Bilgi İşlem **doğrudan işler**, yönlendirme yok |
| AI sınıflandırma | **Mock ekran** — süre kısıtı, skor önceliklendirildi |
| Yenileme eşiği | Günde **10+ farklı engelli birey** düzenli kullanıyorsa |

**Açık soru kalmadı. Ürün tanımı kapandı.**

---

## 12. Başarı ölçütü

**Kamp için:** Jüri karşısında gösterdiğimiz her sayının kaynağını
söyleyebilmek. Çalışan bir demo + dürüst bir kapsam beyanı + net bir yol
haritası.

**Ürün olarak:** Kullanıcının *"bu uygulama bana doğru söylüyor"* demesi.
Bir kez yanlış otobüs gösterirsek bir daha açmaz — bu yüzden İlke 3
pazarlık konusu değil.

---

## 13. İlgili dokümanlar

| Doküman | İçerik |
|---|---|
| `ETA_MODELI.md` | Teşhis edilen 5 hata, 20 etki faktörü, hedef model |
| `ROADMAP.md` | Öncelik sırası ve takvim |
| `EKIBE_OZET.md` | Ekip içi durum özeti |
