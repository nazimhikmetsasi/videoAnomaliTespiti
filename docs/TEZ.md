# Tez Çıktıları — Ölçüm Tabloları ve Kaynakça

Bu belge tezin sayısal omurgasıdır: bütün tablolar tek yerde, her biri
hangi aşamada ve hangi koşulda ölçüldüğüyle birlikte. Ayrıntılı gerekçeler
`docs/DURUM.md`'de, mimari kararlar `docs/PLAN.md`'de.

**Donanım:** RTX 3050 Laptop 4 GB, Windows 11, Python 3.11, torch 2.5.1+cu121.
Görü süreci host'ta native çalışır; PostgreSQL, MongoDB, Kafka, Spark ve API
Docker'dadır.

**Kaynaklar:** IP/güvenlik kamerası donanımı yoktur. Tüm ölçümler
dizüstünün kendi kamerası ve `data/pilot/` altındaki altı klip üzerinde
alınmıştır. RTSP yolu kodda mevcuttur (`vision/source.py`) ama hiç
denenmemiştir — bu, sonuçların açık bir sınırıdır.

---

## 1. v1 / v2 karşılaştırması

| Metrik | v1 | v2 hedefi | v2 ölçülen |
|---|---|---|---|
| Panel canlı FPS | 0.67 | ≥ 20 | **26.3** (4 kamera eşzamanlı, tek süreç) |
| GPU çıkarım / kare | 2 model geçişi | 1 geçiş | 1 geçiş |
| Eşik değişimi | `.env` + restart | panelden anında | panelden, ~1 sn |
| Kanıt | 1 JPEG | mp4 klip + JPEG | mp4 + JPEG |
| Anomali sınıfı sayısı | 4 | 7 | 7 tanımlı; FIGHT duyarlılığı **0.80**, LOITERING ölçülemedi |
| Eşik taşınabilirliği | piksel, kameraya bağımlı | ölçek-normalize | ölçek-normalize |
| 4 GB VRAM'de kamera | 1–2 | 3–4 | **4 eşzamanlı** |
| En büyük dosya | `pipeline.py` 435 satır | < 150 satır | tutmadı: `vision/camera.py` 421 satır |
| Karar kaynağı | yalnız kural | kural + model + hibrit | hibrit F1 **0.67** > kural 0.41 |

Tutmayan tek hedef dosya boyutudur ve olduğu gibi raporlanır. LOITERING
duyarlılığı ölçülemedi (hiçbir kümede olumlu örnek yok). Gerekçeler § 6'da.

---

## 2. Aşama süreleri (tek kamera, temiz koşu)

`data/pilot/run_01.mp4` (3840x2160), 200 kare, tam kural + TCN açık,
başka iş yokken.

| Aşama | Medyan ms | p95 ms |
|---|---|---|
| ön işleme | 19.0 | 24.1 |
| çıkarım | 17.0 | 22.5 |
| takip (BoT-SORT + ReID) | 8.4 | 10.0 |
| düzleme (One-Euro) | 0.0 | 0.1 |
| öznitelik + kural | 0.2 | 2.3 |
| ↑ içinde TCN çıkarımı | 1.6 | 2.5 |
| **döngü toplam** | **44.9** | **56.5** |

Gerçek FPS 20.9. TCN hakeminin bedeli döngünün **%3.6**'sı.

### Toplu çıkarımın etkisi (960x540 kare)

| Batch | Çıkarım, kare başına ms |
|---|---|
| 1 | 14.45 |
| 2 | 12.37 |
| **4** | **10.45** |
| 8 | 10.42 |

Batch 4'ten sonra kazanç yok. Çoklu kamerada tur başına tek çağrı yapılır.

---

## 3. Çoklu kamera ölçeklenmesi

Dört pilot klip, `--loop --max-frames`, gerçek eşzamanlı koşu (kameralar
farklı anlarda biterse son kalan tek başına hızlanır ve toplam şişer).

| Kurulum | Kamera başına FPS | Toplam |
|---|---|---|
| Aşama 8.6 — 3 kamera, **ayrı süreç** | 9.3 / 13.7 / 15.1 | 38.1 |
| Aşama 10.3 — 4 kamera, **tek süreç** | 11.4 × 4 | 45.6 |
| Aşama 10.4 — 4 kamera, hızlı profil | **26.3 × 4** | **105.1** |

Hızlı profil: `--no-reid --no-clahe --imgsz 640`.

### Düğme tablosu — hız ve doğruluk birlikte

| Yapılandırma | FPS / kamera | FALL F1 | Toplam F1 |
|---|---|---|---|
| `yolo26s` + ReID + CLAHE (taban) | 11.7 | 1.00 | 0.50 |
| `s` + ReID kapalı | 15.2 | 1.00 | 0.50 |
| `s` + CLAHE kapalı | — | 1.00 | 0.50 |
| `s` + ReID/CLAHE kapalı | 17.6 | 1.00 | 0.50 |
| **`s` + ReID/CLAHE kapalı + `imgsz 640`** | **26.3** | **1.00** | **0.50** |
| `yolo26n` + ReID | 13.4 | **0.00** | 0.36 |
| `n` + ReID kapalı | 19.2 | **0.00** | — |
| `n` + ReID/CLAHE kapalı | 27.2 | **0.00** | 0.40 |

Doğruluk `eval/pilot_eval.py` ile, saniye bazlı gerçek referansa karşı.

**Bulgu:** `yolo26n-pose` hız kazandırır ama FALL sınıfını tamamen kaybeder.
Planın 1. riski "çoklu kamerada `n`'e düşülür" diyordu; ölçüm bunu
çürüttü. Hız küçük modelden değil ReID, CLAHE ve `imgsz`'den alınmalıdır.

`imgsz 640`'ın küçük/uzak insanı kaçırma riski ayrıca ölçüldü: CASIA
klipleri (kişi kare yüksekliğinin ~%24'ü) pozlu kare oranı %47.6 → %54.1,
yani kaçırmıyor.

---

## 3.5 Uzun koşu dayanıklılığı (8 saat, 4 kamera)

`scripts/soak_test.py`, 60 saniyede bir ölçüm, 459 ölçüm, kesintisiz.
Kameralar: `webcam_01` (dizüstü kamerası), `zone_01`, `run_01`, `fall_01`.

| metrik | ilk saat | son saat | değişim |
|---|---|---|---|
| toplam FPS | 33.2 | 33.4 | +0.6% |
| en düşük kamera FPS | 8.2 | 8.3 | +0.7% |
| çıkarım süresi | 13.9 ms | 14.0 ms | +0.5% |
| görü süreci RSS | 5804 MB | 6005 MB | +3.5% |
| GPU belleği | 791 MB | 898 MB | +13.6% |
| depolama | 7382 MB | 17785 MB | +141% |

Olay sayısı 1216 → 1722 (8 saatte 506 yeni olay).

**FPS ve çıkarım süresi sekiz saat boyunca sapmadı** — %1'in altındaki
değişim ölçüm gürültüsüdür.

GPU belleğindeki %13.6, saatlik kırılıma bakınca sızıntı değil:

| saat | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| GPU MB | 791 | 864 | 899 | 898 | 898 | 898 | 898 | 898 |
| RSS MB | 5804 | 5694 | 5805 | 5866 | 5895 | 5994 | 5985 | 6005 |

GPU üçüncü saatte 898 MB'de oturur ve kalan beş saat oynamaz; artış CUDA
tahsis ön belleğinin ısınmasıdır. RSS'te saatte ~25 MB'lik salınımlı bir
sürüklenme vardır (8 saatte +201 MB). Sekiz saatte sızıntı *görülmedi*;
daha uzun koşu ölçülmediği için "sızıntı yok" iddia edilmez.

Ölçülen tek gerçek engel **disktir**: saatte 1.3 GB, günde ~31 GB. Kanıt
kliplerinin saklama politikası bu tezin kapsamı dışında bırakılmıştır.

---

## 3.6 Kanıt saklama politikası

Uzun koşunun ölçtüğü tek işletim engeli deponun sınırsız büyümesiydi:
saatte 1.3 GB, günde ~31 GB. `vision/retention.py` iki kuralı birlikte
uygular.

| kural | varsayılan | gerekçe |
|---|---|---|
| klip yaşı | 7 gün | öngörülebilir saklama süresi |
| kare yaşı | 90 gün | Mongo `pose_sequences` TTL indeksiyle aynı |
| toplam boyut tavanı | 20 GB | diski kesin sınırlar |

Tek başına yaş kuralı diski sınırlamaz (yoğun bir haftada 7 × 31 =
217 GB); tek başına boyut tavanı saklama süresini öngörülemez yapar.
Tavan aşıldığında yalnız klipler silinir (en eskiden başlayarak);
kareler deponun yalnızca %3'üdür ve silinmeleri tavanı kurtarmazken
panelin görsel geçmişini götürür.

Silinen yalnızca dosyadır: `events` satırı, `clip_path` alanı ve
`pose_sequences` belgeleri yerinde kalır, dolayısıyla bu tezde raporlanan
olay sayıları ve metrikler saklama politikasından etkilenmez.

**Ölçülen sınır:** tavan anlık değil ortalamadır. Budama 60 saniyede bir
koşar; arada yazılan klipler tavanın üstüne çıkar. Ölçülen büyüme hızıyla
aşım 60 saniyede ~22 MB'dır, 20 GB tavanın binde biri.

---

## 3.7 Uçtan uca alarm gecikmesi

Gecikme `events` tablosunun kendi damgalarından hesaplanır: `started_at`
(anomalinin başlangıcı), `ended_at` (bitişi) ve `created_at` (olay
satırının veritabanına yazılması). Üç sayı ayrı raporlanır; en anlamlısı
anomali bittikten sonra alarma kalan süredir.

`data/pilot/fall_01.mp4`, gerçek zamanlı akıtma, 4 olay:

| ölçüt | medyan | en düşük | en yüksek |
|---|---|---|---|
| tespit → alarm | **13,99 sn** | 12,74 | 15,09 |
| toplam (ilk kanıttan) | 14,03 sn | 12,77 | 15,13 |

**Bu sürenin 5 saniyesi tasarım gereğidir ve kısaltılamaz:** Apache Spark
oturum penceresi 3 saniyelik sessizlikten sonra kapanır ve su işareti
(watermark) 2 saniyedir. Kalan yaklaşık 9 saniye Spark mikro-yığın
gecikmesi ile tüketici süresidir; akış sorgusuna açık bir tetikleyici
(`trigger`) verilmediğinden Spark varsayılan davranışla, önceki yığın
tamamlanır tamamlanmaz yeni yığını işler ve kullanılan donanımda yığın
başına süre saniyeler mertebesindedir. Bu iki bileşenin ayrımı ayrıca
ölçülmemiştir.

**Operatörün gördüğü ilk uyarı bu değildir.** Panelin canlı görüntü katmanı
aday anomalileri (`pre_alarms`) her karede WebSocket üzerinden alır; aday
uyarısı operatörün ekranında saniyenin altında belirir. Yukarıdaki 13,99
saniye, **doğrulanmış olayın** veritabanına yazılıp bildirime dönüşme
süresidir. İki sayı farklı şeyleri ölçer ve karıştırılmamalıdır.

### Ölçümün geçerlilik şartı

Dosya kaynağında olay zaman damgası sahne zamanından türer
(`epoch_base + kare_indeksi / FPS`). Dosya diskin izin verdiği hızda
okunursa sahne zamanı duvar saatinden kayar ve bu kayma doğrudan
"gecikme" olarak raporlanır. Bu nedenle ölçüm yalnızca kaynağın **kendi
kare hızında** akıtıldığı koşularda geçerlidir; kaynak bu hızda
akıtılamazsa ölçüm otomatik olarak geçersiz işaretlenir (gecikmenin koşu
boyunca büyümesi sınanır).

Kullanılan donanımda 3840x2160 çözünürlüklü kaynak kendi kare hızında
işlenememektedir; bu çözünürlükte gecikme ölçülememiştir.

---

## 4. Karar katmanı — kural / model / hibrit ablation

Aşamanın onay kriteri. `eval/tcn_eval.py`, üç mod × iki küme. **Tek ortalama
verilmez**, çünkü alan farkı ancak iki tabloyu ayrı tutunca görünür.

### 4.1 Holdout klipler (eğitim dışı, klip bazlı)

| Mod | TP | FP | FN | Kesinlik | Duyarlılık | F1 |
|---|---|---|---|---|---|---|
| kural | 13 | 6 | 31 | 0.68 | 0.30 | 0.41 |
| model | 25 | 6 | 19 | **0.81** | 0.57 | **0.67** |
| hibrit | **28** | 12 | **16** | 0.70 | **0.64** | **0.67** |

Tip bazında F1:

| Tip | kural | model | hibrit |
|---|---|---|---|
| FALL | 0.53 | 0.67 | **0.78** |
| RUN | 0.50 | **0.55** | 0.48 |
| FIGHT | 0.12 | **0.75** | **0.75** |

FIGHT'taki sıçrama Aşama 11'de ölçülen bir kök nedenin düzeltilmesinden
geliyor. Kuralın "karşılıklı uzuv hızı" şartı kavgayı normal hareketten
**ayırmıyor** (0.5 ve üstü her eşikte NORMAL oranı daha yüksek), ve hakem
modelin FIGHT oyunu bu çalışmayan kuralın onayına bağladığı için model
FIGHT'ı hiç üretemiyordu. Yakınlık şartı ayrıldı: model artık iz yakın bir
çiftin parçasıysa tek başına FIGHT üretiyor. Duyarlılık **0.07 → 0.80**.

### 4.2 Pilot klipler (üretim alanı, 1080p ve 4K)

| Mod | TP | FP | FN | Kesinlik | Duyarlılık | F1 |
|---|---|---|---|---|---|---|
| kural | 3 | 24 | 1 | 0.11 | 0.75 | 0.19 |
| model | 1 | 15 | 3 | 0.06 | 0.25 | 0.10 |
| hibrit | 4 | 39 | 0 | 0.09 | **1.00** | 0.17 |

**Alan farkı:** holdout'ta kesinliği 0.93 olan model, pilot kliplerde 12
sahte FALL üretir. 320x240 güvenlik kaydıyla eğitilmiş model 1080p/4K
görüntüde yanılır.

Bu tablodaki FP'lerin çoğu ZONE_VIOLATION'dır ve bunlar **Spark öncesi ham
adaylardır**; üretimde `min_hits` + `min_sec` süzgeci bu gürültüyü eler.

### 4.3 TCN modeli

5 bloklu genişletilmiş nedensel Conv1d, **66 116 parametre**, alım alanı 63
kare. Girdi: iz başına 50 karelik pencere, kare başına 53 kanal (17 keypoint
bbox-normalize x/y, 17 güven, centroid hızı). Bölme klip bazlı %80/%20.

| Sınıf | Kesinlik | Duyarlılık | F1 | Doğrulama penceresi |
|---|---|---|---|---|
| NORMAL | 0.802 | 0.722 | 0.760 | 540 |
| FALL | 0.524 | 0.620 | 0.568 | 71 |
| RUN | 0.704 | 0.974 | 0.817 | 39 |
| FIGHT | 0.615 | 0.686 | 0.649 | 226 |
| **makro F1** | | | **0.698** | |

Pencere başına çıkarım **1.20 ms**.

Etiket düzeltmesinin ölçülen etkisi: URFD düşme klibinin ~%40'ı düşme öncesi
yürüyüştür ve başlangıçta bunlar da FALL etiketi alıyordu. Kaynağın kendi
kare bazlı etiketi kullanılınca FALL kesinliği **0.300 → 0.524**, makro F1
0.672 → 0.698.

---

## 4.4 Alan farkının kaynağı — ölçülmüş açıklama

§4.2'de görülen yanlış pozitiflerin "farklı çözünürlük" ile açıklanması
sınanmıştır, çünkü sınıflandırıcının girdisi zaten ölçek-normalizedir:
iskelet koordinatları sınır kutusuna, hız sınır kutusu yüksekliğine
bölünür. Çözünürlük tek başına bu kanalları değiştirmez.

**Girdi dağılımlarında anlamlı kayma yoktur.** Eğitim ve pilot pencereleri
kanal grubu bazında karşılaştırıldığında, girdinin %32'sini oluşturan
keypoint güveni dahil olmak üzere dağılımlar örtüşmektedir:

| kanal grubu | eğitim | pilot |
|---|---|---|
| iskelet x/y (normalize) | 0,503 | 0,535 |
| keypoint güveni | 0,770 | 0,738 |

**Yanlış pozitifler karar eşiğinin hemen üstünde yoğunlaşır.** Modelin
pilot pencerelerdeki NORMAL tahminlerinin ortalama olasılığı 0,853 iken,
NORMAL dışı tahminlerinki 0,586–0,697 aralığındadır; kullanılan eşik
0,60'tır. Eşik taraması (doğrulama kümesi klip bazında ayrılmıştır):

| eşik | duyarlılık | pilot yanlış alarm |
|---|---|---|
| 0,50 | 0,708 | 23 |
| **0,60** | **0,613** | **18** |
| 0,70 | 0,524 | 12 |
| 0,75 | 0,479 | 8 |
| 0,90 | 0,292 | 3 |

Eşiğin 0,60'tan 0,75'e çıkarılması pilot yanlış alarmlarını %56, buna
karşılık duyarlılığı %22 azaltmaktadır; takas oranı taranan bütün aralıkta
yaklaşık 2,4:1 düzeyinde sabit kalmaktadır.

Bu sabitlik belirleyicidir. Yanlış pozitifler yalnızca yanlış kalibre
edilmiş, eşiğin hemen üstüne yığılmış kararlar olsaydı, eşik yükseltildikçe
hızla yok olur ve duyarlılık büyük ölçüde korunurdu. Her iki büyüklüğün de
düzenli biçimde azalması, sınıf skorlarının pilot alanda **iç içe geçtiğini**
göstermektedir: model bu alanda sınıfları ayırt edememektedir. Dolayısıyla
eşik bir çalışma noktası tercihidir, çözüm değildir; çözüm pilot alandan
eğitim verisi eklemektir.

Bu çalışmada eşik 0,60'ta bırakılmıştır; raporlanan bütün tablolar bu
çalışma noktasında üretilmiştir.

---

## 5. Eğitim veri kümesi

1080 klip, 193 MB. `scripts/fetch_datasets.py` ile yeniden üretilebilir.

| Sınıf | Klip | Pencere | Kaynak dağılımı |
|---|---|---|---|
| NORMAL | 600 | 2726 | casia, bitint, utint, ucarg (yer kamerası), URFD adl |
| FALL | 66 | 262 | casia 36 + URFD fall 30 |
| RUN | 144 | 195 | casia `run` 48 + ucarg ground 96 |
| FIGHT | 270 | 1236 | bitint 150 + utint 60 + casia 12 + ucarg ground 48 |

Kaynak seçimi klipler **açılıp bakılarak** yapıldı; elenenler ölçümle elendi:
`virat` (64x64 piksel kırpma, kişi görünmüyor), `uccrime` (kesilmemiş, süre
medyanı 92.7 sn), `okutama`/`ucaerial`/`ucarg _aerial_` ve `_rooftop_` (kuş
bakışı), `caviar`/`livevid` (kesilmemiş), `casia _jump_` (eylem zıplama).

38 klip kaynağında bozuktur (`moov atom not found`); yerel dosya boyutları
depodakiyle birebir aynıdır, yani indirme kesintisi değildir.

---

## 6. Tutmayan hedefler ve açık sorular

Bunlar gizlenmez; tezin dürüstlüğü buradadır.

| Konu | Durum |
|---|---|
| **FIGHT duyarlılığı** | **Düzeltildi: 0.07 → 0.80** (Aşama 11). Kök neden `HOLD` değil öznitelikti: uzuv hızı FIGHT'ı NORMAL'den ayırmıyor. Kural yolu hâlâ 0.12'dedir ve öyle kalır — kavgayı model tespit eder |
| **LOITERING duyarlılığı** | Ölçülemedi — geçerli olumlu örnek yok. Kural önce pratikte hiç tetiklenmiyordu (sınır titremesi, Aşama 12.6, düzeltildi); sabit kamerada 5 pilot klipte yanlış pozitif sıfır |
| **Model pilot alanda 12 sahte FALL** | Kaynağı ölçüldü (§4.4): girdi kayması değil, model bu alanda sınıfları ayıramıyor. Çözüm pilot alandan eğitim verisi |
| **Uçtan uca alarm gecikmesi** | Ölçüldü (§3.7): medyan 13.99 sn. Dizüstü kamerasıyla değil, gerçek zamanlı akıtılan pilot klibiyle |
| **ReID kalitesi** | Kalabalık sahnede ID değişimi hiç ölçülmedi; pilot kliplerde en fazla 1–2 kişi var ve `--no-reid` sonucu hiç değiştirmedi |
| **En büyük dosya < 150 satır** | Tutmadı: `vision/camera.py` 421 satır. Aşama dosyaları hedefte, kamera hattının kendisi değil |
| **RTSP** | Kod yolu var, donanım yok, hiç denenmedi |
| **Hareketli / PTZ kamera** | Bölge kuralları (ZONE_VIOLATION, LOITERING) görüntü koordinatında tanımlıdır ve yalnızca sabit kamerada anlamlıdır. Ölçüldü: elde taşınan kamerayla çekilmiş pilot klipte kişi yürürken LOITERING tetiklendi (değerlendirme penceresi dışında, tabloya girmez) |
| **8 saat kesintisiz koşu** | Yapıldı (§3.5): 8.0 saat, 4 kamera, FPS sapması +0.6%. Diskin sınırsız büyümesi saklama politikasıyla kapatıldı (§3.6) |

---

## 7. Kaynakça

### Veri kümeleri

Eğitim verisi SPHAR üzerinden toplanmıştır; SPHAR kendisi on bir ayrı
kümenin derlemesidir. Bu projede kullanılan alt kaynaklar ve lisansları:

- **SPHAR** — Melde, A. (2020). *Surveillance Perspective Human Action
  Recognition Dataset.* github.com/AlexanderMelde/SPHAR-Dataset. Derleme ve
  betikler GNU GPL v3; videolar özgün kaynaklarının lisansına tabidir.
- **CASIA Action Database** — Institute of Automation, Chinese Academy of
  Sciences. Yazar izniyle kullanım.
- **BIT-Interaction** — Kong, Y., Jia, Y., Fu, Y. (2012). *Learning Human
  Interaction by Interactive Phrases.* ECCV. Ticari olmayan kullanım.
- **UT-Interaction** — Ryoo, M. S., Aggarwal, J. K. (2010). *UT-Interaction
  Dataset*, ICPR contest on Semantic Description of Human Activities (SDHA).
  MIT lisansı.
- **UCF-ARG** — UCF Center for Research in Computer Vision. Yalnızca
  araştırma amaçlı kullanım. Bu projede yalnız **yer kamerası** görüntüleri
  kullanılmıştır.
- **UR Fall Detection (URFD)** — Kwolek, B., Kepski, M. (2014). *Human fall
  detection on embedded platform using depth maps and wireless
  accelerometer.* Computer Methods and Programs in Biomedicine, 117(3).
  Ticari olmayan akademik kullanım. Kare bazlı düşme etiketleri bu kümenin
  kendi CSV dosyalarından alınmıştır.

### Yöntem ve kütüphaneler

- **YOLO26-pose / Ultralytics** — tek geçişli kutu + iskelet çıkarımı.
- **BoT-SORT** — Aharon, N., Orfaig, R., Bobrovsky, B. (2022). *BoT-SORT:
  Robust Associations Multi-Pedestrian Tracking.*
- **TCN** — Bai, S., Kolter, J. Z., Koltun, V. (2018). *An Empirical
  Evaluation of Generic Convolutional and Recurrent Networks for Sequence
  Modeling.*
- **One-Euro filtresi** — Casiez, G., Roussel, N., Vogel, D. (2012). *1€
  Filter: A Simple Speed-based Low-pass Filter for Noisy Input in
  Interactive Systems.* CHI.
- **Apache Kafka**, **Apache Spark Structured Streaming**, **FastAPI**,
  **PostgreSQL**, **MongoDB**, **OpenCV**, **PyTorch**.

> Künye ayrıntıları (cilt, sayfa, DOI) teze girmeden önce özgün yayından
> doğrulanmalıdır; buradaki liste hangi çalışmanın atfedileceğini gösterir,
> biçimlendirilmiş kaynakça değildir.
