# Aşama 9 — TCN Modeli ve Yeni Sınıflar

Bu aşamanın işi bir sınıflandırıcı eğitmek değil, **kuralın tek karar
mercii olmaktan çıkmasını ölçülebilir kılmak.** Onay kriteri model değil
tablodur: `decided_by` üzerinden kural / model / hibrit karşılaştırması.

Boru hattının tamamı zaten hazır: `events.decided_by` sütunu ve
`CHECK (decided_by IN ('rule','model','hybrid'))` (`infra/postgres/init.sql:109`),
`detection_settings.tcn_min_conf` (`init.sql:85`), `/api/events?decided_by=`
süzgeci, `/api/analytics/ablation` ucu ve panelde kaynak kırılımı
(`frontend/js/analitik.js:133`). Aşama 9 bu boruya yalnızca üç yeni parça
takar: veri kümesi, model, hakem.

---

## 1. Veri kararı

`telemetry` koleksiyonu bu iş için kullanılamaz. İki ayrı sebep:

1. **Boş.** Yalnızca Spark'ın onayladığı olaylar yazılıyor
   (`api/workers/consumer.py:304`); `infra/mongo/init.js:13` "reddedilenler
   dahil tüm aday pencereler" diyor ama reddedilen aday tüketiciye hiç
   ulaşmıyor — Spark onu süzüyor.
2. **Etiketi kuralın kendisi koyuyor** (`consumer.py:222`, `"arbiter": "rule"`).
   Bununla eğitilen model kuralı taklit eder; kural ile model arasındaki
   ablation tablosu tanım gereği anlamsız çıkar.

Bunun yerine dış veri kümesi kullanılır ve **pozlar bizim kendi hattımızdan
çıkarılır** — böylece öznitelik uzayı üretimle birebir aynı olur, iskelet
şeması dönüştürülmez, alan farkı doğmaz.

### Kaynaklar

**SPHAR** (github.com/AlexanderMelde/SPHAR-Dataset) — 7759 klip, 14 eylem
sınıfı, 11 farklı veri kümesinden derlenmiş, hepsi güvenlik kamerası bakış
açısına kırpılmış. Klipler depoya doğrudan işlenmiş; `raw.githubusercontent.com`
üzerinden dosya dosya indirilebilir, 5.9 GB'lık depoyu klonlamak gerekmez.

**UR Fall Detection** (fenix.ur.edu.pl/~mkepski/ds/uf.html) — 30 düşme +
40 günlük yaşam etkinliği, sabit kamera, kayıtsız doğrudan indirme
(`data/fall-01-cam0.mp4` … `adl-40-cam0.mp4`, klip başına ~1.3 MB).
SPHAR'ın yer seviyesindeki düşme klipleri ince (~40 adet); URFD bu sınıfı
ikiye katlar.

### Sınıf eşlemesi (klipler görülerek doğrulandı)

| Bizim sınıf | Kaynak klasör | Kabul edilen kaynak | Klip |
|---|---|---|---|
| FALL | SPHAR `falling` | `casia` | 36 |
| FALL | URFD | `fall-NN-cam0` | 30 |
| RUN | SPHAR `running` | `casia` (yalnız `run`), `ucarg` (yalnız `_ground_`) | 144 |
| FIGHT | SPHAR `hitting` + `kicking` | `bitint`, `utint`, `casia`, `ucarg` `_ground_` | 270 |
| NORMAL | SPHAR `walking` + `neutral` | `casia`, `bitint`, `utint`, `ucarg` `_ground_` | 600'e sınırlı |
| NORMAL | URFD | `adl-NN-cam0` | 40 |

Kaynak seçimi tahminle değil **klipler açılıp bakılarak** yapıldı. Elenenler
ve gerekçeleri:

| Elenen | Gerekçe |
|---|---|
| `okutama`, `ucaerial`, `ucarg` `_aerial_` | Drone / kuş bakışı. Gövde açısı ve adım kanıtı yok |
| `ucarg` `_rooftop_` | Yüksek montaj ama çok uzak: kişi ~30 piksel |
| `virat` | SPHAR bunları anotasyon kutusuna kırpmış; klipler 64x64 – 72x142 piksel, çoğunda kişi hiç görünmüyor |
| `uccrime` | Kesilmemiş: süre medyanı **92.7 sn**, en uzunu 538.7 sn. Olay birkaç saniye; kalan yüzlerce pencere FIGHT diye etiketlenirdi |
| `caviar`, `livevid` | Aynı sebep, kesilmemiş (SPHAR "Known Caveats") |
| `casia` `_jump_` | `running` klasöründe ama eylem zıplama. RUN sınıfı saf kalsın diye elendi (48 klip) |

Kabul edilen `ucarg` klipleri UCF-ARG'ın yer kamerasıdır: sabit, göz
hizasında, kişi kadrajı net kesiyor. `ucarg` `hitting` klipleri boks
hareketidir — tek kişilik. Model zaten **iz başına** hareket sınıflandırıyor,
ikili eşleştirmeyi `FightRule` yapıyor (§ 4), dolayısıyla tek kişilik boks
doğru girdidir.

URFD klipleri 640x240 **yan yana derinlik + renk** olarak geliyor; indirme
sırasında sağ (renkli) yarı kırpılır. Kırpılmasa derinlik yarısındaki hayalet
siluet YOLO'ya ikinci bir kişi gibi görünür ve aynı olayı iki ize bölerdi.

NORMAL ham hâliyle 4966 klip, diğer üç sınıfın toplamı ~480. **NORMAL en
fazla 600 klibe indirilir** (kaynak başına eşit pay, sabit tohum), kalan fark
eğitimde ağırlıklı kayıpla kapatılır.

### Etiket gürültüsü — bilinen ve kabul edilen

SPHAR'ın CASIA klipleri kaynak dosya adında başka eylem adı taşıyor
(`running/casia_..._jump_a1.mp4`). Bunların bir kısmı yukarıda elendi; kalan
CASIA klipleri (17 sn medyan) yalnız zamansal kesilmiştir, yani olayın
öncesi ve sonrası penceresi de sınıf etiketini alır. Bu kabul edilen
gürültüdür ve 9.5'te pilot kliplerle ayrı ölçülerek görünür kılınır.

### Ölçülen fizibilite (bu plan yazılmadan önce koşuldu)

Sekiz SPHAR klibi indirilip `Preprocessor` → `PoseDetector` hattından
geçirildi (her 3. kare):

| Klip | Kare | Pozlu kare | Kişi/kare | En büyük bbox yüksekliği |
|---|---|---|---|---|
| falling casia p01 | 341 | 77.0% | 0.79 | 19.2% |
| falling casia p02 | 489 | 48.5% | 0.52 | 21.2% |
| hitting bitint 0001 | 79 | 100.0% | 2.00 | 74.4% |
| hitting bitint 0002 | 76 | 100.0% | 5.00 | 54.0% |
| running casia p01 | 173 | 71.9% | 0.74 | 23.3% |
| running casia p02 | 184 | 45.9% | 0.49 | 19.9% |
| walking casia p01 | 306 | 77.5% | 0.79 | 19.7% |
| walking casia p02 | 319 | 72.6% | 0.75 | 20.1% |

Sonuç: H265 HEVC OpenCV'de sorunsuz açılıyor (320x240, 25 FPS). CASIA
kliplerinde kişi karenin yalnızca ~%20'sini kaplıyor ve klibin bir bölümünde
kadrajda değil — pozlu kare oranının %46-77 olması budur, tespit hatası
değil. BIT-Interaction klipleri (FIGHT'ın gövdesi) %100 pozlu ve kişi kareyi
dolduruyor.

---

## 2. Model kararı

### Girdi

İz başına 50 karelik pencere (`Thresholds.window_frames` ile aynı), kare
başına **53 kanal**:

- 17 keypoint × (x, y), **bbox'a normalize**: `(kp - [x1, y1]) / [w, h]`.
  Kameradan ve mesafeden bağımsız duruş. (34 kanal)
- 17 keypoint güveni. (17 kanal)
- Centroid yer değiştirmesi ÷ bbox yüksekliği, (dx, dy) — bbox'a
  normalizasyon küresel hareketi sildiği için RUN aksi hâlde görünmez
  olurdu. (2 kanal)

Kuralların türettiği skaler öznitelikler (`norm_speed`, `body_tilt`,
`knee_angle`, …) modele **verilmez.** Model kuralın gördüğünü değil ham
iskeleti görür; ablation tablosunun anlamı buna dayanır.

Pozsuz kareler sıfırlanır; pencerede pozlu kare oranı %60'ın altındaysa
pencere düşürülür — kural motorunun "poz yoksa anomali yok" kuralının
(`vision/rules/engine.py:104`) eğitim tarafındaki karşılığı.

### Mimari

Genişletilmiş nedensel Conv1d (dilated causal TCN):

- 5 blok, 64 kanal, çekirdek 3, genişleme 1-2-4-8-16 → alım alanı 63 kare
  ≥ 50, yani tüm pencere tek geçişte görülür
- Blok: Conv1d → BatchNorm → ReLU → Dropout(0.2), artık bağlantı
- Küresel ortalama havuzlama → `Linear(64, 4)`
- Yaklaşık 50 bin parametre; 4 GB VRAM'de eğitim dakikalar sürer

Sınıflar: `NORMAL`, `FALL`, `RUN`, `FIGHT`.

LSTM veya Transformer denenmez: 50 karelik sabit pencerede TCN'in tek geçişi
yeterli, ikisi de daha çok parametre ve daha yavaş çıkarım demek.

---

## 3. Alt aşamalar

Her alt aşama sonunda `docs/DURUM.md` güncellenir ve commit mesajı verilir.

### 9.1 — Veri kümesi indirme

- `scripts/fetch_datasets.py`: SPHAR contents API'sinden seçili klasörleri
  listeler, kaynak önekine göre süzer, `data/train/<SINIF>/` altına indirir;
  URFD'yi doğrudan URL kalıbıyla çeker. Var olan dosyayı atlar, yani yeniden
  çalıştırılabilir.
- Sınıf başına klip sayısı ve MB tablosu basar.
- Kaynak başına örnek klipler açılıp bakılır; uymayan kaynak tek tek dosya
  değil **bütün olarak** elenir (yukarıdaki eleme tablosu). Tek dosya listesi
  tutmak yerine kaynak elemek, kuralın betikte tek satırda görünür kalmasını
  sağlıyor.
- **Onay kriteri:** RUN, FIGHT ve NORMAL'de ≥ 100 klip; FALL'da ≥ 60 (yer
  seviyesi düşme kaydı gerçekten az: SPHAR'da 36, URFD'de 30). Tablo
  `docs/DURUM.md`'de.

### 9.2 — Dizi çıkarımı

- `eval/extract_sequences.py`: her klibi **gerçek hattan** geçirir
  (`Preprocessor` → `PoseDetector` → `Tracker` → `Smoother` →
  `FeatureEngine`), iz başına 25 kare adımlı kayan 50'lik pencereleri
  `data/sequences/<SINIF>/<klip>_<iz>_<pencere>.npz` olarak yazar.
  `eval/feature_stats.py` içindeki `run_clip_features` aynı hattı zaten
  kuruyor; o kalıp yeniden kullanılır, yeni hat yazılmaz.
- Bölme **klip bazında** yapılır (%80 / %20). Aynı klibin pencereleri iki
  tarafa düşerse doğrulama skoru şişer ve tez tablosu geçersiz olur.
- **Onay kriteri:** sınıf başına pencere sayısı, düşürülen pencere oranı,
  eğitim/doğrulama klip sayıları tabloda.

### 9.3 — Eğitim

- `models/tcn.py`: model tanımı + eğitim döngüsü + değerlendirme.
- Ağırlıklı `CrossEntropyLoss` (sınıf frekansının tersi), Adam, erken durdurma.
- Çıktılar: `models/tcn.pt` ve `models/tcn_meta.json` (sınıf listesi, kanal
  düzeni, pencere uzunluğu, normalizasyon istatistikleri, eğitim tarihi).
  `.gitignore` `*.pt`'yi elediği için ağırlık depoya girmez; yeniden
  üretilebilirliği indirme + eğitim betikleri sağlar.
- **Onay kriteri:** doğrulama karışıklık matrisi, sınıf başına
  precision/recall/F1, pencere başına çıkarım süresi (ms).

### 9.4 — HybridArbiter

- `vision/rules/arbiter.py`: `RuleEngine`'i sarar, aynı `__call__(windows)`
  imzasını verir, `list[Candidate]` döndürür.
  - Model güveni ≥ `tcn_min_conf` ve sınıf ≠ NORMAL → aday üretilir,
    `decided_by="model"`
  - Aynı iz için kural da aynı tipi verdiyse → `decided_by="hybrid"`, skor
    ikisinin maksimumu
  - Model eşiğin altındaysa → yalnızca kural adayları, `decided_by="rule"`
  - ZONE_VIOLATION ve LOITERING **her zaman** kuraldan gelir (bkz. § 4)
- `Candidate` dataclass'ına `decided_by: str = "rule"` alanı eklenir.
- Alanın Kafka'dan geçmesi üç küçük düzenleme ister:
  `vision/publish.py` `candidate_to_dict` (yeni anahtar),
  `stream/spark_job.py` (`CANDIDATE_SCHEMA` + `max_by(...)` toplaması + çıkış
  struct'ı), `api/workers/consumer.py:69` (sabit `"rule"` yerine `msg.get`).
- `vision/run.py:369` tek satır değişir: `rule_engine(windows)` yerine hakem.
  `--no-tcn` bayrağı hakemi devre dışı bırakır (ablation için).
- TCN çıkarımı iz başına her karede değil **5 karede bir** koşulur; pencere
  25 kare kayıyor, daha sık koşmak aynı cevabı üretir. Maliyet
  `vision/run.py` aşama tablosunda ayrı satır olarak raporlanır.
- **Onay kriteri:** aynı klip üç modda (`--no-tcn`, yalnız model, hibrit)
  koşuyor; FPS düşüşü ölçülmüş.

### 9.5 — Ablation ve FIGHT ölçümü

- `eval/tcn_eval.py`: `eval/pilot_eval.py`'ın karşılaştırma mantığını üç mod
  için tekrarlar. İki ayrı küme üzerinde koşar:
  1. **Pilot klipler** (`eval/annotations/`) — üretim alanı, 1080p
  2. **SPHAR/URFD doğrulama klipleri** — klip etiketi gerçek referanstır
- FIGHT'ın gerçek doğruluğu ilk kez ölçülür; bugüne kadar yalnızca "yanlış
  pozitif üretmiyor" biliniyordu.
- LOITERING için **yalnızca yanlış pozitif oranı** ölçülür; olumlu örnek
  hiçbir kümede yok, recall "ölçülmedi" diye yazılır — tahmin edilmez.
- **Onay kriteri (aşamanın onay kriteri):** `decided_by` kırılımıyla
  kural / model / hibrit precision-recall-F1 tablosu, iki küme için ayrı ayrı.

---

## 4. Bilinçli sınırlar

**LOITERING ve ZONE_VIOLATION modele girmez.** İkisi de süre ve geometri
kuralıdır: "poligonun içinde N saniye". İskelet dizisinde öğrenilecek bir
hareket örüntüsü yok; üstelik poligon kameraya bağlı olduğu için model tek
kameraya aşırı uyum sağlardı (`docs/DURUM.md`, bölge poligonu açık sorusu).
Bu iki sınıf kuralda kalır ve `decided_by="rule"` olarak damgalanır.

**Model tek izi sınıflar, FIGHT ise ikili bir olaydır.** TCN'e iki izin
birleşik vektörünü vermek girdi boyunu ve eşleştirme kombinatoriğini ikiye
katlar. Bunun yerine model iz başına "vurma/tekme hareketi" olasılığı
üretir, iki izi eşleştirmeyi `FightRule`'un mevcut yakınlık kontrolü yapar
(`vision/rules/fight.py:22`). Model tek başına FIGHT üretmez; yalnızca kural
yakınlık şartını sağladığında modelin oyu skora girer.

**Alan farkı kapatılmıyor, ölçülüyor.** Eğitim kümesi 320x240 güvenlik
kaydı, pilot klipler 1080p. Ölçek-normalize öznitelikler bunu teoride
kapatır; 9.5 iki kümeyi ayrı satırda raporlayarak pratikte kapanıp
kapanmadığını gösterir. Tek bir ortalama skor verilmez.

**Etkin öğrenme döngüsü kurulmuyor.** Panelde olay durumu zaten insan
etiketi üretiyor (`PATCH /api/events/{id}`); bunu eğitim kümesine geri
besleyen döngü Aşama 10'a kalır — bugün etiket hacmi sıfıra yakın, döngüyü
şimdi kurmak boş bir boru inşa etmektir.

**ONNX'e dönüştürülmüyor.** Model zaten torch'ta ve GPU'da; 50 bin
parametrede ONNX Runtime'ın getirisi ölçülebilir değil. Aşama 10'da çoklu
kamera darboğazı ölçülürse yeniden bakılır.
