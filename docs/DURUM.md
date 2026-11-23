# Proje Durumu

Bu dosya her aşama sonunda güncellenir. Yeni oturumda okuma sırası: bu
dosya → `docs/YOL_HARITASI.md` (kalan işin sırası ve kabul ölçütleri) →
başlanacak aşamanın plan dosyası. Aşama 0–12.6'nın ölçümleri ve bulguları
`docs/DURUM_ARSIV.md`'de, mimari `docs/PLAN.md`'de.

**Son güncelleme:** 2026-11-23

---

## Şu an neredeyiz

**Aşama 13.1 tamamlandı; sıradaki iş 13.2 (hızlı düzeltmeler).**
(2026-11-23)

Spark akışının iki sessiz olay kaybı giderildi ve canlı deneylerle
doğrulandı (ayrıntı aşağıda "Aşama 13.1 sonucu"):

- **A1 — sessiz sahnede tek düşme:** önce 45 sn olay yok; şimdi 7,5–7,9 sn
- **A2 — çoklu kamerada kayıp:** önce `fall_01` adaylarının %80'i,
  `run_01`'inkilerin %75'i geç sayılıp atılıyordu; şimdi 0
- **Alarm gecikmesi:** 13,99 → **7,58 sn** (medyan, 11/11 düşme)
- Yolda bulunan üçüncü kök neden: Spark'ın varsayılan 200 shuffle bölümü
  her yığını 4–5 sn yapıyordu; 2 bölümle < 1 sn

`docs/TEZ.md` §3.7 yeni sayılarla yazıldı. §3.5'in (8 saatlik koşu) olay
sayıları hâlâ geçersiz; düzeltilmiş sayılar 24 saatlik koşudan (18) gelecek.

**Açık kritik bulgu — canlı kamerada doğruluk kare hızına bağlı (13.3).**
Kural pencereleri (`fall.py`, `run.py`, `zone.py`, `loiter.py`,
`features.py`), TCN girdisi (50 kare) ve izleyici tamponu (`track_buffer`,
Ultralytics 8.4'te FPS'e göre ölçeklenmiyor) kare sayısıyla tanımlı.
Çevrimdışı değerlendirme her kareyi işler (25–30 FPS, 50 kare = 2 sn); tam
yığında canlı kamera ~10 FPS'te çalışır ve aynı pencere ~5 sn'ye uzar.
**Koddan çıkarım**; büyüklüğü 13.3'ün ilk adımında alt örneklenmiş
değerlendirmeyle ölçülecek.

**Çalışma ortamı notları:**

- Proje dizini: `C:\Users\pc\OneDrive\Masaüstü\projeler\videoAnomaliTespiti`
- Terminal bazen cmd.exe, bazen Windows PowerShell 5.1: komutlar
  zincirlenmeden (`;`, `&&` yok), her biri ayrı satırda çalıştırılır.
- Ölçümden önce GPU'yu kullanan oyun / tarayıcı kapatılır: 13.1'de açık
  kalan bir oyun görü FPS'ini üçte bire düşürdü ve bir FPS karşılaştırmasını
  geçersiz kıldı.
- `api/` değiştiğinde API imajı yeniden derlenir
  (`docker compose up -d --build api`); konteyner kodu imajın içindedir,
  `stream/` ise bağlanmış klasördür, yeniden başlatmak yeter.

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
| 11 | ReID ölçümü ve FIGHT kök nedeni | Tamamlandı — ReID ölçüldü (F1 0.15), hatta bağlanmadı; FIGHT duyarlılığı 0.07 → 0.80 |
| 12 | İşletim sağlamlaştırma | Tamamlandı (12.1–12.6) |
| 13 | Bütünsel inceleme ve düzeltmeler | 13.0, **13.1 tamam** — sıradaki 13.2 (`docs/YOL_HARITASI.md`) |
| 14–19 | Saha verisi, olay doğrulaması, yüz tanıma, hız, kamera geometrisi, 24 sa koşu, tez | Planlandı (`docs/YOL_HARITASI.md`) |

---

## Aşama 0–12.6 sonuçları

Ölçümler, kök nedenler ve plandan sapmalar: `docs/DURUM_ARSIV.md`.

---

## Aşama 13 — Bütünsel inceleme (2026-11-10)

Proje baştan, koddan okundu (`api/`, `vision/`, `stream/`, `models/`,
`frontend/js/`, `infra/`, `docker-compose.yml`). Bulgular, kanıt düzeyleri
(ölçüldü / koddan / hipotez) ve düzeltme tasarımı `docs/ASAMA13_PLAN.md`'de;
burada yalnızca kayıt.

### Ölçülenler

| bulgu | ölçüm |
|---|---|
| A1 — sessiz sahnede tek düşme | 3 FALL adayı, sonra sessizlik: **45 sn olay yok**; ilgisiz tek aday basılınca 5,3 sn ve 6,7 sn sonra geldi (iki bağımsız koşu) |
| A2 — çoklu kamerada kayıp, gerçek veri | 8 saatlik koşuda `fall_01` ve `run_01` ilk ~20 dk'dan sonra **7 saat sıfır olay**; `zone_01` saatte ~60 |
| A2 — kontrollü deney | 3 dosya kamerası, 4 dk: zone_01 (25 FPS) ortak saati sürükledi; fall_01 adaylarının %80'i, run_01'inkilerin %75'i su işaretinin altında (anlık yaklaşım, üst sınır) |
| C1 — sağlık sorgusu | 1 haftalık sentetik veride (483.840 belge) **445 ms → 1 ms**; dizinle eşleşen sıralama `DISTINCT_SCAN`'e geçiyor |

### Neden şimdiye kadar görülmedi

Bütün ölçümler döngüdeki kliplerle yapıldı: sürekli aday geldi, su işareti
hep ilerledi (A1 gizlendi). `scripts/soak_test.py` yalnız **toplam** olay
sayısını izliyordu; toplam, tek kamera sayesinde düzgün arttı (A2
gizlendi). 12.4'teki 13,99 sn gecikmesi de büyük olasılıkla A1'in ürünü:
her düşme, su işaretini ilerletecek bir sonraki klip döngüsünü bekledi
(7,9 sn döngü + 5 sn taban ≈ 14 sn) — hipotez. **13.1'de ölçüldü: kısmen
doğru.** Gecikmenin bir kaynağı A1'di, öteki Spark'ın 200 shuffle bölümü;
ikisi giderilince 7,58 sn.

### Deney betikleri depoda

`eval/stream_probe.py` — `tek-dusme` ve `saat-kaymasi`. Çıkış kodu hatayı
kodlar; bugün `tek-dusme` 1 döner, 13.1'den sonra 0 dönmeli. Veritabanına
dokunmazlar.

---

## Aşama 13.0 sonucu — belge düzeni (2026-11-23)

- Aşama 0–12.6 sonuçları `docs/DURUM_ARSIV.md`'ye **aynen** taşındı
  (2980 satır, satır satır denetlendi); bu dosya birkaç yüz satıra indi
- Kalan iş `docs/YOL_HARITASI.md`'de sıralandı: 13.0–19, her aşamanın
  kabul ölçütü ve commit mesajıyla. Yeni aşamalar: **13.3 zaman tabanlı
  pencereleme** ve **14.5 olay doğrulaması**; yüz tanıma (Faz 2) artık
  kapsamda (15)
- Açık sorular ayıklandı, her birine kapatılacağı aşama yazıldı
- Plan belgelerinin ve iki kod yorumunun dili sadeleştirildi

---

## Aşama 13.1 sonucu — akış doğruluğu (2026-11-23)

Uygulama sözleşmesi `docs/ASAMA13_1_PLAN.md`. Yazılan:

- ortak duvar saati: `Candidate.event_time`; `CameraPipeline.consume()`
  kare başına bir kez `time.time()` atar. Süre ölçütü yine sahne zamanı `ts`
- kamera başına saniyede bir `_TICK` nabzı (`--tick-sec`, 0 = kapalı)
- Spark: iç tipler toplama sütunu `internal` ile çıkıştan elenir; gelecek
  tarihli ret (`SPARK_FUTURE_SEC` 30); tetik 1 sn; shuffle bölümü 2;
  `AGG_VERSION` 4
- değerlendirme yalıtımı: `spark-eval` servisi (`--profile eval`),
  `eval-candidates` / `eval-events` konuları
- kamera başına aday sayacı sağlık belgesinde; `soak_test.py` kamera
  başına aday / olay artışı ve "aday üretiyor, olay üretmiyor" uyarısı
- `eval/stream_probe.py gelecek` deneyi

Testler: 252 geçti, 7 atlandı.

### Ölçümler (ana dizin, Docker yığını, 2026-11-23)

| deney | önce | sonra |
|---|---|---|
| A1 — sessiz sahnede tek düşme (`stream_probe tek-dusme`) | nabız kapalı: 45 sn olay yok, ilgisiz aday gelince 7,7 sn sonra (çıkış 1) | nabız açık: **7,5 / 7,7 / 7,9 sn** (çıkış 0) |
| gelecek tarihli ret (`stream_probe gelecek`, +3600 sn) | — | ret çalışıyor; ardından düşme 7,8 sn'de (çıkış 0) |
| A2 — 3 dosya kamerası, 280 sn (`saat-kaymasi`) | `fall_01` adaylarının %80'i, `run_01`'inkilerin %75'i geç | geç aday **0**; Spark olayı fall_01 10, run_01 13, zone_01 8 |
| tespit → alarm (`latency_watch`, `fall_01` gerçek zamanlı) | 13,99 sn (12.4, n=4) | **7,58 sn** medyan, 7,23–8,09 (n=11, 11 düşmenin 11'i) |
| değerlendirme yalıtımı (`spark-eval` + `spark_eval --from-cache`) | canlı su işaretini ~1,4 sa ileri itiyordu | Aşama 4 tablosu birebir (F1 0,50 → 0,60); hemen ardından canlı `tek-dusme` 9,1 sn (çıkış 0) |
| 30 dk kısa koşu, 3 kamera (`soak_test`) | 8 sa koşuda iki kamera 7 sa sıfır olay | kamera başına olay artışı fall_01 72, run_01 74, zone_01 35; uyarı yok; toplam FPS 29,3 sabit, düşen kare 0 |
| kap ↔ Spark konteyneri saat kayması | — | 0,32 sn |

### Yolda bulunan üçüncü kök neden: 200 shuffle bölümü

İlk A1 koşusu düzeltmeyle geçti ama olay **15,2 sn**'de geldi, beklenen
5–7 değil. Spark kayıtları: her mikro-yığın 4–5 sn sürüyor ve tetik
aralığını (1 sn) aşıyordu; Spark sürekli **~%294 CPU** yakıyordu. Sebep
Spark'ın varsayılan `spark.sql.shuffle.partitions = 200`'ü: durumlu
toplama, `local[2]`'de her yığında 200 görev koşuyordu. Nabız Spark'a her
saniye veri getirdiği için bu maliyet artık sürekliydi.

Ayrı bir test konteyneriyle (`--conf spark.sql.shuffle.partitions=2`,
ayrı checkpoint) ölçüldü: yığın < 1 sn, CPU **~%68**, A1 olayı 15,2 →
**7,5–7,9 sn**. Ayar `stream/spark_job.py`'ye kondu; bölüm sayısı
checkpoint'e yazıldığı için `AGG_VERSION` 4. 12.4'te "ayrıştırılmadı"
denen ~9 sn'lik Spark payı buydu.

### Nabzın maliyeti

| durum | Spark CPU |
|---|---|
| boşta (kamera yok) | ~%0,5 |
| yalnız nabız (aday üretmeyen tek kamera) | ~%33–42 |
| 3 dosya kamerası, adaylarla | ~%45–77 (nabız açık / kapalı ayırt edilmedi) |

Görü FPS'ine etkisi **ölçülemedi**: aynı ayarla ardışık koşularda toplam
FPS 36,3 → 24,9 → 11,8 → 11,3 → 11,2'ye kaydı. Sebep sonradan bulundu:
ölçüm sırasında GPU'da bir oyun açıktı (GPU %51, 87 °C, 3,3 GB). Oyun
kapatılınca 3 kamera 30 dakika boyunca 29,3 FPS'te sabit kaldı. Nabzın
FPS etkisi temiz koşullarda 16'da yeniden ölçülecek.

### Yolda bulunan diğer arızalar

1. **Veritabanındaki kamera kaynakları eski dizini gösteriyordu.**
   `scripts/seed_pilot.py` mutlak yol yazıyor; proje 2026-11'de
   `projeler\` altına taşınınca 6 dosya kamerası açılamadı ("kaynak
   açılamadı"). Yerel veritabanında yollar yeni dizine çevrildi (6 satır);
   kalıcı çözüm 13.2'de (göreli yol).
2. **API konteyneri eski koddu.** `api/` imaja gömülü (`build: ./api`);
   yeni `candidates` alanı imaj yeniden derlenene kadar dönmedi. Derleme
   ilk denemede Docker Hub TLS zaman aşımına düştü, ikincide geçti.
3. Docker Desktop ölçüm sırasında bir kez kapandı;
   `docker desktop start` ile açıldı, yığın kendiliğinden kalktı.

### Sınırlar

- Ölçümler gerçek zamanlı akıtılan dosya kliplerle; kameranın önünde
  gerçek bir olayla gecikme hâlâ ölçülmedi (14).
- Bir süreç kapanırken attığı `_EOS` su işaretini ~13 sn ileri iter; aynı
  anda çalışan **başka** bir görü sürecinin adayları o süre geç sayılır.
  Tek süreçli dağıtımda geçerli değil.
- `Zone.active_at` dosya kaynağında hâlâ sahne saniyesiyle çağrılıyor
  (ASAMA13_PLAN D1) — 13.3'te.

---

## Bir sonraki adım

**Aşama 13.2 — hızlı düzeltmeler.** Kapsam ve kabul ölçütü
`docs/YOL_HARITASI.md`'de: XSS, portların `127.0.0.1`'e bağlanması, Gemini
anahtarının başlığa taşınması, sağlık sorgusu, kamera başına JPEG kapısı,
kanıt sayfalama, kamera kaynağının göreli yazılması, `build_frontend.py`
önbellek etiketinin satır sonundan bağımsız olması. İlk iş 13.2'nin
uygulama planı.

Sonraki sıra, veri bekleyen işler ve yapılamayacaklar:
`docs/YOL_HARITASI.md`. Tez metni 19'da; **§3.5'in olay sayıları
teze aktarılmamalı** (24 saatlik koşu, 18).

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
| 2026-09-09 | 8.3 iki paralel iş paketine bölündü, paylaşımlı dosyalar tek elde | `app.js`, `build_frontend.py` ve ortak test iki paketin de yolundaydı; birleştirme tek elde toplandı |
| 2026-09-10 | Canlı kutu "AKTİF"i `onopen`'da değil ilk karede yazar | `ws_server` jeton ve yol geçerliyse yayıncısı olmayan bir `camera_id`'ye de bağlanmayı kabul ediyor; açılışa güvenmek hiç yayın olmayan kamerayı yeşil gösteriyordu |
| 2026-09-10 | Görünürlük/gizlenme yönetimi `element.hidden` ile değil `style.display` ile | Tailwind'in `.flex` sınıfı tarayıcının `[hidden]` kuralını eziyor; `hidden = true` sessizce hiçbir şey yapmıyordu |
| 2026-09-10 | Ortak canlı akış mantığı `live.js`'te, sayfa betiklerinde değil | Canlı izleme ve kamera detay aynı WS + çizim işini yapıyor; iki kopya, ölçek dönüşümü gibi ince bir hatayı iki kez düzeltmek demekti. `build_frontend.py` canlı sayfalara ikinci betiği ekliyor |
| 2026-09-10 | Panel FPS'i hedefin altına düşerse önce görü döngüsüne bakılır | Ölçüm: tarayıcı FPS'i sunucu döngü FPS'iyle örtüşüyor (25.2 / 25.1). İstemci kare atlamıyor; düşüş her seferinde hattın kendisinde (CPU rekabeti) |
| 2026-09-10 | Postgres `connect_timeout=3`, Mongo `serverSelectionTimeoutMS=3000` | Docker kapalıyken test paketi 8 sn yerine 5+ dakika sürüyordu: her canlı-veritabanı testi işletim sisteminin varsayılan bağlantı zaman aşımını bekliyordu. Sağlık ucu da aynı sebeple asılı kalırdı |
| 2026-11-23 | Spark pencereleme saati adayın **işlendiği anın duvar saati**, sahne zamanı değil (2026-08-27 kararının yerine) | Su işareti bütün kameralar için ortak; sahne zamanında yavaş akan dosya kamerası geride kalıp adayları "geç veri" diye atılıyordu (A2). Süre ölçütü (`min_sec`) yine sahne zamanı `ts` ile, kuralların anlamı değişmedi |
| 2026-11-23 | Kamera başına saniyede bir `_TICK` nabzı, işleme döngüsünden | Su işareti yalnız veriyle ilerliyor; sessiz sahnede düşme oturumu hiç kapanmıyordu (A1). Ayrı zamanlayıcı değil döngü: hat donarsa nabız da durur, oturum yanlışlıkla kapanmaz |
| 2026-11-23 | İç tipler çıkıştan **toplama sütunuyla** (`internal`) elenir | Yalnız `anomaly_type`'a bakan `where`'i Catalyst toplamanın ve `withWatermark`'ın altına iter; iç tipler su işaretine ulaşmaz ve düzeltme sessizce çalışmaz |
| 2026-11-23 | `spark.sql.shuffle.partitions` 200 → 2 | `local[2]`'de 200 görevlik yığın 4–5 sn sürüyordu; nabızla Spark ~%290 CPU yaktı, gecikme 15,2 sn oldu. 2 bölümle yığın < 1 sn, gecikme 7,58 sn |
| 2026-11-23 | Gelecek tarihli aday `withWatermark`'tan önce reddedilir (30 sn pay) | Tek bir ileri tarihli mesaj su işaretini sıçratıp sistemi susturabiliyordu. 30 sn = `_EOS` önü (15 sn) + saat kayması payı; ölçülen kap/konteyner kayması 0,32 sn |
| 2026-11-23 | Değerlendirme ayrı Spark servisi (`spark-eval`, `--profile eval`) ve ayrı konular | `spark_eval.py` su işaretini ~1,4 saat ileri itiyordu ve checkpoint kalıcı olduğu için canlı hattı susturuyordu (A3). Eşik API'si bu servise bağlanmadı: değerlendirme eşikleri ortam değişkeniyle verilir |

## Açık sorular

Her maddenin yanında kapatılacağı aşama (`docs/YOL_HARITASI.md`).

- **Kare hızı bağımlılığı** (→ 13.3): kural pencereleri, TCN girdisi ve
  izleyici tamponu kare sayısıyla tanımlı; canlı 5–10 FPS'te zaman ölçeği
  2,5–5 kat uzuyor. Çevrimdışı değerlendirme her kareyi işlediği için
  görmüyor (bkz. "Şu an neredeyiz")
- **Gerçek kamerada alarm gecikmesi** (→ 14): 13.1'de gerçek zamanlı
  akıtılan klipte 7,58 sn ölçüldü; kameranın önünde gerçek bir olayla hâlâ
  ölçülmedi (14'ün çekim oturumunda)
- **`zone_01`'in sahte RUN'ı** (→ 13.3): 35 vuruş, 1.80 sn, Spark'tan
  geçiyor. Süzgeç gürültüyü eler, kural hatasını düzeltmez — kök neden RUN
  kuralının kendisinde
- **`police_run` hiç aday üretmiyor** (→ 13.3, 17): 15 FPS, hız tepesi 1.77
  (eşik 1.80), adım medyanı 0.52. Düşük kare hızının adım kanıtını bastırıp
  bastırmadığı 13.3'ün FPS taramasında görülecek; derinlik yönündeki hız
  17'nin zemin kalibrasyonuyla. 13.1 yan gözlemi: aynı klip gerçek zamanlı
  döngüde (`--realtime --loop`) 41 aday üretti, hiçbiri olaya dönüşmedi —
  kaynağı (döngü sarımı mı, kare düşmesi mi) incelenmedi
- **Olay 1023 (RUN) çelişkisi** (→ 14): telemetride `norm_speed_max` 0.142,
  eşik 1.8 — panelde "EŞİK ALTINDA" görünen bir metrikle olay üretilmiş.
  Kuralın hangi kanıtla tetiklendiği (adım ritmi mi) telemetriden
  okunamıyor; tetikleyen kanıt telemetriye yazılmalı
- **Sabit kameralı, etiketli koşu klibi yok** (→ 14): iki etiketli koşu
  klibi de stok görüntü (birinde kamera koşucuyu takip ediyor, diğerinde
  kişi kameraya doğru koşuyor)
- **LOITERING duyarlılığı; FIGHT / LOITERING `min_sec`** (→ 14): geçerli
  olumlu oyalanma örneği yok (12.6); `min_sec` 0.5 / 2.0 ölçüme değil akıl
  yürütmeye dayanıyor
- **ReID kalabalık / kesişmeli sahnede ölçülmedi** (→ 15): pilot kliplerde
  `--no-reid` ID sayılarını değiştirmiyor; olay galerisi Aşama 11'de
  çalışmadı (F1 0.15)
- **CPU rekabeti** (→ 16): Docker yığını ayaktayken görü FPS'i 36.5'ten
  12–15'e düşüyor, profillenmedi. `--kafka` açıkken 36.5 → 31.8 kaybının
  librdkafka'nın arka plan iş parçacığından geldiği de varsayım
- **Denetim kaydı ve bildirim sekmelerinin filtre kutuları bağlı değil**
  (→ 13.7): uçlar filtreleri destekliyor, bağlanmayan yalnız arayüz
- **Tek tüketici süreci** (→ 18): 4 kamerada yetip yetmediği ölçülmedi;
  Kafka tarafı ölçeklenebilir (aynı `group.id` ile ikinci konteyner),
  veritabanı tarafı ölçülmeli

Kapanan sorular:

- ~~Sayfa betiklerinde kopyalanan yardımcılar~~ — `_fetchAuthedBlobUrl`,
  `ROLE_ADI`, `DECIDED_BY_ADI`, `CAMERA_STATUS_ADI`, `num()`,
  `FORBIDDEN_MSG` artık yalnız `frontend/js/app.js`'te (2026-11-23 denetimi)
- ~~`spark_min_sec` Spark'a ortam değişkeninden gidiyor~~ — Aşama 6 / 12.2:
  Spark açılışta `GET /api/settings` çağırıyor. Değer DAG'e açılışta
  gömülür; panelden değişiklik Spark yeniden başlayınca geçerli olur
  (bilinçli sınır)
- ~~ReID'in kare başına ~7 ms maliyeti çoklu kamerada~~ — Aşama 10.4: 4
  kamerada ReID kapalıyken kamera başına 11.7 → 15.2 FPS, pilot doğruluk
  değişmedi; varsayılan değiştirilmedi, bayrak olarak kaldı
- ~~Kadrajdan çıkıp giren kişiyi aynı kimliğe bağlama~~ — Aşama 11: olay
  galerisi ölçüldü, çalışmıyor (F1 0.15); 15'te ham kareden yeniden
  denenecek
- ~~Çoklu kamera toplu çıkarımı gerçek FPS'te~~ — Aşama 10.3: 4 kamera tek
  süreç, çıkarım kare başına 14.45 → 10.5 ms
- ~~Şablon ekranları API'yi karşılıyor mu~~ — Aşama 8.1–8.6: 11 ekran
  gerçek veriye bağlandı
- ~~FIGHT kuralının gerçek doğruluğu~~ — Aşama 9.5 / 11: holdout'ta FIGHT
  duyarlılığı 0.80 (15 klibin 12'si)
- ~~Bölge poligonu kameraya bağlı~~ — kapsam sınırı (12.6): bölge kuralları
  yalnız sabit kamerada anlamlı; hareketli kamera koruması 17'de
- ~~Host'tan API'ye ~600 ms sabit taban~~ — **Aşama 8.1'de ölçüldü, taban
  yok.** 25 istekle host'tan: `/health` medyan 13.8 ms, `/api/cameras` 13.8,
  `/api/events?limit=20` 11.1, `/api/analytics/summary` 18.0; konteyner
  içinden `/health` 1.8 ms. Port yönlendirmesinin maliyeti ~12 ms
- 4 GB VRAM'de `yolov8s-pose` sığıyor mu — evet, 49 MiB tepe kullanım
- Gerçek döngüde FPS ne olacak — YOLO26 + ReID ile 27–37 FPS (4K olmayan
  kliplerde), webcam 24.3
- BoT-SORT ReID çalışıyor mu — evet; YOLO26'da `yolo26s-reid.onnx` üzerinden
- YOLO26'nın daha az kişi bulması gerçek kaçırma mı — hayır, güven eşiği
  kalibrasyonuydu; `conf=0.25` v8 davranışını yakalıyor
- Host'ta çalışan `vision/` `localhost:9092`'ye yazabiliyor mu — evet,
  `scripts/check_kafka.py` gidiş-dönüş 781 ms
- Spark tek kare gürültüsünü eliyor mu — evet, ama tek eşikle değil: vuruş
  sayısı + tipe göre süre gerekti (`docs/DURUM_ARSIV.md`, Aşama 4)

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
