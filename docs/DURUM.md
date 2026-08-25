# Proje Durumu

Bu dosya her aşama sonunda güncellenir. Yeni oturum açıldığında önce
`docs/PLAN.md` sonra bu dosya okunur ve kaldığı yerden devam edilir.

**Son güncelleme:** 2026-08-24

---

## Şu an neredeyiz

**Aşama 2 — Görü çekirdeği tamamlandı.** Kaynak (mp4/webcam/RTSP), ön işleme,
YOLOv8s-pose çıkarımı ve BoT-SORT takibi çalışıyor. Altı pilot klipte ve
webcam'de kutu + iskelet + kalıcı ID doğrulandı; gerçek döngü FPS'i ve ID
kararlılığı ölçüldü. Sıradaki iş Aşama 3 (öznitelik ve kural motoru).

---

## Aşama durumu

| # | Aşama | Durum |
|---|---|---|
| — | Plan ve mimari (`docs/PLAN.md`) | Tamamlandı |
| 0 | Ortam hazırlığı | Tamamlandı |
| 1 | Altyapı (Docker, veritabanı şeması) | Tamamlandı |
| 2 | Kaynak ve görü çekirdeği | Tamamlandı |
| 3 | Öznitelik ve kural motoru | Sırada |
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

## Bir sonraki adım

Aşama 3 — Öznitelik ve Kural Motoru:

1. `vision/stages/smoother.py`: One-Euro filtresi (keypoint titremesi)
2. `vision/stages/features.py`: hız ÷ bbox yüksekliği, omurga açısı, diz açısı,
   en-boy oranı, 30 kare kayan pencere
3. `vision/rules/`: `fall.py`, `run.py`, `zone.py`, `loiter.py`, `fight.py`
4. Pose yoksa anomali üretilmez kuralı
5. Eşikler şimdilik sabit; veritabanından okuma Aşama 5'te

Girdi hazır: `Track` sınıfı `track_id`, `bbox`, `conf`, `keypoints (17,3)` ve
`height` (normalizasyon birimi) taşıyor.

**Onay kriteri:** pilot kliplerde doğru aday olay; ilk precision/recall
ölçümü tabloda.

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

---

## Açık sorular

- ReID kalitesi kalabalık/kesişmeli sahnede ölçülmedi — pilot klipler yeterince
  zor değil, `--no-reid` ile ID sayıları hiç değişmedi
- Kadrajdan çıkıp geri giren kişi yeni ID alıyor. Olay bazlı ReID galerisi
  (aynı kişiyi tekrar bağlama) Aşama 9'a bırakıldı
- Çoklu kamera toplu çıkarımı gerçek FPS'te ölçülmedi (Aşama 10). Temiz
  ölçümde toplu çıkarım kare başına maliyeti belirgin düşürdü, ama tek
  process içinde N kamerayla tekrar ölçülmeli
- Frontend Tailwind şablonu henüz sağlanmadı (Aşama 8'e kadar gerekmiyor)
- Host'ta çalışan `vision/` gerçekten `localhost:9092`'ye yazabiliyor mu —
  port açık, ama uçtan uca producer denemesi Aşama 4'te yapılacak

Kapanan sorular:

- 4 GB VRAM'de `yolov8s-pose` sığıyor mu — evet, 49 MiB tepe kullanım
- Gerçek döngüde FPS ne olacak — 37–54 FPS (4K olmayan kliplerde), webcam 29.5
- BoT-SORT ReID çalışıyor mu — evet, 128 boyutlu görünüm vektörü üretiliyor;
  kalitesi ise henüz kanıtlanmadı (yukarıdaki açık soru)

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
