# Aşama 13.1 — Akış doğruluğu: uygulama planı (2026-11-23)

Bulgular ve kanıtları: `docs/ASAMA13_PLAN.md` bölüm A. Bu dosya uygulama
sözleşmesidir: üç bağımsız iş paketi, dokunulacak dosyalar, imzalar ve
kabul ölçütü. Burada yazmayan davranış değişikliği yapılmaz.

**Uygulayıcıya not:** ölçüm bölümündeki sayılar rapora girer. Kötü sayı
saklanmaz, eşik tabloyu güzelleştirmek için oynatılmaz. Testlerin geçmesi
doğrulama değildir; asıl doğrulama §6'daki canlı deneylerdir.

---

## 1. Kök neden ve düzeltmenin özü

Spark'ın su işareti (watermark) **yalnız yeni veri gelince** ilerler ve
**bütün kameralar için ortaktır**. Bugün `event_time` dosya kaynağında
sahne zamanıdır (`epoch_base + kare/FPS`), canlıda yakalama zamanıdır.

- A1: sessiz sahnede aday gelmez → su işareti durur → düşme oturumu hiç
  kapanmaz.
- A2: dosya kameralarının sahne saatleri farklı hızda akar → ortak su
  işareti geride kalanın adaylarını "geç veri" diye atar.

Düzeltme: **pencereleme saati herkes için aynı duvar saati** ve **her
kameradan düzenli nabız**. Süre ölçütleri (`min_sec`) sahne zamanı `ts`
ile hesaplanmaya devam eder; kuralların anlamı değişmez.

## 2. Sözleşme (paketler bunu ortak kabul eder)

### 2.1 `Candidate.event_time`

`vision/rules/engine.py`:

```python
@dataclass
class Candidate:
    ...
    decided_by: str = "rule"
    event_time: float | None = None   # duvar saati (epoch sn); None = eski davranis
```

- `CameraPipeline.consume()` her karede **bir kez** `now = time.time()`
  alır ve o karenin bütün adaylarına `cand.event_time = now` yazar. Aynı
  süreçteki bütün kameralar aynı turda işlendiği için hiçbiri geride
  kalamaz. `frame.ts` (okuma anı) kullanılmaz: dosya kaynağında 64 karelik
  ileri okuma kameralar arasında saniyelik kayma yaratır.
- `event_time is None` ise eski davranış: `epoch_base + ts`
  (`eval/spark_eval.py`, `eval/pilot_eval.py` aynen çalışır).

### 2.2 Kafka mesajı

`candidate_to_dict`: `"event_time": cand.event_time if cand.event_time is
not None else epoch_base + float(cand.ts)`. Diğer alanlar değişmez.

Nabız mesajı (`TICK_TYPE = "_TICK"`, `vision/publish.py`):

```json
{"schema": 1, "camera_id": "<kamera>", "anomaly_type": "_TICK",
 "track_key": "_tick", "track_ids": [], "score": 0.0, "idx": -1,
 "ts": 0.0, "event_time": <time.time()>, "zone_name": null,
 "decided_by": "rule", "metrics": {}, "thresholds_used": {}}
```

`CandidatePublisher.tick(event_time: float) -> None` bu gövdeyi basar
(bloklamaz, hata saymaz-fırlatmaz, `_last_event_time`'ı günceller).

### 2.3 Nabız politikası

`CameraPipeline`, `consume()` içinde, publisher varsa ve son nabızdan bu
yana `tick_sec` geçtiyse `publisher.tick(now)` çağırır. Nabız **işleme
döngüsünden** çıkar, ayrı zamanlayıcıdan değil: hat donarsa nabız da durur
ve su işareti yanlışlıkla oturum kapatmaz. `vision/run.py`'ye
`--tick-sec` (varsayılan `1.0`, `0` = kapalı; ölçümde A/B için).

### 2.4 Spark

- **İç tipler** `_` ile başlar (`_TICK`, `_EOS`). Toplamaya **girerler**
  (su işaretini ilerletmeleri için) ama çıkışa **asla** yazılmazlar.
- **Tuzak — süzgeç aşağı itilir:** Catalyst, yalnız gruplama sütununa
  (`anomaly_type`) bakan bir `where`'i toplamanın ve `withWatermark`'ın
  **altına** iter (event_time'a bakmayan yüklemler watermark'tan geçer).
  O zaman iç tipler su işaretine hiç ulaşmaz ve düzeltme sessizce
  çalışmaz. Bu yüzden süzgeç bir **toplama sütununa** bakmalıdır:
  `spark_max(col("anomaly_type").startswith("_").cast("int")).alias("internal")`
  ve çıkışta `col("internal") == 0`. Aşağı itilemez.
- **Gelecek tarihli ret:** `withWatermark`'tan **önce**
  `where(col("event_time") <= current_timestamp() + expr(f"INTERVAL {FUTURE_SEC} SECONDS"))`.
  `SPARK_FUTURE_SEC` ortam değişkeni, varsayılan `30` (EOS önü 15 sn +
  kap/konteyner saat kayması payı); `-1` = kapalı (değerlendirme sorgusu).
- **Tetik:** `.trigger(processingTime=f"{TRIGGER_SEC} seconds")`,
  `SPARK_TRIGGER_SEC` varsayılan `1`. Nabız her saniye veri getirdiği için
  tetiksiz Spark durmadan yığın koşar; tetik yığın hızını sınırlar.
- **Konular:** `SPARK_INPUT_TOPIC` (varsayılan `anomaly-candidates`),
  `SPARK_OUTPUT_TOPIC` (varsayılan `anomaly-events`).
- `AGG_VERSION = 3`: toplama yapısı değişiyor (yeni `internal` sütunu) ve
  canlı checkpoint'in su işareti eski değerlendirme koşularınca ileri
  itilmiş olabilir; temiz başlangıç.

### 2.5 Değerlendirme yalıtımı

- Yeni konular: `eval-candidates`, `eval-events` (`infra/kafka/topics.sh`).
- `docker-compose.yml`'a `spark-eval` servisi: `spark` ile aynı imaj ve
  komut, `profiles: ["eval"]` (varsayılan `up`'ta açılmaz), ortam:
  `SPARK_INPUT_TOPIC=eval-candidates`, `SPARK_OUTPUT_TOPIC=eval-events`,
  `SPARK_FUTURE_SEC=-1`, `CHECKPOINT_DIR=/checkpoints`, ayrı volume
  `spark_eval_checkpoints`. Konteyner adı `anomaly-spark-eval`.
- `eval/spark_eval.py`: `--topic-in` (varsayılan `eval-candidates`),
  `--topic-out` (varsayılan `eval-events`); docstring'deki çalıştırma
  talimatı `docker compose --profile eval up -d spark-eval` olur.

### 2.6 Kamera başına aday sayacı (izleme)

- `CameraPipeline.candidates_total`: yayınlanan gerçek aday sayısı
  (nabız ve `_EOS` hariç), birikimli.
- `vision/health_client.py`: `note(fps, infer_ms, candidates=None)`;
  Mongo `camera_health` belgesine `"candidates": <int>` alanı.
- `api/schemas.py` `CameraHealthOut.candidates: int | None = None`;
  `api/routers/health.py` `doc.get("candidates")` geçirir.

### 2.7 Kanıt eşleşmesi

`vision/evidence.py` `_write_job`: olay başlangıç/bitişi
`ep.candidates[0].event_time` / `ep.candidates[-1].event_time` (None ise
eski `self.epoch_base + ep.start_ts/end_ts`). Halka tampondan klip seçimi
`wall_start/wall_end` ile **aynen** kalır. Böylece `events.started_at`
(Spark'ın `min(event_time)`) ile kanıt satırı aynı saati kullanır.

---

## 3. Paket V — görü tarafı

Dosyalar: `vision/rules/engine.py`, `vision/publish.py`,
`vision/camera.py`, `vision/run.py`, `vision/evidence.py`,
`vision/health_client.py`, `tests/test_publish.py`, ilgili kanıt testleri
(`tests/test_evidence.py`, `tests/test_evidence_match.py`).

- §2.1, §2.2, §2.3, §2.6 (görü kısmı), §2.7
- `publish.py` modül ve fonksiyon docstring'leri yeni saat anlaşmasına göre
  güncellenir ("event_time sahne zamanıdır" ifadesi artık yanlış)

Testler (assert tabanlı, mevcut stil):
- `event_time` verilmiş aday → gövdede aynen; verilmemiş → `epoch_base+ts`
- `tick()` gövdesi §2.2 ile birebir; `_last_event_time` güncelleniyor
- nabız politikası: `tick_sec=1.0` iken 0.0/0.4/1.1/1.5/2.2 sn'lik
  `consume` çağrılarında tam 3 nabız (saat enjekte edilebilir olmalı:
  `CameraPipeline` `clock=time.time` parametresi ya da eşdeğeri); `0` →
  hiç nabız
- kanıt POST'unun `start_time`'ı ilk adayın `event_time`'ı

## 4. Paket S — akış tarafı

Dosyalar: `stream/spark_job.py`, `stream/filters.py`,
`docker-compose.yml`, `infra/kafka/topics.sh`, `eval/spark_eval.py`,
`eval/stream_probe.py`, `tests/test_spark_settings.py` (gerekirse),
yeni `tests/test_filters.py` (yoksa).

- §2.4, §2.5
- `stream/filters.py`: `INTERNAL_PREFIX = "_"`; `session_passes()` iç tip
  için her zaman `False` (eşik mantığının referans kopyası Spark ile aynı
  kalsın)
- `spark_job.py` başındaki `_EOS` notu, süzgecin neden toplama sütununa
  baktığını (§2.4 tuzak) anlatacak şekilde güncellenir
- `eval/stream_probe.py`:
  - docstring'in "13.1 sonrası not"u günceldir: `tek-dusme` için yanda en
    az bir kamera nabız basıyor olmalı
  - yeni alt komut `gelecek`: `probe_cam` adına `event_time = şimdi +
    3600` tek aday basar, sonra `tek-dusme` akışını aynen koşar. Çıkış
    kodları `tek-dusme` ile aynı anlamda. Gelecek reddi çalışmıyorsa su
    işareti bir saat ileri sıçrar, düşme geç sayılır, olay gelmez (2)
  - `saat-kaymasi` değişmez

pyspark yerelde yok; mevcut `tests/test_spark_settings.py` sahte modülle
yükleme yapıyor. Spark mantığı burada birim testlenemez — doğrulaması §6.
`filters.py` için saf birim testi yazılır.

## 5. Paket İ — izleme

Dosyalar: `api/schemas.py`, `api/routers/health.py`,
`scripts/soak_test.py`, `tests/test_soak.py`.

- §2.6 (API kısmı)
- `soak_test.py`: her örnekte kamera başına `candidates` (sağlık ucu) ve
  olay sayısı (`GET /api/events?camera_id=<id>&limit=1` → `total`). CSV'ye
  tek sütun `kamera_ozet`: `ad:aday:olay;ad:aday:olay`. `report()` ilk ve
  son satırın farkından kamera başına aday ve olay artışını basar; aday
  artıp olay artmayan kamera için `UYARI: <ad> aday uretiyor, olay
  uretmiyor`. Eski CSV'lerde sütun yoksa rapor bozulmaz.
- Test: `report()` uyarıyı doğru kamerada veriyor, eski CSV'de çökmüyor.

---

## 6. Kabul — canlı deneyler (ana dizinde, Docker açıkken)

Kod birleştirildikten sonra koşulur; sonuçlar `docs/DURUM.md`'ye.

1. Spark yeniden kurulur (`spark` yeniden oluşturulur, eval konuları
   açılır); kap ile Spark konteyneri arası saat kayması ölçülür.
2. **A1** — bir kamera nabız basarken `eval/stream_probe.py tek-dusme`:
   çıkış 0, olay ~5–7 sn içinde.
3. **Gelecek reddi** — `stream_probe gelecek`: çıkış 0.
4. **A2** — üç dosya kamerası 4 dk + `stream_probe saat-kaymasi`: geç
   aday 0; üç kameranın üçü de olay üretiyor (veritabanında).
5. **Gecikme** — `eval/latency_watch.py`, `fall_01` gerçek zamanlı akıtma
   (12.4 ile aynı düzen): yeni medyan; `docs/TEZ.md` §3.7'deki uyarı
   gerçek sayıyla değiştirilir.
6. **Nabız maliyeti** — aynı 4 kamera düzeni, `--tick-sec 1` ve `0`,
   üçer dakika: kamera başına FPS ve Spark CPU (`docker stats`).
7. **Yalıtım** — `spark-eval` açılır, `eval/spark_eval.py --from-cache`
   Aşama 4 tablosunu verir; hemen ardından adım 2 yine çıkış 0 (canlı su
   işareti etkilenmedi).
8. **Kısa çoklu kamera koşusu** — 30 dk, `soak_test.py`: kamera başına
   olay artışı > 0, uyarı yok. `docs/TEZ.md` §3.5'in uyarısı kalır;
   düzeltilmiş olay sayıları Aşama 18'in 24 saatlik koşusundan gelir.

## 7. Bilinen sınırlar (bu aşamada kapatılmaz)

- Bir süreç kapanırken attığı `_EOS` su işaretini ~13 sn ileri iter; aynı
  anda çalışan **başka** bir görü sürecinin adayları o süre geç sayılır.
  Tek süreçli dağıtımda (bugünkü düzen) geçerli değil.
- `Zone.active_at(ts)` dosya kaynağında sahne saniyesiyle çağrılıyor
  (ASAMA13_PLAN D1). Zaman damgalarının tamamı 13.3'te yeniden ele
  alındığı için orada kapatılır.
- Nabız, Spark'ı her saniye yığın koşturur; maliyeti §6.6'da ölçülür,
  sonucu 16'nın CPU rekabeti işine girer.
