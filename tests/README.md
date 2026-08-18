# Testler

```bash
python -m pytest -q
```

62 test. **Canlı servise hiç çıkmazlar** — hepsi diskteki JSON'larla çalışır.
`conftest.py` içindeki `_ag_kapali` fixture'ı ağ çağrılarını bloke eder; bir
test ağa çıkmaya kalkarsa sessizce yavaşlamak yerine açıkça hata verir.
Sebebi: `FiloDurum` saatte 100 istekle sınırlı ve aşılınca tüm şebeke veri
alamıyor.

## Neyi koruyorlar

| Dosya | Kilitlenen iddia |
|---|---|
| `test_karbon.py` | 918 gCO₂/araç-km İETT yakıt verisinden türetiliyor · tüketim 34,2 L/100km ile şehir otobüsü aralığında · solo/körüklü ayrışımı filo oranıyla harmanlanınca kaynağını %0,5'ten az farkla yeniden üretiyor · otomobil 159 · otobüs her doluluk senaryosunda arabadan temiz |
| `test_skor.py` | Ağırlıklar 45/30/25 · p5–p95 normalizasyonu uçları kırpıyor · iptal gerçekleşmeye düşüyor · **kümelenme düzenlilikte yakalanıyor** (aynı sefer sayısı, farklı puan) · toplam skor = üç bileşenin toplamı · harf eşikleri monoton |
| `test_rota_yon.py` | Sıra verisi 800+ hat · SIRANO listesi (ring için çoklu değer) · **"veri yok" ≠ "yanlış yön"** · ileri yön geçerli, ters yön reddediliyor · yol mesafesi kuş uçuşundan kısa değil · ardışık duraklar arası mesafe patlamıyor (kapalı tur regresyonu) · 50 km/s üstü segment yok |
| `test_veri.py` | 15.112 durak, hepsi İstanbul içinde ve adlı · **853 erişilebilir durak = %5,6** · hat-durak grafiği · yürüyerek aktarma indeksi (metrobüsün ada kalmasını çözen) · güzergâh geometrisi · hat profili · kapasite ≥160 metrobüs ailesini ayırıyor · raylı ağ 20+ servis, 200+ istasyon |
| `test_durak_arama.py` | **Arama indeksi doğruluğu bozmuyor** — indeks açık ve kapalı hâlde 21 sorgunun sonuçları birebir aynı (`DURAK_ARAMA_INDEKSSIZ=1` ile daraltma kapatılabilir) |
| `test_performans.py` | `hat_ring_mi` önbelleği çalışıyor **ve doğru cevap veriyor** · durak araması indeksli · uçtan uca rota bütçesi |
| `test_karbon_arac.py` | Araç bazlı emisyon: CNG dizelden %5–20 temiz · elektrikli şebeke faktöründen, sıfır sayılmıyor · bilinmeyen araçta **uydurma yok** · `get_arac_ozellik` servis düşünce "Dizel" uydurmuyor |
| `test_eta_seferde.py` | **Seferde olmayan araca ETA verilmiyor** — garajdaki ve 6 dk'dır hareketsiz araç listeden eleniyor; ışıkta bekleyen (hız 0 ama hareketli) araç ELENMİYOR; rota kartlarını besleyen ayrı kod yolunda da filtre var |
| `test_kota_dayaniklilik.py` | Kota dolunca eldeki veri **silinmiyor** · disk anlık görüntüsü yeniden başlatmayı atlatıyor · yaş dürüst hesaplanıyor · **canlı veri gelince anında devralıyor** · yarım dosya bırakmıyor · bozuk dosya çökertmiyor · güvenilmez küçük görüntü yok sayılıyor |

## Performans

Ölçüldü ve düzeltildi (`python scripts/profil_rota.py` ile tekrarlanabilir):

| Darboğaz | Bulgu | Çözüm | Kazanç |
|---|---|---|---|
| Durak araması | Her sorguda 15.112 durak yeniden token'lara ayrılıyordu — istek başına **241.800** `_tokenize` çağrısı, rota hesabının **%50'si** | Token önbelleği + trigram tersine indeksi | Şehir içi rota **~690 → ~80 ms** |
| Ring tespiti | `hat_ring_mi` tek istekte **31.152 kez** çağrılıp aynı hesabı tekrarlıyordu (2,1 sn / 11,8 sn) | Sonuç önbelleği (girdi açılışta bir kez yükleniyor) | Şehir aşırı rota **1,31 → 0,97 sn** |

Uçtan uca (HTTP, ısınmış): Avcılar→Zincirlikuyu **155 ms** · Mecidiyeköy→Kadıköy
**230 ms** · Avcılar→Kadıköy **211 ms** · Bakırköy→Üsküdar **1,5 sn** (raylı +
çok aktarmalı arama; kalan maliyet arama algoritmasının kendisinde).

### Hızlandırırken yakalanan gerçek hata

Trigram indeksi ilk hâlinde adayları bir **küme** üzerinde geziyordu. Puanlar
doğruydu ama `sort` kararlı olduğu için **eşit puanlı sonuçların sırasını
giriş sırası belirliyor** — küme sırası ise Python'da süreç başına rastgele.
Sonuç: aynı sorgu çalıştırmadan çalıştırmaya farklı ilk durak veriyordu
("AVCILAR" ↔ "AVCILAR METROBÜS", ikisi de 270 puan). `test_durak_arama.py`
bunu ilk çalıştırmada yakaladı. Düzeltme: adaylar indeksin kendi sırasında
gezilir, üyelik kümeden sorulur.

## Neden bunlar

Projede ölçümle bulunmuş 9 gerçek hata var (5 ETA + 4 rota). İkisi staj
panelinden mirastı ve aylarca fark edilmemişti — çünkü yanlış sonuç
"makul" görünüyordu. Bu testler o hataların geri gelmesini engellemek için
yazıldı: her biri bir hatanın izini taşıyor.

Sayı değişirse test kırmızı yanar. Bu bir arıza değil, **haber**: veri
yenilendiyse testteki beklenen değeri güncelle ve aynı sayıyı sunumda da
düzelt. Testin görevi sayının sessizce kaymasını engellemek.

## Kota dayanıklılığı

`FiloDurum` saatte 100 istekle sınırlı. Kota dolması **anormal değil, normal
işletme koşulu** — buna göre davranılıyor:

| Durum | Davranış |
|---|---|
| Çekim başarısız | Bellekteki son veri korunur, silinmez |
| Uygulama yeniden başlar | `filo_anlik.json`'dan son bilinen filo yüklenir (~6.900 araç) |
| Veri eskiyor | Arayüz dürüstçe yazar: "12 dk önceki veri" (sarı), 30 dk üstünde "servis yanıt vermiyor" (kırmızı) |
| **Servis geri gelir** | **İlk başarılı çekim belleği ve diski birlikte tazeler; yaş sıfırlanır** |

Anlık görüntü **yapışmaz**: diskten okuma yalnızca açılışta bir kez yapılır,
zamanlayıcı normal temposunda (120 sn) denemeye devam eder. Yani kota
açıldıktan en geç bir tur sonra canlı veri devralır.

Güvenlik önlemleri: önce `.tmp`'ye yazılıp taşınır (yarım dosya kalmasın),
500 araçtan az görüntü güvenilmez sayılıp yok sayılır (haritada 3 otobüs
gösterip "işte şebeke" demek boş ekrandan beterdir).
