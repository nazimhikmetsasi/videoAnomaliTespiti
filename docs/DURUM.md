# Proje Durumu

Bu dosya her aşama sonunda güncellenir. Yeni oturum açıldığında önce
`docs/PLAN.md` sonra bu dosya okunur ve kaldığı yerden devam edilir.

**Son güncelleme:** 2026-08-28

---

## Şu an neredeyiz

**Aşama 5 — Veri katmanı ve API tamamlandı.** Zincirin son halkası kapandı:
`vision/` → Kafka → Spark → **tüketici → PostgreSQL + MongoDB** → REST API.
Pilot kliplerin tam geçişi veritabanına **5 doğrulanmış olay** yazdı ve bu
beş satır Aşama 4'te ölçülen beş oturumla tip, klip ve **süre olarak birebir**
aynı (`fall_01` 33 ms, `run_01` 11067 ms, `zone_01` 1800 / 27640 / 1000 ms).
Ölçüm iki kez, iki ayrı geçişte tekrarlandı ve aynı çıktı geldi.

Bu aşamanın esas kazancı olay satırının yazılması değil, **zincirin
kırılganlığının nerede olduğunun ölçülmüş olmasıdır.** Uçtan uca ilk deneme
sıfır olay üretti: Spark, ayakta görünen bir konteynerde ölmüştü — kalıcı
checkpoint kalıcı olmayan bir Kafka log'unun offset'ini bekliyordu. Tüketici
ve API kusursuz çalışıyordu; sorun ikisinde de değildi. Aynı sınıftan üç
sessiz hata daha bulundu ve düzeltildi (§ Aşama 5 sonucu, "Yol boyunca
bulunan hatalar"). Sıradaki iş Aşama 6 (canlı görüntü ve kanıt).

## Aşama durumu

| # | Aşama | Durum |
|---|---|---|
| — | Plan ve mimari (`docs/PLAN.md`) | Tamamlandı |
| 0 | Ortam hazırlığı | Tamamlandı |
| 1 | Altyapı (Docker, veritabanı şeması) | Tamamlandı |
| 2 | Kaynak ve görü çekirdeği | Tamamlandı |
| 2.1 | YOLOv8 → YOLO26 geçişi | Tamamlandı |
| 3 | Öznitelik ve kural motoru | Tamamlandı |
| 4 | Kafka ve Spark | Tamamlandı |
| 5 | Veri katmanı ve API | Tamamlandı |
| 6 | Canlı görüntü (WebSocket) | Sırada |
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

## Aşama 4 sonucu (2026-08-27)

Uygulama sözleşmesi `docs/ASAMA4_PLAN.md`'de; burada yalnızca sonuç ve
ölçümler var.

### Yazılan dosyalar

| dosya | satır | iş |
|---|---|---|
| `vision/publish.py` | 132 | Kafka producer, `candidate_to_dict`, `CandidatePublisher` |
| `stream/spark_job.py` | 140 | Structured Streaming, oturum penceresi |
| `stream/filters.py` | 30 | `session_passes` — eşik mantığının tek referans kopyası |
| `eval/spark_eval.py` | 367 | uçtan uca ölçüm: aday üret, bas, tüket, tablo çıkar |
| `scripts/check_kafka.py` | 82 | host → broker gidiş-dönüş öz kontrolü |
| `tests/test_publish.py` | 76 | broker'sız üç öz kontrol |
| `vision/run.py` | 363 (+32) | `--kafka`, `--camera-id`, yayın süresi ölçümü |
| `docker-compose.yml` | +28 | `spark` servisi + iki volume |
| `infra/postgres/init.sql` | +7 | `spark_min_hits` 5→2, yeni `spark_min_sec` JSONB |

Spark imajı: `apache/spark:3.5.4-scala2.12-java17-python3-ubuntu`, paket
`org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.4` (sürüm imajla birebir).

### Ölçüm 1 — host → Kafka (açık soru kapandı)

`scripts/check_kafka.py`: **781 ms** gidiş-dönüş. Host'ta native çalışan
`vision/` gerçekten `localhost:9092`'ye yazıp geri okuyabiliyor. Aşama 1'den
beri açık olan soru kapandı.

### Kayan pencere yerine oturum penceresi

`docs/PLAN.md` "3 sn pencere / 1 sn kayma HAVING hits >= N" diyordu. Bu,
`run_01`'in kesintisiz 11 saniyelik koşusu için **11 ayrı doğrulanmış olay**
yazardı; Aşama 5'in tüketicisi 11 veritabanı satırı, 11 Gemini çağrısı ve 11
Telegram mesajı üretirdi. Tekrarı Aşama 5'te ayıklamak, `PLAN.md`'nin v1'de
eleştirdiği yama yığınının aynısı olurdu.

`session_window(event_time, "3 seconds")` aynı işi tek API ile yapıyor:
kesintisiz bir episod tek satır, `hits` ve süre bedava. Ölçülen sonuç:
`run_01`'in 333 adayı **1 olay**. `spark_window_sec = 3` ayarının anlamı
korundu, artık "3 saniyeden uzun sessizlik yeni olaydır" demek.

### Süzgeç neden tek eşik olamıyor

| kanıt | vuruş | süre |
|---|---|---|
| `fall_01` gerçek düşme | 2 | 0.03 sn |
| `normal_01` sahte koşu | 11 | 0.42 sn |

Tipten bağımsız `hits >= N` ölçütünde N'in 11'den büyük olması gerekirdi;
o da 2 adaylık gerçek FALL'ı elerdi. FALL bir **darbedir**, RUN/ZONE/
LOITERING bir **durumdur**. Süzgeç bu yüzden iki ölçütlü: global
`hits >= 2` (gerçek tek kare gürültüsünü eler, FALL'ın 2 adayını geçirir) +
tipe göre `min_sec` (FALL 0.0, RUN 1.0, ZONE_VIOLATION 1.0, LOITERING 2.0,
FIGHT 0.5).

Süre ölçütü ayrıca kare hızından bağımsızdır. `police_run` 15 FPS, diğer
pilotlar 25–30 FPS; yalnızca vuruş sayılsaydı aynı eşik 15 FPS'lik kamerada
iki katı süre talep ederdi.

### Ölçüm 2 — oturum dökümü (izin verici koşu)

Spark `MIN_HITS=0`, `SPARK_MIN_SEC={}` ile koşuldu; **tüm** oturumlar
`eval/out/events_sweep.jsonl`'a yazıldı.

| klip | tip | vuruş | süre | varsayılan eşikte |
|---|---|---|---|---|
| fall_01 | FALL | 2 | 0.03 | geçti |
| normal_01 | RUN | 11 | 0.42 | **elendi** |
| run_01 | RUN | 333 | 11.07 | geçti |
| zone_01 | ZONE_VIOLATION | 13 | 0.48 | **elendi** |
| zone_01 | RUN | 35 | 1.80 | geçti (yanlış pozitif) |
| zone_01 | ZONE_VIOLATION | 643 | 27.64 | geçti |
| zone_01 | ZONE_VIOLATION (iz 3) | 26 | 1.00 | geçti |
| zone_01 | ZONE_VIOLATION (iz 4) | 22 | 0.84 | **elendi** |

Aday muhasebesi tam: 2 + 11 + 333 + 35 + (13+643+26+22 = 704) = **1085**,
Aşama 3'ün ham aday toplamının birebir aynısı. Kayıp aday yok, yani
publisher → Kafka → Spark zinciri veri düşürmüyor.

Aşama 3'te "ZONE ilk tetik 10.8 sn, gerçek referans 12.0" diye kaydedilen
yanlış pozitif, 13 vuruşluk 0.48 saniyelik bir oturum olduğu için elendi.
Doğrulanmış ZONE olayı 14.44'te başlıyor ve referans aralığın içinde.

### Ölçüm 3 — öncesi/sonrası

| klip | tip | ham aday | oturum | doğrulanmış olay |
|---|---|---|---|---|
| fall_01 | FALL | 2 | 1 | 1 |
| normal_01 | RUN | 11 | 1 | **0** |
| run_01 | RUN | 333 | 1 | 1 |
| zone_01 | RUN | 35 | 1 | 1 |
| zone_01 | ZONE_VIOLATION | 704 | 4 | 2 |

`mixed_01` ve `police_run` sıfır aday üretmeye devam ediyor (Aşama 3 ile
aynı), Spark bunu düzeltemez — ortada süzülecek aday yok.

| tip | Aşama 3 P/R/F1 | Aşama 4 P/R/F1 |
|---|---|---|
| FALL | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| RUN | 0.20 / 0.50 / 0.29 | 0.25 / 0.50 / 0.33 |
| ZONE_VIOLATION | 0.50 / 1.00 / 0.67 | **1.00 / 1.00 / 1.00** |
| **TOPLAM** | 0.38 / 0.75 / 0.50 | **0.50 / 0.75 / 0.60** |

Yanlış pozitif 5 → 3, recall değişmedi. Kalan üç yanlış pozitifin tamamı
`zone_01`'deki tek bir sahte RUN oturumundan geliyor (11.52–13.32 sn, saniye
bazında üç yanlış pozitif sayılıyor).

### Ölçüm 4 — RUN `min_sec` 2.0 varyantı: ölçüldü, alınmadı

| yapılandırma | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|
| RUN `min_sec` 1.0 (varsayılan) | 3 | 3 | 1 | 0.50 | 0.75 | 0.60 |
| RUN `min_sec` 2.0 | 3 | 0 | 1 | **1.00** | 0.75 | **0.86** |

2.0 eşiği `zone_01`'in 1.80 saniyelik sahte RUN oturumunu eler ve tabloyu
kusursuz precision'a çıkarır. **Alınmadı.** İki gerekçe:

1. Altı klipte tek bir yanlış pozitif episoduna göre eşik koymak, Aşama
   3'te bilinçle reddedilen "eşiği pilot kliplere uydurma" davranışının
   aynısıdır. Eşiği o oturumun süresine göre seçmek, test kümesini
   ezberlemektir.
2. Bedeli gerçek: RUN'da zaten 50 karelik adım medyanından gelen 2 saniyelik
   gecikme var; `min_sec` 2.0 bunu 4 saniyeye çıkarır. Koşan birinin 4 saniye
   sonra bildirilmesi güvenlik açısından anlamlı bir kayıptır.

Karar Aşama 10'daki genişletilmiş değerlendirme kümesine bırakıldı. Sabit
kameralı, kadrajı kesen etiketli koşu kayıtları geldiğinde bu eşik gerçek
veriyle seçilebilir.

### Ölçüm 5 — yayının görü döngüsüne maliyeti

`normal_01.mp4 --rules`, ikişer koşu:

| koşu | gerçek FPS |
|---|---|
| `--kafka` yok | 36.4 – 36.6 |
| `--kafka` var | 31.0 – 32.6 |

`kafka publish` aşamasının kendisi medyan ve p95'te **0.0 ms** — yani
`produce()` gerçekten bloklamıyor, tasarım tuttuğu gibi çalışıyor. Yaklaşık
%13'lük FPS kaybı ölçülen aşamanın içinde değil; librdkafka'nın arka plan
I/O iş parçacığının CPU'yu paylaşmasından geliyor. `PLAN.md` hedefi
(panel canlı FPS >= 20) hâlâ fazlasıyla karşılanıyor.

### Ölçüm 6 — gecikme (kısmi)

Yayın bitişinden `anomaly-events`'e düşene kadar: medyan **11.1 sn**, p95
**12.6 sn** (n = 5).

**Bu sayı canlı kırmızı alarm gecikmesi DEĞİLDİR.** Değerlendirme betiği
klipleri toplu basıp akış sonu işaretçisiyle (`_EOS`) pencereleri kapatıyor;
ölçülen süre büyük ölçüde bu kapanış mekaniğidir. Canlı akışta beklenen
gecikme oturum boşluğu (3 sn) + damga (2 sn) + mikro-toplu tetiklemesidir,
ama **ölçülmedi**. Aşama 6'da uçtan uca gecikmeyle birlikte ölçülecek.

### Akış sonu işaretçisi (`_EOS`)

Dosya klibi bitince veri akışı durur, Spark'ın damgası ilerlemez ve klibin
son oturumu hiç yazılmaz. `CandidatePublisher.close()` bu yüzden damgayı 15
saniye ileri iten tek bir `_EOS` mesajı basıyor. `_EOS` toplamadan **önce**
elenmez — elenirse damga da ilerlemez; vuruş sayısı 1 olduğu için
`spark_min_hits >= 2` ile kendiliğinden düşer.

### Bilinen sınırlar (kapatılmadı, ölçüldü)

1. **`zone_01`'in sahte RUN'ı Spark'tan geçiyor.** 35 vuruş, 1.80 sn — süre
   ölçütünü aşıyor. Kalan üç yanlış pozitifin tamamı bu. Süzgeç gürültüyü
   eler, **yanlış kuralı düzeltmez**; bu bir kural/öznitelik sorunudur.
2. **`mixed_01` RUN kaçırması sürüyor.** Aşama 3'ten devam; aday
   üretilmediği için Spark'ın yapabileceği bir şey yok.
3. **FIGHT ve LOITERING hâlâ ölçülmedi.** Pilot kliplerde bu olaylar yok;
   `min_sec` değerleri (0.5 / 2.0) ölçüme değil akıl yürütmeye dayanıyor.
4. **Canlı gecikme ölçülmedi** (bkz. Ölçüm 6).
5. **Çalışan `postgres` volume'u `init.sql`'in gerisinde.** İçindeki şema
   Aşama 2.1 öncesinden kalma (`fall_spine_deg`, `pose_conf = 0.35`,
   `window_frames = 30`). `init.sql` yalnızca ilk oluşturmada çalışır.
   Aşama 5 ORM'i yazmadan önce volume yeniden oluşturulmalı:
   `docker compose down && docker volume rm videoanomalitespiti_postgres_data`.
   Kayıp veri yok, içinde yalnızca tohum admin kaydı var.

### Plandan sapmalar

1. **`Candidate` alanları JSON'a çevrilemiyordu.** `metrics`, `track_ids` ve
   `score` `numpy.float32`/`int64` tipindeydi. `candidate_to_dict` artık
   yerel Python tiplerine çeviriyor. Gerçek bir hatadır, planda yoktu.
2. **`stream/filters.py` planda yoktu.** Eşik mantığı üç yerde lazım
   (Spark işi, süpürme, test). Tek saf fonksiyona alındı ki iki yerde iki
   farklı eşik doğmasın.
3. **`spark_job.py`'da `sys.path` yaması.** `./stream:/app:ro` bağlaması
   paketi düzleştiriyor, konteyner içinde `stream.filters` import edilemiyor.
4. **`SPARK_MIN_SEC_DEFAULT=0` tek başına yetmiyor.** Beş tip de varsayılan
   haritada açıkça yazılı olduğu için gerçekten izin verici koşu
   `SPARK_MIN_SEC='{}'` de istiyor. İlk süpürme koşusu bu yüzden eksik
   çıktı ve tekrarlandı.
5. **`anomaly-events` topic'i koşular arasında birikiyor.** Yeni `group.id`
   + `earliest` ile okuyan tüketici önceki koşuların çıktısını da görüyordu.
   `consume_events` artık `start_time >= base_epoch` süzüyor.
6. **`--from-cache` sıfır adaylı klipleri düşürüyordu.** `candidates.jsonl`
   aday üretmeyen klibi hiç kaydetmiyor. `eval/out/.clip_stems` manifestosu
   eklendi.
7. **Gecikme ölçümü yeniden tanımlandı.** Klipler bilinçli olarak 1000
   saniyelik sentetik epoch aralıklarıyla ayrıldığı için sahne zamanı
   (`event_time`) ile duvar saatinin farkı anlamsız. Ölçüm klip başına
   "yayın bitişi → alım" farkına çevrildi.
8. **`eval/spark_eval.py` 367 satır** (bütçe ~220). Karşılaştırma:
   `pilot_eval.py` 184, `feature_stats.py` 191. İçinde GPU aday üretimi,
   epoch izolasyonlu yayın, bayat mesaj süzen tüketim, dört tablo ve
   çevrimdışı eşik süpürmesi var.
9. **Plandaki imaj doğrulama komutu yanlıştı.** `docker run --rm <imaj>
   python3 -c "import pyspark"` başarısız oluyor; pyspark `PYTHONPATH`'e
   yalnızca `spark-submit` önyüklemesiyle giriyor. İmaj sağlam, doğrulama
   gerçek mekanizmayla yapıldı.

---

## Aşama 5 sonucu (2026-08-28)

Uygulama sözleşmesi: `docs/ASAMA5_PLAN.md`. Kod iki Sonnet alt ajanına
verildi (API katmanı / tüketici + sıcak yükleme + testler); ölçümler ve
aşağıdaki düzeltmeler ana oturumda yapıldı.

### Yazılan dosyalar

| dosya | satır | ne yapar |
|---|---|---|
| `api/main.py` | 45 | FastAPI kurulumu, router kaydı, `/health` |
| `api/config.py` | 42 | tek ortam okuma noktası; `DATABASE_URL` yoksa `POSTGRES_*`'tan kurar |
| `api/auth.py` | 89 | `pgcrypto crypt()` ile şifre doğrulama, JWT, `require_role` |
| `api/schemas.py` | 216 | pydantic v2 gövdeleri |
| `api/audit.py` | 20 | `audit_log` yazıcı |
| `api/db/models.py` | 148 | SQLAlchemy 2.0, 7 tablo, `create_all` yok |
| `api/db/postgres.py` / `mongo.py` | 24 / 25 | engine + oturum / tembel `MongoClient` |
| `api/routers/*.py` | 37–95 | auth, cameras, zones, settings, events, analytics |
| `api/workers/consumer.py` | 256 | `anomaly-events` → PostgreSQL + MongoDB |
| `vision/settings_client.py` | 100 | eşik sıcak yükleme (arka plan iş parçacığı) |
| `scripts/seed_pilot.py` | 73 | pilot klipler için kamera + bölge tohumu |
| `tests/test_consumer.py` | 107 | `event_to_row` saf fonksiyon testi |
| `tests/test_api_units.py` | 183 | JWT, poligon, eşik birleştirme, sıcak yükleme |
| `tests/test_schema_sync.py` | 46 | ORM ile canlı şema arasında drift kontrolü |

Değişenler: `infra/postgres/init.sql` (+`idx_events_dedup`),
`docker-compose.yml` (+`api`, +`consumer`), `.env.example`, `vision/run.py`
(+3 argüman, ~25 satır), `stream/spark_job.py` (+`failOnDataLoss`).

`api/workers/consumer.py` 256 satır — plandaki 140 hedefinin üstünde. Şişme
süs değil: kamera/bölge önbelleği, kalıcı-geçici hata ayrımı ve sayaçlar.
Bölünecek doğal bir sınır yok; bölmek çağrı zincirini uzatırdı.

### Ölçüm 1 — uçtan uca zincir

`docker compose up -d` → `scripts/seed_pilot.py` → beş pilot klip
`--kafka --camera-id <klip>` ile koşturuldu. Veritabanına düşen satırlar
(API'nin `GET /api/events` ucundan okundu):

| id | kamera | tip | iz | skor | şiddet | süre (ms) | Aşama 4 oturumu |
|---|---|---|---|---|---|---|---|
| 8 | run_01 | RUN | [1] | 0.999 | medium | 11067 | 11.07 sn ✓ |
| 9 | fall_01 | FALL | [1] | 0.999 | critical | 33 | 0.03 sn ✓ |
| 10 | zone_01 | RUN | [1] | 0.999 | medium | 1800 | 1.80 sn ✓ |
| 1011 | zone_01 | ZONE_VIOLATION | [1] | 0.999 | high | 27640 | 27.64 sn ✓ |
| 1012 | zone_01 | ZONE_VIOLATION | [4] | 0.999 | high | 1000 | 1.00 sn ✓ |

**Beş olay, beşi de Aşama 4'ün beklediği oturum.** `normal_01`'in 11 adaylık
sahte koşusu ve `mixed_01`'in sıfır adayı beklendiği gibi olay üretmedi;
süzgeç canlı zincirde de eliyor. `id` boşlukları gerçek: 1008–1010 gecikme
ölçümünün sentetik satırları, 3 ise tekrar korumasının yaktığı sıra numarası.

Ölçüm iki geçişte tekrarlandı (ilk geçişte `normal_01` ve `run_01` aşağıdaki
Spark hatası yüzünden kayıptı). İkinci geçiş beş olayın tamamını aynı
sürelerle üretti. Görü tarafındaki aday sayıları da Aşama 4 ile birebir:
`normal_01` 11, `run_01` 333, `fall_01` 2, `zone_01` 35 RUN + 703 ZONE,
`mixed_01` 0.

### Ölçüm 2 — tekrar yazma koruması

Aynı `anomaly-events` mesajı elle iki kez üretildi:

```
mesaj 1 basildi
mesaj 2 basildi
-> events: 1 satir (id 2), telemetry: 1 belge
```

`idx_events_dedup` + `ON CONFLICT DO NOTHING` çalışıyor. İkinci INSERT bir
`BIGSERIAL` değeri yakıyor (id 3 boş kaldı) — beklenen davranış; sıra
numarası boşluğu kayıp satır anlamına gelmiyor.

### Ölçüm 3 — eşik sıcak yükleme

`zone_01` koşarken `PUT /api/settings/7` ile `run_norm_speed` 1.80 → 1.55:

```
PUT 200 @ 15:23:48.072
[15:23:30] esik guncellendi: ... run_norm_speed=1.8 ...     <- baslangic senkronu
[15:23:53] esik guncellendi: ... run_norm_speed=1.55 ...    <- PUT'tan ~5 sn sonra
esik sicak yukleme    : 2 kez uygulandi, 0 hata
```

Gecikme **~5 sn**, yani yoklama aralığının kendisi. **Pipeline yeniden
başlamadı:** aynı process, kesintisiz FPS sayacı, korunan iz id'leri.

Sınır dürüstçe yazılıyor: bu ölçüm eşiğin *uygulandığını* kanıtlar,
*sonucu değiştirdiğini* kanıtlamaz — değişiklik klibin RUN adayları
üretildikten sonra oturdu, aday sayısı (35) değişmedi. Eşik değişiminin
karara etkisi Aşama 8'de panelden ölçülecek.

### Ölçüm 4 — uç gecikmeleri

1008 olay satırıyla, 10 ardışık istek, iki ayrı yerden:

| uç | konteyner içinden p50 / p95 | Windows host'tan p50 / p95 |
|---|---|---|
| `GET /api/events?limit=50` | 41.0 / 71.6 ms | 594 / 728 ms |
| `GET /api/analytics/summary` | 39.3 / 56.4 ms | 647 / 671 ms |
| `GET /api/analytics/ablation` | 25.4 / 42.9 ms | 658 / 730 ms |
| `GET /api/cameras` | 21.6 / 39.1 ms | 588 / 701 ms |
| `GET /api/settings` | 28.4 / 31.8 ms | 604 / 646 ms |
| `GET /health` | 18.1 / 23.2 ms | 754 / 794 ms |

**Bulgu:** host'tan ölçülen ~600 ms sabit bir tabandır, sorgu maliyeti
değil. Konteyner içinden bakınca `/health` (bir `SELECT 1` + bir `ping`) 18
ms, 1008 satır tarayan `/api/events` 41 ms; host'tan bakınca bu fark
kayboluyor. Yük Docker Desktop'ın Windows port yönlendirmesinde (WSL2 NAT),
API'de değil. Panel geliştirilirken bu taban hesaba katılmalı; sunucuya
taşındığında kendiliğinden kalkar.

### Ölçüm 5 — Swagger

`/openapi.json` 200, `/docs` 200. Açılan uçlar: `/health`,
`/api/auth/login|me`, `/api/cameras` (+`{id}`, +`{id}/heartbeat`),
`/api/zones` (+`{id}`), `/api/settings` (+`{camera_id}`), `/api/events`
(+`{id}`), `/api/analytics/summary|ablation`. Plan §9 listesinin tamamı.

### Testler

`venv/Scripts/python.exe -m pytest tests/ -q` → **42 geçti, 2 atlandı**
(8.13 sn). Atlananlar `test_schema_sync.py`: `.env` yüklü olmayan bir kabukta
veritabanına bağlanamıyor. `.env` yüklü ortamda ayrıca koşturuldu, **ikisi de
geçti** — ORM ile canlı şema arasında drift yok.

### Yol boyunca bulunan hatalar (hepsi düzeltildi)

1. **Spark ölmüştü, konteyner ayakta görünüyordu.** `Partition
   anomaly-candidates-2's offset was changed from 12 to 0`. Kafka log'u
   kalıcı değil (Aşama 1 kararı) ama `spark_checkpoints` volume'u kalıcı;
   broker yeniden kurulunca checkpoint var olmayan bir offset'i bekliyor.
   Çözüm: `failOnDataLoss=false` + bozuk checkpoint'in sıfırlanması. Bu
   hatanın belirtisi "hiç olay yazılmıyor"du; tüketici ve API kusursuzdu.
2. **`MongoClient` import anında kuruluyordu.** `MongoClient(url)` şifresiz
   URL'de `ConfigurationError` fırlatıyor; `api.workers.consumer` ortam
   değişkeni olmayan her yerde daha içe aktarılırken patlıyordu ve
   `tests/test_consumer.py` toplama aşamasında düşüyordu. İstemci ilk
   kullanıma ertelendi.
3. **Kalıcı `IntegrityError` sonsuza kadar yeniden deneniyordu.** Plan
   "veritabanı hatasında yeniden dene" diyor; CHECK/FK ihlali ise asla
   düzelmez ve tüketiciyi arkasındaki tüm olaylarla birlikte kilitler.
   `IntegrityError` ayrıldı: satır bozuk sayılıp atlanıyor, offset commit
   ediliyor. (Tekrar kaydı zaten `ON CONFLICT` ile eleniyor, buraya
   düşmüyor.)
4. **`PUT /api/settings` tam gövde istiyordu.** Tek bir eşiği değiştirmek 13
   alanın tamamını göndermeyi gerektiriyordu (422). Panelde bu, forma
   dokunulmamış bir alanı eski değerine geri yazma riski demek. Gövde kısmi
   hale getirildi (`exclude_unset`); yeni kamera satırı global'den miras
   alıyor.
5. **`idx_events_dedup` canlı veritabanında yoktu.** `init.sql` yalnızca boş
   veri diziniyle ilk açılışta çalışır; index elle uygulandı. Şema
   değişikliği bundan sonra hep bu iki adımı isteyecek — Alembic'in Aşama
   9'da gireceği yer tam olarak burasıdır.

### Plandan sapmalar

- **Alembic kurulmadı** (`docs/ASAMA5_PLAN.md` §2): şema tek kaynak
  `init.sql`, drift'i `tests/test_schema_sync.py` yakalıyor. Alembic Aşama
  9'a ertelendi.
- **`api/requirements.txt` ayrı dosya:** kök `requirements.txt` torch +
  ultralytics + onnxruntime-gpu içeriyor, API'nin hiçbirine ihtiyacı yok.
- **`PUT /api/settings` kısmi gövde** kabul ediyor (yukarıda 4).
- **`--settings-url` kullanılıyorsa `--camera-id` sayısal olmalı:**
  `/api/settings/{camera_id}` int bekliyor. Kafka tarafı klip adını da
  kabul ediyor (tüketici `id::text = :cid OR name = :cid` ile çözüyor), eşik
  ucu çözmüyor.

### Bilinen sınırlar (kapatılmadı, ölçüldü)

1. `events.mongo_ref` ve `pose_sequences` boş. Ham keypoint dizisi Kafka
   mesajında yok, `vision/` sürecinin belleğinde — kanıt üretimiyle birlikte
   Aşama 6'da gelecek. `telemetry` koleksiyonu yazılıyor.
2. `frame_path`, `clip_path`, `llm_report_tr` NULL (Aşama 6 / 7).
3. Docker altyapısı ayaktayken görü hattının FPS'i **36.5 → 12–15**'e düştü.
   Aynı dizüstünde Spark, Kafka, iki veritabanı ve iki Python servisi CPU
   için yarışıyor. GPU değil CPU darboğazı; Aşama 10'un çoklu kamera ölçümü
   bunu izole etmek zorunda.
4. Gecikme ölçümünün 1000 sentetik satırı `events` tablosunda duruyor
   (`llm_report_tr = 'SENTETIK-YUK-TESTI'`). Temizlemek için:
   `DELETE FROM events WHERE llm_report_tr = 'SENTETIK-YUK-TESTI';`
5. `spark_min_sec` JSONB sütunu hâlâ Spark işine bağlı değil; Spark eşikleri
   ortam değişkeninden okuyor. Veritabanındaki değer değişince Spark uymuyor.
   Aşama 6'da bağlanacak.
6. Kullanıcı yönetimi CRUD'u yok (yalnızca `admin` tohumu ve `/auth/me`).
   Panelin kullanıcı ekranı Aşama 8'de gerektiğinde açılacak.

---

## Bir sonraki adım

Aşama 6 — Canlı görüntü ve kanıt:

1. `api/ws/live.py`: ikili JPEG kare akışı, adaptif kalite.
2. `api/ws/meta.py`: tracks / poses / zones / sarı ön-alarm JSON akışı.
3. `api/ws/alerts.py`: Spark'tan geçen kırmızı alarmın yayını (tüketici
   satırı yazdıktan sonra tetikler).
4. `vision/evidence.py`: halka tampon → ±5 sn mp4 klip + en iyi kare;
   `events.frame_path` / `clip_path` / `mongo_ref` bu aşamada dolar,
   `pose_sequences` koleksiyonu burada yazılır.
5. `vision/run.py` → `PATCH /api/cameras/{id}/heartbeat` (uç açık, çağıran
   yok) ve `camera_health` koleksiyonuna yazım.
6. `spark_min_sec` JSONB sütununu Spark işine bağla (bilinen sınır 5).

**Onay kriteri:** tarayıcıda 20+ FPS, uçtan uca gecikme 300 ms altında, olay
klibi oynatılabiliyor.

Ölçülmesi gerekenler: canlı akışta kırmızı alarm gecikmesi (Aşama 4'ten kalan
açık soru) ve Docker altyapısı ayaktayken görü FPS'inin düşüşü (bilinen
sınır 3).

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
| 2026-08-27 | Kayan pencere değil `session_window` | Kayan pencere `run_01`'in 11 sn'lik tek koşusu için 11 ayrı doğrulanmış olay yazardı; tekrarı Aşama 5'te ayıklamak yama yığını olurdu. Oturum penceresi episodu tek satır yapıyor: 333 aday → 1 olay |
| 2026-08-27 | Süzgeç iki ölçütlü ve tipe göre | Gerçek FALL 2 aday, sahte RUN 11 aday üretiyor. Tek `hits` eşiği ya FALL'ı eler ya gürültüyü geçirir. FALL darbe, RUN/ZONE durum |
| 2026-08-27 | `min_sec` süre cinsinden, kare cinsinden değil | `police_run` 15 FPS, diğerleri 25–30. Kare sayan eşik 15 FPS'lik kamerada iki katı süre talep eder |
| 2026-08-27 | `spark_min_hits` varsayılanı 5 → 2 | 5, `fall_01`'in 2 adaylık gerçek düşmesini elerdi |
| 2026-08-27 | `spark_min_sec` JSONB sütunu | Tip başına ayrı sütun yeni kural tipinde şema göçü ister; JSONB istemez |
| 2026-08-27 | Akış sonu işaretçisi `_EOS` | Dosya bitince damga ilerlemiyor ve klibin son oturumu hiç yazılmıyordu. Toplamadan önce elenmez, yoksa damgayı da ilerletmez |
| 2026-08-27 | Pencerelenen zaman sahne zamanı | 25 FPS'lik klip 35 FPS'te işlenirse duvar saatiyle 3 sn'lik pencere 4 sn'lik sahneyi kapsar; ölçüm tekrarlanabilir olmaz |
| 2026-08-27 | `confluent-kafka`, `kafka-python` değil | `produce()` kuyruğa atıp dönüyor; ölçülen maliyeti 0.0 ms. Saf Python istemci GPU döngüsünün içinde GIL altında protokol işi yapardı |
| 2026-08-27 | RUN `min_sec` 1.0 kaldı, 2.0 reddedildi | 2.0 toplam precision'ı 1.00'a çıkarıyor ama tek klipteki tek yanlış pozitife göre seçilmiş olur ve RUN gecikmesini 2 sn'den 4 sn'ye çıkarır |
| 2026-08-25 | Eşikler pilot kliplere uydurulmadı | `mixed_01`'in koşusu adım kanıtında normal yürüyüşle örtüşüyor (0.69 vs 0.66). Ayıracak eşik yok; zorlanırsa `zone_01`'in normal yürüyüşü de RUN olurdu. Beş klibe uydurmak test kümesini ezberlemektir |

| 2026-08-28 | Alembic kurulmadı, şema tek kaynak `init.sql` | Üzerinde veri olmayan bir veritabanında göç aracının getirisi yok; şema iki yerde tanımlanınca kaçınılmaz olarak ayrışıyor. Drift'i 46 satırlık bir test yakalıyor. Gerçek ihtiyaç Aşama 9'da (yeni sınıflar + birikmiş `telemetry`) doğacak |
| 2026-08-28 | Şifre doğrulaması `pgcrypto crypt()` ile veritabanında | Hash zaten `init.sql`'de bcrypt'lendi; Python'a `passlib`/`bcrypt` sokmak ikinci bir hash yolu ve ikinci bir hata kaynağı demek |
| 2026-08-28 | Senkron SQLAlchemy + `def` uçlar | 4 kameralık sistemde asenkron sürücünün ölçülebilir getirisi yok; tüketici aynı `sessionmaker`'ı paylaşınca ikinci bir veri katmanı yazılmıyor. WebSocket işleyicileri yine `async` kalabilir |
| 2026-08-28 | `camera_id` çözümü `id::text = :cid OR name = :cid` | Panel sayısal id ile, pilot değerlendirme klip adıyla yayın yapıyor; tek sorgu ikisini de karşılıyor. Bulunamayan kamerada satır yaratılmıyor, mesaj atlanıyor |
| 2026-08-28 | `idx_events_dedup` + `ON CONFLICT DO NOTHING`, offset elle commit | Kafka en-az-bir-kez teslim ediyor. Oturum penceresi bir episodu tek satır yazdığı için (camera, tip, başlangıç, izler) doğal anahtar. Offset DB yazımından sonra commit edilirse en kötü ihtimal tekrar, kayıp değil |
| 2026-08-28 | `IntegrityError` yeniden denenmez, atlanır | CHECK/FK ihlali yeniden denemeyle düzelmez; tüketiciyi arkasındaki tüm olaylarla kilitler. Tekrar kaydı zaten `ON CONFLICT` ile eleniyor |
| 2026-08-28 | `MongoClient` ilk kullanımda kurulur | Import anında kurulunca `consumer` modülü ortam değişkeni olmayan her yerde içe aktarılırken patlıyor; saf fonksiyon testi Mongo'ya bağlanmak zorunda kalıyordu |
| 2026-08-28 | Spark `failOnDataLoss=false` | Kafka log'u kalıcı değil ama checkpoint kalıcı; broker yeniden kurulunca sorgu "offset 12'den 0'a düştü" diye ölüyor. Kalıcı olmayan log'da veri kaybı zaten kabul edilmiş bir maliyet, olaylar PostgreSQL'de yaşıyor |
| 2026-08-28 | `PUT /api/settings` kısmi gövde kabul eder | Tek eşik için 13 alanın tamamını göndermek, formda dokunulmamış alanı eski değerine geri yazma (lost update) riski demek. Yeni kamera satırı global'den miras alır |
| 2026-08-28 | Sıcak yükleme yalnız kural eşiklerini kapsar | `pose_conf`/`track_conf` model ve tracker kurulumunda, `window_frames` öznitelik tamponunda donuyor. API yanıtı `restart_required` listesini taşıyor ki panel yalan söylemesin |
| 2026-08-28 | Şiddet (severity) tipten türetilir, skordan değil | Kural skorları tipler arasında karşılaştırılabilir bir ölçekte değil (her kural kendi eşiğine normalize ediyor); skoru şiddete çevirmek uydurma bir hassasiyet olurdu |
| 2026-08-28 | `api/requirements.txt` ayrı | Kök dosya torch + ultralytics + onnxruntime-gpu içeriyor; API imajının hiçbirine ihtiyacı yok. İkinci bir dosya 2 GB'lık gereksiz imajdan ucuz |

---

## Açık sorular

- Windows host'tan API uçlarına gecikme ~600 ms sabit taban gösteriyor;
  konteyner içinden aynı uç 18–41 ms. Fark Docker Desktop'ın port
  yönlendirmesinden geliyor gibi duruyor ama izole edilmedi (WSL2 NAT mı,
  makinenin GPU yükü mü). Panel geliştirmeye başlamadan ölçülmeli
- Docker altyapısı ayaktayken görü FPS'i 36.5'ten 12–15'e düşüyor. CPU
  rekabeti olduğu varsayıldı (Spark + Kafka + iki veritabanı + iki Python
  servisi), profillenerek doğrulanmadı. Aşama 10'un çoklu kamera ölçümü bu
  taban üzerinde yapılmamalı
- `spark_min_sec` veritabanında ama Spark ortam değişkeninden okuyor;
  panelden değiştirilen değer akışa ulaşmıyor (Aşama 6)
- Tüketici tek process. Aşama 10'un 4 kamerasında tek tüketicinin yetip
  yetmeyeceği ölçülmedi; Kafka tarafı ölçeklenebilir (aynı group.id ile
  ikinci konteyner), veritabanı tarafı ölçülmeli

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

- Canlı akışta kırmızı alarm gecikmesi ölçülmedi. Aşama 4'teki 11.1 sn
  medyan değerlendirme betiğinin kapanış mekaniğidir, sistemin gecikmesi
  değil. Tasarım beklentisi oturum boşluğu 3 sn + damga 2 sn + mikro-toplu;
  Aşama 6'da uçtan uca ölçülecek
- `--kafka` açıkken FPS 36.5'ten 31.8'e düşüyor ama ölçülen `publish`
  aşaması 0.0 ms. Kaybın librdkafka'nın arka plan I/O iş parçacığından
  geldiği varsayıldı, doğrulanmadı. Çoklu kamerada (Aşama 10) tekrar ölçülmeli
- FIGHT ve LOITERING için seçilen `min_sec` değerleri (0.5 / 2.0) ölçüme
  değil akıl yürütmeye dayanıyor; bu olayları içeren klip yok
- `zone_01`'in sahte RUN'ı (35 vuruş, 1.80 sn) Spark'tan geçiyor. Süzgeç
  gürültüyü eler, yanlış kuralı düzeltmez — kök neden RUN kuralının kendisinde

Kapanan sorular:

- 4 GB VRAM'de `yolov8s-pose` sığıyor mu — evet, 49 MiB tepe kullanım
- Gerçek döngüde FPS ne olacak — YOLO26 + ReID ile 27–37 FPS (4K olmayan
  kliplerde), webcam 24.3
- BoT-SORT ReID çalışıyor mu — evet; YOLO26'da `yolo26s-reid.onnx` üzerinden,
  kalitesi ise hâlâ kanıtlanmadı (yukarıdaki açık soru)
- YOLO26'nın daha az kişi bulması gerçek kaçırma mı — hayır, güven eşiği
  kalibrasyonuydu; `conf=0.25` v8 davranışını yakalıyor
- Host'ta çalışan `vision/` `localhost:9092`'ye yazabiliyor mu — evet,
  `scripts/check_kafka.py` gidiş-dönüş 781 ms
- Spark tek kare gürültüsünü eliyor mu — evet, ama tek eşikle değil: vuruş
  sayısı + tipe göre süre gerekti (§ Aşama 4 sonucu)

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
