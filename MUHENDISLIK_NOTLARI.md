# İBB Yolculuk Kararı — Mühendislik Notları

Bu dosya projedeki her düzeltmenin **neden** yapıldığını ve hangi ölçüme
dayandığını tutar. Projede birkaç varsayım veriyle çürüdü; gerekçeler
burada kayıt altında ki aynı hata tekrar yapılmasın.

İETT'nin vatandaş uygulaması konsepti. Tech İstanbul İnovasyon Yaz Kampı
projesi, sunum **1 Ağustos 2026**. Flask + jinja + vanilla JS + Leaflet,
canlı İBB/İETT SOAP servislerine bağlı.

**Önce `docs/INTENT.md` oku** — ürün tanımı, alınmış kararlar ve her kararın
hangi ölçüme dayandığı orada.

---

## Çalıştırma

```bash
python app.py     # → http://localhost:5001
```

Port **5001**. 5000 portunu staj paneli (`Desktop/iett staj/iett_panel`)
kullanıyor, ikisi aynı anda çalışabilsin diye ayrıldı.

Kimlik bilgileri `.env`'den okunur, koda gömülmez. Boşsa uygulama yine
çalışır; sadece kimlik isteyen servisler veri döndürmez.

---

## Dosya haritası

| Dosya | İçerik |
|---|---|
| `app.py` | Giriş noktası, `.env` yükler, tek şablon render eder |
| `services.py` | SOAP istemcisi, cache katmanı, **ETA motoru**, arka plan iş parçacıkları |
| `routes.py` | 45 canlı uç (`scripts/uc_denetimi.py` 42'sini sınıyor) |
| `skor.py` | **Güvenilirlik skoru** — arşiv seferlerinden hat karnesi |
| `rayli.py` | Raylı ağ (GTFS, **planlı** veri — canlı değil) |
| `utils.py` · `models.py` | Küçük yardımcılar (`safe_int`, XML) |
| `profil.py` | **Profil / değerlendirme — KONSEPT, mock veri** |
| `templates/index.html` | Tüm arayüz — tek dosya, harita + rota + analiz |
| `data/hat_profil.json` | Hat profilleri: km, durak, katsayı, **yol_orani**, **p10/p90 yayılım**, saat çarpanı |
| kök dizin | `durak_dict.json`, `memory_db.json`, `haftalik.json`, `hat_durak_sira.json` |
| `panel_data/` | `hat_guzergah_geo.json` (841 güzergâh çizgisi), `hat_master`, `hat_kapasite`, `smart_maintenance` (3.509 araç — karbonun araç bazlı katmanı) |
| `docs/` | INTENT, **URUN_MANTIGI**, ROADMAP, ETA_MODELI, **KARBON**, EKIBE_OZET |

Proje `Desktop/iett staj/iett_panel`'den türetildi. **Orijinale dokunma** —
referans olarak duruyor.

---

## ⚠️ Kritik kısıtlar

**Saatlik kota.** `FiloDurum/SeferGerceklesme.asmx` **saatte 100 istekle**
sınırlı (dokümante). Aşılınca çalışan metotlar da `Policy Falsified` döner —
**yetki hatasıyla birebir aynı mesaj**, karıştırması çok kolay. Test
sırasında bu sınırı bir kez doldurup servisi kestik.

Ayırt etme yöntemi: aynı anda başka bir servisin metodu çalışıyorsa sorun
kotadır, yetki değil.

**Mimari kural.** Kullanıcı başına canlı API çağrısı yapılmaz. Tek merkezi
yoklayıcı çeker, herkes cache'ten okur. Aksi hâlde sunum günü salonda
birkaç kişi haritayı kurcalayınca canlı otobüsler kaybolur.

**Erişim sınırı.** 44 SOAP metodundan yalnızca **15'ine** erişimimiz var;
25'i her formatta `Policy Falsified` veriyor. Kapalı olanlar arasında
`GetDurakGecisZaman_IGA` (durak bazlı geçiş saati), `GetPlanaUyum`,
`GetSeferZayi`, `GetStopLines` var.

**Durak bazlı geçiş saati yok.** Üç kanalda da doğrulandı: SOAP kapalı,
GTFS `stop_times` her seferde yalnızca ilk ve son durağın saatini veriyor
(6,15M satırın %95,6'sı boş), GTFS-Realtime feed'i yok. Türetmek gerekirse
interpolasyon + canlı GPS gözlemi ile yapılır.

---

## ETA motoru — düzeltilmiş 5 hata (tekrar bozma)

| # | Hata | Çözüm |
|---|---|---|
| 1 | Trafik iki kez sayılıyordu | `eta_hesapla()` tek yerde; `gecikme = trafikli − serbest` |
| 2 | Durak sayısı kullanılmıyordu | `kalan_durak` parametresi + `data/hat_profil.json` |
| 3 | Trafik geçmişi ters sıralıydı | Servis en yeniyi başta veriyor; summary artık kronolojik, `values[-1]` = güncel |
| 4 | Yön etiketi güvenilmez | `arac_gercek_yon()` — yönü hareketten türetir, etiket yalnızca yedek. Açılışta 45. sn'de ek çekim → ısınma ~4 dk yerine ~50 sn |
| 5 | Park hâlindeki araca ETA | `arac_hareket_durumu()` — 6 dk'da <150 m ise işaretlenir |
| 6 | **İşaretleniyordu ama ELENMİYORDU** | Aşağıya bak — iki kod yolunda da filtre yoktu |

**⚠️ Seferde olmayan araca ETA verilmez — iki kod yolu da düzeltildi.**
`arac_hareket_durumu()` ve `garajda_mi()` uzun süre yalnızca *işaret*
üretiyordu; hiçbir yerde **filtre** olarak kullanılmıyordu. Sonuç: garajda
park etmiş otobüs yolcuya "geliyor" diye gösteriliyordu. Ölçüldü (canlı
veri): `34G M4852` garajda → **"2 dk"**, `500T C-361` garajda, hız 0 →
**"22 dk"**. Arayüz sunucunun gönderdiği `hareketli` alanını hiç okumuyor,
yani kullanıcı yalnızca süreyi görüyordu.

İki ayrı yol vardı ve **ikisinde de** eksikti:
1. `/api/durak_eta` — durak tıklanınca çıkan liste. Kodda *"park hâlindeki
   otobüse güvenli ETA verilmez"* yorumu vardı ama `hareketli` sadece yanıta
   alan olarak ekleniyordu.
2. `_canli_eta_hesapla` (`routes.py:332`) — **rota kartlarındaki
   "● CANLI 15 dk" rozeti**. Hareket/garaj kontrolü hiç yoktu; kullanıcının
   gördüğü yer burasıydı.

Sınıflandırma `/api/canli_konum` ile aynı: `garajda` · `garaj_cikis` ·
`duruyor` **elenir**, `seferde` gösterilir. Aşırı filtreleme yok — kırmızı
ışıkta bekleyen araç (hız 0 ama son 6 dk'da yol almış) seferde sayılır
(76D `D-107` tam bu durumda). Canlı araç kalmazsa planlı sefer saatine
düşülür ve arayüz **PLAN** rozeti gösterir.

Regresyon: `tests/test_eta_seferde.py` (4 test; filtre kaldırılınca kırmızı
yandığı doğrulandı).

Detay ve saha ölçümleri: `docs/ETA_MODELI.md`

**Model:** `süre = yol_km/42,1 + durak×0,50 × hat_katsayısı × saat_çarpanı × trafik_sapması`

- `yol_km` **güzergâh çizgisinden ölçülür** (`guzergah_mesafe_km`) — kuş uçuşu
  değil. Ölçüldü: gerçek oran medyan **1,77**, eski sabit 1,40 idi.
- `saat_çarpanı` arşivden (gece 0,81 · sabah 0,98)
- `trafik_sapması` **aynı saatin 7 günlük normaline** göre, 24 saat ortalamasına göre değil
- Trafik **rota boyunca** örneklenir (`guzergah_trafik_ort`), tek noktadan değil
- `eta_araligi(hat, dk)` güven aralığı verir — hattın kendi p10/p90 yayılımından

**Doğrulama — 30 Tem 2026'da yeniden ölçüldü** (29 Tem arşivi, 45.102
tamamlanan sefer, 8.152 saat×hat kombinasyonu):

| Ölçüt | Profil onarımı öncesi | Sonrası |
|---|---|---|
| Medyan oran | 0,997 | **0,998** |
| ±%20 içinde | %84,2 | %83,9 |
| ±%30 içinde | %90,3 | %90,0 |

Profil onarımı modeli bozmuyor, medyanı 1,000'e biraz yaklaştırıyor.

⚠️ Belgede daha önce **"±%20 içinde %93,2"** yazıyordu; bu rakam
**doğrulanamadı** (ölçülen %84). Medyan neredeyse birebir tutuyor
(0,996 → 0,997). Özgün ölçüm GTFS + holdout ile yapılmıştı, bu ölçüm arşiv
seferlerinden — yöntem farkı olabilir, ama iddiayı destekleyen veri yok.
Sunumda **%84** kullanılmalı.

---

## Rota planlayıcı — düzeltilmiş 4 hata (tekrar bozma)

| # | Hata | Çözüm |
|---|---|---|
| 1 | **Kapalı tur mesafesi** — hatların **%45,6'sında** `G` kolu gidiş+dönüşü birlikte tutuyor. Durak turda iki kez geçtiği için tek "global en yakın köşe" binişi gidiş, inişi dönüş bacağına düşürüyordu | `_guzergah_gecisler()` tüm yerel minimumları bulur, `_guzergah_segment()` **ileri yönde en kısa** çifti seçer |
| 2 | **Hat-seviyesi düz BFS** — global `visited` yüzünden bir hat ilk hangi yoldan görüldüyse ebeveyni sabitleniyordu; tüm yollar aynı öneki paylaşıyordu. Arama süreyi değil **aktarma sayısını** azaltıyordu | Öncelik kuyruğuyla **dakika maliyeti** üzerinden arama; aktarma cezası (8 dk) arama içinde sayılır; iki hat arasındaki **en iyi** aktarma durağı seçilir |
| 3 | **Profilsiz hatlar kayrılıyordu** — 799 hattın **154'ünün** (%19,3) profili yok; eski kod onlara `×1,4` ve `22 km/s` iyimser sabitlerini veriyordu (şebeke medyanı 1,77) | `SEBEKE_YOL_ORANI/DURAK_YOGUNLUK/KAT` — profilsiz hat **medyan hat** gibi davranır |
| 4 | **Ters yöne bindirme** — durak-hat eşlemesi yönü söylemiyor; araç gerçekte B→A giderken A→B önerilebiliyordu | `guzergah_yon_gecerli()`; geometri karar verebiliyorsa o rotalar **listenin sonuna** atılır (`yon_supheli`), hiç rotasız bırakılmaz |

### 🔑 YÖN + SIRANO — servisin kesin verisi (en önemli düzeltme)

`DurakDetay_GYY_wYonAdi` metodunun adı zaten "yön adıyla" diyor. Yanıtta her
durak için şunlar geliyordu ve **atılıyordu**:

| Alan | Anlam |
|---|---|
| `YON` | **G = gidiş · D = dönüş** |
| `YON_ADI` | O yönün varış terminali |
| `SIRANO` | Durağın o yöndeki **sıra numarası** (1..N, tekrarsız) |
| `DURAKTIPI` | Metrobüs istasyonu için `ISTASYON` |

Önceki sürüm yalnızca `DURAKKODU`'nu alıp yönü **geometriden çıkarmaya**
çalışıyordu. Oysa kesin veri elimizdeydi. `HAT_DURAK_SIRA` (837 hat,
`hat_durak_sira.json`) bunu saklıyor.

**Ring hatları.** Ring, tek yön döner ve ilk durak = son durak (DT1
VADİ→…→VADİ). Bir durak aynı yönde **iki kez** geçebilir, bu yüzden yapı
`{durak: [sıra, …]}` — liste. Tek değer tutulunca ilk geçiş kayboluyordu
(DT1 46 kayıt → 45 durak) ve ring hiç tespit edilemiyordu. **52 ring hattı** var. (Ham kriter "herhangi bir durak tekrar ediyor" 55
verir; `hat_ring_mi` bunlardan 3'ünü eler — 41-47 duraklı bir hatta tek
durağın tekrar etmesi ring değil, uçtaki dönüş manevrasıdır. Doğru sayı 52.)

**Bunun ortaya çıkardığı gerçek hata — yanlış peron.** Metrobüs
istasyonlarının her yönü AYRI durak kaydı: İNCİRLİ **900221 = D** (sıra 22),
**900222 = G** (sıra 23); ALTUNİZADE **900051 = D**, **900052 = G** (sıra 40).
Planlayıcı biniş durağını "en yakın" diye seçtiği için **dönüş peronunda
bindirip gidiş peronunda indiriyordu** — fiziksel olarak imkânsız bir rota.
Bakırköy→Üsküdar'da 34G tam bunu yapıyordu.

İki kademeli düzeltme: `_peron_duzelt()` A/B havuzu uçlarını,
`_peron_zinciri_duzelt()` **tüm bacak zincirini** (ara aktarmalar dahil)
gezip aynı hattı taşıyan, yönü geçerli en yakın peronla (≤350 m) değiştiriyor.

**Ölçüm:** 72 segmentte ters yön **25 → 6**; kullanıcının gördüğü
**ilk sıradaki rotalarda ters segment 0**. Kalan 6'sı 350 m içinde geçerli
peronu olmayan vakalar — `yon_supheli` işaretlenip listenin sonuna atılıyor.

⚠️ `yon_sirali_gecerli()` içinde **"veri yok" ile "yanlış yön" ayrı**
olmalı. İki durak da veride varsa ama farklı yönlerdeyse cevap `None`
(karar veremem) değil **`False`** (geçersiz) — aksi hâlde peron düzeltmesi
hiç devreye girmiyor.

**Canlı harita.** `arac_gercek_yon()` artık aracın yönünü `SIRANO` sıralı
listeden türetiyor; önbellekteki durak listesinin sırasına bağımlı değil
(`hat_yon_durak_listesi`). Geometri çıkarımı yalnızca sıra verisi olmayan
hatlarda yedek.

### Operasyon haritası — denetim (31 Tem 2026)

| Katman | Durum |
|---|---|
| Garajlar | ❌→✅ **düzeltildi**, aşağıya bak |
| Duraklar | ✅ 15.112, koordinatı İstanbul dışı 0, adsız 0 |
| Güzergâh çizgisi | ✅ 841 hat, İstanbul dışı nokta içeren kol 0 |
| Trafik ısısı | ✅ 24 nokta, koordinatlar geçerli |
| Kavşaklar | ⚠️ 2.585 kayıt geliyor ama **arayüzde hiç çizilmiyor** — uç boşta |
| Duyurular | ✅ 93 kayıt; `lat/lon = 0` geldiği için haritaya değil listeye düşüyor (doğru) |

**Garajlar yanlış yerdeydi.** `api_garajlar` içinde **elle yazılmış 27 kayıtlık
statik liste** vardı; yorumu "GetGaraj_json HTTP 500 döndürüyor" diyordu.
Tekrar denendi: **servis çalışıyor**, 86 garaj döndürüyor ve hepsinin
koordinatı geçerli. Statik listenin sapmaları: İkitelli **0,82 km** ·
Avcılar 0,59 km · **Tuzla 6,57 km**; "Sarıyer Garajı" gerçekte hiç yok.

Koordinat WKT geliyor: `POINT (28.7915 41.0605)` — **önce boylam sonra
enlem**, ters çevirmek gerekiyor.

**Kopya birleştirme.** Servis aynı noktayı birden fazla adla döndürüyor
(İkitelli için `IKITELLIISLETTIRMEGARAJI` / `IKITELLIGARAJI` /
`...GARAJI2`, üçü de 41.06059, 28.79151). Haritada üst üste üç işaret
çiziliyordu. Aynı koordinat tek kayıtta toplanıyor → **86 → 83**.

**Garajdaki araç "seferde" görünüyordu.** `arac_hareket_durumu()` yalnızca
ETA ucunda kullanılıyordu; haritayı besleyen `/api/canli_konum` her aracı
hizmetteymiş gibi çiziyordu — garajda park etmiş otobüs de yön okuyla
görünüyor, kullanıcı onu gelecek sanıyordu. Artık her araca `durum` alanı
ekleniyor: `seferde` · `duruyor` · `garajda` · `garaj_cikis`
(`garajda_mi()`, eşik 250 m).

### ✅ Araç yönü — SAHA TESTİ YAPILDI (31 Tem 2026)

`GetHatOtoKonum_json` üç alan veriyor ve **hangisinin ne olduğu kritik**:

| Alan | İçerik | Güvenilir mi |
|---|---|---|
| `yon` | **TERMİNAL ADI** (`B.SONDURAK`, `SÖĞÜTLÜÇEŞME`) — G/D DEĞİL | terminal↔yön eşlemesi %100 |
| `guzergahkodu` | `34G_D_D0` → **gerçek yön** | **%98,9** |
| `yakinDurakKodu` | Aracın o an bulunduğu durak kodu | 55/55 dolu |

**Test:** 4 hat, 87 araç, 130 sn arayla iki ölçüm. `guzergahkodu`'ndan
okunan yön, aracın `SIRANO` ilerlemesiyle **86/87 uyumlu**. Tek sapma
komşu duraklar arası GPS oynaması (500T, sıra 63→62).

**Bu, eski varsayımı çürüttü.** Kodda "34AS'te etiketli araçların yarısı
ters yönde" yazıyordu ve bu yüzden hareketten türetilen yön etiketin
üstüne yazılıyordu. O ölçüm **yanlış alanı** karşılaştırmış (terminal adını
G/D sanmış). Öncelik değiştirildi: **etiket öncelikli**, hareketten türetme
yalnızca etiket yoksa. `yakinDurakKodu` sayesinde geometrik tahmine de
gerek kalmıyor.

**Peron bazlı ETA.** `yon` parametresi verilmezse artık sorgulanan durağın
kendi yönünden türetiliyor. Doğrulandı: İNCİRLİ 900221 (D peronu) → yalnızca
D araçları, 900222 (G peronu) → yalnızca G. Önceden her iki yön de
listeleniyordu; G peronunda bekleyen yolcuya oraya hiç uğramayacak D
otobüsü gösteriliyordu.

**Yığılma gerçek.** Aynı ölçümde ardışık araç çiftlerinin **%59–62'si
1 durak veya daha yakın** (34G: G yönü %59, D yönü %62; 34AS %62). Bu bir
görselleştirme hatası değil, metrobüsün bilinen kümelenme sorunu — ve
güvenilirlik skoru bunu zaten yakalıyor (34G düzenlilik **3,9/25**).

### Aracın yönü — `SGUZERGAHKODU`

Arşivde her seferin güzergâh kodu `HAT_YON_ekstra` biçiminde: `34_D_D9018`
→ hat 34, **D = dönüş**. 29 Tem 2026 arşivinde **51.972 seferin %100'ünde**
bu format geçerli, yön harfi her zaman var. Yani araç yönünün kaynağı
güvenilir; kodun eski yorumundaki "etiketli araçların yarısı ters yönde"
notu bu formatla değil, `GetHatOtoKonum_json`'un kendi `yon` alanıyla
ilgiliydi (o alan terminal adı döndürüyor).

**Ring mesafesi turu kapatabilir.** `_guzergah_segment` eskiden `i2 <= i1`
çiftini koşulsuz reddediyordu; ring tek yönde döndüğü için sıra numarası
büyükten küçüğe gitmek **geriye gitmek değil**, turu tamamlamaktır. Ret
sonucu çağıran kuş uçuşu × 1,77 yedeğine düşüyordu ve ring çember çizdiği
için bu mümkün olan en kötü tahmindi: hat 29M1'de (tam tur 12,60 km) sıra
30 → sıra 8 yolculuğunun gerçek yolu **5,62 km** iken yedek **1,86 km**
veriyordu — %67 eksik, süre 15,4 dk yerine 5,1 dk. Ayrıca
`yon_sirali_gecerli` aynı yolculuğu açıkça geçerli sayıyordu; iki modül
çelişiyordu. Artık ring'te sarmal mesafe hesaplanıyor
(`(kum[-1] − kum[i1]) + kum[i2]`) ve segment `sarmal: True` taşıyor —
`guzergah_trafik_ort` de örneklemeyi buna göre yapıyor.
**Ölçüldü:** ring hatlarında mesafe dönmeyen çift **%22,9 → %0**; ring
olmayan hatlar etkilenmedi (%2,5, değişmedi).

**Ring — arşivle sınandı.** Ring işaretlenen 52 hattın **47'si arşivde
yalnızca G çalışıyor** ve o hatlarda hiçbir araç hiç D yapmamış
(DT1 G=93/D=0 · 30A G=119/D=0 · 30M G=159/D=0). Yani gerçekten tek yönde
turu kapatıyorlar — ring tanımı bu. Yalnızca 5 hatta (BA-4, EM1, EM2, HM1,
KM47) her iki yön de var, orada da G ezici çoğunlukta (130/29, 111/6) —
muhtemelen garaj dönüşleri.

⚠️ **9 hatta çelişki**: durak API'si tek yön veriyor ama arşiv iki yön
diyor (4, AND2Y, AVR1, AVR2 + 5 ring hattı). O hatlarda D yönünün durak
sırası elimizde **yok**; D yönünde giden araç için sıra doğrulaması
yapılamıyor.

### `build_hat_sira` hedefini GRAFİKTEN de almalı

Hedef listesi yalnızca `hat_master`'dan kuruluyordu. Ölçüldü: **10F, 132SP,
132YS, 136T, 55G, K4** grafikte **var** ama `hat_master`'da **yok** — bu
yüzden sıra verileri hiç çekilmiyor, o hatlarda yön doğrulaması hiç
yapılamıyordu (geometrileri de yok). Grafikteki hatlar hedefe katıldı:
kapsama **826 → 837**, sıra verisi olmayan hat **0**.

Not: bu hatların verisi API'de vardı; ilk çekimde zaman aşımına uğramışlar.
Kalıcı eksiklik sanmadan önce tekrar denemek gerekiyor.

### Hat profili aykırı değer koruması

`data/hat_profil.json` dışarıdan üretiliyor ve içinde bozuk kayıtlar var.
**Hat 34** (AVCILAR-ZİNCİRLİKUYU — metrobüsün gövde hattı) iki hatayı
birden taşıyordu: durak sayısı **18** (olması gereken 26) ve `kat_hi`
**0,327** (kardeş metrobüs hatları 0,68–0,83, şebeke medyanı 1,127,
p1 değeri 0,667). İkisi birbirini büyütünce 18,61 km'lik bir segment
**10,5 dk = 106 km/s** hesaplanıyordu.

Elle "34'ü düzelt" denmedi; kurallar **şebeke istatistiğinden** türetildi:

| Koruma | Kural | Etkilenen |
|---|---|---|
| Durak sayısı | Kesin kaynak `HAT_DURAK_SIRA`; oran şebekede medyan **1,00**, p1 **0,677**. Altındaysa sıra verisine güven | **33 hat** — BM4 8→42, ES2 16→45, 85C 10→24, 34 18→27, KM41 12→34, 33TM 13→22, 16F 35→46 |
| Katsayı | p1–p99 aralığına kırp (**0,667 – 2,137**) | **22 katsayı** — 34: 0,327→0,667 |
| Hız tavanı | `segment_sure_tahmini` sonunda: <1 durak/km ise 45 km/s, değilse 38 km/s | Emniyet supabı — profil dosyası yenilenirse yeni bozuk kayda karşı |

**Sonuç:** hat 34'ün 18,61 km segmenti 106 → **40,7 km/s** (`services.py:2476`).
Şebekede 50 km/s üstü segment **0** — tavan `sapma` ile çarpıldıktan SONRA da
uygulandığı için trafik normalden iyiyken de geçerli. Kırpılan hatlar dışındakiler etkilenmedi (test edilen
41AT, 12A, 129T, 40, 16D katsayıları hiç dokunulmadı) — düzeltme hedefli.

### ⚠️ Arayüzde kullanıcı girdisi kaçırılmalı

Sunucu, eşleşmeyen aramayı hata mesajında **aynen yansıtıyor**. Bu metin
kaçırılmadan `innerHTML`'e yazıldığında `<img src=x onerror=...>` gibi bir
yük **gerçekten çalışıyordu** (tarayıcıda doğrulandı). `<script>` etiketi
`innerHTML` ile çalışmaz — o yüzden yanlış yükle test edip "güvenli" sonucuna
varma. `_kacis()` yardımcısı eklendi; hata mesajı ve öneri durak adları
artık ondan geçiyor. Uygulama URL parametresi okumadığı için bu self-XSS
idi (saldırgan hazır link üretemiyor), yine de kapatıldı.

**Ölçümler.** Kapalı tur hatlarında 657 durak çiftinin **%37,4'ü** ciddi
hatalıydı; en uç örnek 88A'da yan yana iki durak — gerçek 0,18 km, eski
yöntem **29,96 km**. Düzeltmeden sonra 1.399 çiftte **geometri ihlali 0**
(yol < kuş uçuşu), yol/kuş uçuşu medyanı 1,37.

Düz güzergâhlarda medyan sapma **%0,0** — düzeltme oralarda bir şey değiştirmiyor.

**Aday üretiminde 1-aktarmalı kırpma.** Eskiden `len(transferler)>30 → break`
vardı ve liste **hiç sıralanmadan** ilk 5'i alınıyordu; `snap_db` sözlük
olduğu için bu "sözlükte ilk rastlanan 30 aktarma durağı" demekti.
Mecidiyeköy→Kadıköy'de **132** geçerli kombinasyon varken ilk 30'dan
seçiliyordu. Artık maliyete göre sıralanıyor.

**Çeşitlilik.** Aynı ilk-iki-hat önekinden en fazla 2 öneri, aynı hat
kümesinden 1 öneri. Öncesinde Bakırköy→Üsküdar'da 9 önerinin 9'u da
`72YT → 30D → 129T` ile başlıyordu — kullanıcıya seçenek gibi görünen şey
tek bir rotanın kopyalarıydı.

### Metrobüs — neden hiç çıkmıyordu, ne yapıldı

İki ayrı sebep vardı, ikisi de düzeltildi.

**1. Havuz yarıçapı 10 metreyle kaçırıyordu.** Kodun kendi yorumu "AVCILAR ↔
AVCILAR MRK.ÜNV.KMP **810 m**" diyor, eşik ise `YAKIN_KM = 0.80` idi. Bu
yüzden "AVCILAR → ZİNCİRLİKUYU" sorgusunda, adı birebir *AVCILAR-ZİNCİRLİKUYU*
olan 34 hattı aday bile olamıyordu.

→ **İki kademeli yarıçap**: sıradan hatlar 0,80 km, yüksek kapasiteli hatlar
**1,50 km**. Yarıçapı topluca büyütmek pahalıydı (1,5 km'de Mecidiyeköy havuzu
48 → 140 durak); metrobüs şehirde toplam 90 durak olduğu için maliyeti yok.
"Yüksek kapasiteli" kodu gömülü değil, **veriden**: `hat_kapasite.json`'da
kapasite ≥ 160 olan 8 hat tam olarak metrobüs ailesi (körüklü araç), yanlış
pozitif yok — sonraki en yüksek sıradan hat 152.

**2. Metrobüs grafikte ADA idi.** Aktarma modeli **aynı durak kodunu** şart
koşuyordu; metrobüs istasyonları (900xxx) yanı başındaki otobüs durağından
ayrı kayıt olduğu için metrobüs duraklarında geçen başka hat sayısı **yalnızca
2** (34T, 34U). Yani metrobüs ancak başlangıç/varış havuzuna girerse
çıkabiliyor, **ara aktarma olarak asla**.

→ **`DURAK_KOMSU`** — ızgara tabanlı yürüme komşuluğu indeksi, eşik **0,35 km**
(≈4 dk). Ölçüldü: 298 durak metrobüse yürüyebiliyor, bu **388 hatta** metrobüs
aktarması açıyor. İndeks kurulumu <1 sn (tam O(n²) 178M işlem olurdu).
Aktarma yürüyüşü `aktarma_yuruyu_dklar` ile süreye **gerçekten** ekleniyor.

**Sonuç (ölçüldü):**

| Rota | Önce | Sonra |
|---|---|---|
| AVCILAR → ZİNCİRLİKUYU | 121 dk, 3 aktarma | **55 dk, direkt 34** |
| AVCILAR → KADIKÖY | 161 dk, 3 aktarma | **96 dk**, 34 → 34A |
| BAKIRKÖY → ÜSKÜDAR | 160 dk, 3 aktarma | **81 dk**, 50B → 34G → 139 |
| MECİDİYEKÖY → KADIKÖY | 67 dk | **44 dk**, 34A direkt |
| AKİK SİTESİ → KADIKÖY | 166 dk, 4 aktarma | **130 dk**, 36AS → 34 → 34Z |

Denetim bulguları 63 → **24**; devasa dolambaç uyarıları (x3–x4 sapma)
tamamen kayboldu.

### ⚠️ Raylı sistem — eklendi, ama **planlı** veri

Eskiden grafik yalnızca İETT otobüs ağıydı; şehir aşırı yollarda süreler
2 saati aşıyordu çünkü gerçek yolcunun kullandığı ray içeride yoktu
(`MR*` hatları Marmaray'a **besleme otobüsü**, rayın kendisi değil).

`rayli.py` + `data/rayli_ag.json` ile İBB Açık Veri GTFS'inden **23 servis
/ 262 istasyon** eklendi: M1A–M9, Marmaray (3 kol), T1/T3/T4, F1/F2/F3,
TF1/TF2. Ölçüldü — Bakırköy→Üsküdar **80 dk → Marmaray ile 34 dk**,
Mecidiyeköy→Kadıköy'de M2→Marmaray üçüncü seçenek olarak çıkıyor.

⚠️ **Bu veri planlıdır, canlı değil.** İstasyon sırası ve sefer sıklığı
GTFS'ten; raylı araçların anlık konumu veya aksaması **yok** — o veri açık
değil. Açık veri yeni uzatmaların gerisinde kalabilir; **T5 pakette yok**.
**Vapur hâlâ yok** — saat-bağımlı ayrı bir rota motoru gerektiriyor.

### Veri kalitesi — ölçülmüş

- Durak-hat eşleşmesi geometriyle **çok iyi** örtüşüyor: medyan **10 m**,
  p95 69 m; 40.744 çiftin yalnızca %1,68'i 500 m dışında
- **15 hattın** geometrisi topluca bozuk (KM2, KM24, TM4, 79Ş, 142K, 151,
  50G, 36CB, 10E, DS1, 402, 133T, 18K, UM61, 134GK) — durakları çizgiden
  uzak. `_guzergah_segment` 1,5 km üstünü zaten reddedip orana düşüyor
- **9 hattın** hiç geometrisi yok: 10F, 132SP, 132YS, 136T, 55G, K4, M5,
  SM12, TM14

---

## Ölçülmüş sayılar — yeniden hesaplama

| Metrik | Değer | Not |
|---|---|---|
| Dakiklik (±3 dk) | %91,5 | Skor için **işe yaramaz**, hatlar ayrışmıyor |
| Süre yayılımı (p90−p10)/medyan | %7,9 – %258,0 | Skor için **ideal**, iyi ayrışıyor |
| İptal oranı | Şebeke %4,03 · hat %0–58,3 | `SGOREVDURUM='I'` |
| Erişilebilir durak | 15.112'ün **%5,6'sı** | İlçeler arası 31 kat fark |
| Korunaklı durak | **%44,1** | `FIZIKI` alanı: KAPALI 4.418 + FULL KAPALI 2.242 = 6.660/15.112 |
| ETA doğruluğu | %46 → **%89** | Holdout, farklı günde test |
| Günlük yolculuk (top 50 hat) | 945.219 | Geri bildirim hacmi argümanı |
| İSPARK | 252 otopark, canlı boş kapasite | Kimlik gerekmiyor |

---

## Konvansiyonlar

- Kod yorumları ve dokümanlar **Türkçe**
- Bir düzeltme yapıldığında **neden** yapıldığı yorumda yazılır — bu
  projede birkaç varsayım veriyle çürüdü, gerekçeler kayıt altında
- Ölçmeden sayı yazılmaz; her rakamın kaynağı gösterilebilir olmalı

---

## Güvenilirlik skoru + Hat Karnesi

`skor.py` · `/api/hat_skoru` · 🏅 Hat Karnesi sekmesi.

```
Skor = 45 × süre_tutarlılığı + 30 × sefer_gerçekleşme + 25 × düzenlilik
```

**Neden bu üçü.** Plan dökümanının ilk formülü "dakiklik ×0,4 + iptal ×0,3"
idi. Ölçüldü: kalkış dakikliği ±3 dk toleransta şebeke genelinde **%91,5**
ve hatlar ayrışmıyor — o formül herkese aynı puanı verirdi. Kullanılan üç
metrik geniş aralıkta dağılıyor: süre yayılımı %7,9–258,0 · gerçekleşmeme
%0–58,3 · headway σ/μ medyan 0,50.

**Eksik metrik puanlanmaz.** Bazı hatlarda bir metrik hesaplanamıyor (ada
taksileri ve füniküler sefer başlama/bitiş damgası vermiyor). Eski kod bu
duruma `_normalize` üzerinden **0,5** veriyordu — "sınava girmedi" cevabı
"orta düzeyde başarılı" diye puanlanıyordu; T2 (Taksim-Tünel) 45 puanın
22,5'ini bedavaya alıp **B** notuna çıkıyordu. Artık skor **yalnızca ölçülen
bileşenlerden** hesaplanıp 100'lük ölçeğe getiriliyor. Yan etkisi var ve
bilinçli: ölçülen ölçütlerde iyi olan eksik verili hat yukarı çıkabiliyor
(T2 → 100), kötü olan sert düşüyor (KA-7 54,9 → 17,5). Bu yüzden liderlik
tablosunda `guven != "yüksek"` olan hatlara **EKSİK VERİ** rozeti basılıyor.

**İptal edilen sefer düzenlilik serisine girmez.** Eski kod gerçek kalkış
yoksa **planlanan** saati kullanıyordu; 2 Ağu arşivinde 2.222 iptalin
2.222'sinde plan saati var, yalnızca 25'inde gerçek başlama. Yani iptaller
"hayalet kalkış" olarak seriye giriyor ve hattı düzenli gösteriyordu.
Ölçüldü: düzeltme 720 hattın **575'ini** etkiliyor, **29 hattın harfi**
değişiyor (U1 −10,5 · 50L −7,7 · 15K −7,1). Şebeke ortalaması neredeyse
sabit (64,49 → 64,46).

**Normalizasyon** şebekenin kendi **p5–p95** aralığına göre, uçlar kırpılarak.
"İyi/kötü" mutlak eşikle değil İstanbul'un gerçek dağılımıyla tanımlanıyor;
tek aykırı hat ölçeği bozmuyor.

**Sonuç (29 Tem arşivi, 51.972 sefer):** 732 hat puanlandı · ortalama 64,2 ·
medyan 66,2 · aralık 5,4–100 · A=75 B=230 C=228 D=117 E=82.

⚠️ **Bu sayılar HER GÜN DEĞİŞİR — sabit değil.** `_arsiv_gorev_cek()` arşivin
T+2 gecikmesi yüzünden 5 gün geriye sarıp veri bulduğu ilk günü kullanır,
yani hangi günün arşivine denk geldiği kendiliğinden belirlenir. En büyük
etken **haftanın günü**: hafta sonu daha az hat sefer yapar, dolayısıyla daha
az hat puanlanır.

Ölçüldü — 4 Ağu 2026'da uygulama **2 Ağustos (PAZAR)** arşivine düşmüştü:
584 hat · ortalama 65,4 · medyan 67,5 · aralık 2,2–100 · A=77 B=164 C=192
D=111 E=40. **34G o gün C 69,2 (259/584)**, 29 Tem'de B 72,8 (245/732) idi.

Yani bir sunumda/dokümanda sayı verilecekse **hangi arşiv gününe ait olduğu
mutlaka yazılmalı**; demo günü ekranda farklı bir sayı çıkması arıza değil.
Değişmeyen şey **gerekçe**: 34G'nin süre tutarlılığı hep tam puana yakın,
düzenliliği hep dipte (3,9/25 → 0/25) — kümelenme kalıcı bir gerçek.

Örnekler — **129T** 5,4 (E, 732/732): yayılım %115, 48 seferin 12'si
yapılmamış. **34G** 72,8 (B, 245.): süre tutarlılığı 44,8/45 ama düzenlilik
3,9/25 — metrobüs araçları kümeleniyor (2,1 dk aralık, 0,67 sapma). Skor
bilinen gerçek sorunu yakalıyor.

Hesap pahalı (51.972 kayıt) → uçta **6 saat önbellek**; ilk çağrı ~8 sn,
sonrası ~2 sn.

## Sırada ne var

`docs/ROADMAP.md`'ye bak. **Araç yönü saha testi 31 Tem 2026'da yapıldı**
(4 hat, 87 araç, 86/87 uyum) — yukarıdaki "Araç yönü" bölümüne bak; bu iş
artık kapalı.

Açık kalanlar: **kavşak katmanı** uçtan geliyor ama haritaya çizilmiyor ·
**vapur** ağda yok · raylı veri **planlı**, canlı değil.

---

## ♿ Erişilebilirlik uyarısı — kart tipine bağlı

Erişilebilirlik ürünün kurucu gerekçesiydi (ilk adı *Erişilebilir
İstanbul* idi) — şebekede durakların yalnızca
**%5,6'sı** (853/15.112) erişilebilir. İlçeler arası uçurum: Fatih %18,6 ·
Beylikdüzü %17,7 ↔ Sultanbeyli %1,4 · Çekmeköy %0,6 · Adalar %0.

Rota yanıtı artık `erisim` alanı taşıyor: her biniş/iniş durağı için
`engelli` (erişilebilir mi), `korunak` (AÇIK / KAPALI / FULL KAPALI),
`akilli`. Ayrıca `erisim_sorunlu` sayacı.

**Uyarı HERKESE gösterilmez** — kart tipi `engelli` olan profilde açılır
(`_erisimModuBelirle()`, `/api/profil`'den okur). İlgisiz kullanıcı için
gürültü olmasın diye. Tam kartlı profilde hiçbir şey görünmüyor
(doğrulandı).

**INTENT bölüm 6 gereği uyarı verilir, rota ELENMEZ** — erişilemez durak da
olsa seçme hakkı yolcunun; sistem karar vermez, bilgilendirir. Panelde
açıkça yazıyor: *"Rota yine de gösteriliyor — seçim sizin."*

İki yerde görünür: rota kartında küçük rozet (`♿ 2 durak erişilebilir
değil`) ve adım panelinin başında durak adları + rol + korunak tipiyle
ayrıntılı kutu.

## Profil — geçmiş sefer, değerlendirme, ödül (KONSEPT)

`profil.py` + sol menüde **👤 Profilim** sekmesi. ⚠️ Gerçek İstanbulkart
entegrasyonu **yok**, veriler mock — amaç ürün mantığını çalışır göstermek.

**Akış.** Kart tanımlı kullanıcının geçmiş seferleri profile otomatik düşer →
her sefer için **4 başlıkta 12 soruluk** anket (Hat / Araç / Durak / Sürücü
ayrı ayrı, INTENT kararı) + serbest yorum → **doğruluk kontrolü** → geçerli
**10 değerlendirme = 1 ücretsiz biniş**.

**Doğruluk kontrolü** ödül avcılığını engeller, yorumu sansürlemez:
soruların en az yarısı yanıtlanmalı · hepsine aynı puan verilmişse ayrım yok
sayılır · düşük puana kısa da olsa gerekçe beklenir. Reddedilen anket yine
kaydedilir, sadece ödül sayacına girmez.

**Kurum görünümü.** Şikâyetler araç / durak / hat bazında gruplanır; aynı
konuda **3+** bildirim alan araç *gece kontrol* listesine, durak *yenileme*
listesine düşer. Engelli kart tipinde erişilemez duraklar ayrıca işaretlenir
(günde 10+ engelli kullanıcı → Bilgi İşlem Dairesi'ne yenileme talebi).
Sınıflandırma kural tabanlı — INTENT'te "AI sınıflandırma mock kalabilir".

**Mock veri gerçekçi olmalı.** İlk sürüm rastgele hat/durak/araç üretiyordu;
o hâlde "tekrarlayan şikâyet" mantığı **hiç tetiklenmiyordu**, çünkü her
şikâyet başka araca gidiyordu. Düzenli bir yolcunun geçmişi 2-3 sabit hat,
sabit durak çifti ve küçük bir araç havuzundan oluşur — üretici buna göre
düzeltildi (500T ×7, 34G ×5; M9279 ×4 gibi).

**Analiz sekmesi kaldırıldı.** Ürün yönüyle uyumlu değildi. `page-dash` HTML
(171 satır), JS bloğu (405 satır) ve yalnızca ona ait 2 uç
(`/api/filo_yuk`, `/api/gecikme_analiz`) çıkarıldı. `/api/yogunluk` **kaldı**
— karbon doluluk hesabını besliyor. (Kaldırma sırasında tutulan
`*.analiz_yedek` dosyaları sonradan silindi, artık yok.)

## Karbon ayak izi

`/api/karbon_rota` — üç seçenek (araç / toplu / hibrit), süre + km + CO₂.
`/api/ispark` — 252 otopark, anlık boş kapasite.

Katsayılar **uydurulmadı**, kaynakları `docs/KARBON.md`'de:
- Otobüs **918 gCO₂/araç-km** — İETT'nin kendi yakıt verisinden
  (356.979 L ÷ 1.042.413 araç-km). Doğrulama: 34,2 L/100km çıkıyor, şehir
  otobüsü tipik aralığı 30–55.
- **Araç tipine göre ayrıştırıldı.** 918 bir FİLO ORTALAMASI; eski kod bunu
  her hatta sabit tutup kapasiteye bölüyordu, böylece metrobüs (kapasite 171)
  **13,4 gCO₂/yolcu-km** gibi gerçek dışı düşük değer alıyordu — körüklü araç
  daha çok yakarken emisyonu ortalama sayıp yolcuyu 171'e bölmek çift
  iyimserlik. Projenin kendi filo verisinden (`smart_maintenance.json`,
  3.509 araç) **%63,6 SOLO / %36,4 KÖRÜKLÜ** çıkıyor. Tek varsayım körüklü/solo
  yakıt oranı **1,4** (12 m ↔ 18 m dizel şehir otobüsü):
  → SOLO **800**, KÖRÜKLÜ **1.120** gCO₂/araç-km.
  **Doğrulama:** filo oranıyla harmanlanınca **916,6** çıkıyor, ölçülen 918 ile
  fark **%0,16** — iki değer kendi kendini doğruluyor.
  Sonuç: metrobüs 13,4 → **16,4**, ortalama otobüs 24,4 → **21,7** g/yolcu-km.
- Kişi başı: canlı doluluktan (`/api/yogunluk`)
- Otomobil 159 gCO₂/km ⚠️ **tek varsayım** (7,0 L/100km), ±%28 belirsizlik

**Varsayım duyarlılığı — ölçüldü (30 Tem 2026).** İki varsayımın ağırlığı
çok farklı; hangisine yatırım yapılacağını bu belirler:

| Varsayım | Aralık | Kişi başı etkisi |
|---|---|---|
| Körüklü/solo yakıt oranı **1,4** | 1,2 – 1,6 | **±%8** (metrobüs 15,0–17,6) |
| **Doluluk %40** (varsayılan) | %15 – %85 | **+%167 / −%53** |

Yani zayıf halka 1,4 değil, **doluluk** — ve canlı ölçüm hatların yalnızca
**%6,3'ünde** var (53/837). Yine de niteliksel sonuç sağlam: otobüs, doluluk
**%5,5'in** (≈5 yolcu) üzerinde olduğu sürece tek kişilik arabadan temiz.
En boş senaryoda bile 57,9 vs 159 gCO₂/km.
- Araç süresine **mutlak tıkanıklık katsayısı** uygulanır (04:00 → 1,00 ·
  17:00 → 1,42), 440.000 seferden türetildi. OSRM ham hâli serbest akıştır.

**Hibrit kapısı — bilinçli olarak GEVŞEK.** Otobüs zaten çalışıyor ve dolu;
kişi başı karbon hesabı doluluğu bölüyor, yani hibritin toplu bacağı gerçekten
düşük karbonlu. Hibrit toplamda arabadan yüksek çıkıyorsa bu neredeyse tamamen
**araç bacağının uzunluğundan** gelir — o da dolambaç filtresiyle sınırlı.
Kalan durumlarda karar **kullanıcıya** bırakılır: sayılar dürüstçe gösterilir
(arabadan yüksekse `karbon_uyari` ile açıkça yazılır), seçimi o yapar.

Ölçüldü: dolambaç filtresi düzeltildikten sonra 8 uzun rotanın **8'inde**
hibrit sunuluyor ve **hiçbiri arabadan kirli değil**. Pendik→Taksim'de araç
bacağı 45,3 → **29,6 km**'ye indi (düz sürüş 35,3 km), %9 daha temiz.

**Dolambaç filtresi — asıl düzeltme buydu.** Eskiden *hızlı **veya** temiz* yeterliydi
ve bu, toplu taşımadan hızlı ama **araçtan kirli** bir seçeneği geçiriyordu —
yani "ekstra adımlarla araba kullanmak". Ölçüldü: Pendik→Taksim'de hibrit
**7.488 g**, düz sürüş **5.614 g** idi; araç bacağı 45,3 km çıkıyordu çünkü
otopark başlangıca 33,3 km, hedef ise 28,4 km uzaktaydı — **yolcu hedefi geçip
geri dönüyordu**. Dolambaç toleransı 1,6 → **1,25** çekildi, "hedeften uzağa
sürme" tamamen yasaklandı. Kapının kodda uygulanan hâli
(`routes.py:746-749`): **araçtan %20+ temiz VE (toplu taşımadan %15+ hızlı
VEYA araçtan %40+ temiz)**. Dolu otopark asla önerilmez.

Sonuç: kötü öneriler elendi (Pendik→Taksim, Mecidiyeköy→Kadıköy artık hibrit
sunmuyor), özellik ölmedi — 10 uzun rotanın **7'sinde** hâlâ sunuluyor ve
hepsi iki koşulu da sağlıyor.

**Arayüz — moda göre filtre.** Karbon kartından bir mod seçilince aşağıdaki
liste, adım adım panel ve **harita** yalnızca o moda göre çiziliyor:
araç → OSRM sürüş çizgisi; hibrit → araç bacağı + İSPARK işaretçisi + toplu
bacağın tam güzergâhı. Hibritin toplu bacağı artık toplu taşımayla **aynı
detayda** (hat, bekleme, canlı ETA, trafik gecikmesi) — uç `toplu_rota` ile
tam rota nesnesini taşıyor.

**Doğrulama:** 72 bağımsız kontrol, 72/72 geçti (katsayı türetimi + uç yanıt
tutarlılığı). Yanıt süresi ~2,6 sn.
