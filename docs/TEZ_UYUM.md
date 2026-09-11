# Tez Belgeleri ile Kod Arasındaki Uyum Denetimi

Kaynak belgeler: `TEZ FİNAL RAPORU` (2026-06-14), `tez planlama.docx`
(16 haftalık plan), `TEZ_KAPSAM.txt` (v1 faz haritası),
`TEST_CHECKLIST.txt` (v1), `tez projesi eklenebilecek geliştirilebilcek
şeyler.docx` (öneri listesi).

Denetlenen kod: bu depo (v2), commit `8b62803`.

Üç ayrı uyumsuzluk türü var ve **karışmamaları önemli**:

- **(A) Farklı teknoloji seçimi** — tez metni X diyor, kod Y yapıyor. Kod
  genelde daha iyi ama tez metni güncellenmezse jüri haklı olarak
  "yazdığını yapmamışsın" der.
- **(B) Tezde yazılı ama üretilmemiş sayı** — en riskli grup.
- **(C) Kapsamda olup hiç yapılmamış modül.**

---

## A. Tez metni ile kodun ayrıştığı teknoloji seçimleri

| Konu | Tez metni ne diyor | Kod ne yapıyor | Değerlendirme |
|---|---|---|---|
| İskelet çıkarımı | **MediaPipe Pose, 33 eklem** (Bölüm 2.3, Tablo 3.1, Tablo 4.1) | YOLO26-pose, **COCO-17** | En büyük ayrışma. Tez MediaPipe'ı ayrı bir başlıkta savunuyor. Kod tek modelle kutu+iskelet çıkarıyor, v1'deki iki model geçişini eliyor |
| Nesne takibi | **DeepSORT** (Tablo 4.1'de gerekçesiyle seçilmiş) | **BoT-SORT** + ReID + kamera hareketi telafisi | BoT-SORT DeepSORT'un üstü; ama tezde DeepSORT seçimi gerekçelendirilmiş |
| Nesne tespiti | YOLOv8 | YOLO26 | Küçük ayrışma, `yolov8s-pose.pt` hâlâ ablation için duruyor |
| Panel | **React + Tailwind** (14. hafta) | Düz HTML + Tailwind CDN, derleme adımı yok | Şablon kullanıcı tarafından verildi; React'e taşımak 11 ekranı elden yeniden yazmak demekti |
| Kafka'nın taşıdığı veri | **Ham kareler, Base64, `video-stream` topic'i** (2. hafta, Tablo 3.2) | Yalnız **aday olay metadatası**, `anomaly-candidates` | Mimari olarak daha doğru (kare taşımak bant genişliğini boşa yakar) ama tez metni kare taşıdığını söylüyor |
| Kare boyutu | 640x480 | 960x540 letterbox | Ölçüldü, gerekçesi `docs/DURUM.md`'de |
| Python | 3.10 | 3.11 | Önemsiz |
| Veri sözlüğü (EK D.1) | `detected_person_id`, `confidence_score`, `ai_generated_report`, `timestamp` | `track_ids INT[]`, `confidence`, `llm_report_tr`, `started_at`/`ended_at` | İçerik aynı, **isimler farklı**. Tezdeki tablo ya güncellenmeli ya sütunlar yeniden adlandırılmalı |

**Öneri:** hiçbirini geri almayın. Tez metnine "Yöntem Değişiklikleri ve
Gerekçeleri" diye bir alt bölüm eklemek, her satır için ölçüm göstermek
(hepsi `docs/TEZ.md`'de var) akademik olarak **daha güçlüdür** — çünkü
ölçüme dayalı karar değişikliği, plana körlemesine uymaktan iyidir.

Tek istisna veri sözlüğü: sütun adlarını tezdeki adlara çekmek ucuz bir
düzeltme, tercih meselesi.

---

## B. Tezde yazılı olup kodun üretmediği sayılar

Bu grup gerçek risk taşıyor.

| Tezde geçen | Değer | Kodun durumu |
|---|---|---|
| MAE (eklem koordinat hatası) | 0.1245 | **Üretilemez.** Gerçek referans eklem koordinatı yok; pilot klipler saniye bazlı olay etiketli, kare bazlı keypoint etiketli değil |
| MSE | 0.0467 | Aynı sebeple üretilemez |
| RMSE | 0.2161 | Aynı sebeple üretilemez |
| R² (belirlilik katsayısı) | 0.9412 | **Üretilemez.** Regresyon modeli yok; sistem sınıflandırma yapıyor |
| Yanlış alarm oranı < %10 hedefi | 5.1 | **Tutmuyor:** pilot kümede kural kesinliği 0.11, yani ham aday düzeyinde yanlış alarm oranı çok yüksek. Spark süzgecinden sonraki oran ayrıca ölçülmedi |
| "FPS ~30" beklentisi | 1. satır | 4 kamerada **26.3**, tek kamerada 20.9–33.5 (klip çözünürlüğüne göre) — hedefe yakın, ölçülü |

Raporun 4.1 bölümü bu dört istatistiği "elde edilen bulgular" diye
sunuyor. Rapor "Profesyonel Yazılım Geliştirme I" dönemine ait ve o dönem
sistem henüz kodlanmamıştı (4.4 bunu açıkça söylüyor: "gelecek dönem
fiziksel olarak kodlanması"). Yani bu sayılar **simülasyon/literatür
değerleridir.**

**İki dürüst yol var:**

1. **Metrikleri değiştir.** Kodun gerçekten ürettiği metrikler
   precision / recall / F1 / karışıklık matrisi / ablation ve bunların
   hepsi ölçülmüş durumda (`docs/TEZ.md`). Tez metninde MAE/MSE/RMSE/R²
   yerine bunlar konur ve "birinci dönem tasarım aşamasında kestirilen
   regresyon metrikleri yerine, uygulama aşamasında sınıflandırma
   metrikleri ölçülmüştür" denir.
2. **Metrikleri gerçekten üret.** Bunun için kare bazlı keypoint gerçek
   referansı gerekir. Böyle bir küme var (örn. COCO-val pose) ama o zaman
   ölçtüğünüz şey sizin sisteminiz değil, Ultralytics'in modelidir.

**Önerim 1. yol.** 2. yol emeğe değmez ve ölçtüğü şey tezin katkısı değil.

---

## C. Kapsamda olup hiç yapılmamış modüller

`TEZ_KAPSAM.txt` üç faz tanımlıyor:

| Faz | Kapsam | v2'deki durum |
|---|---|---|
| Faz 1 | RUN, FALL, ZONE_VIOLATION, RUN_ZONE | **Tamam** ve üstüne çıkıldı: 7 sınıf tanımlı, FIGHT/LOITERING/WRONG_DIRECTION eklendi |
| Faz 2 | **Kişi ayırt: bilinen yüz / izin listesi**, "Evde / Koruma" modu, kritik filtre | **Hiç yok.** Kodda `face`, `person_id`, `armed` diye bir şey yok |
| Faz 3 | Olay sınıfı / aksiyon tanıma | **Kısmen:** TCN sınıflandırıcı + hibrit hakem var (Aşama 9), FIGHT/LOITERING tanımlı ama FIGHT duyarlılığı 0.07 |

Faz 2 kapsamda "AKTİF" işaretli ama v2'de karşılığı yok. Bu, tez
metninde ya kapsam dışı ilan edilmeli ya yapılmalı.

---

## D. Öneri belgesindeki fikirler — hangisi var, hangisi yok

| Öneri | Durum |
|---|---|
| Poligon ROI (Shapely) | **Var** — `zones` tablosu + `cv2.pointPolygonTest`, kameraya bağlı normalize poligon. Shapely yerine OpenCV kullanıldı, ek bağımlılık yok |
| Düşme için 3 metrik (omurga açısı, dikey hız, en/boy oranı) | **Üçü de var** — `FrameFeatures.body_tilt`, `norm_vy`, `aspect` |
| Ölçek-normalize eşikler | **Var** ve v1'e göre asıl kazanç bu (hız ÷ bbox yüksekliği) |
| Modül başına gecikme dağılımı | **Var ve ölçüldü** — `docs/TEZ.md` § 2 |
| Ablation çalışması | **Var** ama önerilen eksende değil: öneri "hafif poz sezgiseli vs ağır 3D-CNN" diyor, yapılan "kural vs TCN vs hibrit" |
| Olay tetiklemeli (event-driven) ReID + durum makinesi | **Yok.** ReID her karede çalışıyor. Ölçüldü: takip aşaması kare başına 8.4 ms ve ReID'yi kapatmak 4 kamerada 11.7 → 15.2 FPS kazandırıyor. Yani önerinin işaret ettiği tasarruf **gerçek ve ölçülü** |
| Qdrant vektör veritabanı + tekrar giriş tespiti | **Yok.** `docs/DURUM.md`'de "kadrajdan çıkıp geri giren kişi yeni ID alıyor" diye açık soru olarak duruyor |
| "En iyi kare" seçimi (Laplacian bulanıklık) | **Yok** |
| Homografi / kuşbakışı düzlem dönüşümü | **Yok.** Aynı sorunu (perspektif) ölçek-normalizasyonla çözüyoruz; homografi daha güçlü ama kamera kalibrasyonu ister |
| Kosinüs eşik taraması (0.65/0.75/0.85) | **Yok** — ReID eşiği hiç taranmadı |
| UCF-Crime / ShanghaiTech | Bilinçli **elendi** — ölçüldü: `uccrime` klipleri kesilmemiş, süre medyanı 92.7 sn, pencere etiketi anlamsız olurdu |
| UR Fall Detection | **Kullanıldı** — üstelik kümenin kendi kare bazlı etiketiyle |
| Market-1501 / MSMT17 | **Yok** — ReID doğrulaması hiç yapılmadı |

---

## E. Sıralı öneri listesi

Tez değeri ÷ emek oranına göre:

**1. Tez metnindeki metrikleri gerçekle değiştir (emek: düşük, değer: çok yüksek).**
MAE/MSE/RMSE/R² yerine ölçülmüş precision/recall/F1/ablation. Bütün
tablolar `docs/TEZ.md`'de hazır. Bu yapılmazsa jüri üretilemeyen bir sayı
sorabilir.

**2. "Yöntem değişiklikleri ve gerekçeleri" bölümü yaz (emek: düşük, değer: yüksek).**
MediaPipe→YOLO-pose, DeepSORT→BoT-SORT, React→düz panel, Kafka'da kare
yerine metadata. Her biri için ölçüm var. Plana uymamak değil, **ölçerek
karar değiştirmek** anlatılır.

**3. Olay tetiklemeli ReID + kosinüs eşik taraması (emek: orta, değer: yüksek).**
Öneri belgesinin en güçlü fikri ve v2'nin açık sorusuyla birebir örtüşüyor
("kadrajdan çıkıp geri giren kişi yeni ID alıyor"). Ölçülecek şey hazır:
ReID kapalı/açık FPS farkı zaten ölçüldü (11.7 → 15.2). Qdrant şart değil,
kişi sayısı küçükken NumPy kosinüs araması yeter — ek servis eklemeden
aynı akademik katkı çıkar.

**4. FIGHT duyarlılığını düzelt (emek: orta, değer: yüksek).**
0.07 tezde açıklanması zor bir sayı. Kök neden ölçüldü: kural üç kare üst
üste şart arıyor, eğitim klipleri 2–3 saniye. `HOLD` düşürüp yeniden
ölçmek birkaç saatlik iş.

**5. Faz 2 (bilinen kişi / izin listesi) kararı (emek: yüksek).**
Ya yapılır ya tezde açıkça kapsam dışı ilan edilir. Kapsam belgesinde
"AKTİF" yazdığı için sessiz bırakmak en kötü seçenek.

**6. Homografi / kuşbakışı (emek: yüksek, değer: orta).**
Kamera kalibrasyonu ister, elde kalibrasyon verisi yok. Ölçek-normalize
eşikler aynı sorunu kısmen çözüyor. Tezde "alternatif yaklaşım ve neden
seçilmediği" olarak anılması yeterli.

**7. Veri sözlüğü sütun adları (emek: çok düşük, değer: düşük).**
`confidence` → `confidence_score`, `llm_report_tr` → `ai_generated_report`
yapılabilir; ya da tezdeki EK D.1 tablosu güncellenir. İkincisi daha ucuz.
