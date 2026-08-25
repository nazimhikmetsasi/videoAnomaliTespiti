# Proje Durumu

Bu dosya her aşama sonunda güncellenir. Yeni oturum açıldığında önce
`docs/PLAN.md` sonra bu dosya okunur ve kaldığı yerden devam edilir.

**Son güncelleme:** 2026-08-25

---

## Şu an neredeyiz

**Aşama 3 — Öznitelik ve kural motoru tamamlandı.** One-Euro düzleştirme,
ölçek-normalize kinematik ve beş kural (FALL, RUN, ZONE_VIOLATION,
LOITERING, FIGHT) çalışıyor. Pilot kliplerde ilk precision/recall ölçümü
alındı: FALL 1.00/1.00, ZONE_VIOLATION 0.50/1.00, RUN 0.20/0.50.

Bu aşamanın esas kazancı tablo değil, tablonun **neden** o şekilde çıktığının
ölçülmüş olmasıdır: ilk uygulama plana birebir sadıktı ve FALL ile RUN hiç
tetiklemedi. Sebep kural kodu değil, plandaki iki öznitelik tanımının
görüntü geometrisiyle uyuşmamasıydı (§ Aşama 3 sonucu). Sıradaki iş Aşama 4
(Kafka ve Spark).

---

## Aşama durumu

| # | Aşama | Durum |
|---|---|---|
| — | Plan ve mimari (`docs/PLAN.md`) | Tamamlandı |
| 0 | Ortam hazırlığı | Tamamlandı |
| 1 | Altyapı (Docker, veritabanı şeması) | Tamamlandı |
| 2 | Kaynak ve görü çekirdeği | Tamamlandı |
| 2.1 | YOLOv8 → YOLO26 geçişi | Tamamlandı |
| 3 | Öznitelik ve kural motoru | Tamamlandı |
| 4 | Kafka ve Spark | Sırada |
| 5 | Veri katmanı ve API | Bekliyor |
| 6 | Canlı görüntü (WebSocket) | Bekliyor |
| 7 | LLM ve Telegram | Bekliyor |
| 8 | Panel (kullanıcı şablonu) | Bekliyor |
| 9 | TCN modeli ve yeni sınıflar | Bekliyor |
| 10 | Ölçek ve tez çıktıları | Bekliyor |

---

## Aşama 0 sonucu (2026-08-24)

Kurulan ortam:

- Git deposu (`main` dalı), `.gitignore`, `README.md`
- Python 3.11.9 venv (`venv/`)
- `torch 2.5.1+cu121`, `torchvision 0.20.1+cu121` — `cuda.is_available() == True`
- `ultralytics 8.4.127`, `opencv-python 5.0.0.93`, `numpy 2.4.6`
- `models/yolov8s-pose.pt`, `models/yolov8n-pose.pt`
- `scripts/check_gpu.py` — doğrulama ve ölçüm betiği

Ölçüm (RTX 3050 Laptop 4 GB, 960x540, FP16, ultralytics `bus.jpg`):

| model | kare başına | FPS | tepe VRAM | bulunan kişi |
|---|---|---|---|---|
| yolov8s-pose | 13.3 ms | 75.4 | 49 MiB | 3 |
| yolov8n-pose | 13.2 ms | 75.5 | 36 MiB | 4 |

**Yorum:** `s` ve `n` süreleri neredeyse aynı. Darboğaz GPU hesabı değil,
çağrı başına düşen sabit yük (ön işleme, NMS, Python). Bu, `s` modelinin
pratikte bedava geldiği anlamına gelir ve PLAN'daki `yolov8s-pose` kararını
doğrular. VRAM kullanımı 4 GB'ın yanında ihmal edilebilir.

**Ölçümün sınırı:** tek kare `predict()` çağrısıdır. Gerçek döngüde takip,
öznitelik çıkarımı ve yayın eklenince FPS düşecektir. Aşama 2'de gerçek
döngü ölçülecek.

Yan bulgu: ultralytics 8.4'te `half=True` kullanımdan kalkmış, yerine
`quantize=16` geldi.

---

## Aşama 1 sonucu (2026-08-24)

Kurulan altyapı:

- `docker-compose.yml` — postgres 16, mongo 7, kafka 3.9 (KRaft), kafka-init
- `infra/postgres/init.sql` — 7 tablo, indexler, admin tohum kaydı
- `infra/mongo/init.js` — 3 koleksiyon, indexler, TTL
- `infra/kafka/topics.sh` — `anomaly-candidates`, `anomaly-events`
- `.env.example` + `.env` (yerel rastgele şifrelerle üretildi, depoya girmez)
- `.gitattributes` — `eol=lf`; CRLF ile yazılan `topics.sh` Linux'ta çalışmaz
- `scripts/check_infra.sh` — onay kriteri kontrolü, tek komut

Servis durumu: üçü de `healthy`, host'tan portlar açık.

| servis | konteyner | host portu |
|---|---|---|
| PostgreSQL 16 | `anomaly-postgres` | 5433 |
| MongoDB 7 | `anomaly-mongo` | 27018 |
| Kafka 3.9 (KRaft) | `anomaly-kafka` | 9092 |

`scripts/check_infra.sh` çıktısı: 19 kontrolün tamamı `[OK]`.

**Plandan üç sapma** (gerekçeleriyle karar günlüğünde):

1. Zookeeper yok — Kafka KRaft modunda.
2. `spark` ve `api` servisleri compose'a girmedi. Karşılık gelen kod
   (`stream/spark_job.py`, `api/`) henüz yok; Aşama 4 ve 5'te eklenecek.
3. Host portları 5432/27017 yerine 5433/27018. v1 projesinin konteynerleri
   (`mcbu-postgres`, `mcbu-mongodb`) `restart: unless-stopped` ile açılışta
   geliyor ve varsayılan portları tutuyor. v1'e dokunulmadı.

**Ortam sorunu ve çözümü:** Docker Desktop 4.79.0 açılışta çöküyordu —
`initializing Inference manager: listening on unix://.../dockerInference:
remove ...: The file cannot be accessed by the system`. Takılı soket dosyası
Windows API'siyle silinemiyordu. `%LOCALAPPDATA%/Docker/run` dizini yeniden
adlandırıldı ve `settings-store.json` içinde `EnableDockerAI` `false` yapıldı
(yedek: `settings-store.json.bak.20260824114154`). Docker AI bu projede
kullanılmıyor; gerekirse Settings > AI'dan geri açılır.

---

## Aşama 2 sonucu (2026-08-24)

Yazılan kod (hepsi ASCII, aşama başına ayrı sınıf):

| dosya | satır | görevi |
|---|---|---|
| `vision/source.py` | 208 | mp4/webcam/RTSP tek arayüz, halka tampon, yeniden bağlanma |
| `vision/stages/preprocess.py` | 92 | letterbox 960x540 + koşullu CLAHE |
| `vision/stages/pose_detector.py` | 102 | YOLOv8s-pose FP16, toplu çıkarım, ReID özniteliği |
| `vision/stages/tracker.py` | 108 | BoT-SORT sarmalayıcı, `Track` veri sınıfı |
| `vision/run.py` | 225 | giriş noktası, ölçüm raporu, hata ayıklama çizimi |
| `tests/test_vision_core.py` | 165 | 6 assert tabanlı öz kontrol, GPU gerektirmez |

`tests/test_vision_core.py` → 6/6 geçiyor (CPU'da, sentetik tespitlerle).

### Ölçüm — altı pilot klip, son varsayılanlar

RTX 3050 Laptop, FP16, 960x540, tek kamera. Süreler medyan ms.

| klip | çözünürlük | FPS | ön işleme | çıkarım | takip | döngü | CLAHE | ID | eş zamanlı |
|---|---|---|---|---|---|---|---|---|---|
| fall_01 | 768x432 | 53.6 | 1.2 | 14.0 | 0.4 | 16.2 | 0/236 | 2 | 2 |
| run_01 | 2160x3840 | 16.1 | 29.9 | 29.5 | 1.8 | 60.7 | 0/467 | 1 | 1 |
| mixed_01 | 898x506 | 37.6 | 8.7 | 14.9 | 1.1 | 24.9 | 570/686 | 1 | 1 |
| normal_01 | 1280x720 | 43.7 | 4.3 | 14.3 | 1.0 | 20.1 | 0/362 | 1 | 1 |
| zone_01 | 640x360 | 39.3 | 8.2 | 14.4 | 1.0 | 23.6 | 1417/1515 | 5 | 3 |
| police_run | 1276x720 | 42.7 | 4.8 | 14.5 | 1.0 | 20.5 | 0/300 | 7 | 2 |

Webcam (`--source 0`): 120 kare, **29.5 FPS**, döngü 23.5 ms, 3 kare düştü
(canlı kaynakta en yeni kare kazanır — tasarım gereği). Oda karanlık olduğu
için CLAHE 120/120 karede tetiklendi ve kimse görünmediği için ID üretilmedi;
doğrulanan şey webcam yolunun uçtan uca çalıştığıdır.

**25 FPS hedefi run_01 dışında her klipte aşıldı.** run_01 2160x3840 dikey
4K'dır; 29.9 ms'lik ön işleme süresi tamamen çözme + letterbox maliyetidir,
model değil. Gerçek IP kamerada bu çözünürlük görülmez.

**Çıkarım süresi 14–15 ms** — Aşama 0'daki tek kare ölçümüyle (13.3 ms)
uyumlu. Yani takip, ön işleme ve yayın eklendiğinde çıkarım yavaşlamıyor;
darboğaz çıkarımın kendisi değil.

### Ölçüm sırasında bulunan tuzak

İlk ölçümler 12–21 FPS gösterdi ve koşudan koşuya %40 oynadı. Sebep tarayıcı:
`nvidia-smi` aynı GPU'da Brave ve `explorer.exe` süreçlerini gösterdi, GPU
kullanımı biz hiçbir şey çalıştırmazken %40, saat 675–1500 MHz (tepe 2100),
güç 4–10 W (sınır 50 W). Tarayıcı kapalıyken sayılar yukarıdaki tabloya
oturdu ve tekrarlanabilir hale geldi. **Tez ölçümleri masaüstü GPU yükü
kapalıyken alınmalıdır.**

### GMC kararı — ölçümle kapatıldı

Altı klip iki kez koşuldu (`sparseOptFlow` ve `none`). **ID sonuçları birebir
aynı çıktı**, buna karşılık `sparseOptFlow` kare başına ~18 ms yiyip FPS'i
yaklaşık yarıya düşürdü. Sabit gözetim kamerasında telafi edilecek kamera
hareketi yok. Varsayılan `none`; PTZ veya elde taşınan kamera için
`--gmc sparseOptFlow` ile açılır.

### ReID durumu — açık soru kapandı

BoT-SORT ReID **aktif ve doğrulandı**: `botsort.yaml` içinde `with_reid: True`
+ `model: auto` seçildiğinde dedektörün kendi gövde öznitelikleri görünüm
vektörü olarak kullanılıyor. Uçtan uca doğrulandı — tespit başına 128 boyutlu
vektör üretiliyor ve izler `smooth_feat` taşıyor. Ek model, ek VRAM, ek çıkarım
maliyeti yok.

Ancak `--no-reid` ile ablation koşulduğunda **ID sayıları hiç değişmedi**.
Bu kliplerde ReID'in fark yaratacağı zorlukta bir sahne yok; kalitesi burada
kanıtlanamaz. Kalabalık ve kesişmeli sahnede yeniden ölçülmeli.

### ID kararlılığı

`police_run` 7 ID / en fazla 2 eş zamanlı kişi, `zone_01` 5 ID / 3 kişi.
İşaretlenmiş çıktı incelendiğinde bunlar **takip içi ID değişimi değil**;
kişiler kadrajdan çıkıp tekrar giriyor ve her giriş yeni ID alıyor. Kadrajdan
çıkmış kişiyi tekrar aynı varlığa bağlamak olay bazlı ReID galerisi ister
(v1'den taşınacak fikir, Aşama 9).

Yan bulgu: `police_run` 250. karede yakın plandaki kişi bitki örtüsünün
arkasında kaldığı için `conf=0.35` eşiğini geçemedi ve hiç tespit edilmedi.
Eşik kamera bazında ayarlanabilir olacak (Aşama 5, `detection_settings`).

**Pozsuz iz sayısı altı klipte de 0** — pose modeli kutu ürettiği her yerde
17 keypoint de üretti. PLAN.md zayıf nokta 7'nin ("pose eşleşmezse bbox
merkeziyle anomali üretme") pratikte hiç tetiklenmediğini gösteriyor, ama
kural Aşama 3'te yine de yazılacak.

### Plandan sapmalar

1. **CLAHE koşullu çalışıyor, her karede değil.** Ölçümde kare başına 8–9 ms
   tuttu — 40 ms'lik 25 FPS bütçesinin beşte biri. İyi ışıkta hiçbir şey
   kazandırmıyor. Artık kare 1/8 boyuta indirilip gri standart sapmasına
   bakılıyor (~0.1 ms); eşik altındaysa CLAHE uygulanıyor. Ölçümde
   `fall_01`/`normal_01`/`police_run` 0 kare, `zone_01` 1417/1515 kare.
2. **`vision/run.py` 225 satır**, plandaki "aşama başına 150 satır" sınırının
   üstünde. Bu bir aşama değil giriş noktası: argüman ayrıştırma, ölçüm
   raporu ve hata ayıklama çizimi burada. Görü aşamalarının hepsi 92–108 satır.
3. **Yeni bağımlılık: `lap`.** BoT-SORT/ByteTrack eşleme çözücüsü. Ultralytics
   çalışma anında kendisi kuruyor; `requirements.txt`'e açıkça eklendi.
4. **Pilot videolar `data/pilot/` altına kopyalandı** (v1 dizininden). `data/`
   zaten `.gitignore`'da; v1 projesine dokunulmadı.

---

## Aşama 2.1 sonucu — YOLOv8 → YOLO26 geçişi (2026-08-25)

Dedektör `yolov8s-pose`'dan `yolo26s-pose`'a taşındı. Gerekçe: YOLO26 uçtan uca
(end2end) çalışır, yani NMS yoktur. Bu bir hız kararı değil mimari karardır —
çift tespit ve kutu birleştirme sorunu (v1 zayıf nokta 2, `detector.py`
merge/alan filtreleri) artık doğamaz ve ayarlanacak bir `iou` eşiği kalmaz.

### Değişen dosyalar

| dosya | değişiklik |
|---|---|
| `vision/stages/pose_detector.py` | varsayılan ağırlık `models/yolo26s-pose.pt`, varsayılan `conf` 0.25 |
| `vision/stages/tracker.py` | `DEFAULT_REID`, `_FixedBatchReID` sarmalayıcı, `cuda` → `cuda:0` normalizasyonu |
| `vision/run.py` | `choose_reid()`, `--reid-model` bayrağı, raporda aktif ReID yolu |
| `scripts/fetch_models.py` | **yeni** — dört ağırlığı tek komutla indirir |
| `infra/postgres/init.sql` | `pose_conf` varsayılanı 0.35 → 0.25 |
| `requirements.txt` | `onnxruntime-gpu==1.22.0` (sürüm sabit, aşağıda gerekçe) |
| `tests/test_vision_core.py` | `test_choose_reid`, `test_fixed_batch_reid` → 8/8 geçiyor |

### ReID: bedava öznitelik yolu kapandı, amaca özel ağ geldi

BoT-SORT'un `model: auto` yolu dedektörün kendi gövde özniteliklerini görünüm
vektörü olarak kullanır — bedavadır ama yalnızca end2end **olmayan** modellerde
çalışır. Ultralytics bunu açıkça dışlar (`trackers/track.py`, `not
...model[-1].end2end` koşulu); nedeni teknik: end2end çıktısı zaten seçilmiş
top-k satırlardır, dönen indeksler artık çapa (anchor) ızgarasına karşılık
gelmez, dolayısıyla eşlenen öznitelik yanlış olurdu.

Karşılığında Ultralytics YOLO26 için **eğitilmiş ReID ağları** yayınlıyor
(`yolo26{n,s,m,l,x}-reid.onnx`, `trackers/utils/reid.py`).
`models/yolo26s-reid.onnx` kullanılıyor. Net sonuç kayıp değil değişim: genel
amaçlı dedektör öznitelikleri yerine ReID için eğitilmiş bir ağ, ölçülen bedeli
kare başına yaklaşık 7 ms.

`vision/run.py` hangi yolun aktif olduğunu her koşuda raporun başına yazar.
`--reid-model` ile elle ağ verilebilir, `--no-reid` ablation için tamamen
kapatır.

### Ölçüm 1 — aynı koşullarda v8 / YOLO26 karşılaştırması

Altı pilot klip, RTX 3050 Laptop, FP16, masaüstü GPU yükü kapalı, her ikisi de
`conf=0.35`. Süreler medyan ms.

| klip | v8s FPS | v8s çıkarım | YOLO26s FPS | YOLO26s çıkarım |
|---|---|---|---|---|
| fall_01 | 60.7 | 13.8 | 38.4 | 18.7 |
| mixed_01 | 29.2 | 19.0 | 29.0 | 17.9 |
| normal_01 | 48.4 | 14.2 | 33.0 | 18.2 |
| zone_01 | 40.1 | 14.7 | 31.2 | 17.8 |
| police_run | 46.5 | 14.1 | 31.5 | 18.4 |
| run_01 (4K) | 19.0 | 25.4 | 16.0 | 23.5 |

Çıkarım 14 → 18 ms (+4 ms). ReID ağı +5–7 ms. Geçişin toplam bedeli yaklaşık
%25–35 FPS.

### Ölçüm 2 — güven eşiği kalibrasyonu

İlk koşuda YOLO26 `police_run` klibinde v8'in gördüğü kişilerin bir kısmını
kaçırıyor göründü. Sebep kaçırma değil kalibrasyon: end2end kafa aynı tespite
daha düşük skor verir.

| ölçüt (police_run) | v8 @0.35 | YOLO26 @0.35 | YOLO26 @0.25 |
|---|---|---|---|
| izli kare | 193 | 132 | 191 |
| benzersiz ID | 7 | 8 | 7 |
| kare başına kişi | 1.31 | 1.06 | 1.24 |

`conf=0.25`'te YOLO26 v8'in `conf=0.35`'teki davranışını yakalıyor. Varsayılan
eşik hem kodda hem `detection_settings.pose_conf` sütununda 0.25 yapıldı.

`fall_01`'de v8'in ürettiği ikinci ID YOLO26'da `conf=0.15`'te bile yok. O ID
110 karenin yalnızca dört kadarında beliriyor — v8'in NMS artığı geçici yanlış
pozitifi. YOLO26 lehine bir fark.

### Ölçüm 3 — p95 sıçraması ve çözümü

İlk YOLO26 + ReID koşularında takip aşaması medyan 0.5 ms, **p95 50.4 ms**
verdi. 40 ms'lik 25 FPS bütçesini tek başına aşan bir sıçrama.

Sebep ölçülerek bulundu: ONNX Runtime CUDA sağlayıcısı girdi şekli her
değiştiğinde yeniden ayarlama yapıyor. Kişi sayısı değiştikçe batch boyutu
değişiyor, her değişim yaklaşık 50 ms. **Isıtma bunu çözmüyor** — 1→2→1
dizisinde daha önce görülmüş şekle dönüşte de aynı bedel ödeniyor (ölçülen:
49.1 / 57.1 / 57.4 ms).

Çözüm `vision/stages/tracker.py` içindeki `_FixedBatchReID`: batch sabit bir
sayının katına yuvarlanır, eksik yerler son tespitin kopyasıyla doldurulur,
fazla vektörler atılır. Şekil sabit kaldığı için yeniden ayarlama hiç
tetiklenmez.

Adım ölçülerek seçildi (`police_run`, takip aşaması):

| yuvarlama | medyan | p95 |
|---|---|---|
| yok | 0.5 ms | 50.4 ms |
| adım 4 | 10.1 ms | 18.9 ms |
| **adım 2** | **7.1 ms** | **13.4 ms** |

Sabit maliyet batch ile büyüdüğü için küçük adım daha ucuz. Üç ve daha fazla
kişili karelerde 4'e çıkılır, şekil yine sabit kalır.

### Ölçüm 4 — son yapılandırma

`yolo26s-pose` + `yolo26s-reid.onnx`, `conf=0.25`, GMC kapalı, CLAHE koşullu.
Süreler medyan ms.

| klip | çözünürlük | FPS | ön işleme | çıkarım | takip | döngü | döngü p95 | CLAHE | ID | eş zamanlı |
|---|---|---|---|---|---|---|---|---|---|---|
| fall_01 | 768x432 | 37.2 | 1.2 | 18.2 | 0.4 | 22.7 | 44.6 | 0/236 | 1 | 1 |
| run_01 | 2160x3840 | 17.5 | 23.9 | 21.0 | 9.0 | 54.0 | 75.7 | 0/467 | 1 | 1 |
| mixed_01 | 898x506 | 27.1 | 9.9 | 18.1 | 8.0 | 35.7 | 43.8 | 570/686 | 1 | 1 |
| normal_01 | 1280x720 | 31.8 | 4.6 | 18.2 | 7.0 | 30.0 | 37.1 | 0/362 | 1 | 1 |
| zone_01 | 640x360 | 30.1 | 9.3 | 18.1 | 6.8 | 32.8 | 42.3 | 1417/1515 | 6 | 3 |
| police_run | 1276x720 | 31.7 | 5.4 | 18.5 | 7.0 | 30.4 | 39.5 | 0/300 | 7 | 2 |

Webcam (`--source 0`, 120 kare): **24.3 FPS**, döngü 37.3 ms, ReID aktif,
120/120 karede kişi bulundu, pozsuz iz 0.

25 FPS hedefi run_01 dışında her klipte aşılıyor. run_01 2160x3840 dikey 4K'dır
ve darboğazı çözme + letterbox'tır (ön işleme 23.9 ms), model değil. Webcam
24.3 FPS ile hedefin hemen altında: oda karanlık olduğu için CLAHE 119/120
karede tetiklendi ve ön işleme payı büyüdü.

**Pozsuz iz altı klipte de 0** — YOLO26 da kutu ürettiği her yerde 17 keypoint
üretiyor.

### Ortam tuzakları

1. **`onnxruntime-gpu` sürümü CUDA sürümüne bağlıdır.** PyPI'daki güncel sürüm
   (1.29) CUDA **13** ister; bizde torch cu121 var. Kurulunca hata vermiyor,
   sessizce CPU'ya düşüyor — `zone_01` FPS'i 19.5'ten 9.8'e indi. Tanı satırı:
   `Error loading onnxruntime_providers_cuda.dll which depends on
   "cublasLt64_13.dll" which is missing`. `==1.22.0` sabitlendi; CUDA 12.x +
   cuDNN 9 ister, ikisini de `venv/Lib/site-packages/torch/lib` sağlıyor
   (`cublasLt64_12.dll`, `cudnn64_9.dll`). Doğrulama satırı: `Using ONNX
   Runtime 1.22.0 with CUDAExecutionProvider`.
2. **Çıplak `"cuda"` cihaz adı ONNX için yetmiyor.** `torch.device("cuda").index`
   `None` olur, ONNX Runtime da `device_id=None` gelen CUDA sağlayıcısını
   reddedip CPU'ya düşer. `Tracker` artık `"cuda"` gördüğünde `"cuda:0"`
   kullanıyor.
3. Ağırlıklar `.gitignore`'da (`*.pt`, `*.onnx`). Depo klonlandıktan sonra
   `venv/Scripts/python.exe scripts/fetch_models.py` bir kez çalıştırılır.

### Elenen seçenekler

- **`yolo26m-pose`** — çıkarımı `s`'nin yaklaşık iki katı (60.9 ms). Aşama
  0'daki "`n` ile `s` aynı süreyi veriyor, demek ki büyük model de bedava"
  beklentisi `m` ölçeğinde tutmuyor.
- **YOLO12** — dikkat (attention) tabanlı. FlashAttention olmayan bu GPU'da
  yavaşlama riski var, kazancı belirsiz.
- **RTMPose / ViTPose** — keypoint doğruluğu daha yüksek ama top-down iki
  aşamalı: önce dedektör, sonra kişi başına ayrı pose ağı. Bu tam olarak v1'in
  1 numaralı zayıf noktası; mimari karara ters.

---

## Aşama 3 sonucu (2026-08-25)

Yazılan kod:

| dosya | satır | görevi |
|---|---|---|
| `vision/stages/smoother.py` | 106 | One-Euro filtresi, iz başına vektörleştirilmiş durum |
| `vision/stages/features.py` | 166 | ölçek-normalize kinematik, 50 kare kayan pencere |
| `vision/rules/engine.py` | 112 | `Thresholds`, `Zone`, `Candidate`, `RuleEngine` |
| `vision/rules/fall.py` | 38 | gövde eğimi + aşağı hız zirvesi |
| `vision/rules/run.py` | 58 | yer değiştirme **veya** adım ritmi |
| `vision/rules/zone.py` | 48 | ayak noktası poligon testi |
| `vision/rules/loiter.py` | 93 | bölgede kalış / sabit dolaşma, kendi durumu |
| `vision/rules/fight.py` | 68 | ikili yakınlık + karşılıklı uzuv hızı |
| `eval/pilot_eval.py` | 184 | saniye bazlı precision/recall, markdown tablo |
| `eval/feature_stats.py` | 191 | öznitelik dağılımı ve eşik kalibrasyon ölçümü |
| `tests/test_features_rules.py` | 304 | 13 assert tabanlı öz kontrol, GPU gerektirmez |

`tests/test_features_rules.py` 13/13, `tests/test_vision_core.py` 8/8 geçiyor.

Uygulama sözleşmesi `docs/ASAMA3_PLAN.md`'dedir; §10 ölçüm sonrası
düzeltmelerin gerekçesini kanıtlarıyla tutar.

### İlk koşu: plana sadık uygulama sıfır sonuç verdi

| tip | TP | FP | FN | precision | recall |
|---|---|---|---|---|---|
| FALL | 0 | 0 | 1 | 0.00 | 0.00 |
| RUN | 0 | 2 | 2 | 0.00 | 0.00 |
| ZONE_VIOLATION | 1 | 20 | 0 | 0.05 | 1.00 |

Kural kodu doğruydu. Plandaki **öznitelik tanımları** yanlıştı. Dört kök neden
ayrı ayrı ölçülerek bulundu.

### Kök neden 1 — omurga açısı düşmeyi göremiyor

`fall_01`, düşme 5.2-6.8 sn:

```
    sn  nspeed     nvy  spine  aspect
  5.21    0.57    0.31    1.2    0.61
  5.34    0.44    0.75    5.1    1.01   <- kisi yatmis, spine hala 5 derece
  5.47    0.38    0.33   16.7    0.98
  5.61    2.46   -2.79    0.0    1.08   <- kalca kaybolunca spine 0.0
```

Klip boyunca `spine_angle` tepesi **20.2 derece**, eşik 45. İki ayrı kusur:
kamera eksenine doğru düşen kişide kalça→omuz vektörü görüntü düzleminde dik
kalır; ayrıca kalça veya omuz keypoint'i güveni geçemeyince fonksiyon `0.0`
döndürüyordu — `0.0` "dimdik" demektir, doğrusu "bilinmiyor"dur.

**Çözüm:** `body_tilt = max(iskelet açısı, bbox eğimi)`, bbox eğimi =
`atan2(genişlik, yükseklik)`. bbox her karede vardır ve `aspect 1.0` tam 45
dereceye düşer — yani mevcut eşik birimi değişmez. `spine_angle` ayrı alan
olarak kalır (bilinmiyorsa `-1.0`) ve teze girer: iskeletin tek başına neden
yetmediği tabloda görünsün.

Yakın plan riski ölçüldü: `mixed_01` 8-14 sn arası kadına yakın plandır,
`aspect` 1.21'e çıkar (`body_tilt` 50 derece). Aynı aralıkta `norm_vy` 0.26'yı
geçmez. FALL kuralı **iki koşulu birlikte** aradığı için yanlış pozitif
üretmez.

### Kök neden 2 — yatay hız iki RUN klibinde gözlemlenemiyor

| klip | kamera | norm_speed tepe | eşik |
|---|---|---|---|
| run_01 | koşucuyu takip ediyor | 0.41 | 1.80 |
| mixed_01 | kişi kameraya doğru koşuyor | 1.04 | 1.80 |
| police_run | sabit, kişi kadrajı kesiyor | 1.77 | 1.80 |

Görüntü düzlemindeki yatay hız, özne kamera ekseni boyunca hareket ettiğinde
veya kamera özneyi takip ettiğinde **ölçülemez**. Sabit kamerada bile eşiğin
kıl payı altında kalıyor.

**Çözüm:** RUN iki kanıttan herhangi biriyle tetikler — yer değiştirme
(mevcut yol) **veya** adım ritmi (`limb_speed` kayan medyanı). Adım döngüsü
kamera geometrisinden bağımsızdır.

### Kök neden 3 — `zone_01` tek kamera değil, kurgu

28. saniyede görüntü tamamen değişiyor (koridor → otopark), 54. saniyede geri
dönüyor. Bölge poligonu 0-1 normalize ve **kameraya bağlıdır**; sahne
değişince aynı koordinatlar otoparktaki yayanın üstüne düşüyor. İlk koşudaki
20 yanlış pozitif saniyenin tamamı buradan geliyordu.

**Çözüm:** `eval/annotations/zone_01.json` içine `eval_end_sec: 28.0`. Bu bir
eşik ayarı değil, ölçüm alanının düzeltilmesidir — kamera değiştikten sonra
o bölge yoktur.

### Kök neden 4 — türev, tampon dolmadan hesaplanıyordu

İz doğduğu ilk karelerde pencere kısa olduğu için `dt` tek kareye kadar
düşüyor, kutunun oturma titremesi hız gibi okunuyordu. `normal_01` bu yüzden
0.4 sn'de 25 RUN adayı üretiyordu. Pencere `velocity_lookback` kareye
ulaşana kadar hız artık 0'dır; bedeli iz başına 0.2 sn sessizlik.

### Ölçüm — öznitelik tepe tablosu (gerçek referans aralıklarına göre)

`eval/feature_stats.py`, altı klip, YOLO26s-pose.

| klip | aralık | body_tilt tepe | norm_vy tepe | norm_speed tepe | limb_speed medyan | kare |
|---|---|---|---|---|---|---|
| fall_01 | NORMAL | 27.0 | 0.07 | 0.78 | 0.39 | 82 |
| fall_01 | **FALL** | **66.1** | **3.16** | 2.97 | 1.73 | 19 |
| mixed_01 | NORMAL | 51.7 | 0.26 | 0.53 | 0.29 | 463 |
| mixed_01 | **RUN** | 44.7 | 0.35 | 0.55 | 0.69 | 188 |
| normal_01 | NORMAL | 35.7 | 0.19 | 0.91 | 0.35 | 324 |
| run_01 | **RUN** | 31.9 | 0.61 | 0.64 | **1.40** | 436 |
| zone_01 | NORMAL | 29.7 | 1.27 | 1.72 | 0.66 | 520 |
| zone_01 | **ZONE_VIOLATION** | 33.0 | 1.02 | 1.49 | 0.50 | 343 |
| police_run | (etiketsiz) | 45.4 | 0.70 | 2.45 | 0.52 | 191 |

`body_tilt` FALL'ı (66.1) her NORMAL satırdan (27.0-51.7) ayırıyor — kök
neden 1'in düzeldiğinin kanıtı budur.

### Ölçüm — adım penceresi süpürmesi

Adım kanıtının kaç karelik medyanla alınacağı ölçülerek seçildi. Havuzlanmış
kayan medyan dağılımları:

| pencere | NORMAL p95 | NORMAL p99 | gerçek koşu (run_01) medyan |
|---|---|---|---|
| 10 kare | 1.28 | 2.22 | 1.45 |
| 25 kare | 1.19 | 1.67 | 1.45 |
| **50 kare** | **1.00** | **1.44** | **1.46** |
| 75 kare | 0.92 | 1.28 | 1.45 |

10 karelik pencerede yürüyüşün tek adımlık sıçraması medyanı koşu bandına
taşıyor, ayrım yok. 50 karede (2 sn) yürüyüş 1.00'a inerken koşu 1.46'da
kalıyor. `run_gait_speed = 1.20` ikisinin arasındadır; `window_frames` 30'dan
50'ye çıkarıldı (`init.sql` varsayılanları da). Bedeli: koşu 2 saniye
gecikmeyle bildirilir.

### Eşik kalibrasyonunda plandaki kuralın kendisi yanlıştı

`docs/ASAMA3_PLAN.md` §10.5, eşiği "NORMAL aralıklarının 90. yüzdeliği ile
olay aralıklarının 10. yüzdeliği arası" diye tanımlıyordu. Bu ölçüt kare
bazında uygulandığında neredeyse kusursuz ayrışma talep eder ve iki
öznitelikte de örtüşme raporladı (`run_norm_speed`: NORMAL p90 0.632, olay
p10 0.037). Ölçüt fazla katıydı; gerçek kalibrasyon yukarıdaki kayan medyan
süpürmesinden geldi. `eval/feature_stats.py` yüzdelik raporunu üretmeye devam
ediyor ama eşiği kendisi koymuyor.

### Ölçüm — pilot değerlendirme (son hâli)

| tip | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|
| FALL | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| RUN | 1 | 4 | 1 | 0.20 | 0.50 | 0.29 |
| ZONE_VIOLATION | 1 | 1 | 0 | 0.50 | 1.00 | 0.67 |
| **TOPLAM** | 3 | 5 | 1 | 0.38 | 0.75 | 0.50 |

Ham aday sayısı (saniyeye indirgenmemiş) — **Aşama 4'te Spark'ın süzeceği
gürültü tabanı budur, öncesi/sonrası karşılaştırması bu satırlardan
yapılacak**:

| klip | ham aday | dağılım |
|---|---|---|
| fall_01 | 2 | FALL |
| mixed_01 | 0 | — |
| normal_01 | 11 | RUN (2.0 sn'de kısa tempolu yürüyüş) |
| police_run | 0 | — |
| run_01 | 333 | RUN (1.6 sn'den itibaren kesintisiz) |
| zone_01 | 739 | ZONE_VIOLATION 703 + RUN 35 |

Aşama süreleri (`normal_01`, medyan ms): düzleme 0.1, öznitelik+kural 0.2.
Aşama 3 zinciri FPS bütçesinde ölçülebilir yer kaplamıyor.

### Bilinen sınırlar (kapatılmadı, ölçüldü)

1. **RUN recall 0.50.** `mixed_01`'in koşusu hem yer değiştirme hem adım
   kanıtında normal yürüyüşle örtüşüyor (RUN limb medyanı 0.69, `zone_01`
   normal yürüyüşü 0.66). Bu klipte ayrım yapacak eşik yok; koyulsaydı
   `zone_01`'in normal yürüyüşü de RUN olurdu. Eşiği beş klibe uydurmak test
   kümesini ezberlemektir, yapılmadı.
2. **`police_run` artık hiç aday üretmiyor.** Sabit kameralı tek gerçek koşu
   klibi bu ve 15 FPS'tir; `norm_speed` tepesi 1.77 (eşik 1.80), adım medyanı
   0.52. Düşük kare hızı uzuv hızını da bastırıyor. Etiketi olmadığı için
   tabloya girmiyor ama gerçek bir kaçırmadır.
3. **ZONE ilk tetik 10.8 sn, gerçek referans 12.0 sn.** Kişi işaretli
   aralıktan önce bölgeye giriyor; 1 saniyelik tolerans yetmiyor. Etiket
   sınırı gevşek, kural erken değil.
4. **FIGHT ve LOITERING pilot kliplerde hiç tetiklemedi.** Bu kliplerde kavga
   ve dolaşma yok, yani yanlış pozitif üretmemeleri doğru davranıştır; gerçek
   doğrulukları ölçülmedi.

### Plandan sapmalar

1. **`vision/stages/features.py` 166 satır**, "aşama başına 150 satır"
   sınırının üstünde. İçinde iki hesap ailesi var (kinematik ve poz açıları)
   ve ölçümden gelen sabitlerin gerekçe yorumları. Bölmek, iki dosyanın aynı
   `FrameFeatures`'ı doldurması demek olurdu.
2. **`RuleEngine.__init__` kural sınıflarını gövde içinde import ediyor.**
   `Candidate`/`Thresholds`/`Zone` `engine.py`'de yaşıyor ve her kural onlara
   bakıyor; modül başında import döngüsel olurdu.
3. **`vision/run.py` 331 satır.** Aşama 2'de zaten 225'ti; `--rules`,
   `--zones`, iki ölçüm satırı ve aday özeti eklendi. Bu bir aşama değil
   giriş noktasıdır.
4. **`detection_settings` değişti:** `fall_spine_deg` → `fall_tilt_deg`,
   yeni `run_gait_speed` sütunu, `window_frames` 30 → 50. Aşama 5 henüz ORM
   yazmadığı için isim düzeltmesi bedava.

---

## Bir sonraki adım

Aşama 4 — Kafka ve Spark:

1. `vision/publish.py`: Kafka producer, `anomaly-candidates` topic'ine aday
   olay JSON'u. `Candidate` alanları hazır (`thresholds_used` dahil).
2. `stream/spark_job.py`: Structured Streaming, 3 sn pencere / 1 sn kayma,
   `(camera, track, type)` başına `hits >= spark_min_hits` → `anomaly-events`
3. `docker-compose.yml`: `spark` servisi (Aşama 1'de bilinçli ertelenmişti)

**Onay kriteri:** tek kare gürültüsü eleniyor, gerçek olay geçiyor;
öncesi/sonrası alarm sayısı karşılaştırma tablosunda.

Gürültü tabanı ölçülmüş durumda — Spark'ın süzeceği ham aday sayıları
"Aşama 3 sonucu" bölümündeki tabloda. Karşılaştırma doğrudan o satırlara
karşı yapılacak. Beklenti: `normal_01`'in 11 adayı (2.0 sn'de kısa tempolu
yürüyüş) elenmeli, `run_01`'in 333 kesintisiz adayı geçmeli. Bu iki klip
Spark filtresinin doğru çalıştığının en temiz sınavıdır.

Ayrıca Aşama 4'te doğrulanacak açık soru: host'ta çalışan `vision/` gerçekten
`localhost:9092`'ye yazabiliyor mu.

---

## Karar günlüğü

| Tarih | Karar | Gerekçe |
|---|---|---|
| 2026-08-24 | Sıfırdan v2 yazılacak, v1 yalnızca referans | v1'in 13 zayıf noktası mimari düzeyde; yamayla değil tasarımla çözülüyor |
| 2026-08-24 | Tek model: `yolov8s-pose` | v1'de detect + pose iki ayrı geçişti, yaklaşık %40 GPU israfı |
| 2026-08-24 | BoT-SORT, DeepSORT değil | ReID + kamera hareketi telafisi hazır gelir; v1'deki ~250 satır elle yama hiç doğmaz |
| 2026-08-24 | Eşikler bbox yüksekliğine normalize | İnsan boyu sabit; kamera açısı ve derinlikten bağımsız eşik |
| 2026-08-24 | Eşikler veritabanında, `.env`'de değil | v1'de 40+ eşik `.env`'deydi, değişiklik restart istiyordu |
| 2026-08-24 | Temiz kare + ayrı metadata, overlay istemcide | Katman aç-kapa, keskin ölçekleme, doğru ROI koordinatı |
| 2026-08-24 | `vision/` host'ta native, geri kalan Docker'da | Windows'ta Docker'a GPU geçirmek zaman kaybı |
| 2026-08-24 | Python 3.11 venv | Sistemde 3.13 varsayılan; CV yığını 3.11'de daha oturmuş |
| 2026-08-24 | LLM: Gemini Flash + şablon yedeği | Ücretsiz kota yeterli, Türkçesi akıcı; yedek sayesinde API çökünce alarm durmaz |
| 2026-08-24 | Bildirim: Telegram Bot (şimdilik) | Token + chat_id yeterli, mobil uygulama gerekmiyor |
| 2026-08-24 | `yolov8s-pose` kesinleşti | Ölçümde `n` ile aynı süreyi verdi (13.3 vs 13.2 ms); darboğaz GPU değil sabit çağrı yükü, yani `s` bedava |
| 2026-08-24 | FP16 için `quantize=16` | ultralytics 8.4'te `half=True` kullanımdan kalktı |
| 2026-08-24 | Kafka KRaft, Zookeeper yok | Bir servis eksilir, tek broker için Zookeeper'ın getirisi yok |
| 2026-08-24 | Kafka log'u kalıcı değil | Olaylar zaten PostgreSQL/MongoDB'ye yazılıyor; restart'ta yalnızca consumer offset'i kaybolur |
| 2026-08-24 | `spark` ve `api` compose'a Aşama 4-5'te girer | Kodları henüz yok; boş servis tanımı sağlığı yanlış raporlar |
| 2026-08-24 | Host portları 5433 / 27018 | v1 konteynerleri açılışta 5432/27017'yi tutuyor; v1 durdurulmadı |
| 2026-08-24 | Admin şifresi `pgcrypto` ile init.sql içinde hash'lenir | Depoda açık şifre yok, yerel bcrypt bağımlılığı da yok |
| 2026-08-24 | `.gitattributes` ile `eol=lf` | CRLF ile yazılan `topics.sh` Linux konteynerde çalışmıyor |
| 2026-08-24 | Docker AI (`EnableDockerAI`) kapatıldı | Docker Desktop 4.79.0 Inference manager soketi yüzünden açılışta çöküyordu |
| 2026-08-24 | `model.track()` değil doğrudan `BOTSORT` sarmalayıcı | ultralytics'in track yolu toplu çıkarımda tüm kareler için tek tracker kullanır; çoklu kamerada her kameranın kendi tracker'ı olmak zorunda |
| 2026-08-24 | ReID: `with_reid: True` + `model: auto` | Dedektörün kendi öznitelikleri kullanılıyor — ek model, ek VRAM, ek çıkarım maliyeti yok |
| 2026-08-24 | GMC varsayılan `none` | Altı klipte açık/kapalı ID sonuçları aynı; `sparseOptFlow` kare başına ~18 ms alıp FPS'i yarıya düşürüyor. Sabit kamerada telafi edilecek hareket yok |
| 2026-08-24 | CLAHE koşullu | Kare başına 8–9 ms; iyi ışıkta kazanç yok. 1/8 boyutta gri standart sapması kapısı ~0.1 ms |
| 2026-08-24 | Canlı kaynak en yeni kareyi tutar, dosya hiç kare atmaz | Canlıda gecikme birikmemeli; kayıtta değerlendirme tekrar edilebilir olmalı |
| 2026-08-24 | Canlı kaynakta okuma zaman aşımı akış sonu sayılmaz | Webcam açılışı bu makinede ~5 sn; ilk sürüm 2 sn'de pes edip "hiç kare okunamadı" diyordu |
| 2026-08-24 | FPS sayacı ilk karede başlar | Webcam/RTSP açılış süresi FPS'i yanlış düşük gösteriyordu |
| 2026-08-24 | `--cv-threads` ayarı eklendi ve kaldırıldı | 0/4/8/16 arasında ölçülebilir fark çıkmadı (~2 FPS gürültü) |
| 2026-08-25 | Dedektör `yolo26s-pose` | End2end (NMS yok): çift tespit ve kutu birleştirme sorunu mimari olarak doğamaz, ayarlanacak `iou` eşiği kalmaz. Bedeli çıkarımda +4 ms |
| 2026-08-25 | ReID: `yolo26s-reid.onnx` | YOLO26 end2end olduğu için dedektörün bedava öznitelikleri ReID'e bağlanamıyor (ultralytics bunu açıkça dışlıyor). Karşılığı amaca özel eğitilmiş ağ, kare başına ~7 ms |
| 2026-08-25 | `onnxruntime-gpu==1.22.0` sabit | 1.23+ CUDA 13 ister; bizde cu121 var. Sabitlenmezse hata vermeden CPU'ya düşüp FPS'i yarıya indiriyor |
| 2026-08-25 | Tracker cihazı `cuda:0` | Çıplak `"cuda"` ONNX Runtime'a `device_id=None` gidiyor, CUDA sağlayıcısı reddedilip CPU'ya düşülüyor |
| 2026-08-25 | Varsayılan `conf` 0.35 → 0.25 | End2end kafa aynı tespite daha düşük skor veriyor; `police_run` izli kare 132 → 191 (v8 @0.35: 193) |
| 2026-08-25 | ReID batch 2'nin katına yuvarlanır | ONNX şekil değişiminde ~50 ms yeniden ayarlama var ve ısıtma çözmüyor. Yuvarlama p95'i 50.4 → 13.4 ms indiriyor |
| 2026-08-25 | `yolo26m-pose` reddedildi | Çıkarım `s`'nin iki katı (60.9 ms); `n`/`s` eşitliği `m` ölçeğinde tutmuyor |
| 2026-08-25 | YOLO12 ve RTMPose/ViTPose reddedildi | YOLO12 dikkat tabanlı, FlashAttention'sız GPU'da riskli; RTMPose/ViTPose top-down iki aşamalı, v1 zayıf nokta 1'e geri dönüş olurdu |
| 2026-08-25 | Düşme ölçütü `body_tilt = max(iskelet açısı, bbox eğimi)` | İskelet omurga açısı tepesi `fall_01`'de 20.2 derece, eşik 45 — kamera eksenine doğru düşende kalça→omuz vektörü görüntüde dik kalıyor. bbox eğimi her karede var ve `aspect 1.0` tam 45 dereceye düşüyor, yani eşik birimi değişmiyor |
| 2026-08-25 | Eksik keypoint'te `spine_angle = -1.0` | Önceki `0.0` "dimdik" demekti; kalça kaybolunca düşme sessizce yanlış negatife dönüyordu |
| 2026-08-25 | `centroid` her zaman bbox merkezi, mid_hip değil | Kalça kaybolunca merkez kaynağı değişiyor ve iki nokta arası sabit fark tek karede hız gibi okunuyordu (`fall_01` 5.61 sn: 2.46 / -2.79) |
| 2026-08-25 | RUN'a ikinci kanıt: adım ritmi | Yatay görüntü hızı kamera ekseni boyunca harekette veya kamera özneyi takip ederken ölçülemiyor (run_01 tepe 0.41, mixed_01 1.04, sabit kamerada police_run 1.77 — eşik 1.80). Adım döngüsü kamera geometrisinden bağımsız |
| 2026-08-25 | Adım medyanı 50 kare, `run_gait_speed` 1.20 | 10 karelik pencerede ayrım yok (yürüyüş p95 1.28, koşu 1.45); 50 karede yürüyüş 1.00'a inerken koşu 1.46'da kalıyor. Bedeli 2 sn tespit gecikmesi |
| 2026-08-25 | `window_frames` 30 → 50 | Adım medyanı 2 saniyelik pencere istiyor; bedeli iz başına 50 `FrameFeatures` |
| 2026-08-25 | Türev, tampon dolmadan hesaplanmaz | Kısa pencerede `dt` tek kareye düşüp kutunun oturma titremesini hız yapıyordu: `normal_01` 0.4 sn'de 25 sahte RUN. Bedeli iz başına 0.2 sn sessizlik |
| 2026-08-25 | `zone_01` değerlendirmesi 28. saniyede kesiliyor | Klip kurgu: 28. sn'de kamera değişiyor, bölge poligonu kameraya bağlı olduğu için otopark sahnesindeki yayaların üstüne düşüyordu. 20 yanlış pozitif saniyenin tamamı buradandı |
| 2026-08-25 | Eşikler pilot kliplere uydurulmadı | `mixed_01`'in koşusu adım kanıtında normal yürüyüşle örtüşüyor (0.69 vs 0.66). Ayıracak eşik yok; zorlanırsa `zone_01`'in normal yürüyüşü de RUN olurdu. Beş klibe uydurmak test kümesini ezberlemektir |

---

## Açık sorular

- ReID kalitesi kalabalık/kesişmeli sahnede ölçülmedi — pilot klipler yeterince
  zor değil, `--no-reid` ile ID sayıları hiç değişmedi. YOLO26 geçişinden sonra
  amaca özel ReID ağıyla tekrar denendi, sonuç aynı: bu kliplerde fark yok
- ReID'in kare başına ~7 ms sabit maliyeti çoklu kamerada N katına çıkar mı,
  yoksa kroplar tek batch'te birleştirilebilir mi (Aşama 10)
- Kadrajdan çıkıp geri giren kişi yeni ID alıyor. Olay bazlı ReID galerisi
  (aynı kişiyi tekrar bağlama) Aşama 9'a bırakıldı
- Çoklu kamera toplu çıkarımı gerçek FPS'te ölçülmedi (Aşama 10). Temiz
  ölçümde toplu çıkarım kare başına maliyeti belirgin düşürdü, ama tek
  process içinde N kamerayla tekrar ölçülmeli
- Frontend Tailwind şablonu henüz sağlanmadı (Aşama 8'e kadar gerekmiyor)
- Host'ta çalışan `vision/` gerçekten `localhost:9092`'ye yazabiliyor mu —
  port açık, ama uçtan uca producer denemesi Aşama 4'te yapılacak
- **Pilot küme RUN için yetersiz.** Etiketli iki koşu klibi de stok
  görüntüdür: birinde kamera koşucuyu takip ediyor, diğerinde kişi kameraya
  doğru koşuyor. Sabit kameralı, kadrajı kesen, etiketli bir koşu klibi yok.
  Aşama 10 değerlendirme kümesine böyle bir kayıt eklenmeli
- `police_run` (sabit kamera, gerçek koşu) hiç aday üretmiyor: 15 FPS, hız
  tepesi 1.77 (eşik 1.80), adım medyanı 0.52. Düşük kare hızı adım kanıtını
  da bastırıyor mu, yoksa klip mi tempolu yürüyüş — ayrı ölçülmeli
- FIGHT ve LOITERING kurallarının gerçek doğruluğu ölçülmedi; pilot kliplerde
  bu olaylar yok. Yalnızca yanlış pozitif üretmedikleri doğrulandı
- Bölge poligonu kameraya bağlıdır. Kurgu, PTZ veya kadraj değişen kayıtta
  aynı normalize koordinat başka bir yere düşer. Aşama 5'te `zones` tablosu
  `camera_id` FK'siyle bunu yapısal olarak çözüyor; kurgu klip yine de
  değerlendirme dışıdır

Kapanan sorular:

- 4 GB VRAM'de `yolov8s-pose` sığıyor mu — evet, 49 MiB tepe kullanım
- Gerçek döngüde FPS ne olacak — YOLO26 + ReID ile 27–37 FPS (4K olmayan
  kliplerde), webcam 24.3
- BoT-SORT ReID çalışıyor mu — evet; YOLO26'da `yolo26s-reid.onnx` üzerinden,
  kalitesi ise hâlâ kanıtlanmadı (yukarıdaki açık soru)
- YOLO26'nın daha az kişi bulması gerçek kaçırma mı — hayır, güven eşiği
  kalibrasyonuydu; `conf=0.25` v8 davranışını yakalıyor

---

## Test videoları

`data/pilot/` altında (v1 projesinden kopyalandı, `.gitignore`'da):
`normal_01`, `run_01`, `fall_01`, `zone_01`, `mixed_01`, `police_run`.

Kaynak:
`C:\Users\pc\OneDrive\Masaüstü\projeler\VideoAnomalySystem\datasets\pilot\videos`

Yeniden kopyalamak için:

```bash
mkdir -p data/pilot
cp "C:/Users/pc/OneDrive/Masaüstü/projeler/VideoAnomalySystem/datasets/pilot/videos/"*.mp4 data/pilot/
```
