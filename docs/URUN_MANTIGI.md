# İETT Yolculuk Kararı — Güncel Ürün Mantığı

## Tek cümlelik ürün

Yolcuya yalnızca “nasıl giderim?” yanıtı vermekle kalmaz; süre, erişilebilirlik
ve tahmini emisyon arasında bilinçli seçim yaptırır, yolculuk sonrasındaki
bağlamsal geri bildirimi İETT için doğrulanabilir iyileştirme adayına çevirir.

## Neden tek bir ürün

Uygulamanın iki yüzü vardır, ancak veri döngüsü tektir:

1. Yolcu tek **Yolculuğum** ekranında canlı ağı görür; rota planlama soldan
   açılan yapışık panelde çalışır ve harita sağda açık kalır.
2. Rota üzerinde süre, tahmini CO₂ ve erişilebilirlik bilgisi açıklanır.
3. MVP'de “Yolculuk sonuna geç” sunum adımıyla süre, mesafe ve otomobile göre
   tahmini karbon farkı gösterilir.
4. Yolcu “sorunsuz tamamlandı” der veya evrensel bir sorun başlığı seçip yazar;
   hat, araç/sefer ve durak bağlamı otomatik eklenir.
5. Tekrarlanan bildirimler İBB ekranında doğrulanacak aday olarak gruplanır.
6. Kurumun doğruladığı iyileştirmeler ileride yolcu deneyimini güçlendirir.

Bu nedenle karbon, erişilebilirlik ve geri bildirim birbirinden kopuk üç
kampanya değildir. Aynı yolculuk kararının öncesi, sırası ve sonrasıdır.

## Vatandaş tarafı

### Yolculuğum

Canlı ağ ve rota planlama ayrı üst sekmeler değildir. Aynı yolculuk işinin iki
görünümüdür. Araç konumu, ETA, hareket saati, güzergâh, trafik, durak ve garaj
bilgisi canlı ağ görünümündedir.

### Rota karşılaştırması

- Toplu taşıma, özel araç ve uygun olduğunda İSPARK aktarmalı hibrit seçenek.
- İETT otobüs alternatiflerinin yanında, istasyona makul yürüme mesafesi
  varsa planlı Metro, Marmaray, tramvay, füniküler veya teleferik alternatifi
  gösterilir. Raylı bekleme süreleri açık GTFS sıklığından hesaplanır ve canlı
  veri gibi etiketlenmez.
- Süre, mesafe ve **tahmini** CO₂ birlikte gösterilir.
- Otomobil hesabı tek kişi ve benzinli araç varsayımını açıkça taşır.
- Hibrit seçenek her koşulda üretilmez. Araca göre en az %20 temiz olmalı;
  ayrıca toplu taşımadan %15 hızlı veya araca göre %40 temiz olmalıdır.
- Hibrit aday havuzu resmî **Park Et Devam Et** tesisleri ile başlar. Normal
  İSPARK'lar; yol üstü değilse, en az %30 boşsa, en az 20 boş yeri varsa ve
  toplu taşımaya yürüyüş 12 dakikayı geçmiyorsa **dinamik aktarma noktası**
  olarak havuza katılır.
- Otopark seçiminde mutlak boş yer değil, boş yer / kapasite oranı kullanılır.
- Sunum modunda İSPARK girişi ile 30 dakika içindeki İstanbulkart geçişi
  temsilî olarak eşleştirilir. Boş kapasite (%40), azaltılan araç kilometresi
  (%30), karbon farkı (%20) ve toplu taşımaya yakınlık (%10) birlikte 100
  üzerinden teşvik puanı üretir. Puan arttıkça %10–40 otopark indirimi ve
  25–100 mobilite puanı gösterilir. Gerçek ödeme veya bakiye entegrasyonu
  yapılmaz.

### Erişilebilirlik

- Kart tipinden veya profilden engellilik çıkarımı yapılmaz.
- İhtiyacı olan herkes bilgiyi Tercihler ekranından açabilir.
- Uygun olmayan durak rotadan otomatik silinmez; bilgi verilir ve seçim
  yolcuya bırakılır.
- Yolcunun açık eylemi olmadan kuruma kişisel bildirim gönderilmez.

### Yolculuk geri bildirimi

- Gerçek yolculuk takibi ve İstanbulkart entegrasyonu yoktur; MVP'de rota
  sonucuna sunum moduyla geçilir ve bağlam temsilîdir.
- Yolculuk sonunda önce “beklendiği gibi geçti mi?” diye sorulur.
- Birden fazla toplu taşıma aracı kullanılan rotada, sorun başlığından önce
  hangi araçta veya hatta sorun yaşandığı seçilir.
- Yıldız veya uzun anket kullanılmaz. Sorun varsa yer, evrensel başlık ve kısa
  açıklama alınır; hat, araç/sefer, durak ve zaman otomatik eklenir.
- Yolcu kendi başlık ve açıklamasını **Yolculuklarım** kartında görür. Kurum
  ekranında kişisel metin değil yalnızca anonim tekrar sayısı gösterilir.
- Sorunsuz yolculuklar da paydada tutulur; kurum yalnızca şikâyet sayısını değil
  sorun oranını görür.
- Ücretsiz biniş ödülü pilot kapsamından çıkarılmıştır. Ödül, spam ve temsil
  yanlılığı yaratabilir; BELBİM, bütçe ve suistimal modeli olmadan vaat edilmez.

## Kurum tarafı

- Tekil bildirim iş emri değildir.
- Aynı hedef ve konuda üç işlenebilir kayıt bir **doğrulama adayı** oluşturur.
- Araç kartına tıklandığında yalnızca gruplanmış başlık ve tekrar sayısı
  gösterilir; yolcunun ham açıklaması bu özette açılmaz.
- Araç ve durak adayları saha doğrulamasına; hat adayları operasyon
  doğrulamasına gider.
- Erişilebilirlik sinyalleri anonim gruplanır. Yatırım önceliği belirlenirken
  kullanım talebi, mevcut uygunluk, yakın alternatif ve saha koşulları birlikte
  değerlendirilmelidir.

## İBB'ye getirdiği yenilik

Tek tek ETA, anket veya otopark doluluğu yeni değildir. İBB'nin Park Et Devam
Et uygulaması ve İSPARK'ın anlık doluluk gösteren çözümü zaten vardır. Bu
projenin iddiası “park et devam eti icat etmek” değildir. Yenilik, yolculuğa
özel otopark seçimini canlı kapasite, toplam süre ve doğrulanabilir karbon
faydasıyla hesaplamak; İBB ve İETT'nin ayrı veri kaynaklarını tek bir kapalı
iyileştirme döngüsünde birleştirmektir:

**canlı karar → açıklanabilir etki → bağlamsal geri bildirim → doğrulanacak
kurum adayı**

Bu yaklaşım yolcunun şikâyetini bağlamsız metin olmaktan çıkarır; hangi sefer,
araç, durak ve rota koşulunda oluştuğunu bilir. Kurum için ölçülebilir değer
buradadır.

## Pilot önerisi

İlk pilot 3–5 hat ve bu hatların beslediği 2–3 İSPARK bölgesiyle sınırlanır.
Sekiz haftada şu göstergeler karşılaştırılır:

- Rota karşılaştırmasını görenlerin düşük emisyonlu seçeneği tercih oranı
- Önerilen hibrit rotaların araca göre ortalama CO₂ kazancı
- Erişilebilirlik bilgisinin görüntülenme ve geri bildirim oranı
- Bildirimlerden saha doğrulaması geçenlerin oranı
- Aynı sorun için tekrar bildirim oranındaki değişim
- Yanlış veya yinelenen bildirim oranı

## Açık sınırlar

- Metro, Marmaray, T1/T3/T4, F1/F2/F3 ve TF1/TF2 planlı GTFS ağına dahildir;
  canlı raylı araç konumu ve anlık aksama bilgisi yoktur. T5 kaynak GTFS
  paketinde bulunmadığından, vapur ise saat-bağımlı motor gerektirdiğinden
  henüz dahil değildir.
- GTFS paketi yeni açılan hat/uzatmaların gerisinde kalabilir; veri yenileme
  betiği kaynak güncellendiğinde ağ dosyasını yeniden üretir.
- Karbon değeri ölçüm değil model tahminidir.
- İSPARK doluluğu anlıktır; varış anındaki boş yeri garanti etmez.
- İstanbulkart geçmişi, kimlik ve açık rıza entegrasyonu konsept kapsamındadır.
- Kamuya açık hat göstergeleri geçmiş veriyi özetler; gelecekteki tek bir
  sefer için vaat veya garanti değildir.
