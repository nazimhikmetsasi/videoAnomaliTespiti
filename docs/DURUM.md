# Proje Durumu

Bu dosya her aşama sonunda güncellenir. Yeni oturum açıldığında önce
`docs/PLAN.md` sonra bu dosya okunur ve kaldığı yerden devam edilir.

**Son güncelleme:** 2026-09-10

---

## Şu an neredeyiz

**Aşama 8.4 — canlı izleme tamamlandı.** Panel artık gerçek kareyi
gösteriyor: ızgara (1 / 2x2 / 3x3), kutu / iskelet / bölge / ID katmanları,
kopmada kendiliğinden yeniden bağlanma ve `/ws/alerts` kırmızı alarmı.

Onay kriteri ölçüldü: **tarayıcıda 25.2 FPS** (v1: 0.67; hedef 20+).
Tarayıcı sunucunun ürettiği her kareyi çiziyor — istemci darboğaz değil.
Tam hat (Kafka + Spark + consumer + Telegram) aynı makinede çalışırken
görü döngüsünün kendisi ~10 FPS'e iniyor; bu, kayıtlı CPU rekabeti açık
sorusunun tazelenmiş kanıtı.

Alarm zinciri uçtan uca çalıştı: 11 yeni olay, 11 gerçek Telegram
bildirimi, panelde toast + kırmızı kutu.

Sıradaki iş 8.5 (yazma ekranları): kamera ekle/düzenle/sil, bölge poligon
çizimi, eşik ayar formu, olay durumu güncelleme, kullanıcı yönetimi.

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
| 6 | Canlı görüntü (WebSocket) | Tamamlandı |
| 7 | LLM ve Telegram | Tamamlandı |
| 8 | Panel (kullanıcı şablonu) | Tamamlandı (8.1–8.6) |
| 9 | TCN modeli ve yeni sınıflar | Tamamlandı (9.1–9.5) |
| 10 | Ölçek ve tez çıktıları | **tamam** — 10.5 dahil: 8.0 saat, 4 kamera, kesintisiz |

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

---

## Aşama 6 sonucu (2026-09-09)

Zincirin son iki eksiği kapandı: panel canlı kareyi görebiliyor ve olayın
kanıtı (klip + kare + iskelet dizisi) üretilip veritabanına bağlanıyor.

```
vision/ (host, GPU) ──┬─ ws://localhost:8001/ws/live  ikili JPEG
                      ├─ ws://localhost:8001/ws/meta  JSON overlay
                      ├─ storage/clips, storage/frames + POST /api/evidence
                      ├─ MongoDB pose_sequences, camera_health
                      └─ Kafka → Spark → consumer → PostgreSQL
                                            └─ ws://localhost:8000/ws/alerts
```

### Yazılan dosyalar

| dosya | satır | ne yapar |
|---|---|---|
| `vision/ws_server.py` | 166 | olay güdümlü WebSocket sunucusu, JWT yerel doğrulama |
| `vision/evidence.py` | 436 | epizot, mp4 klip, en iyi kare, `pose_sequences` |
| `vision/health_client.py` | 93 | kalp atışı + `camera_health` |
| `scripts/ws_client.py` | 151 | ölçüm istemcisi: FPS, gecikme, alarm |
| `api/routers/evidence.py` | 115 | `POST`/`GET /api/evidence`, çift yönlü eşleşme |
| `api/ws/alerts.py` | 120 | `/ws/alerts` + ikinci Kafka tüketicisi |
| `api/ws/manager.py` | 35 | bağlı istemci kümesi, yayın |
| `api/matching.py` | 48 | eşleşme toleransı = `spark_window_sec` |
| `vision/run.py` | +178 | `--ws`, `--evidence`, `--heartbeat-sec` bağlaması |
| `stream/spark_job.py` | +38 | eşikleri açılışta API'den çekme |

### Ölçüm 1 — tarayıcı FPS (hedef 20+)

`scripts/ws_client.py`, 10 sn'den uzun pencerede.

| kaynak | istemci FPS | not |
|---|---|---|
| dosya (`zone_01`, 62 sn) | **23.6** | 1515 karenin 1465'i teslim edildi (%96.7) |
| webcam (40 sn) | **12.5** | hedefin altında |

Dosya kaynağında hedef tutuyor. Webcam'de tutmuyor, **ama darboğaz yayın
değil**: webcam hattının kendisi bu makinede ~12–19 FPS koşuyor
(`camera_health` son kaydı `fps_actual=19.5`, `infer_ms=24.0`) ve istemci
üretilenin neredeyse tamamını alıyor. 20+ için gereken şey daha hızlı yayın
değil, daha hızlı çıkarım — Aşama 10'un konusu.

### Ölçüm 2 — uçtan uca gecikme (hedef 300 ms altı)

`/ws/meta` gövdesindeki `ts` ile mesajın istemcide alındığı an arasındaki
fark, `scripts/ws_client.py` ile.

| kaynak | p50 | p95 | geçerli mi |
|---|---|---|---|
| **webcam (canlı)** | **44.5 ms** | **84.1 ms** | evet, hedef tutuyor |
| dosya (`zone_01`) | 2663 ms | 3785 ms | **hayır — ölçüm artefaktı** |

Dosya kaynağındaki 2.7 saniye hattın gecikmesi değildir. `meta.ts` kareyi
`VideoSource`'un *okuduğu* andır ve dosya kaynağında okuyucu iş parçacığı 64
karelik bir kuyruğu önden doldurur (`vision/source.py:88`; canlıda kuyruk tek
yuvadır). 23.6 FPS'te 64 kare 2.71 saniye eder — ölçülen p50 ile birebir.
Sayı sabit kalıyor, büyümüyor; birikme değil sabit bir kayma.

**Bu yüzden 300 ms ölçütü yalnızca canlı kaynakta anlamlıdır** ve orada 44.5 ms
ile rahat tutuluyor. `camera_health.queue_depth=1` bunu ayrıca doğruluyor.

### Ölçüm 3 — yayının görü döngüsüne maliyeti

`zone_01`, 1515 kare, üç koşum. Üçüncüde istemci koşumun tamamı boyunca bağlı
(yarısında bağlı olsaydı FPS iki fazın ortalaması çıkardı).

| koşum | görü FPS | `ws kodlama+yayın` medyan / p95 |
|---|---|---|
| `--ws` kapalı | 29.1 | — |
| `--ws` açık, 0 istemci | 30.8 | **0.0 / 0.0 ms** |
| `--ws` açık, 1 istemci | 24.2 | 1.7 / 2.6 ms |

Sıfır istemcide maliyet gerçekten sıfır: `live_clients == 0` iken JPEG
kodlaması, `meta_clients == 0` iken meta gövdesi hiç kurulmuyor. İlk iki satır
arasındaki 1.7 FPS fark ölçüm gürültüsüdür (kodlama hiç çağrılmıyor).

Bir istemcide kare başına fark 8.8 ms, ama ölçülen kodlama+yayın bunun yalnız
1.7 ms'si. **Kalan ~7 ms tek bir aşamaya yazılamıyor**: sunucu iş parçacığının
saniyede ~24 kez ~40 KB göndermesinin GIL ve zamanlayıcı maliyeti döngünün
tamamına yayılıyor. Olduğu gibi yazılıyor.

### Ölçüm 4 — alarm gecikmesi (Aşama 4'ten kalan açık soru)

Adayın `end_time`'ı ile kırmızı alarmın `/ws/alerts`'ten çıkışı arası:

| klip | ölçülen |
|---|---|
| `fall_01` | 13.9 sn |
| `run_01` | 46.8 sn |
| `zone_01` | 54.8 sn |

Tasarım beklentisi 3 sn oturum boşluğu + 2 sn damga + mikro-toplu, yani 5–8
sn'ydi. **Beklenti düzeltilmiyor, ölçüm yazılıyor** — ama sayının ne ölçtüğü
söylenmeli: dosya kaynağında Spark'ın oturumu, olayın bitmesiyle değil
**akışın bitmesiyle** kapanıyor. Watermark yalnız yeni veri geldikçe ilerler;
olaydan sonra aday üretilmediği için pencere, klibin sonundaki `_EOS`
işaretçisi gelene kadar açık kalır. `zone_01`'de olay ~13. saniyede bitiyor,
klip 60.6 saniye sürüyor: aradaki ~47 saniye ölçülen gecikmenin içindedir ve
hattın hızıyla ilgisi yoktur.

Canlı kaynakta aday akışı sürekli olduğu için bu etki yoktur, ama **canlı
ölçüm yapılamadı**: kameranın önünde koşan/düşen biri gerekiyordu, webcam
koşumunda kırmızı alarm üretilmedi. Aşama 4'ten kalan açık soru bu haliyle
**hâlâ açık**.

### Ölçüm 5 — kanıt

Beş pilot oturumun tam geçişi (`fall_01`, `run_01`, `zone_01` — sonuncusu
`--zones eval/zones.json` ile):

- **6 klip + 6 kare** diske yazıldı, **6 POST başarılı**, 0 başarısız,
  kuyruktan düşen 0, mongo hatası 0.
- `events` tablosunda `clip_path`, `frame_path`, `mongo_ref` dolu satır: **6/6**.
- `evidence` tablosu: 6 satır, **6'sı eşleşmiş, 0 eşleşmeyen**, 2'si
  `clip_truncated`.
- Süreler Aşama 4 ve 5 ile birebir: 33 / 11067 / 1800 / 27640 / 1000 ms.

Altı klip de açılıp doğrulandı (ilk kare çözülüyor, süreler 7.9–11.4 sn —
kısa epizotların ±5 sn payıyla tutarlı). `GET /api/events/{id}/clip` ve
`/frame` doğru içerik tipiyle 200 dönüyor; jetonsuz istek 401, yolu olmayan
olay 404.

**Uyarı — klip kaynak çözünürlüğünde yazılıyor.** Halka tampon ham kareyi
tuttuğu için klip 960×540 değil, kaynağın kendi boyutundadır. 4K olan
`run_01` (2160×3840) için bu, 8.5 saniyelik klipte **46 MB** demek: altı
klibin 52 MB'ının 46'sı tek dosya. Aşama 10'daki rotasyon borcunu ölçülü hale
getiriyor.

### Ölçüm 6 — `pose_sequences`

- **6 belge**, belge başına kare: 107, 467, 158, ...
- **`event_id` bağlanmış belge oranı: 6/6 (%100).**
- `created_at` alanı BSON `Date` — TTL indeksi çalışıyor.

### Ölçüm 7 — her şey açıkken görü FPS

Docker altyapısı + Kafka + WebSocket + kanıt yazımı + kalp atışı birlikte:

| klip | çözünürlük | FPS |
|---|---|---|
| `fall_01` | 768×432 | 31.6 |
| `zone_01` | 640×360 | 23.8 / 23.4 |
| `run_01` | **2160×3840 (4K)** | **9.3** |

Aşama 5'te ölçülen 12–15 FPS düşüşü tekrar etmedi; 4K dışındaki kliplerde
23–31 FPS korunuyor. `run_01`'in 9.3'ü yayın veya kanıt yüzünden değil, 4K
karenin ön işleme maliyetidir.

### Yol boyunca bulunan hatalar (hepsi düzeltildi)

1. **Yoklama döngüsü yayını çökertiyordu.** `_stream` kutuyu 5 ms'de bir
   yokluyordu. İki bağlantıda saniyede 400 uyanma, CPU'su dolu görü
   döngüsüyle GIL için yarışıyor; asyncio döngüsü kıt zamanını gönderim
   yerine zamanlayıcı muhasebesine harcıyordu. Ölçülen: yoklama 5 ms'de görü
   18.6 FPS / istemci **1.0 FPS**; 33 ms'de 26.6 / 21.6. Yoklama tamamen
   kaldırıldı, `call_soon_threadsafe` ile olay güdümlü uyandırmaya geçildi;
   ayarlanacak sabit kalmadı. Sonuç: görü 24.2, istemci **23.6 FPS**.
   Yalıtım testi (GPU'suz, sentetik 30 Hz üretici) sunucunun ve istemcinin
   temiz olduğunu, sorunun yalnız CPU doygunluğunda ortaya çıktığını gösterdi.
2. **Kalp atışı hiç çalışmıyordu.** `PATCH /api/cameras/{id}/heartbeat`
   `camera_id: int` bekliyordu, `vision/` ise kamerayı **adıyla** çağırıyor
   (`zone_01`): her atım 422 döndü, `cameras.status` ve `last_seen_at` hiç
   güncellenmedi (gönderilen 0, hata 12). Uç, Kafka tüketicisi ve
   `POST /api/evidence` ile aynı kurala getirildi (ad veya id); çözücü
   `api/routers/cameras.py::resolve_camera_id` içinde tek kopya.
3. **Ölçüm betiği yanlış alanı okuyordu.** `ws_client.py` alarm gecikmesini
   `end_ts`'ten hesaplıyordu; o alan adayın **sahne zamanı** (dosya
   kaynağında 0'dan başlar), epoch olan alan `end_time`. Sonuç epoch'un
   tamamını gecikme sanmaktı.
4. **`pose_sequences.event_id` baskın yolda hiç dolmuyordu.** Eşleşmenin iki
   yönünden yalnız biri Mongo'yu güncelliyordu, oysa kanıt neredeyse her
   zaman olaydan önce gelir. Ortak `link_pose_sequence` ile iki yön de
   bağlıyor — ölçümdeki %100 bağlanma bununla geldi.
5. **İki MongoDB TTL indeksi ölüydü.** `pose_sequences.created_at` ve
   `camera_health.ts` `time.time()` ile float yazılıyordu; TTL yalnız BSON
   `Date` alanında çalışır, belgeler hiç silinmezdi.
6. **Yazılmayan dosyanın yolu POST ediliyordu**, veritabanında dolu görünüp
   diskte olmayan kayıt bırakıyordu.
7. **`live_clients` meta istemcisini de sayıyordu**; yalnız overlay dinleyen
   bir panel her kareyi JPEG'e kodlatıyordu.
8. **`_pose` sözlüğü hiç budanmıyordu** — görülen her `track_id` kalıcıydı.
9. **Adaptif kalite yanlış girdiyi ölçüyordu**: süreye meta kurulumu da
   dahildi, kaliteyi gereksiz düşürüyordu.
10. **`docker compose restart` yeni ortamı uygulamıyor.** Spark, compose'a
    eklenen `SETTINGS_API_URL` olmadan çalışmaya devam etti ve §9 sessizce
    devre dışı kaldı; `docker compose up -d spark` ile yeniden oluşturmak
    gerekti. Aşama 5'in "ayakta görünen ölü konteyner" dersinin ikinci hali.

### Plandan sapmalar

- `requirements.txt`'e planın iki satırına ek olarak **`pyjwt`**: `vision/`
  jetonu yerel doğruluyor, plan bunu atlamış.
- `vision/evidence.py` 436 satır, plan bütçesi ~140'tı. Fark spekülatif değil:
  sahne zamanı / duvar saati ayrımı, EOF'ta epizot kapatma, yazma kuyruğu
  drenajı — üçü de gerçek koşumda bulunan hataların düzeltmesi.
- `pose_sequences.track_id` planda `<int>`, kodda metin (`"7"`, `"7-9"`).
  Çoklu iz (FIGHT) için metin daha doğru; **Aşama 9'un TCN okuyucusu buna
  göre yazılmalı.**
- `evidence` satırı eşleşse de yazılıyor. Plan §8.2 madde 1 eşleşince satır
  açmamayı ima ediyordu, ama `events` tablosunda `clip_truncated` kolonu yok;
  satır atlanınca kırpılma bilgisi tamamen kaybolurdu (§5.2 buna izin vermiyor).
- `/ws/alerts` jeton istiyor. Plan §8.4 bunu yazmamıştı; §3'ün görü akışı için
  koyduğu "kimliksiz yayın kabul edilemez" ölçütü alarm akışı için de geçerli.

### Bilinen sınırlar (kapatılmadı, ölçüldü)

1. **Canlı kaynakta alarm gecikmesi ölçülemedi.** Kameranın önünde gerçek bir
   olay gerekiyor. Dosya kaynağındaki 13.9–54.8 sn, hattın hızını değil
   oturumun akış sonuyla kapanmasını ölçüyor (§ Ölçüm 4).
2. **Webcam'de 20+ FPS tutmuyor** (12.5). Darboğaz yayın değil çıkarım.
3. **Kanıt klipleri kaynak çözünürlüğünde** ve rotasyonu yok: 4K bir kaynak
   8.5 saniyede 46 MB yazıyor. Aşama 10.
4. **`SPARK_SETTINGS_TOKEN` 12 saatlik bir kullanıcı jetonu.** Süresi dolunca
   Spark yeniden başlatıldığında eşikleri çekemez ve sessizce ortam
   varsayılanlarına düşer (uyarı basar). Uzun ömürlü servis jetonu gerekiyor.
5. **`camera_health.fps_actual` anlık değil**, koşum başından beri kümülatif
   ortalama; ısınma dönemini hiç unutmuyor.
6. `spark_window_sec` / `spark_min_hits` / `spark_min_sec` **açılışta** okunur;
   panelden değiştirilirse ancak Spark ve tüketici yeniden başlayınca geçerli
   olur. Sıcak yükleme yalnız kural eşiklerindedir (bilinçli, plan §9).

### Testler

`pytest tests/ -q` → **59 passed, 2 skipped**. Yeni: `tests/test_evidence.py`,
`tests/test_ws_units.py`, `tests/test_evidence_match.py`, ve
`test_api_units.py`'ye eklenen jeton denetimi.

## Aşama 7 sonucu (2026-09-09)

**LLM raporu ve Telegram bildirimi tamamlandı.** Zincirin son iki halkası
kapandı: doğrulanan olay artık Türkçe bir ihbar cümlesine dönüşüyor,
`events.llm_report_tr` doluyor ve kanıt karesiyle birlikte güvenlik
personelinin telefonuna düşüyor.

Gerçek bir Telegram botuyla ve gerçek bir Gemini anahtarıyla uçtan uca
koşuldu: **5 olay, 5 bildirim, 0 başarısız, hepsi fotoğraflı.** LLM kapalıyken
de zincir sürdü.

Aşama 6'nın dersi ("test geçmesi doğrulama değildir") burada iki gerçek hata
yakalattı — ikisi de yalnızca canlı koşuda görünüyordu, 34 birim testin
hiçbiri yakalamamıştı: rapordaki saat 3 saat geri çıkıyordu (container UTC
doğuyor) ve güven skoru "bilinmiyor" yazıyordu (ham SQL `NUMERIC` sütununu
`Decimal` döndürüyor, tür denetimi eliyordu).

### Yazılan dosyalar

| Dosya | Satır | İş |
|---|---|---|
| `api/llm.py` | 193 | `action_phrase`, şablon, Gemini REST, kabul süzgeci, kota soğutması |
| `api/notify.py` | 231 | kuyruk + worker thread, `sendPhoto`/`sendMessage`, yeniden deneme, `notifications` kaydı |
| `api/storage_paths.py` | 26 | `storage_path()` — `events.py`'den taşındı, kopya bırakılmadı |
| `api/config.py` | +12 | `GEMINI_*`, `LLM_*`, `TELEGRAM_*`, `NOTIFY_MIN_INTERVAL_SEC` |
| `api/workers/consumer.py` | +7 | `notify.start()` / `enqueue(new_id)` / `stop()` |
| `api/routers/events.py` | −6 | `_safe_storage_path` artık ortak modülü çağırıyor |
| `docker-compose.yml` | +15 | `consumer`'a LLM/Telegram ortamı, `TZ`, `storage:/storage:ro` |
| `tests/test_llm.py` | 246 | 21 test |
| `tests/test_notify.py` | 251 | 13 test |

### Ölçüm 1 — fotoğraflı ihbar (onay kriteri)

Gerçek bot, gerçek telefon. `data/pilot/` klipleri Kafka + Spark + tüketici
zincirinden geçirildi.

| olay | tip | fotoğraf | durum | gecikme |
|---|---|---|---|---|
| 1019 | FALL | var | sent | 1.29 sn |
| 1020 | RUN | var | sent | 0.75 sn |
| 1021 | RUN | var | sent | 0.90 sn |
| 1022 | FALL | var | sent | 0.77 sn |
| 1023 | RUN | var | sent | 1.06 sn |

`notifications` tablosu: **5 `sent`, 0 `failed`.** Beşinin de `frame_path`'i
dolu, yani hiçbiri metin-yedeğine düşmedi — Aşama 6'nın "kanıt olaydan önce
gelir" ölçümü Aşama 7'de de doğrulandı (§ Bilinen sınırlar 1).

### Ölçüm 2 — LLM çökse de zincir sürüyor mu

`GEMINI_API_KEY` boşaltıldı, `consumer` yeniden başlatıldı, `run_01` koşuldu.
`llm_report_tr` şablonla doldu, bildirim gitti (0.75 sn), hiçbir HTTP isteği
kurulmadı. **Onay kriterinin ikinci yarısı sağlandı.**

Bu koşu iki hatayı da ortaya çıkardı (§ Yol boyunca bulunan hatalar).

### Ölçüm 3 — rapor üretim süresi

`gemini-flash-lite-latest`, beş farklı olay tipi, tek çağrı:

| tip | mod | süre |
|---|---|---|
| FALL | llm | 1256 ms |
| RUN | llm | 1188 ms |
| ZONE_VIOLATION | llm | 1062 ms |
| FIGHT | llm | 1148 ms |
| LOITERING | llm | 968 ms |

**Medyan 1148 ms, 5/5 LLM, şablona düşen 0.** Devam turu (v1'in
`_gemini_complete`'i) yazılmadığı halde hiçbir cümle yarım kalmadı — tek
cümlelik ihbar 300 jetona rahat sığıyor.

Asıl doğrulama metinlerin içeriğinde: bölgesiz `RUN` olayının cümlesinde
**"yasaklı" kelimesi geçmiyor**, bölgeli `ZONE_VIOLATION`'da bölge adı
geçiyor. v1'in gerçek yanlış ihbarı (`reporter.py::_build_prompt` yorumu)
tekrarlamadı; `action_phrase()`'in tek doğruluk kaynağı olması işe yaradı.

### Ölçüm 4 — bildirim gecikmesi

`events.created_at` → `notifications.sent_at`, 5 olay: **medyan 0.90 sn**
(en düşük 0.75, en yüksek 1.29). Bunun ~1.1 sn'si Gemini çağrısı, kalanı
Telegram `sendPhoto` yüklemesi; ikisi paralel değil ardışık.

**Ölçümün sınırı Aşama 6 § Ölçüm 2/4 ile aynıdır:** dosya kaynağında
`started_at` → `created_at` arası (9.55 sn ölçüldü) hattın hızı değil, Spark
oturumunun akış sonuyla kapanmasıdır. Buradaki 0.90 sn ise bildirim
halkasının kendi maliyetidir ve bu ölçüm geçerlidir — iki uç da aynı
process'in saatinden gelir.

### Ölçüm 5 — tüketici yavaşladı mı

Bildirim için tüketici döngüsünün ödediği tek maliyet `enqueue()`'dur:
1000 çağrıda **medyan 2.90 µs, en kötü 12.90 µs.** Gemini + Telegram turu
(~1.4 sn) worker thread'de kalıyor, offset commit'i beklemiyor.

Kuyruk taşma davranışı da doğrulandı: `maxsize=200` kuyruğa 1000 öğe
atıldığında 800'ü **en eskiden** düşürüldü, `enqueue` hiç bloklamadı.

### Yol boyunca bulunan hatalar (hepsi düzeltildi)

1. **Rapordaki saat 3 saat geri.** `_format_zaman` `astimezone()` kullanıyor,
   container UTC doğduğu için 10:32'lik olay "07:32" yazıldı. Kod değil ortam
   hatası: `docker-compose.yml`'de `consumer` servisine
   `TZ: ${TZ:-Europe/Istanbul}` eklendi (imajda tzdata zaten var, doğrulandı).
   Birim testleri yakalayamazdı — testler UTC ile UTC'yi karşılaştırıyordu.
2. **"güven skoru bilinmiyor".** `_process_event` olayı ham SQL ile okuyor;
   `NUMERIC(4,3)` sütunu `Decimal` dönüyor (ORM'deki `asdecimal=False` ham
   sorguda geçerli değil) ve `template_report`'un `isinstance(..., float)`
   denetimi bunu eleyip metne "bilinmiyor" yazıyordu. Düzeltme `_sayi()`
   yardımcısıyla `api/llm.py`'de yapıldı — çağıran tarafta değil, çünkü aynı
   tuzağa her çağıran düşerdi. Regresyon testi eklendi.
3. **Şablonda sabit `'te` eki.** "10:29:42'te" — kesme işaretli ek saniye
   rakamına göre `'te / 'de / 'da` olarak değişir, sabit yazılınca cümlelerin
   çoğu yanlış çıkıyordu. `saatinde` ile ekin gerekliliği ortadan kaldırıldı.

### Plandan sapmalar

1. **`api/llm.py` ve `api/notify.py`**, `PLAN.md`'nin dediği gibi
   `api/workers/` altında değil. `api/workers/` çalıştırılabilir servisleri
   barındırıyor (`python -m api.workers.consumer`); bu ikisi kütüphanedir.
2. **`api/notify.py` 231 satır** (bütçe ~180). Fazlalık yeniden deneme
   tablosunun üç dalı ve orkestrasyon; spekülatif soyutlama yok.
3. **Hız sınırı olay başına**, aynı olayın birden fazla alıcısı arasında
   değil. Kodda `ponytail:` yorumuyla işaretli; çoklu alıcı senaryosu
   ölçülmedi.
4. **`TZ` ortam değişkeni** planda yoktu, Ölçüm 2'de ortaya çıktı.

### Bilinen sınırlar (kapatılmadı)

1. **Kanıt olaydan sonra gelirse bildirim fotoğrafsız gider.** Tetik
   `consumer.py`'dedir ve kanıtın zaten bağlanmış olmasına dayanır. Beş
   ölçümün beşinde de kanıt önce geldi, ama bu yön garantili değil.
   `api/routers/evidence.py` tarafına ikinci tetik konmadı: çift gönderme
   riskini ve bir tekilleştirme mekanizmasını birlikte getirirdi.
2. **429 / kota soğutması gerçek koşulda tetiklenmedi.** Kod yolu yalnızca
   `MockTransport` ile test edildi; gerçek bir kota aşımı görülmedi.
3. **Çoklu alıcı denenmedi.** `users.telegram_chat_id` boş olduğu için
   `.env`'deki `TELEGRAM_CHAT_ID` yedeği kullanıldı. Panelden kullanıcı
   eklenince (Aşama 8) çoklu alıcı yolu ilk kez çalışacak.
4. **Bildirim bastırma yok.** Evde/Koruma modu, bilinen kişi listesi, sessiz
   saat, severity süzgeci — hepsi bilinçli olarak Aşama 8/9'a bırakıldı.
   Şu an doğrulanmış her olay telefona gidiyor.

### Testler

`pytest tests/ -q` → **93 passed, 2 skipped**. Yeni: `tests/test_llm.py`
(21 test), `tests/test_notify.py` (13 test). Hiçbiri ağa çıkmıyor, hiçbiri
gerçek `time.sleep` çağırmıyor.

---

## Aşama 8.1 sonucu (2026-09-09)

Panel iskeleti, kimlik akışı ve ekran-uç denetimi. Plan: `docs/ASAMA8_PLAN.md`
(§ 1 yığın kararı, § 5 uç denetimi sonucu).

### Yapılanlar

| Dosya | Satır | İş |
|---|---|---|
| `scripts/build_frontend.py` | 292 | `sablon/*/code.html` -> `frontend/*.html`; kenar çubuğu `href="#"` bağlantılarını etikete göre gerçek dosyaya çevirir, `js/app.js` betiğini ekler, `login.html`'in sahte davranışını gerçek uca bağlar. Idempotent (iki koşu, aynı özet) |
| `frontend/*.html` | 12 ekran | 11 panel ekranı + giriş ekranı, şablonla birebir |
| `frontend/js/app.js` | 112 | `token`/`setToken`/`api`/`requireAuth`/`logout`, tarih-süre biçimleyicileri, `TIP_ADI`/`SEVERITY_ADI`/`DURUM_ADI`, `rowTemplate` |
| `api/main.py`, `api/config.py` | — | `FRONTEND_DIR` (varsayılan `/frontend`) + `StaticFiles` mount, router'lardan **sonra**; dizin yoksa mount atlanır |
| `docker-compose.yml` | — | `api` servisine `./frontend:/frontend:ro` ve `FRONTEND_DIR` |
| `tests/test_frontend_asama8.py` | 133 | 6 test: nav hedefleri var, `href="#"` kalmadı, her sayfa `js/app.js` yüklüyor, şablon ile kopya arasında yalnız beyan edilen farklar var, `FRONTEND_DIR` yokken `api.main` import edilebiliyor |

`sablon/` kaynak olarak duruyor; şablon güncellenirse `build_frontend.py`
yeniden çalıştırılır. Tasarım korunuyor kanıtı testte: kopyadaki beyan edilen
değişiklikler geri uygulanınca şablon birebir yeniden kuruluyor.

### Giriş ekranı

Kullanıcı 11 ekrandan sonra ayrı bir giriş şablonu gönderdi
(`sablon/girisekrani/`). Elle yazılan ilk sürüm atıldı. Şablonun sahte
`simulateLogin()`'i gerçek `POST /api/auth/login`'e bağlandı (form gövdesi,
jeton `localStorage`), gömülü demo kimlik bilgileri temizlendi, hata için
`#loginError` alanı eklendi. Karşılığı olmayan iki öğe **silindi**: "2FA
Aktif" rozeti ve "Oturumu 8 saat açık tut" kutusu. Karşılığı olmayan ama
yanıltıcı olmayan öğeler (Parolamı Unuttum, NODE/WSS/FPS altbilgisi,
operatör/yönetici sekmeleri) pasif bırakıldı.

### Doğrulama

- `pytest tests/test_frontend_asama8.py -q`: 6 passed. Tüm paket: **99 passed,
  2 skipped**
- Konteynerden servis: `/login.html` 200, `/` 200, `/js/app.js` 200,
  `/health` 200, `/api/cameras` 401 (jetonsuz) — statik mount API'yi
  gölgelemiyor
- Tarayıcıda uçtan uca: `admin` ile giriş -> `index.html`, konsolda hata yok,
  kenar çubuğu bağlantıları gerçek dosyalara gidiyor
- `build_frontend.py` iki kez koştu, 12 dosyanın özeti değişmedi

### Bu aşamada yakalanan hata

Testler yeşilken konteyner `/login.html` için **404** döndü. `api` servisi
kodu imaja gömüyor (`build: ./api`, kod için volume yok); `docker compose up
-d` çalışan imajı yeniden kullanıyor, yeni `main.py` konteynere hiç girmiyor.
`docker compose up -d --build api` ile çözüldü. 8.2'den itibaren her API kod
değişikliği `--build` ister.

### Gecikme ölçümü (Aşama 5'in açık sorusu)

25 istek, GPU boşta, `vision/` kapalı:

| uç | host medyan | konteyner içi medyan |
|---|---|---|
| `/health` | 13.8 ms | 1.8 ms |
| `/api/cameras` | 13.8 ms | — |
| `/api/events?limit=20` | 11.1 ms | — |
| `/api/analytics/summary` | 18.0 ms | — |

Aşama 5'te ölçülen ~600 ms taban **yeniden üretilemedi**. Port
yönlendirmesinin payı ~12 ms. Eski ölçüm GPU'su yüklü makinede alınmıştı;
canlı koşuda (8.6) tekrar bakılacak.

### 8.2'ye devreden

Üç eksik uç (kullanıcı CRUD, `audit_log` listesi, Mongo `camera_health`
okuması) + denetimde çıkan dördüncü: analitik ekranının
Doğruluk/Kesinlik/Duyarlılık/F1 tablosunun API karşılığı yok, bu metrikler
yalnız `eval/pilot_eval.py` ve `eval/spark_eval.py`'nin çevrimdışı
raporlarında var. Ya bir metrik ucu yazılacak ya ekran sayı kırılımlarına
daraltılacak. Ayrıntı: `docs/ASAMA8_PLAN.md` § 5.

---

## Aşama 8.2 sonucu (2026-09-09)

Panelin ihtiyaç duyduğu eksik uçlar. Plan: `docs/ASAMA8_PLAN.md` § 3'ün 8.2
maddesi, § 5 uç denetimi sonucu.

### Yapılanlar

| Dosya | Satır | İş |
|---|---|---|
| `api/routers/users.py` | 105 | `GET/POST/PUT/DELETE /api/users` — liste pasifler dahil, `admin` rol denetimi (`require_role` zaten `api/auth.py`'de vardı, yenisi yazılmadı). Şifre hash'i `crypt(:password, gen_salt('bf'))` ile DB'de üretilir (Aşama 5 kararı bozulmadı); `PUT`'ta `password` gönderilmezse hash'e dokunulmaz. Kendi kendini pasifleştirme ve son aktif admin'i pasifleştirme 403. `DELETE` gerçek silme değil `is_active=false` — `audit_log.user_id`/`zones.created_by` FK'leri koptuğunda denetim izi kaybolur |
| `api/routers/audit.py` | 76 | `GET /api/audit` — `user_id`/`action`/`entity`/`from`/`to` filtreleri, `limit`/`offset` sayfalama, `created_at DESC`. `users` LEFT JOIN (audit_log.user_id NULL olabilir — silinmiş/pasif kullanıcı). Dosya adı `api/audit.py` (write_audit yardımcısı) ile karışmasın diye `api/routers/audit.py` |
| `api/routers/health.py` | 66 | `GET /api/health/cameras` — Mongo `camera_health`'ten kamera başına en son belge, tek `aggregate` ile (N+1 yok). Ham `camera_id` (ad/id metni) gerçek kamera id'sine `resolve_camera_id` (`api/routers/cameras.py`, ikinci kopya açılmadı) ile çözülür. Mongo kaydı olmayan kamera da listede kalır, ölçüm alanları `null`. `age_sec` belge yaşını taşır. Kimlik ister (`/health` istemez) |
| `api/routers/analytics.py` | +50 | `GET /api/analytics/quality` — 8.1 denetiminde çıkan gerçek eksik: ground-truth yok, recall/F1 hesaplanamaz, **uydurulmadı**. `events.status` geri bildiriminden `confirmed`/`false_positive`/`pending`/`precision` (tip başına), `recall`/`f1` her zaman `null`, `note` alanı nedenini açıklıyor. `/ablation` artık `response_model=list[AblationRowOut]` (davranış aynı) |
| `api/schemas.py` | +75 | `UserCreate`, `UserUpdate`, `AuditOut`, `AuditListOut`, `CameraHealthOut`, `AblationRowOut`, `QualityRowOut`, `QualityOut` |
| `api/main.py` | +3 | `users`, `audit`, `health` router'ları `/api/users`, `/api/audit`, `/api/health` altında kayıtlı |
| `tests/test_asama8_2.py` | 200 | 13 test: `require_role("admin")` kabul/red (users+audit'in ortak geçidi), son-admin/kendi-kendini pasifleştirme guard'ı, `quality` precision hesabı (payda 0 dahil, çoklu tip sıralaması), `health/cameras` Mongo kaydı olmayan/olan kamera, gerçek DB'ye karşı (skip edilebilir) audit filtresi ve boş `camera_health` koleksiyonu |

`events.status` dörtlü değerleri (`new/acknowledged/false_positive/resolved`)
`infra/postgres/init.sql`'deki CHECK kısıtından doğrulandı (8.1'in notu
teyit edildi, tahmin edilmedi).

### Doğrulama

- `venv/Scripts/python.exe -m pytest tests -q`: **110 passed, 4 skipped**
  (önceki 99 passed/2 skipped + 11 yeni saf test geçti, 2 yeni DB-bağımlı
  test venv dışı ağ erişimi olmadığı için skip edildi)
- `docker compose up -d --build api` ile konteyner yeniden kuruldu (8.1'in
  dersi: `--build` şart, kod imaja gömülü)
- Gerçek jetonla 5 uç: `/api/users`, `/api/health/cameras`,
  `/api/analytics/quality`, `/api/analytics/ablation`, `/api/audit` — hepsi
  200, gövdeler beklenen alanları taşıyor. `health/cameras` boş Mongo
  belgesinde patlamadı (`normal_01`/`police_run` tüm ölçüm alanları `null`)
- Rol denetimi canlı doğrulandı: jetonsuz istek 401; geçici bir `viewer`
  kullanıcı oluşturulup onunla `GET /api/users` ve `GET /api/audit` 403,
  `GET /api/health/cameras` 200 (yalnız kimlik ister, admin değil)
- Son-admin ve kendi-kendini pasifleştirme guard'ı canlı denendi: admin
  kendini pasifleştiremedi (403, "kendi hesabinizi pasiflestiremezsiniz");
  test `viewer`'ı `DELETE` ile pasifleştirildi (204), listede `is_active:false`
  olarak kaldı (gerçek silme değil)
- `write_audit` → `GET /api/audit` zinciri: kamera 2'ye `PUT` atıldı, audit
  satırı (`action:"update", entity:"camera"`) anında göründü; `action`/`entity`
  filtreleri doğru daraltıyor. Test verisi (geçici viewer, kamera 2'nin
  `source`/`location` alanları) temizlenip/geri yazıldı

### Sürprizler

- Aşama 7'nin `Decimal` tuzağı bu turda tetiklenmedi: yeni uçların hiçbiri
  `detection_settings`/`events.confidence` gibi `NUMERIC` sütunlara dokunmuyor
  (health verisi Mongo'dan geliyor, zaten `float`/`int`; quality/ablation
  yalnız `count()` ve string kolonlar kullanıyor)
- `PUT /api/cameras/{id}` tüm gövdeyi ister (kısmi değil, `settings` gibi
  `Patch` değil) — audit'i tetiklemek için atılan test `PUT`'u kamera 2'nin
  gerçek `source` yolunu geçici olarak ezdi; fark edilip aynı istekte geri
  yazıldı. 8.3/8.5 panel tarafı bunu zaten tam gövde olarak gönderecek, ama
  ileride benzer bir elle test yapılırsa hatırlatma: `cameras.py`'de lost-update
  koruması yok, `zones.py` de aynı

### Gözden geçirmede bulunan iki eksik (düzeltildi)

- **Son admin'in rolü düşürülebiliyordu.** Guard yalnız `is_active=false`
  yolunu koruyordu; `PUT /api/users/{id}` ile `role: "viewer"` göndermek aynı
  sonucu doğuruyordu — sistemde aktif admin kalmazsa panel bir daha
  yönetilemez. `_yetki_kaybi()` eklendi (pasifleştirme **veya** admin
  rolünden düşürme), guard `_guard_admin_loss` olarak yeniden adlandırıldı.
  Canlı doğrulama: `PUT /api/users/1 {"role":"viewer"}` -> 403
- **Aynı kullanıcı adı 500 dönüyordu.** `users.username` UNIQUE; `IntegrityError`
  yakalanmıyordu. `POST` ve `PUT` artık 409 + Türkçe mesaj döndürüyor.
  Canlı doğrulama: aynı adla ikinci `POST` -> 409 "bu kullanici adi zaten kayitli"
- İki yeni saf test eklendi (`_yetki_kaybi` doğru/yanlış halleri);
  `tests/test_asama8_2.py` 13 -> 15 test
- Agent'ın canlı denemelerinden kalan iki kullanıcı satırı
  (`asama82_test_viewer`, `gecici_8_2_kontrol`) geliştirme veritabanından
  silindi; `users` tablosunda yalnız `admin` kaldı

---

## Aşama 8.3 sonucu (2026-09-09)

Sekiz okuma ekranına gerçek veri bağlandı. İş iki paralel ajana bölündü
(kamera/olay ekranları ve yönetim ekranları); paylaşımlı üç dosyaya
(`app.js`, `build_frontend.py`, ortak test) yalnızca koordinatör dokundu.

### Yapılanlar

| Dosya | Satır | Ekran |
|---|---|---|
| `frontend/js/kameralar.js` | 131 | Kamera listesi, istemci tarafı arama/durum/konum süzgeci, satır -> detay |
| `frontend/js/kamera-detay.js` | 152 | `?id=` kamera başlığı/çözünürlük/durum + o kameranın olay akışı (gerçek kanıt küçük resimleri) |
| `frontend/js/olaylar.js` | 194 | Sunucu tarafı filtre (kamera/tip/önem/durum/tarih) + `limit`/`offset` sayfalama, önem renkleri, kanıt küçük resmi |
| `frontend/js/olay-detay.js` | 254 | Olay özeti, kanıt karesi + klip (`<video>`), LLM raporu, **Ölçülen Değerler tablosu telemetriden** |
| `frontend/js/analitik.js` | 223 | `summary`/`quality`/`ablation`; çubuk grafik ve ısı haritası şablonun kendi `div`leriyle |
| `frontend/js/sistem-sagligi.js` | 164 | `/health` + `/api/health/cameras`, `age_sec` ile bayat/çevrimdışı ayrımı |
| `frontend/js/kullanicilar.js` | 82 | Kullanıcı listesi, pasifler ayrışıyor, 403 durumu |
| `frontend/js/denetim-kaydi.js` | 131 | İki sekme: bildirim teslim kaydı + denetim kaydı |
| `api/routers/notifications.py` | 76 | **Yeni uç** `GET /api/notifications` |
| `frontend/img/placeholder.svg` | 7 | Şablonun uzak görsellerinin yerel karşılığı |
| `tests/test_frontend_8_3a.py`, `test_frontend_8_3b.py`, `test_notifications.py` | 166 + 92 + 65 | 22 yeni kontrol |

### Bulunan gerçek eksik: bildirim teslim kaydı

8.3b ajanı şablonun "Bildirimler" sekmesini "veri kaynağı yok" durumuna
çevirmişti; doğru gözlem, yanlış sonuç: `notifications` tablosu Aşama 7'den
beri doluyor (5 gerçek Telegram satırı), yalnız okuyan uç yoktu.
`GET /api/notifications` yazıldı (olay + kamera LEFT JOIN, kanal/durum/tarih
filtreleri, admin) ve sekme bağlandı. Başarısız gönderimde hata metni
rozetin `title`'ında durur.

### Şablonun sahte verisi temizlendi

- **Uzak görseller.** Şablonun `lh3.googleusercontent.com` bağlantıları
  (avatar + "kamera görüntüsü" diye konmuş stok fotoğraflar) her sayfada
  404 dönüyordu. `build_frontend.py` hepsini `img/placeholder.svg` ile
  değiştiriyor: hem konsol temiz, hem stok fotoğraf kamera karesi gibi
  görünmüyor. Gerçek kare canlı akıştan 8.4'te gelecek
- **Olay detayının "Ölçülen Değerler" tablosu** artık gerçek: kaynak
  `GET /api/events/{id}` yanıtındaki `telemetry` belgesi. Metrik adları
  kural tipine göre değiştiği için sabit dört satır yerine belgede ne varsa
  o listeleniyor; eşik karşılaştırması `rule_verdict.thresholds_used`'dan
  geliyor, eşleşen eşik yoksa durum `—` kalıyor. Örnek (olay 1023):
  Normalize Hız medyan 0.068 / tepe 0.142 (eşik 1.8), Uzuv Hızı 1.204,
  Süreklilik 11 sn, Vuruş 333
- **"Hareket Analizi" eğrisi** kare kare seri ister, API özet metrik
  döndürüyor: sahte eğri silindi, yerine tek satırlık açıklama kondu
- **Video üstündeki "İNSAN %94" kutusu** sabit konumlu ve uydurma etiketli:
  katman gizlendi, gerçek kutu 8.4'te canlı akışta çizilecek

### Tarayıcının yakaladığı, testlerin yakalamadığı dört hata

1. **Metin düğümü seçimi yanlış düğüme yazıyordu.** Şablonda etiketin metni
   ikon `span`'inin *sonrasında*, boşluk düğümü *öncesinde*; `childNodes`
   içindeki ilk metin düğümüne yazınca şablon metni satırda kalıyordu
   ("VADAP Core v4.2..." kalite tablosunda asılı kaldı). Çözüm: tüm metin
   düğümlerini silip tek yeni düğüm eklemek
2. **`gpu_mem` bayt, MB değil** (`torch.cuda.memory_reserved()`); ekranda
   "104857600MB" yazıyordu. Şema alan adı birimi söylemiyor
3. **Kamera sayacı seçicisi kenar çubuğunun alt başlığını buluyordu** (aynı
   sınıf üçlüsü); sayaç sessizce yanlış öğeye yazılıyordu
4. **JS'te Türkçe kesme işareti** (`API'de`) tırnak kaçışı olmadan yazılınca
   dosya parse edilemedi; ekran şablon verisine geri düştü. Konsol hatası
   olmasa fark edilmezdi

### API karşılığı olmadığı için boş bırakılanlar

Analitik: ortalama tespit gecikmesi, hafta-üstü-hafta trendi, doğruluk /
duyarlılık / F1 (`—` + dipnot). Sistem sağlığı: Kafka QPS-kuyruk, Spark iş
yükü-batch süresi, GPU sıcaklığı ve model adı, kamera başına TREND grafiği.
Olay detayı: hareket eğrisi. Kamera detayı: gerçek FPS / düşen kare /
çıkarım süresi (8.4'te canlı akıştan gelecek).

### Doğrulama

- `venv/Scripts/python.exe -m pytest tests -q`: **134 passed, 5 skipped**
- Sekiz ekran gerçek tarayıcıda, gerçek konteynere karşı açıldı; konsolda
  hata yok, 404 yok. Boş durum (olayı olmayan kamera), 403 durumu (geçici
  `viewer` kullanıcıyla kullanıcılar/denetim ekranları) ve eksik `?id=`
  durumu ayrı ayrı denendi
- Deneme sırasında yaratılan geçici kullanıcılar geliştirme veritabanından
  silindi

---

## Aşama 8.4 sonucu (2026-09-09)

Panel ilk kez canlı görüntü gösteriyor: `/ws/live` ikili JPEG akışı,
`/ws/meta` üzerinden kutu/iskelet/bölge/ID katmanları ve `/ws/alerts`
kırmızı alarmı.

### Yapılanlar

| Dosya | Satır | İş |
|---|---|---|
| `frontend/js/live.js` | 185 | Ortak WS bağlantısı, üstel geri çekilmeli yeniden bağlanma (1 -> 15 sn), canvas overlay çizimi, blob URL serbest bırakma, FPS sayacı |
| `frontend/js/index.js` | 313 | Canlı izleme ızgarası (1 / 2x2 / 3x3), kamera kutusu çoğaltma, `/ws/alerts` toast + olay kartı + kırmızı kutu |
| `frontend/js/kamera-detay.js` | 247 | Tekli canlı görüntü, katman düğmeleri, gerçek FPS / düşen kare / çıkarım süresi (8.3'te `—` bırakılmıştı) |
| `frontend/js/app.js` | 140 | Kopyalanmış yardımcılar tek yere alındı: `_fetchAuthedBlobUrl`, `ROLE_ADI`, `DECIDED_BY_ADI`, `CAMERA_STATUS_ADI`, `num()`, `FORBIDDEN_MSG` |
| `scripts/build_frontend.py` | +11 | `LIVE_PAGES`: canlı sayfalara `live.js` de eklenir (app.js sonrası) |

Ölçek dönüşümü iki farklı uzayı birleştiriyor: `bbox` işlenen kare uzayında
piksel, `zones` 0-1 normalize, canvas ekrandaki kutu boyutunda. Kare
"contain" ile yerleştiği için letterbox payı da hesaba katılıyor.

### Ölçüm: tarayıcı FPS'i

Onay kriteri "tarayıcıda 20+ FPS" (v1: 0.67). İstemci tarafında
`performance.now()` ile son 100 kare sayılarak ölçüldü:

| Koşu | Sunucu döngü FPS | Tarayıcı FPS |
|---|---|---|
| `fall_01`, Spark durdurulmuş | 25.1 | **25.2** |
| `zone_01`, Spark durdurulmuş | ~23 | **22.8 – 23.6** |
| `zone_01`, Spark ayakta (boşta) | 19.9 | **20.2** |
| `run_01`, tam hat (`--kafka`, Spark + consumer + Telegram aktif) | 10.2–19 | 9.9 |

**Sonuç: kriter karşılanıyor, darboğaz panel değil.** Tarayıcı, sunucunun
ürettiği her kareyi çiziyor — iki sayı neredeyse birebir örtüşüyor, istemci
kare atlamıyor ve gecikme eklemiyor. Tam hat çalışırken düşen şey görü
döngüsünün kendisi: aynı klipte ön işleme medyanı Spark ayaktayken 38.6 ms,
Spark durdurulunca 1.9 ms. Bu, DURUM'da zaten kayıtlı olan "Docker altyapısı
ayaktayken FPS 36.5'ten 12-15'e düşüyor" açık sorusunun tazelenmiş kanıtı —
yeni bir gerileme değil, aynı CPU rekabeti. `docker stats` sırasında
`anomaly-kafka` boştayken bile %150 CPU yakıyor.

### Alarm zinciri uçtan uca çalıştı

`vision.run --kafka --rules` -> Kafka -> Spark -> consumer -> `/ws/alerts`:
üstte kırmızı toast, sağda olay kartı, ilgili kamera kutusu "İHLAL"
durumuna geçti. Bağımsız doğrulama: `notifications` tablosu 5 satırdan 16
satıra çıktı (11 gerçek Telegram bildirimi), son 3 saatte 11 yeni olay.

Kopma testi: `vision.run` süreci defalarca durdurulup başlatıldı; kutular
"Bağlantı Yok"a düşüp süreç dönünce kendiliğinden bağlandı.

### Tarayıcının yakaladığı altı hata (hepsi düzeltildi)

1. Alarm toast'ı açılışta şablonun sahte "Depo A - 14:32:05" verisiyle
   görünüyordu -> varsayılan gizli
2. Çevrimdışı kutunun "Son Görülme" saati şablonun sabit değeriydi ->
   `cameras.last_seen_at`
3. **En ciddisi:** `ws_server` jeton ve yol doğruysa yayıncı olmayan bir
   `camera_id`'ye de bağlantıyı kabul ediyor; kutu `onopen`'da "AKTİF"
   yazınca hiç yayın olmayan kameralar yeşil görünüyordu. "AKTİF" artık
   yalnız ilk gerçek kare gelince yazılıyor
4. Tailwind'in `.flex` sınıfı tarayıcının `[hidden]` kuralını eziyor;
   `element.hidden = true` görsel olarak hiçbir şey yapmıyordu -> `style.display`
5. Her gelen kare durum metnini koşulsuz "AKTİF"e çeviriyor, alarmın kırmızı
   durumunu ≤150 ms içinde siliyordu -> `alarming` bayrağı
6. `visibilitychange` dinleyicisi ikinci bir `connect()` çağırınca ilk soket
   referanssız kalıp yayın almaya devam ediyordu; kareler çiftlenip FPS'i
   29.3 gibi yanlış yüksek gösteriyordu -> `connect()` idempotent

Ayrıca `kameralar.js` ile `kamera-detay.js`'in kamera durumu sözlükleri
birbirinden farklıydı ("Aktif/Devre Dışı" vs "Çevrimiçi/Çevrimdışı"); alan
bağlantı durumudur (`online/offline/error`), kanonik karşılık
"Çevrimiçi / Çevrimdışı / Hata" oldu.

### Kalan sınırlar

- Alarm kartındaki "İncele" bağlantısı olay listesine gidiyor, tek olaya
  değil: Kafka `anomaly-events` mesajı veritabanı `events.id`'sini taşımıyor
  (id ancak consumer yazarken atanıyor)
- `--settings-url` ile metin `--camera-id` kullanılınca eşik sıcak yükleme
  422 veriyor (bilinen kısıt, yeni değil)
- Canlı kamerada alarm gecikmesi hâlâ ölçülmedi; dosya kaynağında ölçmek
  hattın hızını değil akışın bitişini ölçüyor (Aşama 6'dan devreden açık soru)

---

## Aşama 8.5 sonucu (2026-09-10)

Yazma ekranları. Şablon HTML'i `scripts/build_frontend.py` tarafından
üretildiği için hiçbir yeni DOM elle eklenmedi: diyaloglar, saat alanları,
kamera seçici ve "Sil" düğmesi çalışma zamanında JavaScript'le kuruluyor.
Tek build değişikliği `LIVE_PAGES`'e `bolgeler.html` eklenmesi (çizim arka
planında canlı kare için `js/live.js` gerekiyor).

### Yapılanlar

- `app.js`: `openFormDialog()` — native `<dialog>` + `showModal()`, kütüphane
  yok. Yazma isteğini kendisi atmaz; hata olursa çağıran taraf diyaloğu önceki
  değerlerle yeniden açar, girdi kaybolmaz. `_escXml()` de buraya taşındı
  (iki yeni betikte kopyalanmıştı)
- `kameralar.js`: ekle / düzenle (`PUT` tam `CameraIn` gövdesi) / sil
- `kullanicilar.js`: ekle / düzenle / pasifleştir. Düzenlemede şifre alanı boş
  gelir, boş bırakılırsa gövdeye hiç konmaz (hash'e dokunulmaz)
- `olaylar.js`: başlık onay kutusu = sayfadaki tüm satırlar; "Seçilenleri
  Görüldü Yap" seçili her olay için ayrı `PATCH` atar (toplu uç yok)
- `olay-detay.js`: üç durum düğmesi `PATCH`, rozet yanıttan güncellenir,
  mevcut duruma karşılık gelen düğme devre dışı
- `bolgeler.js` (yeni): kamera listesi, canlı kare arka planı, tıklayarak
  poligon çizimi, mevcut bölgeyi tıklayarak seçme (ray-casting), kaydet /
  sil, `restricted_hours` için saat aralığı alanları
- `ayarlar.js` (yeni): global / kamera bazlı kapsam, yalnızca değişen alanları
  gönderen kısmi `PUT`, `restart_required` uyarısı, "Varsayılana Dön" kamera
  kapsamında global değerleri forma yükler

### Doğrulama — tarayıcıda, gerçek yığın üzerinde

Testler ağsız kaynak-deseni kontrolü; asıl kanıt aşağıdaki koşu (Docker
yığını ayakta, gerçek Postgres, gerçek JWT):

1. **Kamera CRUD:** `test_cam_85` eklendi (6 → 7 kamera), `target_fps` 25 → 30
   ve konum düzenlendi (`PUT` tam gövde, hiçbir alan kaybolmadı), silindi
   (7 → 6). Diyalog koyu temada okunur çıktı
2. **Kullanıcı CRUD:** `test_op_85` eklendi; ad değiştirilip şifre alanı boş
   bırakılarak kaydedildi, ardından **eski şifreyle `POST /api/auth/login`
   200 döndü** — hash'e gerçekten dokunulmadı; sonra pasifleştirildi
   (`is_active=false`, satır soluklaştı)
3. **Hata yolu:** admin'in rolü `viewer` yapılmak istendiğinde sunucu
   "kendi hesabinizin yetkisini kaldiramazsiniz" döndü; diyalog açık kaldı,
   girilen ad ve rol korundu
4. **Toplu işaretleme:** sayfadaki 20 olay seçildi, tek tıkla hepsi
   `acknowledged` oldu (`acked_by=1`, `acked_at` doldu)
5. **Olay detayı:** #1034 "Yanlış Alarm" düğmesiyle `false_positive` oldu,
   rozet "YANLIŞ ALARM"a döndü, düğme devre dışı kaldı
6. **Bölge çizimi — koordinat isabeti ölçüldü.** `zone_01` kamerası seçildi,
   canlı kare geldi (durum "CANLI ÇİZİM MODU", arka plan blob URL'e döndü).
   Hedeflenen 0.2/0.8 normalize noktalarına tıklandı; panelin yazdığı ve
   veritabanına giden değerler **0.201 / 0.204 / 0.799 / 0.802** — sapma
   ≤ 0.002 (tıklamanın tam sayı ekran koordinatına yuvarlanmasından).
   Letterbox dönüşümü doğru. Bölge poligona tıklanarak seçildi ve silindi
7. **Kısmi PUT:** yalnızca eğim açısı değiştirildiğinde gövde tam olarak
   `{"fall_tilt_deg": 55}` gitti

### Onay kriteri geçti: sıcak yükleme panelden tetiklendi

`vision/run.py --camera-id 7 --settings-url http://localhost:8000
--settings-interval 3` çalışırken panelin "Kamera Bazlı" sekmesinden
`zone_01` seçilip eğim açısı 45 → 62 yapıldı:

```
[11:14:00] esik guncellendi: fall_tilt_deg=45.0, ...   <- ilk yoklama (taban)
[11:14:30] esik guncellendi: fall_tilt_deg=62.0, ...   <- panelden PUT 11:14:29
```

Süreç yeniden başlatılmadı; uygulama gecikmesi ~1 sn (yoklama aralığı 3 sn).

**Yol boyunca öğrenilen:** aynı deneme önce global kapsamdan yapıldı ve
hiçbir şey olmadı. Sebep kusur değil kapsam: `zone_01` (camera_id=7) Aşama
5'ten kalan **kendi** `detection_settings` satırına sahip, `GET
/api/settings/7` global satırı hiç okumuyor. Global sekmeden yapılan
değişiklik, kendi satırı olan bir kamerayı etkilemez — panelde bu ayrımı
gösteren tek işaret `source` alanına bağlı ipucu metni.

### Tarayıcının yakaladığı gerçek hata: `window_frames` sessizce 0'a düşüyordu

Şablonun "Kayan Pencere Boyutu" `<select>`'i yalnızca 15/30/60/90 sunuyor;
veritabanı varsayılanı ise **50** (`infra/postgres/init.sql`). Listede
olmayan bir değeri `select.value`'ya atamak seçimi boş bırakır, `Number("")`
= 0 olur ve fark hesabı bunu "değişmiş" sayardı. Sonuç: **eşik formunda
hangi alan değiştirilirse değiştirilsin gövdeye `window_frames: 0`
ekleniyordu** ve global satır gerçekten 50'den 0'a düştü. Testler bunu
yakalayamazdı — hata yalnızca gerçek veritabanı değeri seçenek listesinde
yokken ortaya çıkıyor.

Düzeltme (`_setWindowFrames`): gerçek değer listede yoksa seçenek olarak
eklenir; hem görünür kalır hem fark hesabı doğru çalışır. Regresyon testi
`tests/test_frontend_8_5b.py` içinde. Bozulan iki satır (global ve kamera 7)
özgün değerlerine geri yazıldı.

Aynı koşuda düzeltilen ikinci kusur: FastAPI'nin 422 gövdesi metin değil
`[{loc, msg, type}, ...]` listesi; `api()` bunu doğrudan `Error()`'a verince
kullanıcı "[object Object]" görüyordu. `app.js` `_detailText()` ile tek yerde
düzeltildi — bölge poligonu doğrulaması tam bu yoldan geçiyor.

### Bilinçli sınırlar

- **`zone_type="direction"` arayüzde yok:** `vision/rules/` altında ters yön
  kuralı yazılmadı (`fall/fight/loiter/run/zone` var). O tipte bölge hiçbir
  kuralı beslemezdi. Şablonun "Ters Yön Tespiti" seçeneği karşılıksız
- **Ayarlar formunda 13 eşikten 6'sı bağlı** (`pose_conf`, `fall_tilt_deg`,
  `spark_min_sec.FALL`, `run_norm_speed`, `spark_min_sec.FIGHT`,
  `window_frames`) — kalanların şablonda kontrolü yok, uydurulmadı. Kısmi
  `PUT` sayesinde dokunulmuyorlar. `spark_min_sec` gönderilirken sözlüğün
  tamamı kopyalanıyor: kısmi güncelleme alan bazında çalışıyor, sözlük içi
  anahtar bazında değil
- **"Varsayılana Dön" sıfırlama ucu yok:** kamera kapsamında global değerleri
  forma yükler (kaydedilene kadar sunucuya dokunmaz), global kapsamda devre
  dışı ve nedeni `title`'da
- **Toplu durum ucu yok:** seçili her olay için ayrı `PATCH`
- **Bildirim katmanı yazılmadı:** hata için `alert()`, onay için `confirm()`

### Kalan iz

Doğrulama koşusundan `test_op_85` kullanıcısı pasif durumda kaldı
(`DELETE /api/users/{id}` soft delete, kalıcı silme ucu yok). Kamera, bölge
ve eşik değişikliklerinin tamamı geri alındı.

---

## Aşama 8.6 sonucu (2026-09-10)

Uçtan uca demo altyapısı ve panel ölçümleri. Demo kaynakları: `data/pilot/`
klipleri **ve dizüstünün kendi kamerası** (`webcam_01`, panelden eklendi —
8.5'in kamera ekleme formu ilk gerçek işini yaptı).

### Çözülen mimari çatal: çoklu kamerada canlı görü portu

Plan "her kamera için bir `vision.run` süreci" diyordu ama canlı görü WS
sunucusu tek port dinliyor ve `frontend/js/live.js`'de `LIVE_WS_PORT = 8001`
sabitti. 8.4/8.5'te tek kamera çalıştığı için ortaya çıkmamıştı; N süreç aynı
porta bağlanamaz.

Değerlendirilen üç yol: (a) türetilmiş port `8001 + kamera_id` — iki satır ama
formül iki yere gömülür ve kamera başka makinede çalışırsa yalan söyler,
(b) `cameras` tablosuna `ws_port` kolonu — `init.sql` yalnızca ilk kurulumda
çalışıyor, elle migration gerekir, 1032 olay riske girer, (c) portu kamera
sağlığı üzerinden bildirmek.

**(c) seçildi.** Gerekçe: `GET /api/health/cameras` zaten var ve kamera başına
çalışma-zamanı telemetrisi taşıyor (FPS, düşen kare, GPU); port da o cinsten
bir bilgi. Mongo belgesi şemasız — migration yok. Üstelik kalp atışının Mongo
yazımı zaten bozuktu (`gonderilen 9 hata 9`, "A password is required"):
host'tan çalışırken `.env` ortama geçmiyordu. Sistem Sağlığı ekranı demoda bu
düzeltme olmadan boş kalacaktı, yani iş zaten yapılacaktı — port ona bedavaya
bindi.

Yan kazanç: panel artık sağlık kaydı olmayan ya da bayat olan kameraya soket
**açmıyor**. Önceden görünen her kameraya körlemesine bağlanıyor, tarayıcı
konsolu başarısız WebSocket hatalarıyla doluyordu.

### Yapılanlar

- `vision/source.py` + `run.py`: `--loop`. Dosya bitince başa sarar, `idx`
  SIFIRLANMAZ — `ts = idx/fps` hep ileri gider, iz kimlikleri ve kural
  pencereleri sarımda bozulmaz. İkinci ve daha önemli gerekçe: dosya kaynağı
  `_EOS` ile bittiğinde Spark oturumu olayın değil akışın bitişiyle
  kapanıyordu (Aşama 6'nın 13.9–54.8 sn "gecikme" ölçümü bu yüzden hattın
  hızını değil akışın bitişini ölçüyordu). Döngüde akış hiç bitmez
- `vision/health_client.py` + `api/schemas.py` + `api/routers/health.py`:
  `ws_port` sağlık belgesine yazılır ve `CameraHealthOut` ile dışarı verilir.
  Port yalnızca StreamServer GERÇEKTEN açıldıysa yazılır (JWT_SECRET yoksa
  açılmıyor) — panel olmayan porta bağlanmaya çalışmasın
- `frontend/js/live.js`: sabit port kalktı; kamera adı → port eşlemesi sağlık
  ucundan, **tek paylaşılan yoklayıcı** ile (ızgarada N kutu N istek atmaz).
  `ws_port` yoksa ya da kayıt 60 sn'den bayatsa soket açılmaz, kamera ayağa
  kalkınca kendiliğinden bağlanır. `index.js`, `kamera-detay.js`, `bolgeler.js`
  ortak `liveUrlFn()`'i kullanır
- `api/routers/settings.py`: `GET/PUT /api/settings/{camera_id}` artık ad ya da
  sayısal id kabul ediyor (`resolve_camera_id`, cameras.py'deki tek çözücü).
  Bu, "`--settings-url` ile metin `--camera-id` 422 veriyor" bilinen kısıtını
  kapatır — `vision/run.py`'ye ikinci bir kimlik argümanı eklemeye gerek kalmadı
- `scripts/run_pilot_cameras.py` (yeni): `.env`'i okuyup alt süreçlere geçirir,
  admin jetonu alır, veritabanından kameraları çeker (`file` ve `webcam`),
  varsayılan ilk 3 kamera (4 GB VRAM), port `8001 + id`, kamera başına
  `logs/<ad>.log`, sağlık ucunu yoklayarak "hazır" bildirir, Ctrl+C hepsini
  durdurur (Windows'ta `CTRL_BREAK_EVENT`)
- `scripts/build_frontend.py`: betik etiketleri artık içerik özetiyle
  sürümleniyor (`js/live.js?v=fb50e8e3`)

### Ölçümler (Docker yığını ayakta, 3 kamera eşzamanlı, tek 4 GB kart)

| Ölçüm | Değer |
|---|---|
| Panel canlı FPS | run_01 9.3 · zone_01 13.7 · webcam_01 15.1 — toplam 38.1 |
| Panel canlı FPS, tek kutu (1x1) | 8.5 |
| Canlı İzleme açılışı | DOM 861 ms · load 1.63 sn · ilk canlı kare 3.8–5.2 sn |
| Olaylar ekranı (1033 olay) | DOM 551 ms · load 781 ms · 20 kanıt küçük resmiyle veri ekranda 1.63 sn |
| Sağlık yoklaması | ~3 sn'de tek paylaşılan istek |
| Alarmın panele ulaşması | 09:02:03.855 — veritabanı yazımından (09:02:04.107) ~250 ms ÖNCE |

Izgarayı 1x1'e düşürmek FPS'i değiştirmedi (8.5 → 8.5): **darboğaz panel
değil, tek kartı paylaşan üç görü süreci.** v1'in 0.67'sine karşı en düşük
kamera bile 9.3. Hedef olan ≥ 20'ye kamera başına ulaşılamadı; tek kamerayla
tek başına ölçüm yapılmadı (o koşuda üç süreç birden açıktı).

Alarmın veritabanı yazımından ÖNCE panele düşmesi tasarım gereğidir:
`/ws/alerts` ve tüketici aynı Kafka konusunu ayrı grup kimlikleriyle bağımsız
okur.

### Tarayıcı/gerçek koşunun yakaladığı dört kusur (hepsi düzeltildi)

1. **`run_pilot_cameras.py` `--kafka` ve `--evidence` vermiyordu.** Üç kamera
   20 dakika çalıştı, **tek olay üretilmedi**: aday olaylar Kafka'ya
   basılmayınca Spark'a hiçbir şey gitmiyor, olay yazılmıyor, `/ws/alerts`
   sessiz kalıyor, Telegram bildirimi de gitmiyor — zincirin tamamı sessizce
   kopuk. Eklendikten sonra yeni olay (#1035) geldi. Testler bunu göremezdi:
   komut kurulumu doğruydu, EKSİK olan bayraktı
2. **Tarayıcı eski JS'i önbellekten sunuyordu.** `index.js` yeni, `live.js`
   eski geldi ve panel `liveUrlFn is not defined` ile tek kutuda takıldı.
   FastAPI `StaticFiles` `Cache-Control` göndermiyor, tarayıcı sezgisel
   önbellekliyor — yani bu her dağıtımda tekrarlanacak gerçek bir kusurdu.
   `build_frontend.py` artık içerik özetiyle sürümlüyor
3. **Izgara ilk N kamerayı id sırasıyla alıyordu.** Çalışan üç kamera
   listenin sonundaydı, ekran baştan aşağı "Bağlantı Yok" görünüyordu.
   Yayında olan kameralar öne alınıyor (sıra içinde id sırası korunur)
4. **Alt süreç logları tamponluydu**, `logs/*.log` demo boyunca boş
   görünüyordu (`Kafka:` banner satırı bu yüzden görünmedi) — `python -u`

Ayrıca: `api` konteyneri `build: ./api` ile imaja gömülü, `api/` bağlanmıyor.
8.6'nın şema değişikliği (`ws_port`) çalışan konteynerde görünmedi;
`docker compose up -d --build api` gerekti. Kod değişince API'nin yeniden
inşası şart.

### Kalan sınırlar

- **Canlı kaynakta uçtan uca alarm gecikmesi hâlâ ölçülmedi.** Dosya
  kaynağında `started_at` duvar saati değil (epoch tabanı 0), bu yüzden
  gecikme yalnızca canlı kameradan ölçülebilir ve kameranın önünde gerçek bir
  olay gerektirir. Aşama 8'in kapsamı dışında bırakılmıştı
- Kamera başına ≥ 20 FPS hedefine ulaşılamadı (3 eşzamanlı süreç, tek kart).
  Tek kamerayla yalnız başına ölçüm yapılmadı; çoklu kamera toplu çıkarım
  (tek süreç, tek model) zaten Aşama 10'un işi
- `CTRL_BREAK_EVENT` ile düzgün kapanma gerçek koşuda denenmedi; süreçler
  ölçüm sonunda `Stop-Process` ile kapatıldı
- Webcam görüntüsü karanlık geldi (kamera kapağı/ortam ışığı) — akış ve
  iskelet çizimi çalışıyor, görüntü kalitesi ayrı konu

---

## Aşama 9.1 sonucu (2026-09-10)

Eğitim veri kümesi indirildi: **1080 klip, 193 MB, 0 hata**
(`scripts/fetch_datasets.py`, yeniden çalıştırılabilir).

| Sınıf | Klip | Kaynak dağılımı |
|---|---|---|
| FALL | 66 | casia 36 + URFD fall 30 |
| RUN | 144 | casia `run` 48 + ucarg ground 96 |
| FIGHT | 270 | bitint 150 + utint 60 + casia 12 + ucarg ground 48 |
| NORMAL | 600 | casia, bitint, utint, ucarg ground, URFD adl (kaynak başına eşit pay, `Random(0)`) |

`telemetry` koleksiyonu kullanılmadı ve kullanılamaz: reddedilen aday
tüketiciye hiç ulaşmıyor (Spark süzüyor), üstelik etiketi kuralın kendisi
koyuyor — onunla eğitilen model kuralı taklit eder ve ablation tablosu
tanımı gereği anlamsız çıkardı. Gerekçe ve kaynak seçimi
`docs/ASAMA9_PLAN.md` § 1'de.

**Kaynak seçimi tahminle değil klipler açılıp bakılarak yapıldı.** Elenenler
ölçümle elendi:

| Elenen | Ölçülen gerekçe |
|---|---|
| `virat` | SPHAR bunları anotasyon kutusuna kırpmış: klipler 64x64 – 72x142 piksel, çoğunda kişi hiç görünmüyor |
| `uccrime` | Kesilmemiş; süre medyanı **92.7 sn**, en uzunu 538.7 sn. Olay birkaç saniye, kalan yüzlerce pencere FIGHT diye etiketlenirdi |
| `okutama`, `ucaerial`, `ucarg _aerial_` / `_rooftop_` | Kuş bakışı / çok uzak; rooftop'ta kişi ~30 piksel |
| `caviar`, `livevid` | Kesilmemiş (SPHAR "Known Caveats") |
| `casia _jump_` | `running` klasöründe ama eylem zıplama (48 klip) |

İki gerçek hata bulundu ve düzeltildi:

1. **URFD klipleri 640x240 yan yana derinlik + renk geliyor.** Kırpılmasa
   derinlik yarısındaki hayalet siluet YOLO'ya ikinci bir kişi gibi görünür
   ve aynı olayı iki ize bölerdi. İndirme sırasında sağ (renkli) yarı
   kırpılıyor.
2. **"Dosya var, atla" dalı kırpmayı da atlıyordu.** Kırpma betiğe sonradan
   eklendiği için daha önce inen 36 URFD klibi sessizce yan yana kalmıştı.
   Atlama yolunda da `crop_right_half` çağrılıyor (kırpılmış dosyada
   hiçbir şey yapmaz).

## Aşama 9.2-9.4 kod durumu (2026-09-10)

Kod yazıldı ve doğrulandı; **ölçümler dizi çıkarımı bitince alınacak.**

- `eval/extract_sequences.py` — klipleri gerçek hattan geçirip iz başına
  50x53 pencere üretir. **Kök neden düzeltmesi:** ilk sürüm 50 kare
  *kesintisiz* dizi istiyordu ve 6 klipten 7 pencere çıkıyordu (22 düştü).
  İzler yeterince uzun (91–198 kare) ve %100 pozlu, ama her ~15 karede bir
  kare atlıyor. Üretimde de pencere "son 50 **görülme**"dir, 50 ardışık kare
  değil (`FeatureEngine` yalnız izin görüldüğü kareyi ekliyor). Şart
  üretimin tanımına çekildi: aynı 6 klipten **29 pencere, 0 düşen**. İz
  `STALE_FRAMES`'ten uzun kaybolursa zincir kopar — bu da üretimdeki
  davranış.
- `models/tcn.py` — 5 bloklu genişletilmiş nedensel TCN, **66 116 parametre**.
  Eğitim hattı kısmi veriyle uçtan uca doğrulandı (klip bazlı bölme,
  ağırlıklı kayıp, karışıklık matrisi, kayıt). Pencere başına çıkarım
  **1.87 ms**.
- `vision/rules/arbiter.py` — `HybridArbiter`, `RuleEngine` ile aynı imza.
  `tests/test_arbiter.py` 8 test: eşik altında karar kuralda kalır, model
  tek başına aday üretir, uzlaşmada hibrit olur, ZONE/LOITERING modele
  dokunmaz, model tek başına FIGHT üretmez.
- `decided_by` uçtan uca geçiyor: `Candidate` → `publish.py` →
  `spark_job.py` (şema + `max_by` + çıkış struct'ı) → `consumer.py` →
  `events.decided_by` ve MongoDB `telemetry.arbiter`. Panel etiketleri
  (`Kural Motoru` / `Model` / `Hibrit`) zaten vardı.
- `vision/run.py`: `--no-tcn` ve `--tcn-min-conf` bayrakları; ağırlık yoksa
  hat aynen kural motoruyla çalışır (doğrulandı). `tcn_min_conf` sıcak
  yükleme yolundan da geliyor.
- Tüm paket **191 test + 8 yeni test yeşil.**

Aşama 10'a not: toplu çıkarım ölçüldü, kare başına **27.5 ms → 16.8 ms**
(batch 4); batch 8 ve 16 ek kazanç vermiyor. Dizi çıkarımında toplu hâle
getirilmedi — tüm döngüdeki kazanç ~1.3x ve toplu çıkarım Aşama 10'un işi.

### 9.2 dizi çıkarımı sonucu

| Sınıf | Klip | Pencere | İzsiz klip | Kaydırma |
|---|---|---|---|---|
| NORMAL | 600 | 2726 | 185 | 25 |
| FALL | 66 | 262 | 28 | **10** |
| RUN | 144 | 195 | 65 | 25 |
| FIGHT | 270 | 1236 | 40 | 25 |

Toplam **4419 pencere**. Hız 7–10 klip/dakika.

**38 klip hiç açılmıyor** (FIGHT 13, NORMAL 24, RUN 1): `moov atom not found`
/ `non-existing PPS`. Yerel dosya boyutları SPHAR deposundakiyle birebir aynı
— indirme kesilmemiş, dosyalar kaynakta bozuk.

İki düzeltme yapıldı, ikisi de ölçümle:

1. **URFD kare bazlı etiketi kullanılıyor.** İlk eğitimde FALL kesinliği
   0.300 çıktı. Kök neden: URFD düşme klibinin **~%40'ı düşme öncesi
   yürüyüş** (1192 kare `-1`, 900 kare `0` geçiş, 903 kare `1` yerde) ama
   hepsi FALL etiketi alıyordu — model yürüyüşü düşme sanıyordu. Kaynak
   kendi kare etiketini `urfall-cam0-falls.csv` ile veriyor; pencere artık
   yalnızca gerçekten düşme geçen kareyi içeriyorsa tutuluyor (31 pencere
   elendi). CASIA düşme kliplerinde böyle anotasyon yok, onlar klip
   etiketiyle kalıyor — kabul edilen gürültü.
2. **FALL için `--stride 10`.** Sınıf ince (66 klip); yarım pencere
   kaydırma yerine %80 örtüşme. Bölme klip bazlı olduğu için sızıntı yok.
   FALL 128 → 262 pencere.

Ayrıca pencere üretmeyen klip için de boş `.npz` yazılıyor: yoksa dosya
oluşmuyordu ve betik her yeniden başlatıldığında o klip baştan işleniyordu
(yarım kalan bir koşuda 213 klip boşuna tekrar edildi).

## Aşama 9.3 sonucu — TCN eğitimi (2026-09-10)

66 116 parametre, klip bazlı %80/%20 bölme, ağırlıklı `CrossEntropyLoss`,
erken durdurma. **Pencere başına çıkarım 1.20 ms.**

| Sınıf | Kesinlik | Duyarlılık | F1 | Doğrulama penceresi |
|---|---|---|---|---|
| NORMAL | 0.802 | 0.722 | 0.760 | 540 |
| FALL | 0.524 | 0.620 | 0.568 | 71 |
| RUN | 0.704 | 0.974 | 0.817 | 39 |
| FIGHT | 0.615 | 0.686 | 0.649 | 226 |
| **makro F1** | | | **0.698** | |

Karışıklık matrisi (satır = gerçek, sütun = tahmin):

| | NORMAL | FALL | RUN | FIGHT |
|---|---|---|---|---|
| **NORMAL** | 390 | 40 | 13 | 97 |
| **FALL** | 27 | 44 | 0 | 0 |
| **RUN** | 1 | 0 | 38 | 0 |
| **FIGHT** | 68 | 0 | 3 | 155 |

Etiket düzeltmesinin etkisi ölçüldü: FALL kesinlik 0.300 → **0.524**, FALL
F1 0.333 → **0.568**, makro F1 0.672 → **0.698**. RUN F1 0.892'den 0.817'ye
düştü — FALL artık rekabet ediyor, beklenen bir takas.

En büyük kalan zayıflık NORMAL ↔ FIGHT karışması (97 + 68 pencere). Kaynağı
muhtemelen `ucarg` boks klipleri: tek kişilik gölge boks, kol hareketi
normal harekete yakın.

## Aşama 9.5 sonucu — ablation tablosu (2026-09-10)

**Aşamanın onay kriteri.** `eval/tcn_eval.py`, üç mod × iki küme, tek
ortalama verilmedi.

### Holdout klipler (eğitim dışı, klip bazlı)

| Mod | TP | FP | FN | Kesinlik | Duyarlılık | F1 |
|---|---|---|---|---|---|---|
| kural | 13 | 6 | 31 | 0.68 | 0.30 | 0.41 |
| model | 13 | **1** | 31 | **0.93** | 0.30 | 0.45 |
| hibrit | **17** | 7 | **27** | 0.71 | **0.39** | **0.50** |

Tip bazında F1:

| Tip | kural | model | hibrit |
|---|---|---|---|
| FALL | 0.53 | 0.67 | **0.78** |
| RUN | 0.50 | **0.55** | 0.48 |
| FIGHT | 0.12 | 0.00 | 0.12 |

**Hibrit kazanıyor** (F1 0.41 → 0.50), model tek başına en kesin olan
(0.93) ama duyarlılığı kuralla aynı. FALL'da model gerçekten katkı veriyor:
0.53 → 0.78. Model FIGHT'ta 0.00 çünkü tasarım gereği tek başına FIGHT
üretmiyor (ikili eşleştirme kuralda).

### Pilot klipler (üretim alanı, 1080p)

| Mod | TP | FP | FN | Kesinlik | Duyarlılık | F1 |
|---|---|---|---|---|---|---|
| kural | 3 | 24 | 1 | 0.11 | 0.75 | 0.19 |
| model | 1 | 15 | 3 | 0.06 | 0.25 | 0.10 |
| hibrit | 4 | 39 | 0 | 0.09 | **1.00** | 0.17 |

**Alan farkı burada görünüyor ve tam da beklendiği gibi:** holdout'ta
kesinliği 0.93 olan model, pilot kliplerde 12 sahte FALL üretiyor. 320x240
güvenlik kaydıyla eğitilmiş model 1080p pilot görüntüde yanılıyor. Tek
ortalama alınsaydı bu görünmezdi.

Pilot FP'lerinin çoğu ZONE_VIOLATION (20 adet) ve bu Aşama 3'ten beri
bilinen davranış: bölge kuralı koşul sürdükçe her karede aday üretiyor.
Tablodaki sayılar **Spark öncesi ham adaylardır**; üretimde `min_hits` +
`min_sec` süzgeci bu gürültüyü eliyor (Aşama 4 ölçümü).

### FIGHT ve LOITERING — ilk gerçek ölçüm

- **FIGHT duyarlılığı 0.07** (15 holdout klibinin 1'i). PLAN.md risk 3
  kural tabanlı kavga için ~%70 bekliyordu; ölçülen bunun çok altında.
  Kural ikili yakınlık + karşılıklı uzuv hızı istiyor, `bitint`/`utint`
  klipleri 2-3 saniye ve pencere 2 saniye — çoğu klipte şart üç kare
  (`HOLD`) üst üste sağlanmıyor. Model penceresi de aynı sebeple zor
  doluyor.
- **LOITERING hiçbir kümede tek aday üretmedi.** Yanlış pozitif oranı
  sıfır; duyarlılık **ölçülmedi** — olumlu örnek hiçbir kümede yok, tahmin
  edilmiyor. Aşama 10'a devrediyor.

## Aşama 10.1-10.4 sonucu (2026-09-10)

### 10.1 — `CameraPipeline` çıkarımı

`vision/run.py`'nin `main()` gövdesindeki kamera başına durum
`vision/camera.py`'ye taşındı. `run.py` artık **sürücü**: N adet
`CameraPipeline` kurar, hepsinden birer kare toplar, **tek**
`detector(images)` çağrısı yapar, sonuçları sahibine dağıtır. N=1 ve N=4
aynı koddan geçer — tek kameralık davranış ayrı bir yol değil, dolayısıyla
sessizce ayrışamaz.

İkinci bir `run_multi.py` yazılmadı: canlı yayın, kanıt, kalp atışı, JPEG
kalite denetleyicisi ve rapor mantığı iki kopyada yaşardı (v1'in 435
satırlık `pipeline.py`'sinin tekrarı). `run.py` 582 → 303 satır,
`camera.py` 421 satır.

Davranış korunumu ölçüldü — `mixed_01`, 300 kare, refactor öncesi/sonrası:

| | Önce | Sonra |
|---|---|---|
| aday olay | RUN 14, iz 1, ilk tetik 4.8 sn | **aynı** |
| benzersiz ID | 1 | **aynı** |
| pozsuz iz | 0 / 300 | **aynı** |
| FPS | 33.5 | 32.7 (ölçüm gürültüsü) |

Refactor sırasında iki hata yapıldı ve yakalandı: `build_meta` elle yeniden
yazılınca `schema`, `width/height`, `kp` ve `pre_alarms` alanları değişmişti
(test yakaladı, paneli sessizce bozardı) ve `load_zones` taşınırken `json` /
`datetime` importları düşmüştü. İkisi de git'teki özgün gövde **birebir**
kopyalanarak düzeltildi. Ders: taşırken yeniden yazma, kopyala.

Ayrıca bir ölçüm hatası düzeltildi: kamera kendi klibini bitirdikten sonra da
`elapsed` turun sonuna kadar sayıyordu, kısa klipli kameranın FPS'i yanlış
düşük çıkıyordu. Süre artık kaynak bitince durur.

### 10.2 — Ön işleme küçültme yöntemi

4K karede `letterbox` maliyetinin tamamı `cv2.resize`. Beş pilot klipte
(4K `run_01` dahil) ölçüldü:

| Yöntem | Ön işleme medyan | Pozlu kare | Benzersiz ID | `pilot_eval` TP/FP/FN |
|---|---|---|---|---|
| INTER_AREA (eski) | 7.73 ms | %70.9 | 4 | 3 / 5 / 1 |
| **INTER_LINEAR** | **1.75 ms** | %70.9 | 4 | 3 / 5 / 1 |
| INTER_NEAREST | 1.49 ms | %70.9 | 4 | — |

Doğruluk tablosu birebir aynı çıktı, hız 4.4 kat. INTER_LINEAR seçildi
(`vision/stages/preprocess.py` `DOWNSCALE_INTERP`).

**Ama uçtan uca kazanç yok denecek kadar az: 4 kamera 45.2 → 45.6 FPS.**
Sebep ölçülebilir: `zone_01` (640x360) ve `mixed_01` (898x506) küçültülmüyor,
**büyütülüyor**; onların 8-9 ms'i resize değil CLAHE. Turun kritik yolu
orası. Kritik yolda olmayan bir aşamayı hızlandırmak uçtan uca hiçbir şey
kazandırmıyor — ölçmeden yapılsaydı "iyileştirdik" denirdi.

### 10.3 — Tek süreç, 4 kamera, toplu çıkarım

`--source a.mp4,b.mp4,c.mp4,d.mp4`. Toplu çağrının tek sahibi sürücüdür.
Çıkarım kare başına **14.45 → 10.5 ms** (batch 4).

Gerçek eşzamanlı ölçüm `--loop --max-frames` ile alınır: kameralar farklı
anlarda biterse son kalan tek başına hızlanır ve toplam şişer (ilk ölçümde
59.0 FPS çıkmıştı, gerçek eşzamanlı değer 45.2).

| Kurulum | Kamera başına FPS | Toplam |
|---|---|---|
| Aşama 8.6, **3 kamera ayrı süreç** | 9.3 / 13.7 / 15.1 | 38.1 |
| Aşama 10.3, **4 kamera tek süreç** | 11.4 × 4 | 45.6 |

### 10.4 — Düğme tablosu (4 kamera, aynı klipler)

Hız **ve** doğruluk birlikte ölçüldü; hızlı olanı doğruluk bakmadan seçmek
bu tablonun varlık sebebini yok ederdi.

| Yapılandırma | Kamera başına FPS | `pilot_eval` FALL F1 | Toplam F1 |
|---|---|---|---|
| `s` + ReID + CLAHE (taban) | 11.7 | 1.00 | 0.50 |
| `s` + ReID kapalı | 15.2 | 1.00 | 0.50 |
| `s` + CLAHE kapalı | — | 1.00 | 0.50 |
| `s` + ReID/CLAHE kapalı | 17.6 | 1.00 | 0.50 |
| **`s` + ReID/CLAHE kapalı + `imgsz 640`** | **26.3** | **1.00** | **0.50** |
| `n` + ReID | 13.4 | **0.00** | 0.36 |
| `n` + ReID kapalı | 19.2 | **0.00** | — |
| `n` + ReID/CLAHE kapalı | 27.2 | **0.00** | 0.40 |

**`yolo26n-pose` FALL'ı tamamen kaybediyor** (F1 1.00 → 0.00). PLAN.md risk 1
"çoklu kamerada `yolo26n-pose`'a düşülür" diyordu; ölçüm bunu **çürüttü** —
düşülemez, düşülürse sistemin ana anomali sınıfı ölür. Hız `n`'den değil
ReID + CLAHE + `imgsz`'den alınmalı.

ReID ve CLAHE kapatmanın pilot kümede ölçülebilir doğruluk bedeli **yok**
(TP/FP/FN birebir aynı). ReID için bu, Aşama 2'de `--no-reid` ile ID
sayılarının hiç değişmemesi bulgusuyla tutarlı.

`imgsz 640` küçük/uzak insanı kaçırır mı diye ayrıca ölçüldü — CASIA
kliplerinde (kişi kare yüksekliğinin ~%24'ü) **kaçırmıyor, tersine artırıyor**:
pozlu kare %47.6 → %54.1.

**Onay kriteri (kamera başına ≥ 20 FPS, 4 kamera) karşılandı: 26.3 FPS.**
Ölçülen doğruluk bedeli sıfır.

Üç uyarı, üçü de bu kümenin sınırı:

1. **ReID kapalı** — pilot kliplerde en fazla 1-2 kişi var; kalabalıkta ID
   değişimi hiç ölçülmedi (Aşama 2'den beri açık soru)
2. **CLAHE kapalı** — pilot klipler karanlık değil. Gerçekten düşük ışıkta
   CLAHE'nin kapalı olması tespiti düşürebilir
3. Bu yüzden **varsayılanlar değiştirilmedi**; bunlar `vision/run.py`
   bayrakları olarak kalıyor. 4 kamera profili: `--no-reid --no-clahe
   --imgsz 640`

### 10.3 devamı — tek süreçli başlatıcı ve uçtan uca açılış (2026-09-10)

`scripts/run_pilot_cameras.py` artık **kamera başına bir süreç değil tek
süreç** açıyor: kaynaklar ve adlar virgülle birleşip `vision.run`'a veriliyor,
tek model, tek toplu çıkarım, tek WS portu. Önceden her süreç kendi model
kopyasını VRAM'e yüklüyordu ve 4 GB'ta 3 kamerada tıkanıyordu.

`--camera-id` de artık virgülle ayrılabiliyor ve kaynaklarla aynı sırada
eşleşiyor; sayı tutmuyorsa ad kaynaktan türer (tek kameralı eski davranış).

Tüm sistem açılıp panelden doğrulandı: 6 konteyner sağlıklı, 4 kamera
(dizüstü kamerası + 3 pilot klip) tek süreçte, kamera başına ~5.9 FPS. Bu
sayı 10.4'teki 26.3'ün altında çünkü burada tam zincir açık (Kafka + kanıt +
WebSocket + TCN) ve Spark/tüketici aynı makinede CPU paylaşıyor.

**Bulunan gerçek hata: canlı kaynak kalıcı olarak ölü sayılıyordu.**

Webcam açılışta 30 saniyeyi aşınca `LIVE_WAIT_SEC` doluyor ve hat kamerayı
`finished` işaretliyordu — bir daha hiç okunmuyordu. Kuyruğu dolu kaldığı
için düşen kare durmadan arttı (**ölçülen: 955**) ve `VideoSource`'un üstel
geri çekilmeli yeniden bağlanma mantığı hiç devreye giremedi.

Tek kamerada bu görünmezdi: eski kodda aynı durum tüm koşuyu bitiriyordu,
yani "normal son" sayılıyordu. Çoklu kamerada bir kamera sessizce ölürken
diğerleri koştuğu için ortaya çıktı — `docs/ASAMA10_PLAN.md` § 2'nin "kamera
biri düşerse diğerleri devam eder" sözünün fiilen tutmadığı yer.

Düzeltme: canlı kaynak **asla** kalıcı bitmiş sayılmaz. Kesinti sayılır
(`outages`), uyarı basılır, okumaya devam edilir; yeniden bağlanma ancak
böyle çalışabilir. Dosya kaynağı gerçekten biter (EOF), canlı kaynak bitmez.
Düzeltmeden sonra webcam 4.7 FPS'te çalıştı. `tests/test_asama8_6.py` içinde
regresyon testi var.

Canlı kaynakta yüksek `dropped` **normaldir**: kamera ~30 FPS üretir, hat ~5
tüketir, gerisi tasarım gereği atılır (kuyruk derinliği 1, "gecikme yerine
tazelik").

## Aşama 11 sonucu — olay tetiklemeli ReID ve FIGHT kök nedeni (2026-09-11)

### 11.1–11.3 — ReID galerisi: ölçüldü, **çalışmıyor**

`vision/reid_gallery.py` (olay anında gömme, kosinüs eşleştirme, kalıcı
`person_id`) ve `eval/reid_eval.py` yazıldı. Gerçek referans uydurulmadı:
CASIA klipleri dosya adında kişi kimliği taşıyor (`..._p01_...`).

| Koşul | Kosinüs |
|---|---|
| Aynı kişi, ardışık kare | **0.749** |
| Farklı kişi, aynı kare | 0.563 |
| Aynı kişi, tekrar giriş (klip başı ↔ sonu) | **0.465** |
| Aynı kişi, farklı klip / farklı eylem | 0.358 |

**Aynı kişinin birkaç saniye sonraki hâli, farklı bir kişiden daha uzak.**
Gömme vektörü zamanla/duruşla, kişiler arasındaki farktan hızlı bozuluyor.
Eşik taramasında en iyi F1 tekrar girişte **0.15** (eşik 0.75, kesinlik
0.38, duyarlılık 0.09). Bu sayıyla kimlik atamak olayların çoğuna yanlış
`person_id` yazmak demek — **hatta bağlanmadı.**

Kodlayıcı hatası değil: ardışık karede 0.749, aynı karedeki iki kişiyi
+0.186 ile ayırıyor. Yani model kare-kare eşleştirme için çalışıyor (zaten
BoT-SORT onu o iş için kullanıyor), zaman içinde kimlik taşımaya yetmiyor.
Sebep çözünürlük: CASIA kaynağı 320x240, kişi kare yüksekliğinin ~%27'si,
kırpım ~35x146 **interpolasyonlu** piksel.

Olumlu yan bulgu: **en iyi kare seçimi (Laplacian) işe yarıyor** — tekrar
girişte 0.465, ilk kareyi almaya göre belirgin daha iyi (0.346 → 0.465
farklı-klip koşulunda da aynı yönde).

Kendi kusurum olarak kayda geçer: kırpım 960x540 letterbox karesinden
alınıyor, ham kareden değil. CASIA'da fark yok (kaynak zaten küçük) ama
1080p/4K kamerada mevcut çözünürlüğün çoğunu atıyor. Gerçek kamerada
ölçülecekse önce bu düzeltilmeli.

### 11.4 — FIGHT duyarlılığı 0.07: kök neden

Önce varsayılan suçlu `HOLD = 3` (üç kare üst üste şart) sanılmıştı.
**Ölçüm bunu çürüttü.** 15 FIGHT klibi, 1069 kare:

| Şart | Sağlanma |
|---|---|
| Karede en az 2 pozlu iz | 96.9% |
| Yakınlık < 1.20 | çoğu çiftte (medyan **0.93**) |
| Her iki izin uzuv hızı ≥ 2.0 | **%0.3** |
| İkisi birden | %0.3 |
| En uzun ardışık seri | **1 kare** |

`HOLD` hiç sıraya gelmiyor. Şart uzuv hızında düşüyor: medyan 0.11, p90 1.14,
eşik 2.0.

Eşiği düşürmek de çözmüyor — çünkü öznitelik ayırmıyor. FIGHT ve NORMAL
kliplerinde yakın çiftlerin uzuv hızı dağılımı:

| Eşik | FIGHT kare % | NORMAL kare % |
|---|---|---|
| 0.3 | 19.8 | 17.3 |
| 0.5 | 10.4 | **13.0** |
| 0.7 | 5.4 | **9.1** |
| 1.1 | 1.8 | **4.4** |
| 2.0 | 0.1 | 0.1 |

**0.5 ve üstü her eşikte NORMAL oranı daha yüksek.** Hiçbir eşik bunu
kurtaramaz; sorun eşikte değil özniteliktedir.

### Yapılan değişiklik

Yakınlık şartı uzuv hızı şartından **ayrıldı** (`fight.close_pairs`).
Hakem artık modelin FIGHT oyunu, iz yakın bir çiftin parçasıysa tek başına
aday olarak kabul ediyor. Önceden şart "kural da aynı tipte aday versin"di
ve çalışmayan bir kurala bağımlılık modelin FIGHT duyarlılığını sıfıra
çakıyordu (holdout F1: kural 0.12, model 0.00).

Gerekçe ölçüme dayanıyor: kuralın uzuv hızı şartı ayırmıyor, yakınlık
şartı ayırıyor, TCN pencere bazında FIGHT F1 **0.649** veriyor. PLAN.md
risk 3 zaten "gerçek çözüm TCN modelidir" diyordu.

### Değişikliğin ölçülen etkisi — 9.5 ablation yeniden koşuldu

| Mod | TP | FP | FN | Kesinlik | Duyarlılık | F1 |
|---|---|---|---|---|---|---|
| kural | 13 | 6 | 31 | 0.68 | 0.30 | 0.41 (değişmedi) |
| model | 13 → **25** | 1 → 6 | 31 → **19** | 0.93 → 0.81 | 0.30 → **0.57** | 0.45 → **0.67** |
| hibrit | 17 → **28** | 7 → 12 | 27 → **16** | 0.71 → 0.70 | 0.39 → **0.64** | 0.50 → **0.67** |

Tip bazında F1:

| Tip | kural | model | hibrit |
|---|---|---|---|
| FALL | 0.53 | 0.67 | **0.78** |
| RUN | 0.50 | **0.55** | 0.48 |
| FIGHT | 0.12 | 0.00 → **0.75** | 0.12 → **0.75** |

**FIGHT duyarlılığı 0.07 → 0.80** (15 holdout klibinin 12'si; kesinlik 0.71).
Pilot kliplerde değişiklik yok — o kümede hiç FIGHT olayı yok.

Kaybedilen: model kesinliği 0.93'ten 0.81'e indi (5 yanlış pozitif FIGHT).
Takas bilinçli ve ölçülü: duyarlılık 0.30 → 0.57. Kavga tespitinde 0.07
duyarlılık, kesinliği ne olursa olsun kullanılamaz bir sistemdir.

## Aşama 10.5 sonucu — uzun koşu (2026-09-11)

8 saat yerine **1 saat** koşuldu (zaman kısıtı). Onay kriteri tam
karşılanmadı ve tezde öyle yazılacak. Buna rağmen koşu **üç gerçek hata
buldu** — hepsi dakikalık testlerde görünmeyen cinsten.

### Bulgu 1 — halka tampon 4K kaynakta belleği tüketiyordu

İlk koşu 13. dakikada çöktü: `RuntimeError: cuDNN error:
CUDNN_STATUS_EXECUTION_FAILED`, toplu çıkarım çağrısında.

| dk | kamera | FPS | görü RSS MB | GPU MB |
|---|---|---|---|---|
| 0.0 | 4 | 17.9 | 1870 | 950 |
| 4.3 | 4 | 19.0 | **4235** | 1129 |
| 8.5 | 4 | 18.8 | **4870** | 1131 |
| 12.8 | — | — | **0** (öldü) | 378 |

**GPU belleği sabit 1131 MB** — VRAM taşması değil, host belleği tükendi.
Kök neden: `VideoSource` halka tamponu kare **sayısıyla** sınırlı
(`BUFFER_FRAMES = 300`), bayt ile değil. `run_01.mp4` 3840x2160 → kare
başına 24.9 MB × 300 = tek kamera için **7.5 GB**.

Düzeltme: tampona giden kopya `BUFFER_MAX_W = 960` piksele küçültülür.
Kuyruğa giden kare **ham kalır** (tespit kalitesi değişmez); yalnız kanıt
klibinin çözünürlüğü sınırlanır — panel zaten 960x540 gösteriyor. 4K'da
tampon 7.5 GB → ~470 MB. Regresyon testi `tests/test_vision_core.py`'de.

### Bulgu 2 — tek çıkarım hatası tüm süreci öldürüyordu

Dört kamera birden sustu ve kimse haberdar olmadı. Gözetim sistemi tek bir
geçici hatada ölmemeli. Tur atlanır, sayılır, sebep basılır, döngü devam
eder; 10 ardışık hatada pes edilir (`MAX_INFER_ERRORS`).

### Bulgu 3 — Spark iki gündür sessizce ölüydü

**Bir saat boyunca tek yeni olay üretilmedi** (sayaç 1040'ta sabit). Sebep:

```
Existing value schema: ... (Asama 9 oncesi)
Provided value schema: ... (max_by(decided_by) eklenmis)
StateSchemaCompatibilityChecker.check ... incompatible schema
```

Aşama 9'da `decided_by` için `max_by` eklendiğinde Spark durum deposunun
şeması değişti; kalıcı checkpoint eski şemayı tutuyordu ve Spark sorguyu
**başlatmayı reddediyordu**. Hiçbir şey gürültülü biçimde başarısız
olmadı: görü çalıştı, Kafka'ya aday bastı, panel açıldı — yalnızca olay
yazılmadı. İki gün böyle geçti.

Düzeltme kalıcı: checkpoint yolu artık toplama sürümünü taşıyor
(`/checkpoints/agg2`). `groupBy/agg` yapısı her değiştiğinde `AGG_VERSION`
artırılır, checkpoint kendiliğinden yenilenir — elle volume silmek
gerekmez. Doğrulandı: olay sayısı 1040 → 1045, yeni kayıtlar bugünün
damgasıyla.

### İkinci koşu — düzeltmelerden sonra

| Metrik | İlk ölçüm | Son ölçüm | Değişim |
|---|---|---|---|
| Toplam FPS | 30.6 | 30.7 | **+0.0%** |
| GPU belleği | 947 MB | 1133 MB | oturdu, sabit |
| Görü RSS | 4705 MB | 5657 MB | ilk 20 dk'da plato, sonra 5.2–5.9 bandında salınım |
| storage | 2099 MB | 3359 MB | **+1260 MB / saat** |

1 saat, 58 ölçüm, 4 kamera kesintisiz. **FPS sapması yok, RSS'te doğrusal
artış yok** — sızıntı belirtisi yok.

Açık kalan: **disk saatte 1.3 GB büyüyor** (8 saatte ~10 GB). Kanıt
kliplerinin saklama politikası yok. Aşama 12'ye.

Ayrıca görüldü: Spark eşikleri API'den çekemiyor (`HTTP Error 401`),
ortam varsayılanlarına düşüyor. Sessiz bir bozulma daha; panelden eşik
değiştirmek Spark süzgecini etkilemiyor demektir.

### Kesintisiz çalışma süresi — 2 saat 50 dakika

Ölçüm betiği 1 saatte kendi süresini doldurup çıktı, ama **görü süreçleri
çalışmaya devam etti**: 11:05'te başladılar, 13:55'te elle kapatıldılar.
Toplam **2 saat 50 dakika kesintisiz**, 4 kamera, çökme yok.

Bu sürenin tamamı ölçülmedi; enstrümanlı bölümler `logs/soak_2.csv`
(11:05–12:05, 58 ölçüm) ve `logs/soak_ev.csv` (13:50–13:55, 20 ölçüm).
Aradaki 12:05–13:50 aralığında hat çalıştı ama kaydedilmedi.

Son ölçümlerde olay sayısı **1139 → 1140** artıyordu, yani Spark
checkpoint düzeltmesi saatler sonra da tutuyor — düzeltmenin kalıcı
olduğunun ikinci kanıtı.

İki dosya tek tabloda birleştirilmez: `gecen_dk` her koşuda sıfırdan
sayar, birleştirme ilk saat / son saat karşılaştırmasını bozar.

### Bulgu 4 — hata işleyicisinin kendisi koşuyu öldürüyordu (2026-09-12)

8 saatlik koşu 4. dakikada öldü. Zincir:

1. API'den ölçüm çekerken geçici okuma hatası: `httpx.ReadError [WinError 10053]`
2. `soak_test.py` bunu yakalıyor ve sebebi basıyor — tasarım doğru, satır
   atlanıp koşu sürmeli
3. Ama Windows konsolu **cp1252**; hata mesajı Türkçe ("bağlantı ... iptal
   edildi") ve `ğ` harfi bu kod sayfasında yok
4. `print` `UnicodeEncodeError` atıyor, `except` bloğunun *içinden*, yani
   yakalanmıyor → süreç 1 ile çıkıyor

Yani hatayı tolere etmek için yazılmış blok, hatayı **ölümcül** yapan
şeydi. Kısa testlerde görünmez: geçici ağ hatası olmadan bu yol hiç
çalışmıyor.

Düzeltme tek satır — basım asla çatlamamalı:

```python
sys.stdout.reconfigure(errors="replace")
sys.stderr.reconfigure(errors="replace")
```

Doğrulandı: `PYTHONIOENCODING=cp1252` altında `ğşı` basımı çıkış kodu 0,
karakterler `???` oluyor, çökme yok.

**Ders:** hata yolunu da hata yolu gibi test et. Kayıt/basım satırı,
koruduğu koddan daha kırılgan olmamalı.

### Bulgu 5 — konteyner "healthy" ama ana makineden ölü (2026-09-12)

8 saatlik koşunun üç başlatma denemesi üst üste düştü. Belirti her seferinde
başka göründü: önce `httpx.ReadError [WinError 10053]`, sonra `Server
disconnected without sending a response`, kameralarda ise
`rdkafka ... connection closed by peer: POLLHUP`.

Tek bir kök neden: **Docker Desktop'ın ana makine port yönlendirmesi yarım
kalkmıştı.** Yayınlanan portlar TCP bağlantısını kabul edip yanıt vermeden
kapatıyordu — hem 8000 hem 9092.

Yanıltıcı olan: `docker compose ps` altı konteyneri de **healthy**
gösteriyordu. Sağlık yoklaması konteynerin *içinden* (`127.0.0.1`)
koşuyor, o yüzden geçiyordu. API kayıtlarında ana makineden **tek bir
istek bile yoktu** — yalnız kendi yoklaması. Teşhisi veren buydu.

`docker compose start` ve `up -d` düzeltmedi; Docker Desktop'ın kendisini
kapatıp açmak düzeltti.

**Ders:** yığın kontrolü konteyner sağlığına bakmakla bitmez. Ana
makineden en az bir gerçek istek atılmalı:

```powershell
Invoke-WebRequest http://localhost:8000/health -UseBasicParsing
(New-Object Net.Sockets.TcpClient).Connect("localhost", 9092)
```

Koşu öncesi kontrol listesine bu iki satır eklendi.

## Aşama 10.5 — 8 saatlik koşu TAMAM (2026-09-12)

Onay kriteri karşılandı: **8.0 saat, 4 kamera, 459 ölçüm, kesintisiz.**
Kameralar `webcam_01, zone_01, run_01, fall_01` (Aşama 10.4'teki kümenin
aynısı, sayılar karşılaştırılabilir). Kayıt: `logs/soak_8saat.csv`.

| metrik | ilk saat | son saat | değişim |
|---|---|---|---|
| toplam FPS | 33.2 | 33.4 | +0.6% |
| en düşük kamera FPS | 8.2 | 8.3 | +0.7% |
| çıkarım | 13.9 ms | 14.0 ms | +0.5% |
| görü RSS | 5804 MB | 6005 MB | +3.5% |
| GPU | 791 MB | 898 MB | +13.6% |
| depolama | 7382 MB | 17785 MB | +141% |

Olay sayısı 1216 → 1722 (506 yeni olay, 8 saatte).

### GPU artışı sızıntı değil

Ham %13.6 yanıltıcı. Saatlik ortalama:

| saat | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| GPU MB | 791 | 864 | 899 | 898 | 898 | 898 | 898 | 898 |
| RSS MB | 5804 | 5694 | 5805 | 5866 | 5895 | 5994 | 5985 | 6005 |

GPU **3. saatte 898 MB'de oturuyor ve 6 saat boyunca oynamıyor** — CUDA
tahsis ön belleğinin ısınması, sızıntı değil. Sızıntı olsaydı artış
doğrusal sürerdi.

RSS'te hafif sürüklenme var: saatte ~25 MB, salınımlı (2. saatte 5694'e
düşüyor). 8 saatte +201 MB. Plato demek doğru olmaz ama bu hızda 24 saat
+600 MB eder; işletim için engel değil. Daha uzun koşu ölçmediğimiz için
"sızıntı yok" değil **"8 saatte sızıntı görülmedi"** denmeli.

### Kalan gerçek sorun: disk

Depolama 8 saatte 7.4 GB'den 17.8 GB'ye çıktı — **saatte 1.3 GB**, günde
~31 GB. Kanıt kliplerinin saklama politikası yok. Aşamanın teknik onay
kriteri karşılandı ama bu haliyle sistem günlerce çalışamaz. Aşama 12'nin
ilk maddesi.

### Koşuya ulaşana kadar çıkan üç arıza

Koşu başlatılabilene kadar üç deneme düştü; üçü de dakikalık testlerde
görünmez cinsten ve ayrı ayrı yukarıda (Bulgu 4, Bulgu 5). Ayrıca
`run_pilot_cameras.py` `--cameras` boş bırakılınca **3** kamera açıyor
(`DEFAULT_CAMERA_COUNT = 3`); 4 kameralık ölçümle karşılaştırmak için
kamera listesi açıkça verilmeli.

<sub>Önceki durum kaydı: onay kriteri karşılanmadan önce en uzun
kesintisiz süre 2 saat 50 dakikaydı.</sub>

## Aşama 12.1 — Kanıt saklama politikası (2026-09-14)

Aşama 10.5'in açık bıraktığı tek işletim engeli kapandı: depo saatte
1.3 GB, günde ~31 GB büyüyordu ve hiçbir sınır yoktu.

### Kural

`vision/retention.py`, iki kural birlikte:

| | varsayılan | neden |
|---|---|---|
| klip yaşı | 7 gün | öngörülebilir saklama süresi |
| kare yaşı | 90 gün | Mongo `pose_sequences` TTL'i ile aynı |
| toplam tavan | 20 GB | diski kesin sınırlar |

Tek başına ikisi de yetmiyor: yaş kuralı diski sınırlamaz (yoğun haftada
7 × 31 = 217 GB), boyut tavanı tek başına saklama süresini öngörülemez
yapar (sakin hafta aylarca durur, yoğun gün saatler içinde silinir).

Tavan aşılırsa **yalnız klipler** silinir, en eskiden başlayarak. Kareler
deponun %3'ü (474 MB / 17 GB); hepsini silmek tavanı kurtarmaz ama
panelin tüm görsel geçmişini götürür.

Silinen şey yalnızca **dosyadır**. `events` satırı, `clip_path` alanı ve
Mongo'daki `pose_sequences` yerinde kalır — olay geçmişi ve ölçülen
metrikler bozulmaz. API zaten iki durumu ayırıyor: `clip_path` boşsa
"klip bulunamadi", doluyken dosya yoksa "klip dosyasi diskte yok".

### Nerede koşuyor

Kanıt yazıcısının arka plan thread'inde, klip yazılıp bildirildikten
sonra. Ana görü döngüsü diskte hiç beklemez. Budayıcı kameralar arasında
**paylaşılır**: depo dizini ortaktır, kamera başına bir tane kurmak aynı
7500 dosyayı dört kez taratır ve aynı dosyayı silmek için yarışırlar.

### Ölçülen sınır: tavan anlık değil ortalama

İki budama arasında (60 sn) yazılan klipler tavanın üstüne çıkar. Ölçüldü:
10 MB tavanla canlı koşu 20 MB'a kadar çıktı, budama çalışınca 9 MB'a
indi. Gerçek ölçekte aşım saatte 1.3 GB'lik büyümeyle 60 saniyede ~22 MB,
yani 20 GB tavanın binde biri.

### Testin yakalayamadığı hata

Birim testleri geçtikten sonra tek kamerayla gerçek koşu yapıldı ve
`NameError: name 'keeper' is not defined` çıktı: budayıcı `__init__`
imzasına eklenmişti ama `EvidenceWriter` `start()` içinde kuruluyor.
Hiçbir test kanıt üretimi açık bir boru hattı kurmuyor, o yüzden 221 test
yeşilken kod üretimde ilk saniyede çöküyordu.

**Ders (yine):** testin geçmesi doğrulama değildir.

### Mevcut depo

Kuru koşu: 17.3 GB, 3764 klip, 3761 kare; hiçbir dosya 7 günden eski
değil, tavan aşılmıyor — yani politika şu an hiçbir şey silmez. İlk
silme, koşular birikip 20 GB'ı aştığında ya da klipler bir haftayı
doldurduğunda olur.

```bash
venv/Scripts/python.exe -m vision.retention --dry-run     # ne silinecek
venv/Scripts/python.exe -m vision.retention               # elle buda
```

---

## Aşama 12.2 — Spark eşikleri artık gerçekten API'den geliyor (2026-09-14)

Aşama 10.5'te görülen sessiz bozulma kapandı: Spark `GET /api/settings`'ten
`HTTP Error 401` alıyor, tek satır uyarı basıp ortam varsayılanlarına
düşüyordu. Sonuç: **panelden eşik değiştirmek Spark süzgecini hiç
etkilemiyordu** ve hiçbir şey gürültülü biçimde başarısız olmuyordu.

### Kök neden

`.env`'deki `SPARK_SETTINGS_TOKEN`, elle yapıştırılmış 164 karakterlik bir
JWT'ydi. `JWT_EXPIRE_MINUTES=720`, yani jeton **12 saat sonra ölmüştü**.
Sabit jeton koymak sorunu çözmez, erteler.

### Çözüm

Spark açılışta **kendisi giriş yapar**. Eşikler yalnızca açılışta bir kez
okunduğu (sorguya gömüldükleri) için tek giriş yeter, yenileme döngüsü
gerekmez.

Akış: elindeki jetonla dener → `401/403` alırsa bir kez giriş yapıp tekrar
dener → o da olmazsa eski davranış (uyarı + ortam varsayılanları).
`401` dışı hatalarda (örn. `500`) giriş denenmez; kimlik sorunu değildir.

`SPARK_SETTINGS_TOKEN` artık **isteğe bağlı**, geriye dönük uyum için
duruyor. Kimlik `ADMIN_PASSWORD`'dan gelir.

**ponytail:** `admin` kimliği kullanılıyor, çünkü veritabanında tohumlanan
tek kullanıcı o ve `init.sql` yalnızca ilk kurulumda koşuyor — var olan
kuruluma servis kullanıcısı eklemek elle migration ister. Ayrı bir
salt-okunur `viewer` kullanıcısı yükseltme yoludur.

### Doğrulama — testle değil, uçtan uca

Birim testleri (6 adet) 401 yolunu, giriş gövdesinin form-kodlu olmasını ve
`500`'de giriş denenmemesini ölçüyor. Ama asıl iddia "panelden eşik
değiştirmek artık Spark'a geçiyor"; o canlı ölçüldü:

1. Yığın kaldırıldı → `[spark_job] jeton gecersiz/suresi dolmus, yeniden
   giris yapildi` → `esikler API'den alindi: window=3s`
2. `PUT /api/settings` ile `spark_window_sec` 3 → 5
3. `docker compose restart spark` → `esikler API'den alindi: window=5s`
4. Eşik 3'e geri alındı

Eskiden 3. adımda ortam varsayılanı okunurdu.

### Değişmeyen bilinçli sınır

Eşikler akan sorguya **gömülüdür**; panelden değiştirilen değer ancak Spark
yeniden başlatılınca geçerli olur. Sıcak yükleme checkpoint uyumsuzluğu
yaratacağı için bilinçli olarak yok (ASAMA6_PLAN.md §9).

---

## Aşama 12.3 — Kur/Bırak (Evde / Koruma) modu (2026-09-14)

`TEZ_KAPSAM.txt` **Faz 1** satırı: *"Kur/Bırak: Evde = bildirim yok,
Koruma = alarm."* Kapsamda AKTİF işaretliydi, kodda karşılığı yoktu.
`TEZ_UYUM.md` bunu yanlışlıkla Faz 2'ye yazmıştı; Faz 2 olan, bu modun
**bilinen kişi** ile birlikte çalışmasıdır (§49), modun kendisi değil.

### Ne yapar, ne yapmaz

Evde modunda **tespit, kanıt üretimi ve olay kaydı aynen sürer**; kesilen
yalnızca dışarı bildirimdir. Ölçüldü: kapalıyken koşan klip 5 yeni olay
yazdı (1725 → 1730), hepsi veritabanında, klipleriyle birlikte.

Bastırma **LLM çağrısından önce** yapılır: kimseye gitmeyecek bir rapor
için kota harcanmaz. Ölçümde görüldü — bastırılan olayda `llm_report_tr`
boş, gönderilende dolu.

Bastırılan bildirim **kayıt bırakır** (`notifications.status = 'skipped'`,
`error = 'evde modu'`). Bir güvenlik sisteminde "alarm gönderilmedi"
bilgisi, gönderildi bilgisi kadar denetlenebilir olmalıdır.

### Şema göçü — init.sql tek başına yetmiyor

`infra/postgres/init.sql` yalnızca veritabanı birimi **boşken** koşar. Bu
kurulumda 1725 olay vardı; init.sql'i değiştirmek o veritabanına hiçbir şey
yapmazdı. Bu yüzden `api/db/migrate.py` eklendi: açılışta koşan,
tekrarlanabilir DDL listesi. Her ifade `IF NOT EXISTS` ya da
`DROP CONSTRAINT IF EXISTS` + yeniden ekleme biçimindedir.

**Ölçülen tuzak:** ilk yazımda bütün göçler tek `engine.begin()` bloğundaydı.
PostgreSQL'de bir ifade patlayınca işlem iptal olur ve aynı işlemdeki
sonraki ifadeler "current transaction is aborted" ile düşer — yani ilk hata
geri kalan göçlerin hepsini sessizce götürürdü. Her göç kendi işlemine
alındı.

Alembic kurulmadı: tek şemalı, tek geliştiricili ve ileriye dönük göçler
için sürüm grafiği, çakışma çözümü ve ayrı komut satırı karşılığı olmayan
bir maliyettir. Göç sayısı artarsa yükseltme yolu odur.

### Ölçülen ikinci tuzak: arıza sessizliği

`_is_armed` ilk yazımda `bool(value)` dönüyordu. Sorgu beklenmedik biçimde
`None` dönerse bu **False** verir, yani sistem kendiliğinden sessizleşirdi —
yazdığım gerekçenin tam tersi. Bunu yakalayan şey testin kendisi değil,
**değersiz bir testi düzeltmekti**: `assert x is False or True` yazmıştım,
hiçbir şey ölçmüyordu. Anlamlı hâle getirince hata çıktı.

Güvenlik sisteminde güvenli taraf gürültülü olandır: satır yoksa, sütun
yoksa, sorgu boş dönerse **KURULU** sayılır.

### Panelde

Ayarlar ekranına Kur/Bırak düğmesi enjekte edildi (`camSelect` ile aynı
desen: şablonda karşılığı olmayan ama işlevin kullanılabilmesi için şart
olan öğe JS'te üretilir). Diğer alanlardan farklı olarak **Kaydet
beklemez** — kur/bırak sık ve aceleyle yapılan bir iştir, kaydedilmemiş bir
formda unutulması sistemin sessiz kalması demektir. Kapatırken onay
istenir, açarken istenmez.

### Uçtan uca doğrulama

| bildirim | durum | sebep | LLM raporu |
|---|---|---|---|
| 739 | `skipped` | evde modu | yok |
| 740–743 | `sent` | — | var |

Aynı klip, aynı kamera; arada yalnızca panelden mod değişti.

### Yan bulgu

`docker compose up -d` kodu güncellemez: API ve tüketici `build: ./api`
ile imaja derleniyor. Göç ilk denemede koşmadı ve sütun eklenmedi; kayıtta
hata yoktu çünkü çalışan imajda o kod hiç yoktu. `--build` gerekiyor.

---

## Aşama 12.4 — Uçtan uca alarm gecikmesi ölçüldü (2026-09-14)

Aşama 6'dan beri açık duran soru kapandı. Ölçüm `eval/latency_watch.py`,
kaynak `events` tablosunun kendi damgaları — ek enstrümantasyon gerekmedi:

| damga | ne |
|---|---|
| `started_at` | anomalinin başladığı an |
| `ended_at` | bittiği an |
| `created_at` | olay satırının veritabanına yazıldığı an |

Raporlanan üç sayı ayrı tutulur: **anomali süresi** (`ended−started`),
**tespit → alarm** (`created−ended`) ve **toplam** (`created−started`).

### Ölçülen

`data/pilot/fall_01.mp4`, gerçek zamanlı akıtma, 4 olay:

| | medyan | en düşük | en yüksek |
|---|---|---|---|
| tespit → alarm | **13.99 sn** | 12.74 | 15.09 |
| toplam | 14.03 sn | 12.77 | 15.13 |

### Yapısal taban 5 saniye, gerisi Spark

Gecikmenin 5 saniyesi **tasarım gereğidir ve kısaltılamaz**:

- Spark oturum penceresi 3 sn sessizlikten sonra kapanır (`spark_window_sec`)
- Su işareti 2 sn (`SPARK_WATERMARK_SEC`)

Kalan ~9 saniye Spark mikro-yığın gecikmesi + tüketicidir. `writeStream`'e
açık bir `trigger` verilmemiş, yani varsayılan "önceki yığın biter bitmez"
çalışıyor ve bu donanımda yığın başına saniyeler sürüyor. **Bu ayrım ayrıca
ölçülmedi**, yalnızca tabandan artakalan olarak biliniyor.

### Operatör ne zaman görüyor — iki ayrı sayı

Panelin canlı görüntüsü `pre_alarms`'ı **her karede** WebSocket'ten alır
(`build_meta`), yani aday anomali operatörün ekranında saniyenin altında
belirir. 13.99 saniye, **doğrulanmış olayın** veritabanına yazılıp bildirime
dönüşme süresidir. Tezde ikisi karıştırılmamalı.

### Dosya kaynağıyla ölçmenin şartı: gerçek zamanlı akıtma

`started_at` = `epoch_base + idx/fps`, yani **sahne zamanıdır**. Dosya
diskin hızında okunursa sahne zamanı duvar saatinden kayar ve kayma
doğrudan "gecikme"ye eklenir. Bu yüzden `VideoSource`'a `--realtime`
eklendi: dosya kendi FPS'inde akar ve **canlı kaynakla aynı devir teslimi**
kullanır (tek kutuluk kuyruk, eski kareyi düşürme). Kuyrukta biriktirmek
yetmiyordu — hat kaynağa yetişemeyince borç kuyruğa yazılıyor ve aynı kayma
geri geliyordu (ölçüldü: koşu boyunca 14 sn'den 19 sn'ye tırmandı).

### Sessiz bozulma görünür yapıldı

Bu kaymanın en kötü yanı **geçerli görünmesiydi**. Aşama 6'da raporlanan
"13.9–54.8 sn alarm gecikmesi" ve bu oturumda görülen 139578 saniyelik
değerler aynı hatanın ürünü. İki koruma eklendi:

1. `VideoSource.pace_lag` — programın gerisinde kalınan en büyük süre.
   Koşu raporu 0.5 sn'yi aşarsa **GERÇEK ZAMANLI AKIŞ TUTTURULAMADI** basar.
2. `latency_watch --report` — gecikme koşu boyunca %25'ten fazla büyüyorsa
   **ÖLÇÜM GEÇERSİZ** uyarısı verir.

Doğrulandı: 4K klip koşusu (hat 12.8 FPS, kaynak 30 FPS istiyor) geçersiz
işaretlendi (39.3 → 72.8 sn), `fall_01` koşusu temiz geçti.

**Sınır:** ölçüm dizüstü kamerasıyla değil, gerçek zamanlı akıtılan pilot
klibiyle yapıldı. Kameranın önünde gerçek bir düşme ölçümü hâlâ yapılmadı;
hattın kaynak ayrımı yapmadığı göz önüne alınırsa sayının değişmesi
beklenmez ama bu **varsayımdır, ölçüm değildir**.

**4K kaynakta gecikme ölçülemez:** bu donanımda hat 3840x2160 klibi kendi
FPS'inde işleyemiyor. Ölçüm yalnız hattın yetişebildiği çözünürlükte
geçerlidir.

---

## Bir sonraki adım

Aşama 10 kapandı (10.5 dahil: 8 saat, 4 kamera, kesintisiz). Sırada duran
işler, önem sırasıyla:

### 1. Disk saklama politikası — tek gerçek işletim engeli

Kanıt klipleri saatte 1.3 GB, günde ~31 GB büyüyor. Sistem bu haliyle
günlerce çalışamaz. En basit çözüm: `storage/` altında yaş veya toplam
boyut sınırı, olay veritabanı kaydı kalır, klip düşer. Ölçülmüş sayı
`docs/TEZ.md` §3.5'te.

### 2. Spark eşikleri API'den çekemiyor (`HTTP Error 401`)

Sessiz bozulma: panelden eşik değiştirmek Spark süzgecini etkilemiyor,
ortam varsayılanına düşüyor. Kimlik doğrulama yolu düzeltilmeli.

### 3. Tez metni — ölçülen sayılarla değiştirilecek yerler

Tez taslağında MAE/MSE/RMSE/R² geçiyor; bu proje sınıflandırma yapıyor,
o metrikler geçerli değil. Yerine precision/recall/F1 ve gecikme
tabloları konacak. Kaynak sayıların tamamı `docs/TEZ.md`'de,
belge-kod farkları `docs/TEZ_UYUM.md`'de.

Ayrıca yazılacak: "yöntem değişiklikleri ve gerekçeleri" bölümü
(Qdrant yerine NumPy galeri, ReID'nin hatta bağlanmaması, LSTM yerine
TCN — hepsinin ölçüm gerekçesi DURUM'da var).

### 4. Ölçülmemiş kalanlar — iddia edilmeyecek

- **LOITERING duyarlılığı** hiç ölçülmedi; hiçbir kümede olumlu örnek yok
- **Canlı kaynakta uçtan uca alarm gecikmesi** ölçülmedi; dosya kaynağında
  `started_at` duvar saati değil, gerçek sayı kamera önünde gerçek olay ister
- **Model pilot alanda 12 sahte FALL** üretiyor — alan farkı
- **RTSP** kod yolu var, donanım yok, denenmedi
- **8 saatten uzun koşu** yok; RSS'te saatte ~25 MB sürüklenme sürüyor mu
  bilinmiyor

### Sistemi açmak

```bash
docker compose up -d
venv/Scripts/python.exe scripts/run_pilot_cameras.py --cameras webcam_01,zone_01,run_01,fall_01
```

`--cameras` boş bırakma: varsayılan **3** kamera açar, 4 kameralık
ölçümlerle karşılaştırılamaz.

Yığın kontrolü konteyner sağlığıyla bitmez — ana makineden gerçek istek at:

```powershell
Invoke-WebRequest http://localhost:8000/health -UseBasicParsing
```

Panel `http://localhost:8000`, kullanıcı `admin`, şifre `.env`'deki
`ADMIN_PASSWORD`.

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
| 2026-09-09 | WS yayını yoklama değil olay güdümlü | 5 ms yoklama iki bağlantıda saniyede 400 uyanma demekti; CPU'su dolu görü döngüsüyle GIL yarışı teslimi 1 FPS'e düşürdü — daha sık yoklamak daha az kare teslim ediyordu |
| 2026-09-09 | Kalp atışı ucu ad **veya** id kabul eder | vision/ kamerayı adıyla tanır; int bekleyen uç her atımda 422 döndü ve cameras.status hiç güncellenmedi |
| 2026-09-09 | Bildirim tetiği `consumer.py`'de, kuyruk + tek worker thread | Olay kimliği ve kanıt yolu yalnız orada birlikte var; gönderim inline olsaydı 3–8 sn'lik LLM+Telegram turu offset commit'i ve arkadaki olayların yazımını geciktirirdi (ölçüldü: `enqueue` 2.90 µs) |
| 2026-09-09 | Eylem ifadesi kodda (`action_phrase`), üslup LLM'de | v1'de model, bölgeyle ilgisi olmayan RUN olayına "yasaklı alana giriş yaptı" yazdı — güvenlik sisteminde gerçeğe aykırı ihbar kabul edilemez |
| 2026-09-09 | Gemini/Telegram için yeni bağımlılık yok, ham REST | `httpx` zaten kurulu; iki servisin de tek uç noktası var, SDK bakım yükü getirirdi |
| 2026-09-09 | Ayrı `TELEGRAM_ENABLED`/`LLM_ENABLED` bayrağı yok | Token boşsa kanal kapalıdır; v1'de bayrak ile token ayrı ayrı yanlış ayarlanabiliyordu |
| 2026-09-09 | `consumer` container'ına `TZ: Europe/Istanbul` | Rapordaki saat operatörün yerel saatidir; container UTC doğduğu için 3 saat geri yazıyordu |
| 2026-09-09 | Sayı biçimleme `_sayi()` ile, tür denetimiyle değil | Ham SQL `NUMERIC` sütununu `Decimal` döndürüyor; `isinstance(..., float)` bunu eleyip metne "bilinmiyor" yazdı — düzeltme çağıranda değil ortak yerde |
| 2026-09-09 | Uçtan uca gecikme ve alarm gecikmesi yalnız canlı kaynakta ölçülür | Dosya kaynağında ikisi de hattın hızını değil, 64 karelik ileri okumayı ve oturumun akış sonuyla kapanmasını ölçüyor |
| 2026-09-09 | Kanıt satırı eşleşse de yazılır | events tablosunda clip_truncated kolonu yok; satır atlanırsa klibin kırpıldığı bilgisi tamamen kaybolur |
| 2026-09-09 | `login.html`de "2FA Aktif" rozeti ve "Oturumu 8 saat açık tut" onay kutusu pasif bırakılmadı, silindi | Sistemde iki adımlı doğrulama yok; jeton süresi sunucuda `JWT_EXPIRE_MINUTES` ile sabitlenir, istemci değiştiremez. İkisi de gerçek olmayan bir vaat -- diğer bağlanmayan öğelerin (Parolamı Unuttum, NODE/WSS/FPS altbilgisi) aksine "arayüzde var ama pasif" bırakmak burada yanıltıcı olurdu |
| 2026-09-09 | Panel React'siz, derleme adımı yok | Şablon düz HTML + Tailwind CDN geldi; React'e taşımak 11 ekranı elle yeniden yazmak, yani "tasarıma dokunulmaz" kuralını fiilen ihlal etmek demekti. Node/bundler zinciri de projeye girmiyor. PLAN.md'deki Recharts maddesi düştü: analitik grafikleri şablonda zaten `div` genişlikleriyle çizili, veriden hesaplanan tek şey yüzde |
| 2026-09-09 | Panel API ile aynı origin'den, `StaticFiles` ile sunuluyor | Ayrı nginx konteyneri CORS, ikinci port ve ikinci yapılandırma demekti; tek `app.mount` ile jeton, kanıt dosyaları ve göreli yollar tek origin'de kalıyor. Mount router'lardan sonra: `/` tüm yolları yakalar |
| 2026-09-09 | Şablon `frontend/`e elle değil `build_frontend.py` ile kopyalanıyor | Kullanıcı şablonu güncellerse 12 dosyadaki href ve betik satırı düzeltmesi elle tekrarlanamaz; betik idempotent ve testte "tasarım korunuyor" kanıtının kaynağı |
| 2026-09-09 | `require_admin` yazılmadı, mevcut `require_role("admin")` kullanıldı | `api/auth.py`'de Aşama 5'ten beri duruyordu, `cameras.py`/`zones.py`/`settings.py` zaten kullanıyor; ikinci bir rol bağımlılığı kod tekrarı olurdu |
| 2026-09-09 | `GET /api/health/cameras` kamera başına ayrı Mongo sorgusu değil, tek `aggregate` | N kamera için N round-trip yerine `$group` ile en son belgeyi tek seferde çeker; ham `camera_id` -> gerçek kamera id eşlemesi sonra `resolve_camera_id` ile bellek içinde yapılır, ikinci bir ad-veya-id sorgusu yazılmaz |
| 2026-09-09 | `/api/analytics/quality`'de recall/f1 hesaplanmadı, `null` + `note` | Ground-truth etiketi çalışma zamanında yok, kaçırılan olay bilinmiyor; uydurma bir sayı üretmek yerine gerçek sinyal (`events.status` geri bildirimi) üzerinden yalnız precision döner |
| 2026-09-09 | Kullanıcı `DELETE` gerçek silme değil `is_active=false` | `audit_log.user_id` ve `zones.created_by` FK'leri var; kullanıcı gerçekten silinirse "kim yaptı" denetim izi kopar |
| 2026-09-09 | Admin yetkisi kaybı tek yerde denetlenir (`_yetki_kaybi`) | Guard önce yalnız `is_active=false` yolunu koruyordu; `role: "viewer"` aynı sonucu doğuruyor ve sistemi admin'siz bırakıyordu. İki yolu ayrı ayrı korumak yerine "yetkiyi kaldıran değişiklik" tek predikatta toplandı |
| 2026-09-09 | Tekrar eden kullanıcı adı 409, 500 değil | `users.username` UNIQUE; yakalanmayan `IntegrityError` panele 500 olarak döner ve formda gösterilecek bir mesaj kalmaz |
| 2026-09-09 | Şablonun uzak görselleri yerel yer tutucuyla değiştirildi | `lh3.googleusercontent.com` bağlantıları 404 dönüyor; ayrıca "kamera görüntüsü" diye konmuş stok fotoğraflar sahte veridir. Tek `re.sub` ile `build_frontend.py`'de değiştiriliyor, yerleşim ve sınıflar aynı kalıyor |
| 2026-09-09 | Ölçülen Değerler tablosu sabit satır değil, telemetriden üretiliyor | Metrik kümesi kural tipine göre değişiyor (RUN'da hız, FALL'da eğim); sabit dört satır yazmak, olmayan metriği uydurmak ya da olanı gizlemek demekti. Eşleşen eşik yoksa durum `—` |
| 2026-09-09 | Sayfa betiği `build_frontend.py`'de dosya varsa eklenir | Sayfa listesini ikinci bir yerde tutmak, betiği ekleyip listeye yazmayı unutmak demekti; olmayan betiğe `<script>` koymak da konsola 404 dökerdi |
| 2026-09-09 | 8.3 iki paralel ajana bölündü, paylaşımlı dosyalar koordinatörde |
| 2026-09-10 | Canlı kutu "AKTİF"i `onopen`'da değil ilk karede yazar | `ws_server` jeton ve yol geçerliyse yayıncısı olmayan bir `camera_id`'ye de bağlanmayı kabul ediyor; açılışa güvenmek hiç yayın olmayan kamerayı yeşil gösteriyordu |
| 2026-09-10 | Görünürlük/gizlenme yönetimi `element.hidden` ile değil `style.display` ile | Tailwind'in `.flex` sınıfı tarayıcının `[hidden]` kuralını eziyor; `hidden = true` sessizce hiçbir şey yapmıyordu |
| 2026-09-10 | Ortak canlı akış mantığı `live.js`'te, sayfa betiklerinde değil | Canlı izleme ve kamera detay aynı WS + çizim işini yapıyor; iki kopya, ölçek dönüşümü gibi ince bir hatayı iki kez düzeltmek demekti. `build_frontend.py` canlı sayfalara ikinci betiği ekliyor |
| 2026-09-10 | Panel FPS'i hedefin altına düşerse önce görü döngüsüne bakılır | Ölçüm: tarayıcı FPS'i sunucu döngü FPS'iyle örtüşüyor (25.2 / 25.1). İstemci kare atlamıyor; düşüş her seferinde hattın kendisinde (CPU rekabeti) |
| 2026-09-10 | Postgres `connect_timeout=3`, Mongo `serverSelectionTimeoutMS=3000` | Docker kapalıyken test paketi 8 sn yerine 5+ dakika sürüyordu: her canlı-veritabanı testi işletim sisteminin varsayılan bağlantı zaman aşımını bekliyordu. Sağlık ucu da aynı sebeple asılı kalırdı | `app.js`, `build_frontend.py` ve ortak test iki ajanın da yolunda; ikisine de "dokunma, ihtiyacını raporla" denip birleştirme tek elde toplandı |

## Açık sorular

- Olay 1023 (RUN) telemetrisinde `norm_speed_max` 0.142, kullanılan eşik 1.8
  — yani panelde "EŞİK ALTINDA" görünen bir metrikle olay yine de üretilmiş.
  Kuralın hangi kanıtla tetiklendiği (uzuv hızı 1.204 mü, başka pencere mi)
  telemetri belgesinden okunamıyor. 8.6 demosunda ya da Aşama 9'da
  netleştirilmeli; operatöre çelişkili görünen tek yer burası
- Denetim kaydı ve bildirim sekmelerinin filtre kutuları henüz bağlı değil
  (8.5). Uçlar filtreleri destekliyor, bağlanmayan yalnız arayüz
- `app.js`'e taşınması gereken yardımcılar sayfa betiklerinde kopyalandı:
  `_fetchAuthedBlobUrl` (üç dosyada), `ROLE_ADI`, `DECIDED_BY_ADI`,
  `CAMERA_STATUS_ADI`, `num()`, `FORBIDDEN_MSG`. Paralel çalışma bitince
  (8.4 veya 8.5) tek yere alınmalı

- Docker altyapısı ayaktayken görü FPS'i 36.5'ten 12–15'e düşüyor. CPU
  rekabeti olduğu varsayıldı (Spark + Kafka + iki veritabanı + iki Python
  servisi), profillenerek doğrulanmadı. Aşama 10'un çoklu kamera ölçümü bu
  taban üzerinde yapılmamalı
- ~~`spark_min_sec` veritabanında ama Spark ortam değişkeninden okuyor~~ —
  **Aşama 6'da kapatıldı**: Spark açılışta `GET /api/settings` çağırıyor.
  Değer yine de DAG'e açılışta gömülür; panelden değişiklik ancak Spark
  yeniden başlayınca geçerli olur (bilinçli sınır)
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
- Frontend şablonu `sablon/` altında hazır: 11 ekran (canlı izleme, kameralar,
  kamera detay, olaylar, olay detay, bölgeler, analitik, ayarlar, kullanıcılar,
  sistem sağlığı, denetim kaydı) + `sentinel_control_system/DESIGN.md` renk ve
  tipografi jetonları (Material 3 şeması, koyu tema, Inter). Aşama 8'de
  tasarıma dokunulmadan veri bağlanacak; API uçları bu ekranların alanlarını
  karşılıyor mu, ekran ekran doğrulanmadı
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

- Canlı akışta kırmızı alarm gecikmesi **hâlâ ölçülmedi.** Aşama 6'da
  `/ws/alerts` uçtan uca çalıştı ve dosya kaynağında 13.9–54.8 sn ölçüldü,
  ama bu sayı hattın hızı değil: dosya kaynağında Spark oturumu olayın
  bitmesiyle değil akışın `_EOS` ile bitmesiyle kapanıyor. Gerçek değer için
  kameranın önünde gerçek bir olay gerekiyor
- `--kafka` açıkken FPS 36.5'ten 31.8'e düşüyor ama ölçülen `publish`
  aşaması 0.0 ms. Kaybın librdkafka'nın arka plan I/O iş parçacığından
  geldiği varsayıldı, doğrulanmadı. Çoklu kamerada (Aşama 10) tekrar ölçülmeli
- FIGHT ve LOITERING için seçilen `min_sec` değerleri (0.5 / 2.0) ölçüme
  değil akıl yürütmeye dayanıyor; bu olayları içeren klip yok
- `zone_01`'in sahte RUN'ı (35 vuruş, 1.80 sn) Spark'tan geçiyor. Süzgeç
  gürültüyü eler, yanlış kuralı düzeltmez — kök neden RUN kuralının kendisinde

Kapanan sorular:

- ~~Host'tan API'ye ~600 ms sabit taban~~ — **Aşama 8.1'de ölçüldü, taban
  yok.** 25 istekle host'tan: `/health` medyan 13.8 ms, `/api/cameras` 13.8,
  `/api/events?limit=20` 11.1, `/api/analytics/summary` 18.0; konteyner
  içinden `/health` 1.8 ms. Port yönlendirmesinin maliyeti ~12 ms. Aşama 5'in
  600 ms'lik ölçümü GPU'su yüklü makinede alınmıştı; panel için istek sayısı
  bir tasarım kısıtı değil. Canlı koşuda (8.6) tekrar bakılacak

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
