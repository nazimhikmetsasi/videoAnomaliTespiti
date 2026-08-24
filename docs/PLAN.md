# Video Tabanlı Anomali Tespiti ve Davranış Analizi Platformu (v2)

Bu belge projenin dondurulmuş mimari kararlarını ve aşama planını içerir.
Oturum sıfırlansa bile (`/clear`) çalışmaya buradan devam edilir.

- **Proje dizini:** `C:\Users\pc\OneDrive\Masaüstü\videoAnomaliTespiti`
- **Referans (v1, eski proje):** `C:\Users\pc\OneDrive\Masaüstü\projeler\VideoAnomalySystem`
- **Güncel durum:** `docs/DURUM.md`
- **Plan tarihi:** 2026-08-24

---

## 0. Amaç

Gözetim kameralarından gelen canlı video akışında normal dışı hareketleri
(düşme, koşma, yasaklı alan ihlali, kavga, şüpheli dolaşma) otonom olarak
saptayan; olayları web kontrol panelinde yöneten; operatöre Türkçe doğal dil
raporu sunan ve güvenlik personelinin telefonuna anlık bildirim ileten kurumsal
platform.

Bu proje, aynı geliştiricinin `VideoAnomalySystem` (v1) projesinin sıfırdan
yeniden tasarlanmış halidir. v1 çalışan bir tez projesidir; v2 onun ölçülen
zayıf noktalarını mimari düzeyde çözer.

---

## 1. v1 İncelemesi — Neyi Neden Değiştiriyoruz

v1 projesi 74 backend Python dosyası, 16 test içeriyor. Docker, Kafka, Spark,
PostgreSQL, MongoDB, LLM raporlama, FCM/Telegram bildirimi, JWT auth, bölge
öğrenme, ReID galerisi, homografi, ablation/pilot değerlendirme altyapısı
mevcut ve çalışır durumda.

Tespit edilen 13 zayıf nokta ve v2 karşılıkları:

| # | v1 sorunu | v1 kanıtı | v2 çözümü |
|---|---|---|---|
| 1 | Aynı kareye iki ayrı model çıkarımı | `pipeline.py:147` YOLOv8n detect, `pipeline.py:159` YOLOv8n-pose | Tek `yolov8s-pose` geçişi; pose modeli kutuyu zaten üretir |
| 2 | Düşük eşik + heuristik yama yığını | `YOLO_CONF_THRESHOLD=0.10`, `detector.py` merge/alan/en-boy filtreleri, `tracker.py` `_is_sane_bbox`/`_merge_overlaps`/`_soft_reacquire` (~250 satır) | Makul eşik + BoT-SORT; yamalar hiç doğmaz |
| 3 | Zayıf ReID (DeepSORT `embedder='mobilenet'`) | `tracker.py` DeepSort init | BoT-SORT: güçlü ReID + GMC (kamera hareketi telafisi) |
| 4 | Hız ham pikselde | `kinematics.py` `vx = dx/dt` | Hız ÷ bbox yüksekliği — derinlik ve kamera bağımsız |
| 5 | Keypoint titremesi filtresiz | `pose.py` ham landmark doğrudan türeve giriyor | One-Euro filtresi |
| 6 | CLAHE her karede yeniden yaratılıyor | `pipeline.py:142` döngü içinde `cv2.createCLAHE()` | Bir kez kurulur, yeniden kullanılır |
| 7 | Pose eşleşmezse bbox merkeziyle anomali üretiliyor | `pipeline.py:251-266`, omurga açısı 85.0 sabit veriliyor | Pose yoksa anomali üretilmez, sadece "takipte" gösterilir |
| 8 | Karar tamamen kural tabanlı | `motion_classifier.py` if/elif zinciri, 8 adet `.env` eşiği | Kural tabanı + TCN modeli hibrit karar |
| 9 | Eşikler `.env` içinde, değişiklik restart ister | 40+ eşik `.env`'de | PostgreSQL `detection_settings` + hot-reload |
| 10 | Panel canlı değil | `pipeline.py:329` diske JPEG, `LivePreview.jsx` 1500 ms polling = 0.67 FPS | WebSocket ikili kare akışı, 20–25 FPS |
| 11 | Overlay piksele yakılmış | `visualizer.py` çizimi `display` karesine gömüyor | Temiz kare + ayrı metadata JSON; çizim istemcide Canvas katmanlarında |
| 12 | Kanıt sadece tek JPEG | `frame_store.save_alert_snapshot` | Halka tampon → ±5 sn mp4 klip + en iyi kare |
| 13 | Çoklu kamera lineer ölçekleniyor | Kamera başına ayrı process ve model kopyası | Tek process, toplu (batch) çıkarım |

Ek yapısal sorun: `pipeline.py` 435 satırlık tek dev döngü. Test edilemez,
parça değiştirilemez. v2'de her aşama ayrı sınıf, her biri 150 satır altında,
ayrı test edilebilir.

### v1'den taşınacak iyi fikirler (kod değil, tasarım)

- Ablation / pilot değerlendirme koşum düzeni ve tez tabloları
- Evde / Koruma güvenlik modu (bildirim bastırma)
- Otomatik serbest bölge öğrenme
- Olay bazlı ReID (aynı kişi tekrar anomali yaparsa aynı varlık)
- LLM Türkçe rapor üretimi
- En iyi kare seçici (bildirimde net görüntü)
- Bilinen kişi listesi ile bildirim bastırma

---

## 2. Donanım ve Ortam (ölçüldü, 2026-08-24)

| Bileşen | Değer | Sonuç |
|---|---|---|
| GPU | NVIDIA RTX 3050 Laptop, 4096 MiB VRAM | `yolov8s-pose` FP16 tek kamera; çoklu kamerada `yolov8n-pose` |
| CUDA | Toolkit 12.1, sürücü 610.74 | cu121 wheel uyumlu |
| Kurulu torch | `2.13.0+cpu` — CUDA yok | cu121 derlemesiyle değiştirilecek |
| Python | 3.13.5 varsayılan, 3.11 de kurulu | venv **3.11** ile açılacak |
| Docker | 29.5.3, WSL `docker-desktop` durdurulmuş | Aşama 1'de başlatılacak |
| mediapipe | 1.0.1 mevcut | Kullanılmayacak (YOLOv8-pose tercih edildi) |

**Dağıtım kararı:** Windows'ta Docker'a GPU geçirmek (WSL2 +
nvidia-container-toolkit) zaman kaybıdır. `vision/` servisi host üzerinde
native venv'de çalışır ve Kafka'ya `localhost:9092` üzerinden bağlanır. Geri
kalan tüm servisler (PostgreSQL, MongoDB, Kafka, Zookeeper, Spark, FastAPI)
Docker'da yaşar. Sunucuya taşınırken `vision/` de container'a alınır.

## 3. Seçilen Teknoloji Yığını

**Görü ve çıkarım:** Python 3.11, OpenCV, Ultralytics YOLOv8s-pose (CUDA/FP16),
BoT-SORT (ReID + GMC), NumPy, One-Euro filtresi, PyTorch TCN

**Dağıtık akış:** Apache Kafka + Zookeeper (`anomaly-candidates`,
`anomaly-events`), Apache Spark Structured Streaming

**Depolama:** PostgreSQL + SQLAlchemy ORM (ilişkisel), MongoDB + PyMongo
(değişken yapılı zaman serisi)

**Backend:** FastAPI + Uvicorn (asenkron), WebSocket

**Raporlama ve bildirim:** Google Gemini Flash + deterministik Türkçe şablon
yedeği, Telegram Bot API (`sendPhoto`)

**Frontend:** React + Tailwind CSS (şablon kullanıcı tarafından sağlanacak),
Canvas API, Recharts

**Dağıtım:** Docker Compose

---

## 4. Uçtan Uca Veri Hattı

```
KAYNAK
  SourceManager: mp4 / webcam(0) / RTSP — tek arayüz
  CaptureThread (kamera başına) -> RingBuffer(300 kare, en eskiyi at)
        |
        | N kamera x 1 kare
        v
INFERENCE WORKER (tek process, GPU)
  1. Preprocess     CLAHE (bir kez kurulur) + letterbox 960x540
  2. PoseDetector   YOLOv8s-pose FP16, BATCH=N -> kutu + 17 keypoint
  3. Tracker        BoT-SORT + ReID + GMC     -> kalıcı track_id
  4. Smoother       One-Euro filtresi / keypoint
  5. FeatureEngine  ölçek-normalize kinematik + poz öznitelikleri
                    (30 kare pencere, bbox yüksekliğine bölünmüş)
  6. Decision       RuleEngine + TCNClassifier -> HybridArbiter -> aday olay
        |                              |
        | (A) aday olay JSON           | (B) temiz kare + metadata
        v                              v
KAFKA                            WebSocket
  anomaly-candidates               /ws/live/{cam}  ikili JPEG 20-25 FPS
  anomaly-events                   /ws/meta/{cam}  tracks/poses/zones JSON
        |                          -> Canvas katmanları istemcide çizer
        |                          -> SARI ön-alarm (filtrelenmemiş)
        v
SPARK STRUCTURED STREAMING
  window(3 sn, kayma 1 sn) x (camera, track, type) HAVING hits >= N
  tek kare gürültüsü elenir -> anomaly-events
        |
        v
EVENT WORKER (FastAPI async)
  PostgreSQL olay satırı
  MongoDB keypoint zaman serisi
  RingBuffer -> +-5 sn mp4 klip + en iyi kare JPEG
  Gemini -> Türkçe ihbar metni (şablon yedeği)
  WebSocket /ws/alerts -> KIRMIZI doğrulanmış alarm
  Telegram sendPhoto -> güvenlik personeli
```

### İki kademeli alarm

Spark mikro-toplu işlemesi 1–3 sn gecikme ekler. Bu yüzden:

1. **Sarı ön-alarm:** `vision/` servisi tespit anında doğrudan WebSocket'e
   basar. Operatör anında görür. Veritabanına yazılmaz, telefona gitmez.
2. **Kırmızı doğrulanmış alarm:** Spark penceresinden geçen olay
   veritabanına yazılır, LLM raporu üretilir, telefona bildirim gider.

Böylece yanlış alarm operatörü bezdirmez, gerçek olayda gecikme hissedilmez.

---

## 5. Klasör Yapısı

```
videoAnomaliTespiti/
├── docker-compose.yml         # postgres, mongo, kafka, zookeeper, spark, api
├── .env.example               # SADECE sırlar/bağlantı — eşikler veritabanında
├── pyproject.toml
├── README.md
│
├── docs/
│   ├── PLAN.md                # bu dosya
│   └── DURUM.md               # ilerleme takibi
│
├── infra/
│   ├── postgres/init.sql
│   ├── mongo/init.js
│   └── kafka/topics.sh
│
├── vision/                    # host'ta native venv (GPU)
│   ├── run.py                 # giriş noktası
│   ├── source.py              # mp4/webcam/RTSP + RingBuffer + yeniden bağlanma
│   ├── stages/
│   │   ├── preprocess.py      # CLAHE bir kez, letterbox
│   │   ├── pose_detector.py   # YOLOv8s-pose, batch, FP16
│   │   ├── tracker.py         # BoT-SORT sarmalayıcı
│   │   ├── smoother.py        # One-Euro
│   │   ├── features.py        # ölçek-normalize kinematik
│   │   └── decision.py        # RuleEngine + TCN + HybridArbiter
│   ├── rules/
│   │   ├── fall.py  run.py  zone.py  fight.py  loiter.py
│   ├── models/tcn.py          # keypoint dizisi sınıflandırıcı
│   ├── evidence.py            # halka tampon -> mp4 + en iyi kare
│   ├── publish.py             # Kafka + WebSocket yayını
│   └── settings_client.py     # API'den eşik çeker, hot-reload
│
├── api/
│   ├── main.py
│   ├── db/{postgres.py, mongo.py, models.py}
│   ├── routers/{auth,cameras,zones,settings,events,analytics}.py
│   ├── ws/{live.py, meta.py, alerts.py, manager.py}
│   └── workers/{consumer.py, llm.py, notify.py}
│
├── stream/spark_job.py
├── frontend/                  # kullanıcının Tailwind şablonu
├── eval/                      # pilot değerlendirme + ablation + gecikme
├── storage/{clips,frames,gallery}
└── tests/
```

---

## 6. Veritabanı Şeması

### 6.1 PostgreSQL

**users**

| sütun | tip | not |
|---|---|---|
| id | SERIAL PK | |
| username | VARCHAR(50) UNIQUE | |
| password_hash | VARCHAR(255) | bcrypt |
| full_name | VARCHAR(100) | |
| role | VARCHAR(20) | admin / operator / viewer |
| telegram_chat_id | VARCHAR(50) NULL | kişisel bildirim hedefi |
| is_active | BOOLEAN | |
| last_login | TIMESTAMPTZ NULL | |
| created_at | TIMESTAMPTZ | |

**cameras**

| sütun | tip | not |
|---|---|---|
| id | SERIAL PK | |
| name | VARCHAR(100) | "Ana Giriş" |
| source | TEXT | `0` \| `data/test.mp4` \| `rtsp://...` |
| source_type | VARCHAR(20) | webcam / file / rtsp |
| location | VARCHAR(150) | |
| width, height | INT | 960 / 540 |
| target_fps | INT | 25 |
| is_active | BOOLEAN | pipeline bu kamerayı işlesin mi |
| status | VARCHAR(20) | online / offline / error |
| last_seen_at | TIMESTAMPTZ NULL | kalp atışı |
| created_at | TIMESTAMPTZ | |

**zones**

| sütun | tip | not |
|---|---|---|
| id | SERIAL PK | |
| camera_id | INT FK → cameras ON DELETE CASCADE | |
| name | VARCHAR(100) | |
| zone_type | VARCHAR(30) | forbidden / restricted_hours / direction |
| polygon | JSONB | `[[x,y],...]` **0–1 normalize** |
| direction_vector | JSONB NULL | ters yön tespiti için `[dx,dy]` |
| active_from, active_to | TIME NULL | saat bazlı ihlal |
| is_active | BOOLEAN | |
| created_by | INT FK → users | |
| created_at | TIMESTAMPTZ | |

Poligon piksel değil 0–1 normalize saklanır; kamera çözünürlüğü değişince
koordinat bozulmaz.

**detection_settings** (`camera_id NULL` = global varsayılan)

| sütun | tip | varsayılan | açıklama |
|---|---|---|---|
| id | SERIAL PK | | |
| camera_id | INT FK UNIQUE NULL | | |
| pose_conf | NUMERIC(3,2) | 0.35 | YOLOv8-pose güven eşiği |
| track_conf | NUMERIC(3,2) | 0.30 | BoT-SORT eşiği |
| fall_spine_deg | NUMERIC(5,2) | 45.0 | omurga-dikey açı |
| fall_norm_vy | NUMERIC(6,3) | 1.20 | dikey hız / bbox yüksekliği (1/sn) |
| run_norm_speed | NUMERIC(6,3) | 1.80 | yatay hız / bbox yüksekliği (1/sn) |
| loiter_sec | INT | 30 | bölgede kalış süresi |
| fight_proximity | NUMERIC(4,2) | 1.20 | ikili mesafe / bbox yüksekliği |
| window_frames | INT | 30 | kayan pencere |
| spark_window_sec | INT | 3 | |
| spark_min_hits | INT | 5 | |
| tcn_min_conf | NUMERIC(3,2) | 0.60 | modele güvenme eşiği |
| updated_by | INT FK → users NULL | | |
| updated_at | TIMESTAMPTZ | | |

Tüm hız/mesafe eşikleri **bbox yüksekliğine normalize** birimdedir. İnsan boyu
gerçek dünyada sabit olduğu için bu birim kamera açısından, çözünürlükten ve
kişinin uzaklığından bağımsızdır. v1'in en büyük kalibrasyon sorunu buydu.

**events**

| sütun | tip | not |
|---|---|---|
| id | BIGSERIAL PK | |
| camera_id | INT FK | |
| zone_id | INT FK NULL | ihlal ise |
| anomaly_type | VARCHAR(30) | FALL / RUN / ZONE_VIOLATION / RUN_ZONE / FIGHT / LOITERING / WRONG_DIRECTION |
| track_ids | INT[] | kavgada iki kişi olabilir |
| confidence | NUMERIC(4,3) | |
| severity | VARCHAR(10) | low / medium / high / critical |
| decided_by | VARCHAR(10) | rule / model / hybrid |
| started_at, ended_at | TIMESTAMPTZ | |
| duration_ms | INT | |
| frame_path | TEXT | en iyi kanıt karesi |
| clip_path | TEXT NULL | ±5 sn mp4 |
| llm_report_tr | TEXT | Türkçe ihbar metni |
| mongo_ref | VARCHAR(24) | pose_sequences ObjectId |
| status | VARCHAR(20) | new / acknowledged / false_positive / resolved |
| acked_by | INT FK → users NULL | |
| acked_at | TIMESTAMPTZ NULL | |
| created_at | TIMESTAMPTZ | |

`decided_by` sütunu tez için kritiktir: kararı kural motorunun mu, TCN
modelinin mi verdiği buradan okunur ve ablation tablosu bundan üretilir.

Indexler: `(camera_id, started_at DESC)`, `(anomaly_type)`, `(status)`,
`(decided_by)`, `(started_at DESC)`

**notifications** — `id, event_id FK, channel (telegram/fcm), target, status
(sent/failed), error TEXT, sent_at`

**audit_log** — `id, user_id FK, action, entity, entity_id, payload JSONB, ip,
created_at`

`false_positive` işaretlenen olaylar ileride eşik otomatik kalibrasyonu ve TCN
eğitimi için negatif örnek kümesi olur.

### 6.2 MongoDB

**`pose_sequences`** — olay başına ham iskelet zaman serisi

```
{
  _id: ObjectId,
  event_id: 1042,                    // PostgreSQL mantıksal FK
  camera_id: 3,
  track_id: 17,
  anomaly_type: "FALL",
  fps: 25,
  frames: [
    { idx: 0, ts: ISODate, bbox: [x1,y1,x2,y2],
      kp:          [[x,y,conf], ... 17 adet],
      kp_smoothed: [[x,y,conf], ... 17 adet] }
  ],
  normalization: { origin: "mid_hip", scale: "bbox_height" },
  created_at: ISODate
}
```

Index: `{event_id:1}`, `{camera_id:1, created_at:-1}`, TTL `created_at` 90 gün.

**`telemetry`** — reddedilenler dahil tüm aday pencereler

```
{
  _id, camera_id, track_id, window_start, window_end,
  metrics: {
    norm_speed: [...], norm_vy: [...], spine_angle: [...],
    knee_angle: [...], aspect: [...]
  },
  rule_verdict:  { type: "FALL", score: 0.87, thresholds_used: {...} },
  model_verdict: { type: "FALL", probs: {...} },
  arbiter: "rule" | "model" | "agree",
  spark_verdict: "confirmed" | "filtered_noise"
}
```

Index: `{camera_id:1, window_start:-1}`, TTL 30 gün.

Bu koleksiyon TCN modelinin eğitim veri setidir. Sistem çalıştıkça kendi
eğitim verisini biriktirir — Aşama 9'un girdisi buradan gelir.

**`camera_health`** — `{camera_id, ts, fps_actual, dropped, infer_ms, gpu_mem,
queue_depth}`, TTL 7 gün. Panelde performans grafiğinin kaynağı.

**Bölünme kuralı:** sorgulanan ve ilişkilendirilen veri PostgreSQL'e; hacimli,
değişken şemalı, yalnızca olay detayında okunan veri MongoDB'ye.

---

## 7. Aşama Planı

Her aşama sonunda: dur, `docs/DURUM.md` güncelle, commit mesajı ver.
Kullanıcı commit atar, `/clear` çeker, sonraki aşamadan devam edilir.

### Aşama 0 — Ortam Hazırlığı
- `git init`, `.gitignore`, `README.md`
- Python 3.11 venv
- `torch` cu121 kurulumu (mevcut `+cpu` derlemesi değiştirilecek)
- `ultralytics`, `opencv-python`, `numpy` kurulumu
- `yolov8s-pose.pt` indirimi
- GPU doğrulama betiği: `torch.cuda.is_available()` ve tek kare çıkarım süresi
- **Onay kriteri:** GPU'da `yolov8s-pose` çalışıyor, kare başı ms ölçülmüş

### Aşama 1 — Altyapı
- `docker-compose.yml`: postgres, mongo, zookeeper, kafka, spark, api
- `infra/postgres/init.sql`: tüm tablolar, indexler, admin tohum kaydı
- `infra/mongo/init.js`: koleksiyonlar, indexler, TTL
- `infra/kafka/topics.sh`: topic oluşturma
- `.env.example`
- **Onay kriteri:** `docker compose up -d` tüm servisler healthy, tablolar ve
  indexler yerinde

### Aşama 2 — Kaynak ve Görü Çekirdeği
- `source.py`: mp4 / webcam / RTSP tek arayüz, halka tampon (en eskiyi at),
  üstel geri çekilmeli yeniden bağlanma
- `stages/preprocess.py`: CLAHE bir kez kurulur, letterbox
- `stages/pose_detector.py`: YOLOv8s-pose, FP16, toplu çıkarım
- `stages/tracker.py`: BoT-SORT sarmalayıcı (ReID + GMC)
- **Onay kriteri:** test videosu ve webcam'de kutu + iskelet + kalıcı ID;
  FPS raporu alınmış

### Aşama 3 — Öznitelik ve Kural Motoru
- `stages/smoother.py`: One-Euro filtresi
- `stages/features.py`: ölçek-normalize kinematik (hız ÷ bbox yüksekliği),
  omurga açısı, diz açısı, en-boy oranı, 30 kare pencere
- `rules/fall.py`, `rules/run.py`, `rules/zone.py`, `rules/loiter.py`,
  `rules/fight.py`
- Pose yoksa anomali üretilmez kuralı
- **Onay kriteri:** pilot kliplerde doğru aday olay; ilk precision/recall
  ölçümü tabloda

### Aşama 4 — Kafka ve Spark
- `publish.py`: Kafka producer
- `stream/spark_job.py`: Structured Streaming, kayan pencere filtresi
- **Onay kriteri:** tek kare gürültüsü eleniyor, gerçek olay geçiyor;
  öncesi/sonrası alarm sayısı karşılaştırma tablosunda

### Aşama 5 — Veri Katmanı ve API
- SQLAlchemy modelleri, Alembic, PyMongo bağlantısı
- JWT auth, CRUD uçları: cameras, zones, detection_settings, events, analytics
- `settings_client.py`: eşik hot-reload (pipeline yeniden başlatılmadan)
- `workers/consumer.py`: `anomaly-events` → PostgreSQL + MongoDB + kanıt
- **Onay kriteri:** Swagger'dan tüm uçlar çalışıyor; panelden eşik değişince
  pipeline restart'sız uyum sağlıyor

### Aşama 6 — Canlı Görüntü
- `ws/live.py`: ikili JPEG kare akışı, adaptif kalite
- `ws/meta.py`: tracks / poses / zones / ön-alarm JSON akışı
- `evidence.py`: halka tampon → ±5 sn mp4 klip + en iyi kare
- **Onay kriteri:** tarayıcıda 20+ FPS, uçtan uca gecikme 300 ms altında,
  olay klibi oynatılabiliyor

### Aşama 7 — LLM ve Telegram
- `workers/llm.py`: Gemini Flash ile Türkçe ihbar metni + deterministik şablon
  yedeği
- `workers/notify.py`: Telegram `sendPhoto`, yeniden deneme, hız sınırı
- **Onay kriteri:** telefona fotoğraflı Türkçe ihbar geliyor; LLM API çökse
  bile alarm zinciri sürüyor

### Aşama 8 — Panel
- Kullanıcının Tailwind şablonu `frontend/` içine yerleştirilir
- **Tasarıma dokunulmaz**, yalnızca veri bağlanır
- Canlı grid, Canvas katmanları (kutu / iskelet / bölge / ID aç-kapa),
  ROI poligon çizimi, eşik ayar formu, olay geçmişi ve filtreler,
  Recharts yoğunluk grafikleri
- **Onay kriteri:** uçtan uca demo

### Aşama 9 — TCN Modeli ve Yeni Sınıflar
- `telemetry` koleksiyonundan etiketli veri seti üretimi
- `models/tcn.py`: keypoint dizisi sınıflandırıcı eğitimi
- `HybridArbiter`: model güveni `tcn_min_conf` altındaysa kural motoruna düşer
- FIGHT ve LOITERING sınıflarının açılması
- **Onay kriteri:** `decided_by` üzerinden kural / model / hibrit ablation
  tablosu

### Aşama 10 — Ölçek ve Tez
- Çoklu kamera toplu çıkarım (tek process, tek model, N kare)
- 4 kamera yük testi
- Ablation raporu, gecikme dağılımı, tez tabloları
- README ve mimari dokümantasyon
- **Onay kriteri:** 4 kamera 8 saat kesintisiz çalışma

---

## 8. Ölçülebilir Hedefler (v1 karşılaştırması)

| Metrik | v1 | v2 hedefi |
|---|---|---|
| Panel canlı FPS | 0.67 | ≥ 20 |
| GPU çıkarım / kare | 2 model geçişi | 1 geçiş, model `n` → `s` |
| Eşik değişimi | `.env` düzenle + restart | panelden anında |
| Kanıt | 1 JPEG | mp4 klip + JPEG |
| Anomali sınıfı sayısı | 4 | 7 |
| Eşik taşınabilirliği | kameraya bağımlı (piksel) | ölçek-normalize |
| 4 GB VRAM'de kamera | 1–2 | 3–4 |
| En büyük dosya | `pipeline.py` 435 satır | aşama başına < 150 satır |

---

## 9. Bilinen Riskler

1. **4 GB VRAM sınırı.** `yolov8s-pose` FP16 yaklaşık 1.5 GB kullanır. BoT-SORT
   ReID modeli ek yük getirir. Çoklu kamerada `yolov8n-pose`'a düşülür. Aşama 2
   sonunda ölçülüp karar verilir.
2. **BoT-SORT ReID kalitesi ölçülmeli.** Ultralytics varsayılanı v1'in
   mobilenet'inden iyi olmalı ama doğrulanmadan kabul edilmeyecek; Aşama 2'de
   ID değişim sayısı sayılacak.
3. **Kavga tespiti kural tabanlı zordur.** İkili mesafe + karşılıklı uzuv hızı
   heuristiği ile yaklaşık %70 beklenir. Gerçek çözüm Aşama 9'daki TCN
   modelidir.
4. **Spark, dakikada birkaç olay için ağır bir araçtır.** Aynı filtre yaklaşık
   20 satır Python ile yazılabilir. Tez gereksinimi olduğu için bilinçli
   tutuluyor; yatay ölçeklenme ve tekrar oynatma avantajı gerçektir.
5. **RTSP kopması kaçınılmazdır.** Halka tampon ve üstel geri çekilmeli yeniden
   bağlanma Aşama 2'de zorunlu, sonraya bırakılmaz.
6. **TCN için etiketli veri gerekir.** Aşama 9'a kadar `telemetry` koleksiyonu
   birikmeli. Aşama 3'ten itibaren her koşu veri toplar.

---

## 10. Çalışma Protokolü

- Her aşama sonunda çalışma durur.
- `docs/DURUM.md` güncellenir.
- Commit mesajı kullanıcıya verilir; commit'i kullanıcı atar.
- Kullanıcı `/clear` çeker; sonraki oturum `docs/PLAN.md` ve `docs/DURUM.md`
  okunarak kaldığı yerden devam eder.
- Önemsiz olmayan her mantık için çalıştırılabilir bir kontrol bırakılır
  (`assert` tabanlı öz kontrol veya küçük `test_*.py`).
- Arayüz tasarımına dokunulmaz; şablon kullanıcı tarafından sağlanır.
