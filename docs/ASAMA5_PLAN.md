# Aşama 5 — Veri Katmanı ve API (uygulama sözleşmesi)

Bu dosya, Aşama 5'in kod uygulamasını üstlenecek alt ajan için tek bağlam
kaynağıdır. Alt ajan soğuk başlar: burada yazmayan şey yoktur sayılır.

Okuma sırası: `docs/PLAN.md` (§6 şema, §7 Aşama 5) → `docs/DURUM.md`
(Aşama 4 sonucu, karar günlüğü) → bu dosya.

**Ajana uyarı:** Ölçüm bölümündeki (§12) sayılar rapora girer. Kötü sayıyı
saklama, eşiği güzelleştirmek için oynatma, "muhtemelen çalışıyor" yazma.
Çalışmayan bir şey varsa çalışmadığını yaz.

---

## 0. Girdi durumu

Aşama 4 sonunda elimizde olan:

- `vision/publish.py` → `anomaly-candidates` topic'i (JSON, `schema: 1`)
- `stream/spark_job.py` → oturum penceresi süzgeci → `anomaly-events` topic'i
- `infra/postgres/init.sql` → 7 tablo, indexler, admin tohum kaydı, global
  `detection_settings` satırı
- `infra/mongo/init.js` → `pose_sequences`, `telemetry`, `camera_health`
- Docker: postgres (5433), mongo (27018), kafka (9092 host / 29092 iç), spark

Eksik olan: `anomaly-events` topic'ini **kimse okumuyor**. Spark doğrulanmış
olayı yazıyor ve orada kalıyor. Aşama 5 bu zincirin son halkasını kapatır ve
paneli besleyecek okuma uçlarını açar.

---

## 1. Bağımlılıklar

`api/requirements.txt` (yeni dosya, §10'daki gerekçeyle ayrı):

```
fastapi>=0.115
uvicorn[standard]>=0.32
sqlalchemy>=2.0
psycopg[binary]>=3.2      # SQLAlchemy 2.0 psycopg3 surucusu
pymongo>=4.9
pyjwt>=2.9
python-multipart>=0.0.9   # OAuth2PasswordRequestForm form govdesi
confluent-kafka>=2.5.0    # consumer; vision tarafiyla ayni istemci
httpx>=0.27               # testler (TestClient zaten httpx istiyor)
```

Kök `requirements.txt`'e yalnızca `httpx>=0.27` eklenir — `vision/settings_client.py`
onu kullanır.

**Eklenmeyenler ve nedeni:**

- `passlib` / `bcrypt` — gerek yok. Şifre hash'i `pgcrypto` ile veritabanında
  üretiliyor (`init.sql` admin tohumu `crypt(..., gen_salt('bf'))`). Doğrulama
  da aynı yerde yapılır (§3). Python tarafına ikinci bir bcrypt uygulaması
  sokmak, iki farklı hash yolu ve iki farklı hata kaynağı demektir.
- `alembic` — §2'de gerekçesiyle reddedildi.
- `pydantic-settings` — FastAPI zaten pydantic v2 getiriyor; 12 ortam
  değişkeni için `os.getenv` yeterli.

---

## 2. Alembic reddedildi — şema tek kaynak `init.sql`

PLAN.md Aşama 5 satırında "Alembic" yazıyor. Bu aşamada kurulmuyor. Gerekçe:

- Şema bugün `infra/postgres/init.sql` içinde yaşıyor ve o dosya çalışıyor.
  Alembic eklenirse şema iki yerde tanımlanır; ikisi kaçınılmaz olarak
  ayrışır ve hangisinin doğru olduğu belirsizleşir.
- Göç (migration) aracının değeri, **üzerinde veri olan** bir veritabanını
  yeniden kurmadan değiştirebilmektir. Şu an üretim verisi yok; şema
  değişince `docker compose down -v && up -d` yeterli.
- Gerçek göç ihtiyacı Aşama 9'da doğar (FIGHT/LOITERING sınıfları, TCN
  sütunları, birikmiş `telemetry` verisi). Alembic oraya ertelendi.

Yerine konan koruma: **`tests/test_schema_sync.py`** — canlı veritabanını
`sqlalchemy.inspect` ile yansıtır, `api/db/models.py` içindeki tablo ve sütun
adlarını karşılaştırır, fark varsa düşer. Veritabanı erişilemiyorsa
`pytest.skip` (CI'da DB olmayabilir). Bu test ~30 satırdır ve Alembic'in bu
aşamada verdiği tek gerçek faydayı (drift yakalama) verir.

`api/db/models.py` **`create_all` ÇAĞIRMAZ.** Tabloları `init.sql` yaratır;
modeller yalnızca var olan tabloları tarif eder.

---

## 3. Kimlik doğrulama — hash veritabanında kalır

`api/auth.py` (~90 satır).

**Şifre doğrulama** (Python'da bcrypt yok):

```sql
SELECT id, username, full_name, role, is_active
FROM users
WHERE username = :username
  AND password_hash = crypt(:password, password_hash)
```

`crypt(pw, mevcut_hash)` mevcut hash'in tuzunu kullanarak yeniden hash'ler.
Yeni şifre yazarken `crypt(:password, gen_salt('bf'))`.

**JWT:** PyJWT, HS256, `JWT_SECRET` ve `JWT_EXPIRE_MINUTES` ortamdan.
Gövde: `{"sub": str(user_id), "username": ..., "role": ..., "exp": ...}`.

**Bağımlılıklar (FastAPI `Depends`):**

- `current_user()` — `Authorization: Bearer` başlığını çözer, süresi geçmiş
  veya geçersiz imzada 401, `is_active=false` kullanıcıda 403.
- `require_role("admin", "operator")` — rol listesi dışındaysa 403.

**Rol matrisi** (uçlara §9'da işlenir):

| işlem | viewer | operator | admin |
|---|---|---|---|
| okuma uçları (GET) | ✓ | ✓ | ✓ |
| olay durumu değiştirme (ack / false_positive) | ✗ | ✓ | ✓ |
| kamera / bölge / eşik yazma | ✗ | ✗ | ✓ |

`last_login` başarılı girişte güncellenir.

---

## 4. Eşzamanlılık kararı — senkron SQLAlchemy

Uçlar `async def` değil **`def`** ile yazılır; FastAPI bunları otomatik olarak
iş parçacığı havuzunda çalıştırır. Gerekçe:

- Asenkron sürücü (`asyncpg` + `AsyncSession`) 4 kameralık bir sistemde
  ölçülebilir bir kazanç vermez; getirisi her sorguda `await`, ayrı oturum
  yönetimi ve ayrı test kurulumudur.
- `api/workers/consumer.py` zaten senkron bir Kafka döngüsüdür; aynı
  `sessionmaker`'ı paylaşabilmesi ikinci bir veri katmanı yazmayı önler.
- Aşama 6'nın WebSocket işleyicileri `async def` kalır; sıcak yolda
  veritabanına dokunmazlar, yani bu karar onları bağlamaz.

`api/db/postgres.py`: `create_engine(url, pool_pre_ping=True, pool_size=5)` +
`SessionLocal` + `get_db()` üreteç bağımlılığı.
`api/db/mongo.py`: tek `MongoClient`, `get_mongo()` bağımlılığı.

---

## 5. Kimlik eşlemesi — `camera_id` sözleşmesi

Kafka mesajındaki `camera_id` **metin**dir (`vision/run.py --camera-id`,
verilmezse klip dosya adı: `run_01`). `events.camera_id` ise `INT FK`.
Aradaki eşleme tüketicide çözülür:

```sql
SELECT id FROM cameras WHERE id::text = :cid OR name = :cid
```

Tek sorgu her iki kullanımı da karşılar: panelden tanımlanan kamera sayısal
id'siyle yayın yapar, pilot değerlendirmesi klip adıyla. Sonuç bellekte
sözlükte tutulur; **kaçırma durumunda** (yeni kamera eklenmiş) sözlük bir kez
tazelenir, yine bulunamazsa mesaj **atlanır**, `skipped_unknown_camera` sayacı
artar ve tek satır uyarı basılır. Otomatik kamera yaratılmaz — Kafka'ya
rastgele bir `camera_id` yazan biri veritabanına satır ekleyememelidir.

`zone_name` benzer şekilde `(camera_id, name)` ile `zones` tablosunda aranır.
Bulunamazsa **olay yine yazılır**, yalnızca `zone_id = NULL` olur. Bölge adı
kozmetik bir bağdır; olayın kendisi ondan bağımsızdır.

Pilot kliplerin veritabanı karşılığı için **`scripts/seed_pilot.py`** (~50
satır): `data/pilot/*.mp4` için `cameras` satırı açar (`name` = klip adı,
`source_type='file'`, `source` = klip yolu), `eval/zones.json` içindeki
poligonları ilgili kameranın `zones` satırlarına yazar, oluşan id'leri basar.
Tekrar çalıştırılabilir olmalı (var olan adı atla).

---

## 6. `api/workers/consumer.py` (yeni, ~140 satır)

`anomaly-events` → PostgreSQL `events` + MongoDB `telemetry`.

### 6.1 Tüketici ayarları

```python
Consumer({
    "bootstrap.servers": BOOTSTRAP,          # kafka:29092 (container ici)
    "group.id": "anomaly-event-consumer",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,             # SS6.4
})
```

`earliest`: tüketici Spark'tan sonra ayağa kalkabilir; aradaki olayların
kaybolmaması gerekir.

### 6.2 Mesaj → satır dönüşümü (saf fonksiyon)

`event_to_row(msg: dict, camera_id: int, zone_id: int | None) -> dict | None`
**veritabanına dokunmaz**, bu yüzden brokersız test edilebilir (§11).
Zorunlu alan eksikse `None` döner (mesaj atlanır), istisna fırlatmaz.

| `events` sütunu | kaynak |
|---|---|
| `camera_id` | §5 eşlemesi |
| `zone_id` | §5 eşlemesi (yoksa NULL) |
| `anomaly_type` | `msg["anomaly_type"]` |
| `track_ids` | `msg["track_ids"]` |
| `confidence` | `min(max(msg["score"], 0.0), 0.999)` — sütun `NUMERIC(4,3)` |
| `severity` | §6.3 tablosu |
| `decided_by` | sabit `"rule"` — TCN Aşama 9'da gelir |
| `started_at` | `datetime.fromtimestamp(msg["start_time"], tz=utc)` |
| `ended_at` | `datetime.fromtimestamp(msg["end_time"], tz=utc)` |
| `duration_ms` | `round(msg["duration_sec"] * 1000)` |
| `frame_path`, `clip_path`, `llm_report_tr`, `mongo_ref` | NULL — Aşama 6/7 |
| `status` | varsayılan `'new'` |

`start_time`/`end_time` epoch saniyedir (Spark `timestamp` → `double`).
`start_ts`/`end_ts` ise **sahne zamanıdır** (klip başından itibaren saniye) ve
`events`'e yazılmaz; `telemetry` belgesinde saklanır — pilot değerlendirmesi
klip zamanıyla eşleştirme yaparken bunu ister.

### 6.3 Şiddet (severity) eşlemesi

Sabit sözlük, tek yerde:

```python
SEVERITY = {
    "FALL": "critical", "FIGHT": "critical",
    "ZONE_VIOLATION": "high", "RUN_ZONE": "high",
    "RUN": "medium", "WRONG_DIRECTION": "medium",
    "LOITERING": "low",
}   # bilinmeyen tip -> "medium"
```

Skora göre kademelendirme **yapılmıyor**: kural skorları tipler arasında
karşılaştırılabilir bir ölçekte değil (her kural kendi eşiğine göre normalize
ediyor), bunu şiddete çevirmek uydurma bir hassasiyet olur.

### 6.4 Tekrar yazma koruması (idempotency)

Kafka en-az-bir-kez teslim eder; tüketici yeniden başlarsa aynı olay tekrar
gelir. İki katmanlı koruma:

1. `infra/postgres/init.sql` içine yeni index:

```sql
CREATE UNIQUE INDEX idx_events_dedup
    ON events (camera_id, anomaly_type, started_at, track_ids);
```

Spark oturum penceresi bir episodu tek satır olarak yazar, dolayısıyla bu
dörtlü doğal anahtardır.

2. `INSERT ... ON CONFLICT DO NOTHING RETURNING id`. Dönen id yoksa mesaj
   zaten işlenmiştir; `duplicates` sayacı artar, Mongo'ya da yazılmaz.

Offset **veritabanı yazımından sonra** elle commit edilir
(`consumer.commit(msg)`). Sıra tersine dönerse çökme anında olay kaybolur; bu
sırada ise en fazla tekrar gelir, onu da index eler.

### 6.5 MongoDB `telemetry` belgesi

Her doğrulanmış olay için (PLAN.md §6.2 şeması):

```python
{"camera_id": <int>, "track_id": <track_ids[0] veya None>, "event_id": <yeni id>,
 "window_start": <start_ts>, "window_end": <end_ts>,
 "metrics": msg["metrics"], "hits": msg["hits"],
 "rule_verdict": {"type": ..., "score": ..., "thresholds_used": msg["thresholds_used"]},
 "model_verdict": None, "arbiter": "rule",
 "spark_verdict": "confirmed", "created_at": <utcnow>}
```

`pose_sequences` bu aşamada **yazılmaz** ve `events.mongo_ref` NULL kalır:
ham keypoint dizisi Kafka mesajında yok, `vision/` sürecinin belleğindedir.
Onu taşımanın yeri kanıt üretimidir (Aşama 6, halka tampon).

### 6.6 Dayanıklılık

Görü hattı gibi tüketici de tek bir kötü mesaj yüzünden durmaz: JSON çözme
veya alan hatasında mesaj atlanır, `malformed` sayacı artar, offset commit
edilir (aynı bozuk mesajı sonsuza kadar tekrar denemek anlamsızdır).
Veritabanı hatası **farklıdır**: commit edilmez, oturum geri alınır, üstel
geri çekilmeyle yeniden denenir — geçici bağlantı kopması yüzünden olay
kaybedilmemelidir.

`SIGTERM`/`SIGINT` ile temiz kapanış (`consumer.close()`), kapanışta sayaç
özeti basılır.

---

## 7. `vision/settings_client.py` (yeni, ~90 satır) — eşik sıcak yükleme

**Ne yapar:** API'den kamera eşiklerini periyodik çeker ve çalışan
`RuleEngine.thresholds` nesnesini değiştirir. Pipeline yeniden başlamaz.

```python
class SettingsClient:
    def __init__(self, base_url: str, camera_id: str, engine: RuleEngine,
                 interval: float = 5.0, token: str | None = None) -> None: ...
    def start(self) -> None: ...   # arka plan daemon thread
    def stop(self) -> None: ...
    # sayaclar: applied, failures, last_error, last_updated_at
```

**Sıcak yüklemenin sınırı — açıkça yazılacak.** Yalnızca kural eşikleri canlı
değişir:

`fall_tilt_deg`, `fall_norm_vy`, `run_norm_speed`, `run_gait_speed`,
`loiter_sec`, `fight_proximity`

Şunlar **yeniden başlatma ister** ve API yanıtında `"restart_required"`
listesinde döner: `pose_conf`, `track_conf` (model/tracker kurulumunda
donuyor), `window_frames` (FeatureEngine halka tamponunun boyu). Panel bu
alanları değiştirdiğinde kullanıcıya "yeniden başlatma gerekir" uyarısı
gösterebilsin diye liste yanıtın içindedir.

**Atomik uygulama:** yeni bir `Thresholds` nesnesi kurulur ve
`engine.thresholds = yeni` ile tek atamada takılır. `RuleEngine.__call__` her
çağrıda `self.thresholds` okuduğu için yarı uygulanmış eşik kümesi görülemez;
kilide gerek yoktur (CPython'da nitelik ataması atomiktir).

**Asla düşürmez:** ağ hatası, 401, bozuk JSON — hepsinde son bilinen eşikler
korunur, `failures` artar, hata metni saklanır. API kapalıyken görü hattı
varsayılan eşiklerle çalışmayı sürdürür.

`updated_at` alanı değişmediyse yeni nesne kurulmaz (gereksiz iş yok).

`vision/run.py` bağlaması (+ ~20 satır):

```
--settings-url http://localhost:8000   (bos = sicak yukleme kapali, varsayilan)
--settings-interval 5.0
--settings-token <JWT>                 (bos = uc anonim okunabiliyorsa gerekmez)
```

Kapanışta `stop()` ve son rapor satırı: `settings: N kez uygulandi, M hata`.

---

## 8. `api/` dosya düzeni ve satır bütçesi

PLAN.md hedefi: aşama başına dosya < 150 satır.

```
api/
├── main.py              ~70   FastAPI kurulumu, router kaydi, CORS, /health
├── config.py            ~35   os.getenv sarmalayici, tek yerde URL'ler
├── auth.py              ~90   JWT, current_user, require_role
├── schemas.py          ~140   pydantic v2 govdeleri (istek/yanit)
├── audit.py             ~35   audit_log yazan yardimci
├── db/
│   ├── postgres.py      ~40   engine, SessionLocal, get_db
│   ├── mongo.py         ~30   MongoClient, get_mongo
│   └── models.py       ~150   SQLAlchemy 2.0 mapped siniflar (7 tablo)
├── routers/
│   ├── auth.py          ~60
│   ├── cameras.py       ~90
│   ├── zones.py        ~100
│   ├── settings.py      ~90
│   ├── events.py       ~110
│   └── analytics.py     ~90
└── workers/
    └── consumer.py     ~140
```

`api/__init__.py` ve alt paketlerin `__init__.py` dosyaları boş.

---

## 9. Uç sözleşmesi

Tümü `/api` önekiyle. Yanıtlar pydantic modelleridir
(`model_config = ConfigDict(from_attributes=True)`).

### 9.1 auth

| yöntem | yol | rol | not |
|---|---|---|---|
| POST | `/api/auth/login` | — | `OAuth2PasswordRequestForm` → `{access_token, token_type, user}` |
| GET | `/api/auth/me` | herkes | jetondaki kullanıcının güncel satırı |

Hatalı kullanıcı adı ile hatalı şifre **aynı** 401 mesajını döndürür
("kullanici adi veya sifre hatali") — hangi kullanıcının var olduğu
sızdırılmaz.

### 9.2 cameras

`GET /api/cameras` (filtre: `is_active`), `GET /api/cameras/{id}`,
`POST` / `PUT` / `DELETE /api/cameras/{id}` (admin).

`source_type` doğrulaması pydantic `Literal["webcam","file","rtsp"]` ile;
veritabanı CHECK'ine ikinci kez güvenmek yerine 422 dönmek daha okunur bir
hatadır.

`PATCH /api/cameras/{id}/heartbeat` — `status` + `last_seen_at` günceller
(Aşama 6'da `vision/` çağıracak, uç şimdi açılır).

### 9.3 zones

`GET /api/zones?camera_id=`, `POST`, `PUT`, `DELETE` (admin).

**Poligon doğrulaması** (pydantic validator, tek yer): en az 3 nokta, her
nokta 2 sayı, **her koordinat 0.0–1.0 aralığında**. Aralık dışı değer 422.
Bu doğrulama olmadan panel piksel koordinatı gönderdiğinde bölge sessizce
kadrajın dışına düşer — v1'de aynı hata vardı ve `zone_01` yanlış
pozitiflerinin kaynağı buydu (bkz. `docs/DURUM.md`).

`zone_type='direction'` ise `direction_vector` zorunlu, aksi halde yasak.

### 9.4 settings

| yöntem | yol | rol | not |
|---|---|---|---|
| GET | `/api/settings` | herkes | global satır (`camera_id IS NULL`) |
| GET | `/api/settings/{camera_id}` | herkes | **birleştirilmiş**: kamera satırı varsa o, yoksa global |
| PUT | `/api/settings/{camera_id}` | admin | kamera satırını upsert eder |
| PUT | `/api/settings` | admin | global satırı günceller |

Yanıt gövdesi eşiklerin yanında şunları taşır:

```json
{"camera_id": 3, "source": "camera",
 "updated_at": "...", "restart_required": ["pose_conf","track_conf","window_frames"],
 "pose_conf": 0.25, "run_norm_speed": 1.80, "...": "..."}
```

`source` alanı (`"camera"` | `"global"`) panelde "bu kamera globali mi
kullanıyor" sorusunu cevaplar; `settings_client` ise `updated_at` ile
değişiklik olup olmadığını anlar.

Yazma uçları `updated_by` ve `updated_at` alanlarını doldurur ve `audit_log`'a
satır yazar.

### 9.5 events

`GET /api/events` filtreleri: `camera_id`, `anomaly_type`, `status`,
`severity`, `decided_by`, `from`, `to`, `limit` (varsayılan 50, tavan 500),
`offset`. Sıralama `started_at DESC`. Yanıt `{"total": N, "items": [...]}`.

Filtre kümesi `idx_events_camera_time` ve `idx_events_time` indexleriyle
uyumludur; `total` için ayrı `COUNT(*)` sorgusu atılır.

`GET /api/events/{id}` — olay + kamera adı + bölge adı + `telemetry` belgesi
(Mongo'dan, varsa).

`PATCH /api/events/{id}` (operator+) — yalnızca `status` değiştirir
(`acknowledged` / `false_positive` / `resolved`), `acked_by` ve `acked_at`
doldurur, `audit_log` yazar. `new` dışına çıkmış bir olay tekrar `new`
yapılamaz.

### 9.6 analytics

`GET /api/analytics/summary?from=&to=&camera_id=` →

```json
{"total": 42,
 "by_type":     [{"anomaly_type": "FALL", "count": 7}],
 "by_severity": [{"severity": "critical", "count": 9}],
 "by_status":   [{"status": "new", "count": 30}],
 "by_camera":   [{"camera_id": 3, "name": "Ana Giris", "count": 12}],
 "by_hour":     [{"hour": "2026-08-27T14:00:00Z", "count": 3}]}
```

`by_hour` `date_trunc('hour', started_at)` ile gruplanır — Recharts'ın
doğrudan tüketeceği biçim.

`GET /api/analytics/ablation` — `decided_by` × `anomaly_type` × `status`
kırılımı. Tez ablation tablosunun kaynağıdır; şu an tüm satırlar `rule`
olacak, Aşama 9'dan sonra anlamlanır. Uç şimdi açılır çünkü şeması bugünden
bellidir.

### 9.7 sistem

`GET /health` — kimlik istemez, `{"status": "ok", "postgres": true,
"mongo": true}`. Docker healthcheck ve panelin "sistem sağlığı" ekranı bunu
kullanır. Kontrol hafif olmalı (`SELECT 1`, `ping`).

---

## 10. Docker

`api/Dockerfile` — `python:3.11-slim`, `api/requirements.txt` kurar.

**Karar:** kök `requirements.txt` görü yığınını (torch, ultralytics,
onnxruntime-gpu) içeriyor ve API'nin bunların hiçbirine ihtiyacı yok. Ayrı bir
`api/requirements.txt`, 2 GB'lık gereksiz bir imajdan ucuzdur.

`docker-compose.yml`'e iki servis:

```yaml
  api:
    build: ./api
    container_name: anomaly-api
    depends_on: {postgres: {condition: service_healthy},
                 mongo:    {condition: service_healthy}}
    environment: DATABASE_URL, MONGO_URL, MONGO_DB, JWT_SECRET, JWT_EXPIRE_MINUTES
    ports: ["${API_PORT:-8000}:8000"]
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000
    healthcheck: python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"

  consumer:
    build: ./api            # ayni imaj, farkli komut
    container_name: anomaly-consumer
    depends_on: {postgres: healthy, mongo: healthy, kafka: healthy}
    environment: DATABASE_URL, MONGO_URL, MONGO_DB, KAFKA_BOOTSTRAP=kafka:29092
    command: python -m api.workers.consumer
```

İmaj bağlamı `./api` olduğu için `api` paketi imajda `/app/api` altına
kopyalanır (`WORKDIR /app`, `COPY . /app/api`), böylece `api.main:app` ve
`python -m api.workers.consumer` çalışır.

`.env.example`: `API_PORT=8000`, `DATABASE_URL`, `MONGO_URL` eklenir. Tek
tanım noktası `api/config.py`; ortamda yoksa mevcut `POSTGRES_*` / `MONGO_*`
değişkenlerinden kurulur.

`vision/` host'ta kaldığı için API'ye `http://localhost:8000` üzerinden
ulaşır — bu zaten `--settings-url` için önerilen değerdir.

---

## 11. Testler (`tests/`, brokersız ve DB'siz koşan kısım)

Mevcut düzen korunur: saf fonksiyonlar test edilir, altyapı test edilmez.

`tests/test_consumer.py` (~90 satır)
- `event_to_row`: tam bir `anomaly-events` mesajı → beklenen sözlük (zaman
  dönüşümü, `duration_ms`, `confidence` kırpma, severity eşlemesi)
- bilinmeyen `anomaly_type` → `severity="medium"`, hata yok
- eksik alanlı mesaj → `None` döner, istisna fırlatmaz
- `score=1.5` gibi aralık dışı skor `0.999`a kırpılır (sütun `NUMERIC(4,3)`
  taşarsa INSERT patlar)

`tests/test_api_units.py` (~90 satır)
- JWT üret → çöz → aynı `sub`/`role`; süresi geçmiş jeton reddedilir
- poligon doğrulayıcı: 2 nokta → hata, `[1.4, 0.2]` → hata, geçerli → geçer
- eşik birleştirme: kamera satırı yoksa global döner, varsa kamera döner,
  `source` alanı doğru
- `SettingsClient` uygulama fonksiyonu: kısmi/bozuk JSON'da eski eşikler
  korunur, `failures` artar

`tests/test_schema_sync.py` (~30 satır) — §2, DB yoksa `skip`.

---

## 12. Zorunlu ölçümler (rapora ve `docs/DURUM.md`'ye girer)

Ajan bunları çalıştırır ve **ham çıktıyı** rapor eder. Sayı kötüyse kötü
yazılır.

1. **Uçtan uca zincir.** `docker compose up -d` → `scripts/seed_pilot.py` →
   beş pilot klip için
   `python -m vision.run --source data/pilot/<klip>.mp4 --rules --zones eval/zones.json --kafka --camera-id <klip>`
   → `SELECT anomaly_type, camera_id, started_at, duration_ms FROM events ORDER BY started_at;`
   çıktısı **olduğu gibi** rapora yazılır.
   **Beklenen:** Aşama 4'te ölçülen 5 doğrulanmış olayın veritabanındaki
   karşılığı. Sayı 5 değilse nerede kaybolduğu araştırılır (Spark mı yazmadı,
   tüketici mi atladı, `camera_id` mi eşleşmedi) — sayı düzeltilmez, sebep
   yazılır.
2. **Tekrar yazma koruması.** Aynı `anomaly-events` mesajı elle iki kez
   üretilir (`scripts/check_kafka.py` deseniyle). `events` satır sayısı
   değişmemeli; `duplicates` sayacı 1 olmalı.
3. **Sıcak yükleme gecikmesi.** Pipeline koşarken `PUT /api/settings/{id}` ile
   `run_norm_speed` değiştirilir; `settings_client`'ın yeni değeri uyguladığı
   ana kadar geçen süre ölçülür. Beklenen: yoklama aralığı (5 sn)
   mertebesinde. **Pipeline yeniden başlamamalıdır** — FPS sayacının ve iz
   id'lerinin sürekliliği bunun kanıtıdır, rapora yazılır.
4. **Uç gecikmeleri.** 1000 sentetik olay satırıyla `GET /api/events?limit=50`
   ve `GET /api/analytics/summary` için p50/p95 (10 ardışık istek yeterli).
5. **Swagger.** `/docs` üzerinden her uç bir kez çağrılır; çalışmayan uç varsa
   listelenir.

---

## 13. Kapsam dışı (bilinçli, Aşama 5'te YAPILMAYACAK)

- WebSocket (`ws/live.py`, `ws/meta.py`, `ws/alerts.py`) — Aşama 6
- Kanıt üretimi: mp4 klip, en iyi kare, `pose_sequences`, `events.mongo_ref`
  — Aşama 6 (halka tampon `vision/` içindedir)
- LLM raporu (`llm_report_tr`) ve Telegram (`notifications` tablosu) — Aşama 7
- Frontend bağlama — Aşama 8 (`sablon/` altındaki HTML şablonları hazır, bu
  aşamada dokunulmaz)
- Alembic — Aşama 9 (§2)
- `decided_by` değerinin `model`/`hybrid` olabilmesi — Aşama 9
- `camera_health` koleksiyonuna yazım — Aşama 6 (kaynağı `vision/` döngüsüdür)
- Kullanıcı yönetimi CRUD'u — yalnızca `admin` tohum kaydı ve `/auth/me`
  vardır; panelin kullanıcı ekranı Aşama 8'de gerektiğinde açılır
