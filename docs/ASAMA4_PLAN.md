# Aşama 4 — Kafka ve Spark (uygulama sözleşmesi)

Bu dosya Aşama 4'ün uygulama planıdır. `docs/PLAN.md` mimariyi, `docs/DURUM.md`
ilerlemeyi tutar; burada yalnızca **ne yazılacağı ve hangi imzalarla**
yazılacağı vardır. Aşama bitince bu dosya silinmez, uygulanan sözleşme olarak
kalır.

Kod stili mevcut dosyalarla aynı: modül başında neden-açıklaması, **kod ve
yorumlarda ASCII** (Türkçe harf yok), `from __future__ import annotations`,
tip ipuçları, dosya başına ~150 satır hedefi.

---

## 0. Girdi durumu

Hazır olan:

- `Candidate(anomaly_type, track_ids, score, idx, ts, metrics, thresholds_used,
  zone_name)` — `vision/rules/engine.py`. Alanların tamamı seri hale
  getirilebilir (`metrics` ve `thresholds_used` `dict[str, float]`).
- `docker-compose.yml`: `kafka` (KRaft, host `localhost:9092`, docker içi
  `kafka:29092`) ve `kafka-init` (topic'leri açar) çalışıyor.
- Topic'ler: `anomaly-candidates` (3 partition, 1 saat), `anomaly-events`
  (3 partition, 24 saat).
- `infra/postgres/init.sql` → `detection_settings.spark_window_sec = 3`,
  `spark_min_hits = 5`.
- Aşama 3 ölçümü — Spark'ın süzeceği gürültü tabanı (`docs/DURUM.md`):

  | klip | ham aday | dağılım |
  |---|---|---|
  | fall_01 | 2 | FALL |
  | mixed_01 | 0 | — |
  | normal_01 | 11 | RUN (2.0 sn'de kısa tempolu yürüyüş) |
  | police_run | 0 | — |
  | run_01 | 333 | RUN (1.6 sn'den itibaren kesintisiz) |
  | zone_01 | 739 | ZONE_VIOLATION 703 + RUN 35 |

**Bu tablodaki `fall_01 = 2` sayısı bu aşamanın en kritik kısıtıdır.** Gerçek
düşme olayı yalnızca 2 aday üretiyor; `normal_01`'in yanlış pozitifi 11 aday
üretiyor. Yani "kaç vuruş" ölçütü tek başına, tip ayrımı yapmadan
uygulandığında gerçek FALL'ı eleyip sahte RUN'ı geçirir. Tasarım bunun
üstüne kuruluyor (§5.3).

---

## 1. Bağımlılık

`requirements.txt`'e eklenecek:

```
confluent-kafka>=2.5.0   # librdkafka; produce() kuyruga atip doner, GPU dongusunu bloklamaz
```

`kafka-python` seçilmedi: saf Python, her mesajda GIL altında sıkıştırma ve
protokol işi yapıyor; `produce()` çağrısı görü döngüsünün içinde. `confluent-kafka`
cp311 win_amd64 tekerleği hazır gelir. Tekerlek bulunamazsa uygulama durur ve
bana sorulur — kütüphane kendi başına değiştirilmez.

---

## 2. `vision/publish.py` (yeni, ~120 satır)

Kafka producer. **WebSocket yayını bu aşamada YOK** (Aşama 6); `PLAN.md` bu
dosyayı "Kafka + WebSocket" diye tarif eder, WebSocket kısmı Aşama 6'da
eklenecek.

```python
CANDIDATE_TOPIC = "anomaly-candidates"
EOS_TYPE = "_EOS"
EOS_LEAD_SEC = 15.0      # akis sonu isaretcisi bu kadar ileri damgalanir (SS5.5)
SCHEMA_VERSION = 1


def candidate_to_dict(cand: Candidate, camera_id: str, epoch_base: float) -> dict:
    """Candidate -> Kafka JSON govdesi (SS4 sozlesmesi)."""


class CandidatePublisher:
    def __init__(self, bootstrap: str, camera_id: str, *,
                 epoch_base: float = 0.0, topic: str = CANDIDATE_TOPIC,
                 queue_max: int = 100_000) -> None: ...

    def __call__(self, candidates: list[Candidate]) -> None:
        """Bloklamaz. Hata sayilir, yukari FIRLATILMAZ."""

    def close(self, *, eos: bool = True, timeout: float = 10.0) -> None:
        """Akis sonu isaretcisini basar ve kuyrugu bosaltir."""

    published: int      # broker'a teslim edildigi onaylanan mesaj
    queued: int         # produce() cagrisi kabul edilen mesaj
    failed: int         # teslim edilemeyen + kuyruga alinamayan
    last_error: str     # rapora yazilir
```

Kurallar:

- **Görü döngüsü Kafka yüzünden durmaz.** `produce()` `BufferError`
  fırlatırsa (kuyruk dolu, broker yok) yakalanır, `failed += 1`, döngü devam
  eder. Teslim geri çağrısı (`delivery callback`) hatayı `failed` ve
  `last_error`'a yazar. `flush()` yalnızca `close()` içinde çağrılır.
  Gerekçe: alarm hattının kendisi kamera hattını düşüremez; Kafka'nın
  yokluğu ölçülür ve raporlanır, sessizce yutulmaz.
- `poll(0)` her `__call__` başında bir kez — teslim geri çağrıları böyle
  işlenir, ayrı iş parçacığı gerekmez.
- **Anahtar (key):** `f"{camera_id}:{track_key}"`. Aynı iz hep aynı
  partition'a gider, iz içi sıra korunur.
- `track_key = "-".join(str(t) for t in sorted(cand.track_ids))` — FIGHT iki
  izlidir, tek dize anahtar Spark grubunun anahtarı olur.
- **`event_time`:** `epoch_base + cand.ts`. Bu, Spark'ın pencereleyeceği
  zamandır ve **sahne zamanıdır, duvar saati değildir.** Gerekçe: dosya
  kaynağı 25 FPS'lik klibi 35 FPS'te işleyebilir; duvar saatiyle pencerelenirse
  3 saniyelik pencere 4 saniyelik sahneyi kapsar ve ölçüm tekrarlanabilir
  olmaz. Canlı kaynakta `cand.ts` zaten epoch olduğu için `epoch_base = 0.0`
  verilir ve iki mod aynı koda düşer.
- `producer` yapılandırması: `linger.ms=50`, `compression.type=lz4`,
  `acks=1`, `queue.buffering.max.messages=queue_max`. Gerekçe: adaylar
  hacimli ve kısa ömürlü; `acks=all` bir broker'lı kümede getirisi olmayan
  gecikmedir.

### Akış sonu işaretçisi (`_EOS`)

`close(eos=True)` tek bir mesaj basar: `anomaly_type = "_EOS"`,
`camera_id = "_eos"`, `track_key = "_eos"`,
`event_time = <son basilan event_time> + EOS_LEAD_SEC`.

**Neden gerekli:** Spark oturum penceresi `append` modunda ancak damgası
(watermark) pencere sonunu geçince yazar. Dosya klibi bitince veri akışı
durur, damga ilerlemez, klibin **son olayı hiç yazılmaz**. `_EOS` damgayı
ileri iter ve bekleyen tüm oturumlar kapanır.

`_EOS` kendi başına bir oturum oluşturur, vuruş sayısı 1'dir ve
`spark_min_hits >= 2` ile elenir — Spark tarafında özel bir durum kodu
gerekmez (ve gerekmemeli: filtreleme toplamadan önce yapılırsa damga da
ilerlemez, bkz. §5.5).

---

## 3. `vision/run.py` — bağlama (+ ~25 satır)

Yeni argümanlar:

```python
parser.add_argument("--kafka", nargs="?", const=os.getenv("KAFKA_BOOTSTRAP_HOST", "localhost:9092"),
                    default="", help="aday olaylari Kafka'ya bas (varsayilan bootstrap: env)")
parser.add_argument("--camera-id", default="", help="bos = kaynak dosya adi / webcam indeksi")
```

- `--kafka` verilmezse davranış Aşama 3 ile birebir aynıdır (yayın yok).
- `camera_id` boşsa `Path(str(args.source)).stem` (webcam için `cam-0`).
- `epoch_base = 0.0 if source.is_live else time.time()`.
- `publisher` `--rules` yokken kurulmaz (aday üretilmiyor).
- Yayın çağrısı `all_candidates.extend(candidates)` satırının hemen yanında,
  süresi `publish_ms` listesine ölçülür ve rapora **medyan/p95** olarak
  eklenir. Bu ölçüm zorunludur (§11.6).
- `with VideoSource(...)` bloğu bittikten sonra `publisher.close()`; rapora
  `yayinlanan / kuyruga alinan / basarisiz` satırı ve hata varsa
  `last_error`.

---

## 4. Mesaj sözleşmesi (JSON)

### 4.1 `anomaly-candidates` (vision → Spark)

```json
{
  "schema": 1,
  "camera_id": "zone_01",
  "anomaly_type": "ZONE_VIOLATION",
  "track_key": "3",
  "track_ids": [3],
  "score": 0.83,
  "idx": 412,
  "ts": 16.48,
  "event_time": 1772100000.48,
  "zone_name": "bina girisi",
  "metrics": {"...": 0.0},
  "thresholds_used": {"...": 0.0}
}
```

- `ts`: klibe/akışa göreli saniye (değerlendirme ve tez tabloları bunu
  kullanır).
- `event_time`: epoch saniye (double). Spark'ın olay zamanı sütunu.
- `zone_name` yoksa `null`.

### 4.2 `anomaly-events` (Spark → Aşama 5 tüketicisi)

```json
{
  "schema": 1,
  "camera_id": "zone_01",
  "anomaly_type": "ZONE_VIOLATION",
  "track_key": "3",
  "track_ids": [3],
  "hits": 703,
  "start_ts": 10.84, "end_ts": 27.96, "duration_sec": 17.12,
  "start_time": 1772100000.84, "end_time": 1772100017.96,
  "score": 0.91,
  "zone_name": "bina girisi",
  "metrics": {"...": 0.0},
  "thresholds_used": {"...": 0.0}
}
```

- `metrics` / `thresholds_used` / `track_ids` / `zone_name`: **tepe skorlu
  adaydan** alınır (`max_by(col, score)`). Aşama 5 kanıt klibinin en iyi
  karesini bu değerlerle seçecek.
- `start_time` / `end_time`: oturumdaki **gerçek** ilk/son `event_time`
  (`min`/`max`). Spark'ın `session_window.end` alanı boşluk süresini
  içerdiği için kullanılmaz.

---

## 5. `stream/spark_job.py` (yeni, ~150 satır)

### 5.1 Plandan sapma: kayan pencere yerine **oturum penceresi**

`PLAN.md` "window(3 sn, kayma 1 sn) HAVING hits >= N" diyor. Bu, kesintisiz
13 saniyelik bir koşu için **13 ayrı doğrulanmış olay** yazar; Aşama 5'in
tüketicisi 13 veritabanı satırı, 13 Gemini çağrısı ve 13 Telegram mesajı
üretir. Tekrarı Aşama 5'te ayıklamak, `PLAN.md`'nin v1'de eleştirdiği yama
yığınının aynısıdır.

`session_window(event_time, "<gap> seconds")` (Spark 3.2+) aynı işi tek
API ile ve yapısal olarak doğru yapar: kesintisiz bir olay episodu **tek**
satır olur, `hits` ve süre bedava gelir, tek kare gürültüsü `hits = 1`
oturumu olarak zaten elenir. Boşluk süresi `spark_window_sec` (3 sn) olarak
kalır, yani ayarın anlamı korunur: "3 saniyeden uzun sessizlik yeni olaydır".

### 5.2 Akış

```python
raw = (spark.readStream.format("kafka")
       .option("kafka.bootstrap.servers", BOOTSTRAP)
       .option("subscribe", "anomaly-candidates")
       .option("startingOffsets", "latest")
       .load())

cand = (raw.select(from_json(col("value").cast("string"), CANDIDATE_SCHEMA).alias("c"))
        .select("c.*")
        .withColumn("event_time", col("event_time").cast("timestamp"))
        .withWatermark("event_time", f"{WATERMARK_SEC} seconds"))

sessions = (cand.groupBy(session_window(col("event_time"), f"{GAP_SEC} seconds"),
                         col("camera_id"), col("track_key"), col("anomaly_type"))
            .agg(count(lit(1)).alias("hits"),
                 spark_min("ts").alias("start_ts"),
                 spark_max("ts").alias("end_ts"),
                 spark_min("event_time").alias("start_time"),
                 spark_max("event_time").alias("end_time"),
                 spark_max("score").alias("score"),
                 max_by(col("track_ids"), col("score")).alias("track_ids"),
                 max_by(col("zone_name"), col("score")).alias("zone_name"),
                 max_by(col("metrics"), col("score")).alias("metrics"),
                 max_by(col("thresholds_used"), col("score")).alias("thresholds_used")))
```

`CANDIDATE_SCHEMA` elle yazılır (`StructType`); akışta şema çıkarımı yok.
`metrics` ve `thresholds_used` → `MapType(StringType(), DoubleType())`.

### 5.3 Süzgeç — iki ölçüt, tipe göre süre

```python
confirmed = sessions.where(
    (col("hits") >= MIN_HITS) &
    ((col("end_ts") - col("start_ts")) >= element_at(MIN_SEC_MAP, col("anomaly_type")))
)
```

`MIN_SEC_MAP` Python sözlüğünden `create_map(...)` ile kurulur; tipte
karşılık yoksa `coalesce(..., lit(MIN_SEC_DEFAULT))`.

**Neden iki ölçüt ve neden tipe göre:**

1. Süre ölçütü kare hızından bağımsızdır. `police_run` 15 FPS, pilotların
   geri kalanı 25–30 FPS. Yalnızca vuruş sayarsak aynı eşik 15 FPS'lik
   kamerada iki katı süre talep eder — `docs/DURUM.md`'de zaten ölçülmüş bir
   tuzak (`police_run`'ın düşük kare hızı adım kanıtını da bastırıyor).
2. FALL bir **darbedir**, RUN/ZONE/LOITERING bir **durumdur**. Gerçek FALL 2
   aday, sahte RUN 11 aday üretiyor (§0). Tek eşik ikisini ayıramaz; ayırmaya
   zorlamak FALL recall'unu 1.00'dan 0.00'a düşürür. Tipe göre süre, sayıyı
   güzelleştirme değil, olay fiziğinin karşılığıdır.

Başlangıç varsayılanları (**ölçümden sonra değişebilir, §11.3**):

| tip | `min_sec` | gerekçe |
|---|---|---|
| FALL | 0.0 | darbe; `hits >= 2` tek koruma |
| RUN | 1.0 | `normal_01` gürültüsü ~11 kare |
| ZONE_VIOLATION | 1.0 | bölgeden geçiş anlık olmamalı |
| LOITERING | 2.0 | kural zaten 30 sn bekliyor |
| FIGHT | 0.5 | ölçülmedi, muhafazakâr |

Global `MIN_HITS = 2` — tek kare gürültüsünü eler, `fall_01`'in 2 adayını
geçirir.

### 5.4 Çıkış

```python
(confirmed.select(
    concat_ws(":", "camera_id", "track_key", "anomaly_type",
              col("start_time").cast("string")).alias("key"),
    to_json(struct(lit(SCHEMA_VERSION).alias("schema"), ...)).alias("value"))
 .writeStream.format("kafka")
 .option("kafka.bootstrap.servers", BOOTSTRAP)
 .option("topic", "anomaly-events")
 .option("checkpointLocation", CHECKPOINT_DIR)
 .outputMode("append")
 .start().awaitTermination())
```

`start_time`/`end_time` JSON'a **epoch double** olarak yazılır
(`unix_timestamp(...) + saniye altı kısım`; pratikte
`col("start_time").cast("double")`).

### 5.5 `_EOS` toplamadan önce ELENMEZ

`anomaly_type != "_EOS"` süzgeci `groupBy`'dan önce konursa damga ilerlemez
ve `_EOS`'un tek işlevi yok olur. `_EOS` normal bir kayıt gibi toplanır,
`hits = 1` olduğu için `MIN_HITS >= 2` ile düşer. Ölçüm koşusunda
(`MIN_HITS = 0`, §11.3) `_EOS` satırı çıktıda görünür — bu beklenen
davranıştır, `eval/spark_eval.py` bu tipi eler.

### 5.6 Yapılandırma (ortam değişkenleri)

| değişken | varsayılan |
|---|---|
| `KAFKA_BOOTSTRAP` | `kafka:29092` |
| `SPARK_GAP_SEC` | `3` |
| `SPARK_WATERMARK_SEC` | `2` |
| `SPARK_MIN_HITS` | `2` |
| `SPARK_MIN_SEC` | `{"FALL":0.0,"RUN":1.0,"ZONE_VIOLATION":1.0,"LOITERING":2.0,"FIGHT":0.5}` |
| `SPARK_MIN_SEC_DEFAULT` | `1.0` |
| `CHECKPOINT_DIR` | `/checkpoints` |

Eşiklerin PostgreSQL'den okunması ve sıcak yeniden yüklenmesi **Aşama 5**'tir.

---

## 6. `docker-compose.yml` — `spark` servisi

```yaml
  spark:
    image: apache/spark:3.5.4-scala2.12-java17-python3-ubuntu
    container_name: anomaly-spark
    restart: unless-stopped
    depends_on:
      kafka:
        condition: service_healthy
    # ponytail: root olarak calisiyor. apache/spark imaji uid 185'tir, adlandirilmis
    # volume'lar root'a aittir; yerel gelistirmede sahiplik ayari yerine root ucuz.
    # Uretimde: volume'lari 185:185 yap, user satirini kaldir.
    user: root
    entrypoint: ["/opt/spark/bin/spark-submit"]
    command:
      - "--master"
      - "local[2]"
      - "--packages"
      - "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.4"
      - "--conf"
      - "spark.jars.ivy=/ivy"
      - "/app/spark_job.py"
    environment:
      KAFKA_BOOTSTRAP: kafka:29092
      CHECKPOINT_DIR: /checkpoints
    volumes:
      - ./stream:/app:ro
      - spark_checkpoints:/checkpoints
      - spark_ivy:/ivy
```

- **İmaj etiketi doğrulanacak.** `docker run --rm <imaj> python3 -c "import
  pyspark; print(pyspark.__version__)"` çalışmalı. Çalışmıyorsa Docker Hub'da
  `apache/spark` etiketleri taranır ve **çalışan etiket rapora yazılır**;
  imaj kendi başına başka bir dağıtıma (bitnami vb.) çevrilmez, bana sorulur.
- `--packages` sürümü imaj sürümüyle **birebir** aynı olmalı.
- `spark_ivy` volume'u ilk indirmeden sonra çevrimdışı başlatmayı sağlar.
- `docker-compose.yml` başındaki "spark -> Asama 4'te eklenecek" yorumu
  güncellenir.
- Yeni volume'lar `volumes:` bloğuna eklenir.

---

## 7. `infra/postgres/init.sql` güncellemesi

Aşama 5 henüz ORM yazmadığı için şema değişikliği bedava (Aşama 3'te aynı
gerekçeyle `fall_spine_deg` → `fall_tilt_deg` yapılmıştı).

- `spark_min_hits` varsayılanı `5` → `2` (gerekçe §5.3; 5 gerçek FALL'ı eler).
- Yeni sütun:

```sql
    spark_min_sec    JSONB        NOT NULL DEFAULT
        '{"FALL":0.0,"RUN":1.0,"ZONE_VIOLATION":1.0,"LOITERING":2.0,"FIGHT":0.5}',
```

  Tip başına ayrı sütun yerine JSONB: yeni bir kural tipi şema göçü
  gerektirmesin.
- `spark_window_sec` yorumu güncellenir: artık **oturum boşluğu** (bu kadar
  saniyelik sessizlikten sonrası yeni olaydır).

---

## 8. `scripts/check_kafka.py` (yeni, ~50 satır)

`docs/DURUM.md`'deki açık soruyu kapatır: *host'ta çalışan `vision/` gerçekten
`localhost:9092`'ye yazabiliyor mu.*

Bir UUID'li `_SELFTEST` mesajı `anomaly-candidates`'e basar, benzersiz
`group.id` + `auto.offset.reset=latest` ile geri okur, gecikmeyi yazdırır.
Bulamazsa çıkış kodu 1.

```
venv\Scripts\python.exe scripts/check_kafka.py --bootstrap localhost:9092
```

---

## 9. `eval/spark_eval.py` (yeni, ~220 satır)

Aşama 4 onay kriterini üreten betik. `eval/pilot_eval.py`'ı **yeniden
kullanır**, kopyalamaz: `run_clip`, `to_second_set`, `score`,
`markdown_table` oradan import edilir.

```
venv\Scripts\python.exe -m eval.spark_eval --clips data/pilot --zones eval/zones.json
venv\Scripts\python.exe -m eval.spark_eval --from-cache        # GPU'suz, esik supurmesi icin
```

Akış:

1. **Aday üretimi.** Her klip için `run_clip(...)` (GPU). Sonuç
   `eval/out/candidates.jsonl` dosyasına yazılır (`camera_id = clip.stem`).
   `--from-cache` bu adımı atlar — eşik süpürmesi GPU istemesin.
2. **Epoch tabanı.** `eval/out/.epoch_base` dosyasında son koşunun en büyük
   `event_time`'ı tutulur; yeni taban `max(time.time(), son + 1.0)`.
   **Neden:** Spark damgası kalıcı (checkpoint); bir önceki koşunun `_EOS`
   mesajı damgayı geleceğe ittiği için taban duvar saatinden alınırsa yeni
   koşunun tamamı "geç veri" sayılıp sessizce düşer. Klipler ayrıca
   `base + i * 1000.0` ile ayrılır, olay zamanları klipler arası artan olur.
3. **Yayın.** `CandidatePublisher` ile hepsi basılır, sonra `close(eos=True)`.
4. **Tüketim.** `anomaly-events` benzersiz `group.id` + `earliest` ile
   okunur; `idle_timeout` (varsayılan 30 sn) boyunca yeni mesaj gelmezse
   durur. Çıktı `eval/out/events.jsonl` — **ham dökümdür, ana oturumda elle
   incelenecektir.**
5. **Puanlama.** Her doğrulanmış olay, kapsadığı saniyelere açılır
   (`range(int(start_ts), int(end_ts) + 1)`) ve `(tip, saniye)` kümesine
   çevrilir. **Neden:** Aşama 3 tablosu da `(tip, saniye)` kümesi üzerinden
   sayıldı; birim aynı olmazsa öncesi/sonrası karşılaştırması anlamsızdır.
   Sonra `score()` + `markdown_table()` aynen çağrılır.
6. **Süpürme.** `--sweep` verilirse `events.jsonl` üzerinde `min_hits` ve
   `min_sec` değerleri **çevrimdışı** taranır ve tablo basılır (Spark
   `MIN_HITS=0`, `SPARK_MIN_SEC_DEFAULT=0` ile koşulmuş olmalı; bu durumda
   tüm oturumlar yazılır).

Çıktı tabloları:

- **Tablo A** — klip × tip: ham aday → oturum sayısı → doğrulanmış olay.
- **Tablo B** — oturum dökümü: klip, tip, `hits`, `duration_sec`, geçti/elendi.
- **Tablo C** — precision/recall/F1: Aşama 3 (Spark öncesi) vs Aşama 4
  (Spark sonrası), aynı puanlama koduyla.
- **Tablo D** — gecikme: `event_time` → mesajın `anomaly-events`'e düşüşü
  (duvar saati), medyan ve p95.

**Ajana uyarı:** eşikler tabloyu güzelleştirmek için oynatılmaz. Ölçüm ne
söylüyorsa o yazılır; FALL veya RUN kötüleşirse **kötüleşmiş hâliyle**
raporlanır. Aşama 3'te tam olarak bu tuzağa düşülmüştü.

---

## 10. `tests/test_publish.py` (yeni, ~70 satır, broker'sız)

Mevcut testlerin biçimi: `assert` tabanlı, GPU'suz, `pytest` gerekmez.

1. `candidate_to_dict` — `track_key` sıralı ve tireli ("7-3" değil "3-7"),
   `event_time == epoch_base + ts`, `zone_name` yoksa `None`, tüm gövde
   `json.dumps` edilebiliyor.
2. `CandidatePublisher` ulaşılamayan bir bootstrap ile (`localhost:1`)
   kurulup çağrıldığında **istisna fırlatmıyor**, `failed` artıyor.
   `close()` de fırlatmıyor. Bu, §2'deki "görü döngüsü Kafka yüzünden
   durmaz" kuralının koşulabilir kanıtıdır.
3. Süzgeç mantığı saf fonksiyona alınırsa (`session_passes(hits, duration,
   anomaly_type, min_hits, min_sec)`) Spark'sız test edilebilir —
   `spark_job.py` bu fonksiyonu import edip `udf` yerine sütun ifadesiyle
   kullanmayacaksa, en azından `eval/spark_eval.py`'ın süpürmesi aynı
   fonksiyonu çağırmalı ki iki yerde iki farklı eşik mantığı olmasın.
   Test: `fall_01` senaryosu (2 vuruş, 0.04 sn) geçer, `normal_01` senaryosu
   (11 vuruş, 0.44 sn) elenir.

`stream/spark_job.py` için birim test yok — koşulabilir kanıtı
`eval/spark_eval.py`'ın uçtan uca koşusudur.

---

## 11. Zorunlu ölçümler (rapora giren)

1. `scripts/check_kafka.py` çıktısı — host → `localhost:9092` uçtan uca
   çalışıyor mu, gecikme kaç ms. (Açık soruyu kapatır.)
2. Kullanılan Spark imaj etiketi ve `spark-sql-kafka` paket sürümü.
3. Eşik süpürmesi (Tablo B + `--sweep`): `min_hits ∈ {1,2,3,5}` ×
   `min_sec ∈ {0.0,0.5,1.0,1.5,2.0}`. Varsayılanlar bu tablodan seçilir ve
   seçim gerekçesi yazılır.
4. Tablo A — ham aday → doğrulanmış olay. Beklenti (§0): `normal_01`'in 11
   adayı elenmeli, `run_01`'in 333 adayı tek olay olarak geçmeli,
   `fall_01`'in 2 adayı geçmeli. **Beklenti tutmazsa gerçek sonuç yazılır.**
5. Tablo C — precision/recall öncesi/sonrası.
6. Tablo D — uçtan uca gecikme + `vision/run.py`'da `publish` aşamasının
   medyan/p95 ms'si ve `--kafka` ile/olmadan gerçek FPS (yayın GPU
   döngüsüne ne kadar mal oluyor).

---

## 12. Kapsam dışı (bilinçli)

- **WebSocket / sarı ön-alarm** — Aşama 6.
- **`anomaly-events` tüketicisi, PostgreSQL/MongoDB yazımı, kanıt klibi** —
  Aşama 5. Bu aşamada olaylar yalnızca topic'e yazılır.
- **Eşiklerin veritabanından okunması ve sıcak yeniden yüklenmesi**
  (`settings_client.py`) — Aşama 5.
- **Çoklu kamera** — tek `camera_id` ile çalışılır; şema çoklu kameraya
  hazırdır (anahtar `camera_id:track_key`), ama ölçüm Aşama 10'dur.
- **Kafka güvenliği (SASL/TLS)** — tek makine, yerel ağ.
- **TCN / HybridArbiter** — Aşama 9.
