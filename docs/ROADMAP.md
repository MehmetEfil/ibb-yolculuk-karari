# Erişilebilir İstanbul — Yol Haritası

> Sunum: 1 Ağustos 2026 Cumartesi
> Ürün tanımı ve kararlar için: `INTENT.md`

## Takvim

```
Pazartesi 27  ✅ ETA motoru onarıldı (5 hata), dokümanlar yazıldı
Salı      28  ← geliştirme
Çarşamba  29  ← geliştirme
Perşembe  30  entegrasyon + test · FEATURE FREEZE
Cuma      31  slaytlar, yedek demo videosu, 2 prova
Cumartesi  1  SUNUM
```

**İki tam geliştirme günü var.** Her fikir bu ölçüye vurulur.

---

## Durum

### ✅ Çalışıyor
- 44 canlı uç, İBB/İETT servislerine bağlı
- Operasyon haritası — canlı araç, durak, güzergâh, trafik, duyurular
- Yol tarifi — direkt ve 1–4 aktarmalı rota, harita üzerinde çizim
- **Metrobüs artık kullanılıyor** — iki kademeli havuz (yüksek kapasiteli hat
  1,50 km) + yürüyerek aktarma indeksi. Avcılar→Zincirlikuyu 121 → 55 dk,
  Bakırköy→Üsküdar 160 → 81 dk
- **Yön kesinleşti** — servisin `YON` + `SIRANO` verisi kullanılıyor,
  geometriden çıkarım yapılmıyor. 837 hat kapsanıyor, eksik 0
- **Karbon ayak izi** — araç/toplu/hibrit, İSPARK park-and-ride, moda göre
  filtreli harita ve adım adım panel
- **Profil + Geçmiş Seferler** (konsept) — değerlendirme, doğruluk kontrolü,
  10 değerlendirme = 1 ücretsiz biniş, kurum görünümü
- **ETA motoru onarıldı:** 5 hata düzeltildi. 45.102 gerçek seferle yeniden
  doğrulandı: medyan oran 0,998 · ±%20 içinde **%84** (eski belgede yazan
  %93,2 doğrulanamadı)
- 735 hat için kalibre edilmiş süre profili (`data/hat_profil.json`) +
  aykırı değer koruması (33 hattın durak sayısı, 22 katsayı düzeltildi)

### ❌ Kaldırıldı
- **Analiz sekmesi** — ürün yönüyle uyumsuz olduğu için çıkarıldı
  (30 Tem 2026). Geçici `*.analiz_yedek` dosyaları sonradan silindi.

### ✅ Tamamlandı — araç yönü saha testi
- **31 Tem 2026'da yapıldı**: 4 hat, 87 araç, 130 sn arayla iki ölçüm.
  `guzergahkodu`'ndan okunan yön araçların `SIRANO` ilerlemesiyle **86/87**
  uyumlu. Detay: `CLAUDE.md` → "Araç yönü — SAHA TESTİ YAPILDI".

### ✅ Demoya alınan ürün katmanı
- **Hat performansı** — açıklanabilir skor ve hat detayı
- **Karbon ayak izi + İSPARK hibrit rota**
- Rota içinde erişilebilir durak uyarıları
- **Hesabım + Yolculuklarım** konsept ekranları
- Geri bildirim gruplama ve kurum içi özet görünümü

### ⏳ Sonraki aşama
- İlçe bazlı erişilebilirlik haritası
- Gerçek İstanbulkart entegrasyonu
- Canlı AI yorum sınıflandırması ve kurum iş emri bağlantısı

---

## P0 — Salı sabahı

| # | İş | Süre | Neden |
|---|---|---|---|
| 0.1 | ~~Yön düzeltmesi~~ ✅ **bitti** | — | 34AS'te 1/5 → 5/5 |
| 0.2 | Sefer iptalini ETA'ya bağla | 1 saat | %4,03 sefer hiç yapılmıyor, yolcu boşuna bekliyor |
| 0.3 | Duyuru + kaza katmanını ETA'ya bağla | 2 saat | Mazeret cümlesinin "olay" bacağı; veri hazır |
| 0.4 | Merkezi yoklama mimarisi | 1 saat | Saatte 100 istek sınırı — sunumda çökmesin |

---

## P1 — ✅ **BİTTİ** (31 Tem 2026)

**Güvenilirlik skoru + Hat Karnesi.** `skor.py` + `/api/hat_skoru` +
🏅 Hat Karnesi sekmesi.

Ölçüm (29 Tem arşivi, 51.972 sefer): **732 hat puanlandı**, ortalama 64,2 ·
medyan 66,2 · aralık 5,4–100. Harf dağılımı A=75 · B=230 · C=228 · D=117 ·
E=82 — yani skor gerçekten ayırt ediyor. Karşılaştırma: dakiklik %91,5'te
düz kalıyordu.

Örnek: **129T** (Bostancı-Taksim) 5,4 puan / 732. sıra — yayılım %115
(aynı yolculuk 42,6 dk da sürüyor 108,9 dk da), 48 seferin 12'si yapılmamış,
araçlar kümeleniyor. **34G** 72,8 (B, 245. sıra) — süre tutarlılığı 44,8/45
ama düzenlilik 3,9/25, çünkü metrobüs araçları kümeleniyor (2,1 dk aralık,
0,67 sapma). Skor bilinen gerçek sorunu yakalıyor.

Formül (ölçülmüş metriklerle, uydurma değil):

```
Skor = 45 × süre_tutarlılığı      (p90−p10)/medyan · %7,9–258,0 aralığında
     + 30 × sefer_gerçekleşme     100 − iptal oranı · %0–58,3 aralığında
     + 25 × düzenlilik            headway sapması σ/μ · medyan 0,50
```

Daha önce planlanan "dakiklik + iptal" formülü **çalışmıyordu**: dakiklik
%91,5'te düz, hiçbir hattı ayırt etmiyor. Ölçüp değiştirdik.

Çıktı: `/api/hat_skoru` ucu + hat karnesi ekranı (skor, üç alt kırılım,
zaman dilimi grafiği, "bu hat neden bu puanı aldı" açıklaması).

---

## P2 — ⚠️ **KISMEN BİTTİ** (31 Tem 2026)

**Erişilebilirlik.** Rota planlayıcıdaki uyarı ✅ yapıldı — kart tipi
`engelli` olan profilde biniş/iniş duraklarının erişilebilirlik durumu
gösteriliyor, rota elenmiyor. Harita katmanı ve ilçe kırılımı ekranı
❌ yapılmadı (veri hazır: 853/15.112 durak, Fatih %18,6 ↔ Adalar %0).

- 15.112 durağın erişilebilirlik/korunaklılık durumu haritada
- İlçe bazında oran (Çekmeköy %0,6 ↔ Fatih %18,6)
- Rota planlamada uyarı: "biniş durağın erişilebilir değil"
  (uyarı verilir, **rotadan çıkarılmaz** — gerekçe `INTENT.md` bölüm 6)

Bu katman ürünün adını doğruluyor ve eşitlik anlatısını taşıyor.

---

## P3 — Çarşamba

**Karbon ayak izi + hibrit rota** — ~1,5 gün.

- İSPARK entegrasyonu (252 otopark, canlı boş kapasite)
- Üç seçenek: araç / toplu taşıma / hibrit
- Her ayak için süre + km + CO₂, ekranda toplam
- İSPARK seçimi dengeli puanlama: süre + karbon + o anki boş yer
- Dolu otopark asla önerilmez

> **Süre kısıtı olursa** hibrit kısmı sadeleştirilir: en yakın uygun
> otopark seçilir, dengeli puanlama sonraki sürüme kalır. Karbon
> göstergesi tek başına da anlamlı.

Karbon katsayılarının kaynağı slaytta gösterilir — uydurulmaz.

---

## P4 — Perşembe gecesi · mock ekranlar

Tasarım işi, kod değil:

- Akbil ile geçmiş yolculuk listesi
- Yolculuk puanlama (hat / araç / durak / şoför ayrı + serbest yorum)
- AI yorum sınıflandırma çıktısı — **mock**, süre kısıtı nedeniyle
- Kuruma giden bildirim paneli
- Teşvik kampanyası ekranı

Hepsi "konsept" etiketiyle sunulur.

---

## Roadmap slaydına (yapılmayacak, anlatılacak)

- Şehir paneli (ilçe ısı haritası) — verisi hazır, **anlatısı riskli**:
  güvenilirlik verisi eşitsizlik değil merkez–çeper sıkışıklığı gösteriyor
  (en kötü Fatih, Beyoğlu, Şişli). Eşitlik anlatısı erişilebilirliğe taşındı.
- Tüm 837 hatta ML modeli
- Push bildirim
- Belbim entegrasyonuyla gerçek Akbil bağlantısı
- AI sınıflandırma motorunun canlıya alınması

---

## Zaman bütçesi — gerçekçi bakış

```
P0 kalanı            ~4 saat
P1 skor + karne      ~4 saat     ← pazarlıksız
P2 erişilebilirlik   ~2 saat
P3 karbon + hibrit  ~10 saat
─────────────────────────────
toplam              ~20 saat  ≈ 2,5 gün
```

Elde **2 gün** var. Yani bir şey kısılacak. Kısılacak ilk şey **P3'ün
hibrit kısmı** — karbon göstergesi kalır, İSPARK seçimi basitleşir.

**Kısılmayacak olan:** P1. Güvenilirlik skoru olmadan sunuma gidilmez,
çünkü ürünün adı o.

---

## Sunum günü riskleri

| Risk | Önlem |
|---|---|
| Canlı demo çöker | **Yedek demo videosu zorunlu** (2–3 dk) |
| Salonda kota dolar, otobüsler kaybolur | Merkezi yoklama mimarisi (P0.4) |
| "Bu sayı nereden?" sorusu | Her rakamın kaynağı hazır — `INTENT.md` kanıt defteri |
| Mock ekran gerçek sanılır | Her ekranda "konsept" etiketi |
