# Proje Durumu

Bu dosya her aşama sonunda güncellenir. Yeni oturum açıldığında önce
`docs/PLAN.md` sonra bu dosya okunur ve kaldığı yerden devam edilir.

**Son güncelleme:** 2026-08-24

---

## Şu an neredeyiz

**Aşama 1 — Altyapı tamamlandı.** PostgreSQL, MongoDB ve Kafka Docker'da
ayakta; şema, indexler, TTL'ler ve topic'ler yerinde; `scripts/check_infra.sh`
tüm kontrolleri geçiyor. Sıradaki iş Aşama 2 (kaynak ve görü çekirdeği).

---

## Aşama durumu

| # | Aşama | Durum |
|---|---|---|
| — | Plan ve mimari (`docs/PLAN.md`) | Tamamlandı |
| 0 | Ortam hazırlığı | Tamamlandı |
| 1 | Altyapı (Docker, veritabanı şeması) | Tamamlandı |
| 2 | Kaynak ve görü çekirdeği | Sırada |
| 3 | Öznitelik ve kural motoru | Bekliyor |
| 4 | Kafka ve Spark | Bekliyor |
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

## Bir sonraki adım

Aşama 2 — Kaynak ve Görü Çekirdeği:

1. `vision/source.py`: mp4 / webcam / RTSP tek arayüz, halka tampon
   (300 kare, en eskiyi at), üstel geri çekilmeli yeniden bağlanma
2. `vision/stages/preprocess.py`: CLAHE bir kez kurulur, letterbox 960x540
3. `vision/stages/pose_detector.py`: YOLOv8s-pose, FP16 (`quantize=16`),
   toplu çıkarım
4. `vision/stages/tracker.py`: BoT-SORT sarmalayıcı (ReID + GMC)
5. Test videoları v1 projesinden alınacak (aşağıdaki yol)

**Onay kriteri:** test videosu ve webcam'de kutu + iskelet + kalıcı ID;
gerçek döngü FPS raporu ve ID değişim sayısı ölçülmüş.

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

---

## Açık sorular

- BoT-SORT ReID kalitesi ölçülmedi (Aşama 2'de ID değişim sayısı sayılacak)
- Gerçek döngüde (takip + öznitelik + yayın dahil) FPS ne olacak (Aşama 2)
- Frontend Tailwind şablonu henüz sağlanmadı (Aşama 8'e kadar gerekmiyor)
- Host'ta çalışan `vision/` gerçekten `localhost:9092`'ye yazabiliyor mu —
  port açık, ama uçtan uca producer denemesi Aşama 4'te yapılacak

Kapanan soru: 4 GB VRAM'de `yolov8s-pose` sığıyor mu — evet, 49 MiB tepe
kullanım. Çoklu kamera için de rahat yer var.

---

## Test videoları

v1 projesinde hazır pilot videolar var, Aşama 2'de kullanılacak:
`C:\Users\pc\OneDrive\Masaüstü\projeler\VideoAnomalySystem\datasets\pilot\videos`
(`normal_01`, `run_01`, `fall_01`, `zone_01`, `mixed_01`, `police_run`)
