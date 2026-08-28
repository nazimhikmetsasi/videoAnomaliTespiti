# Aşama 6 — Canlı Görüntü ve Kanıt (uygulama sözleşmesi)

Bu dosya, Aşama 6'nın kod uygulamasını üstlenecek alt ajan için tek bağlam
kaynağıdır. Alt ajan soğuk başlar: burada yazmayan şey yoktur sayılır.

Okuma sırası: `docs/PLAN.md` (§4 veri hattı, §7 Aşama 6) → `docs/DURUM.md`
(Aşama 5 sonucu, bilinen sınırlar, karar günlüğü) → bu dosya.

**Ajana uyarı:** §12'deki sayılar rapora girer. Kötü sayıyı saklama, eşiği
güzelleştirmek için oynatma, "muhtemelen çalışıyor" yazma. Çalışmayan bir şey
varsa çalışmadığını yaz.

---

## 0. Girdi durumu

Aşama 5 sonunda çalışan zincir:

```
vision/ (host, GPU)  ->  Kafka anomaly-candidates  ->  Spark oturum penceresi
   ->  anomaly-events  ->  api/workers/consumer.py  ->  PostgreSQL + MongoDB
   ->  REST API (14 uç, JWT)
```

Elimizde olan ve bu aşamada kullanılacak parçalar:

- `vision/source.py` — `VideoSource`, **300 karelik halka tampon** ve
  `snapshot() -> list[Frame]` (kanıt klibinin kaynağı budur, yeniden
  yazılmayacak)
- `vision/run.py` — ana döngü; kare, `Track` listesi, `Candidate` listesi ve
  aşama süreleri burada zaten mevcut
- `vision/settings_client.py` — API'den eşik çeken arka plan iş parçacığı
  (aynı desen kalp atışı için tekrar kullanılacak)
- `api/` — FastAPI, JWT (`api/auth.py`), SQLAlchemy modelleri, tüketici
- `sablon/canl_i_zleme_vadap_kontrol_paneli/` — panelin canlı ekranı: 2×2
  kamera ızgarası, **Kutu / İskelet / Bölge / ID** katman düğmeleri, kamera
  başına FPS rozeti ve durum etiketi, sağda canlı olay akışı, üstte kritik
  alarm bandı. Bu aşamanın ürettiği akışlar o ekranı besleyecek

Eksik olan: panel canlı kareyi göremiyor. Olay veritabanına düşüyor ama
`frame_path`, `clip_path`, `mongo_ref` NULL; operatör olayı **göremeden**
sadece satır olarak okuyor.

---

## 1. En kritik karar: kare akışını kim sunar

**Kareyi `vision/` süreci doğrudan sunar. API'ye taşınmaz.**

Aşama 5'te ölçüldü (`docs/DURUM.md`, Ölçüm 4): aynı uç konteyner içinden
18–41 ms, Windows host'tan 594–754 ms. Aradaki ~600 ms Docker Desktop'ın
port yönlendirmesidir. Kareyi API üzerinden geçirmek, **saniyede 20–25 kez**
o hattı kullanmak demektir; PLAN.md'nin 300 ms uçtan uca hedefi tek başına
bu hop yüzünden tutmaz. Kare zaten `vision/` sürecinin belleğindedir;
oradan tarayıcıya doğrudan gitmesi hem en kısa hem en az kopyalı yoldur.

Sonuç:

| akış | sunan | adres |
|---|---|---|
| `/ws/live/{camera_id}` ikili JPEG | **vision** (host) | `ws://localhost:8001` |
| `/ws/meta/{camera_id}` JSON | **vision** (host) | `ws://localhost:8001` |
| `/ws/alerts` kırmızı alarm | **api** (Docker) | `ws://localhost:8000` |

Sarı ön-alarm meta akışının içindedir (aday anında, süzgeçten geçmemiş).
Kırmızı alarm Spark'tan geçmiş olaydır ve veritabanına yazıldıktan sonra
API'den duyurulur. PLAN.md'nin iki kademeli alarm tasarımı budur.

**Bedeli dürüstçe yazılıyor:** panel iki ayrı origin'e bağlanır. Sunucuya
taşındığında (PLAN.md §2, `vision/` de container'a alınır) tek reverse proxy
arkasında birleşirler; bugün Windows'ta GPU container'a verilemediği için
bölünme zaten mevcut mimarinin bir sonucudur, yeni bir borç değildir.

---

## 2. Bağımlılıklar

Kök `requirements.txt`'e:

```
websockets>=13.0     # vision/ WebSocket sunucusu; saf Python, C uzantisi yok
pymongo>=4.9         # vision/ pose_sequences'i dogrudan yazar (SS6)
```

`api/requirements.txt` değişmiyor: FastAPI WebSocket'i çekirdekte destekler.

Eklenmeyenler: Redis / ZeroMQ / paylaşımlı bellek — kare zaten üretildiği
process'ten sunuluyor, aradan geçirilecek bir kuyruk yok.

---

## 3. `vision/ws_server.py` (yeni, ~140 satır)

Ana görü döngüsünden **ayrı bir iş parçacığında** kendi asyncio döngüsünü
çalıştıran WebSocket sunucusu.

```python
class StreamServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8001,
                 jwt_secret: str | None = None) -> None: ...
    def start(self) -> None: ...          # arka plan daemon thread
    def stop(self) -> None: ...
    def publish_frame(self, camera_id: str, jpeg: bytes) -> None: ...
    def publish_meta(self, camera_id: str, meta: dict) -> None: ...
    @property
    def live_clients(self) -> int: ...    # kamera basina bagli istemci sayisi
```

**Görü döngüsü ASLA bloklanmaz.** `publish_*` çağrıları kamera başına tek
elemanlı bir "son değer" kutusuna yazar (`dict[str, bytes]` + `Event`), asyncio
tarafı oradan okur. Yavaş bir istemci yüzünden kare biriktirilmez, **en yeni
kare kazanır** — `vision/source.py`'nin canlı kaynak kuralının aynısı
(`docs/DURUM.md` karar günlüğü, 2026-08-24).

**Kimlik doğrulama:** bağlantı `?token=<JWT>` ile açılır. Jeton `api/auth.py`
ile aynı `JWT_SECRET` ve HS256 kullanılarak **yerel** doğrulanır; veritabanına
gidilmez (görü hattı API'ye bağımlı hale gelmemeli). Jeton yok/geçersizse
bağlantı 1008 (policy violation) ile kapatılır. `JWT_SECRET` ortamdan okunur;
yoksa sunucu **açılmaz** ve tek satır uyarı basar — sessizce kimliksiz yayın
yapmak kabul edilemez.

**Kare kodlama sadece dinleyen varken yapılır.** `live_clients == 0` iken JPEG
kodlaması hiç çağrılmaz (§4). Panel kapalıyken görü hattı bugünkü hızında
kalır.

---

## 4. `vision/run.py` bağlaması (+ ~60 satır)

Yeni argümanlar:

```
--ws                          WebSocket sunucusunu ac (varsayilan kapali)
--ws-port 8001
--jpeg-quality 70             baslangic kalitesi (adaptif, SS4.2)
--evidence                    kanit uretimini ac (SS5)
--storage-dir storage         klip ve kare kok dizini
--heartbeat-sec 5             0 = kapali (SS7)
```

### 4.1 Meta gövdesi (`/ws/meta`)

Kare başına bir JSON. Panelin katman düğmeleri (Kutu / İskelet / Bölge / ID)
bu gövdedeki alanları açıp kapatır; **overlay piksele yakılmaz** (PLAN.md
zayıf nokta 11).

```json
{
  "schema": 1,
  "camera_id": "3",
  "frame_idx": 1042,
  "ts": 1756300000.42,
  "width": 960, "height": 540,
  "fps": 24.8,
  "tracks": [
    {"id": 7, "bbox": [x1, y1, x2, y2], "conf": 0.91,
     "kp": [[x, y, c], ...17],
     "has_pose": true}
  ],
  "zones": [{"name": "bina girisi", "type": "forbidden",
             "polygon": [[0.30, 0.26], ...]}],
  "pre_alarms": [{"type": "RUN", "track_ids": [7], "score": 0.83}],
  "stage_ms": {"pre": 1.2, "infer": 21.4, "track": 8.1, "rules": 0.6}
}
```

Kurallar:

- `bbox` **piksel**, işlenen kare uzayında (960×540); `width`/`height` ile
  birlikte gönderildiği için istemci ölçekler.
- `zones` **0–1 normalize** kalır (veritabanındaki hâli).
- `kp` yalnızca `has_pose` doğruyken doldurulur; pozsuz iz `null` alır —
  "pozsuz iz takipte gösterilir ama anomali üretmez" kuralının panele yansıması.
- `pre_alarms` **süzgeçten geçmemiş** adaydır; panel bunu SARI gösterir.
  Kırmızı yalnızca `/ws/alerts`'ten gelir.

### 4.2 Adaptif JPEG kalitesi

Kodlama süresi ölçülür (`cv2.imencode`). Basit kural, tek yerde:

```
kodlama + yayin toplami > 8 ms  ->  kalite -5 (taban 40)
                        < 4 ms  ->  kalite +5 (tavan 85)
```

Amaç bir hedef bant genişliği tutturmak değil, **görü döngüsünün FPS'ini
korumaktır**: kalite düştüğünde tespit kalitesi etkilenmez, çünkü kodlanan
şey yalnızca gösterim kopyasıdır — çıkarım ham kare üzerinde yapılır.

`ponytail:` yorumu düşülecek: sabit adım (5) ve sabit eşikler (4/8 ms) kaba
bir denetleyicidir; istemci başına bant genişliği ölçümü gerekirse buraya
girer.

---

## 5. `vision/evidence.py` (yeni, ~140 satır) — kanıt üretimi

### 5.1 Epizot kavramı

`vision/` bir olayın *doğrulandığını* bilemez (doğrulama Spark'ta, 1–3 sn
sonra). Ama kendi ürettiği adayları izleyerek **epizot** kurabilir:
`(camera_id, track_key, anomaly_type)` üçlüsü için adaylar akarken epizot
açıktır; `spark_window_sec` kadar (varsayılan 3 sn) yeni aday gelmezse
epizot kapanır.

Bu, Spark'ın `session_window`'unun yerel ikizidir. **Eşik mantığı
kopyalanmaz** — `stream/filters.py` zaten tek referans kopyadır ve epizot
kapanışında `session_passes()` ile aynı ölçüt uygulanır. Geçmeyen epizot için
kanıt üretilmez (diske çöp yazılmaz).

### 5.2 Klip ve en iyi kare

Epizot kapanınca:

1. `source.snapshot()` ile halka tampon okunur (300 kare ≈ 10–12 sn).
2. Epizodun `[start_ts - 5, end_ts + 5]` aralığına düşen kareler seçilir.
   Tampon 300 kareyle sınırlı olduğu için **uzun epizotta klip kırpılır**;
   kırpıldığı `clip_truncated: true` ile bildirilir, sessizce kısaltılmaz.
3. `cv2.VideoWriter` (mp4v) ile `storage/clips/{camera}_{type}_{start}.mp4`.
4. **En iyi kare:** epizottaki **en yüksek skorlu adayın** karesi.
   `storage/frames/{camera}_{type}_{start}.jpg`, kalite 90.
   `ponytail: en yuksek skor = en iyi kare varsayimi. Bulaniklik (Laplacian
   varyansi) veya poz tamlik olcutu gerekirse buraya girer.`
5. Keypoint dizisi MongoDB `pose_sequences` koleksiyonuna yazılır (§6),
   dönen `ObjectId` kanıt bildiriminde taşınır.
6. `POST /api/evidence` (§8.1) ile kanıt bildirilir.

Yazma işi **ayrı bir iş parçacığında** yapılır: mp4 kodlama yüzlerce
milisaniye sürer, görü döngüsü bunu beklememelidir. Kuyruk dolarsa
(varsayılan 8 epizot) en eskisi düşürülür ve `dropped` sayacı artar.

### 5.3 Depolama düzeni

```
storage/
├── clips/{camera_id}_{anomaly_type}_{start_ts_ms}.mp4
├── frames/{camera_id}_{anomaly_type}_{start_ts_ms}.jpg
└── gallery/          # Asama 9 (olay bazli ReID), bu asamada bos
```

`storage/` `.gitignore`'a eklenir. `docker-compose.yml`'de `api` servisine
**salt okunur** bağlanır (`./storage:/storage:ro`): dosyaları host'taki
`vision/` yazar, API yalnızca sunar.

---

## 6. `pose_sequences` — kim yazar

**`vision/` doğrudan MongoDB'ye yazar** (host'tan `localhost:27018` zaten
açık). Gerekçe: ham dizi 17 nokta × N kare × 3 sayıdır; bunu HTTP gövdesinde
API'ye taşımak, Aşama 5'te ölçülen ~600 ms'lik host→container hattından
megabaytlarca veri geçirmek demektir. Belge şeması PLAN.md §6.2'dir:

```python
{"event_id": None,            # SS8.2'de tuketici dolduracak
 "camera_id": <int|str>, "track_id": <int>, "anomaly_type": "FALL",
 "fps": 25,
 "frames": [{"idx": 0, "ts": <epoch>, "bbox": [...],
             "kp": [[x, y, c], ...17], "kp_smoothed": [[x, y, c], ...17]}],
 "normalization": {"origin": "mid_hip", "scale": "bbox_height"},
 "created_at": <utcnow>}
```

`kp` ham, `kp_smoothed` One-Euro sonrası. İkisi birlikte saklanır çünkü
Aşama 9'un TCN eğitimi hangisinin daha iyi çalıştığını ölçecek.

Mongo erişilemezse: kanıt üretimi **durmaz**, `mongo_ref` `None` gider,
sayaç artar. Klip ve kare yine yazılır.

---

## 7. Kalp atışı ve `camera_health`

`vision/run.py` içinde, `settings_client` ile aynı desende
(`vision/health_client.py`, ~60 satır) `--heartbeat-sec` aralığında:

1. `PATCH /api/cameras/{id}/heartbeat` → `status="online"`, `last_seen_at`
   (uç Aşama 5'te açıldı, çağıran yoktu).
2. MongoDB `camera_health` belgesi: `{camera_id, ts, fps_actual, dropped,
   infer_ms, gpu_mem, queue_depth}`.

`gpu_mem`: `torch.cuda.memory_reserved()` (ek bağımlılık yok).
`dropped`: `VideoSource`'un düşürdüğü kare sayacı.

Hata durumunda: sayılır, yutulur, görü döngüsü etkilenmez — `settings_client`
ile aynı sözleşme.

---

## 8. API tarafı

### 8.1 `POST /api/evidence` (yeni, `api/routers/evidence.py` ~90 satır)

Gövde:

```json
{"camera_id": "3", "anomaly_type": "FALL", "track_key": "7",
 "start_time": 1756300000.0, "end_time": 1756300002.5,
 "frame_path": "frames/3_FALL_1756300000000.jpg",
 "clip_path":  "clips/3_FALL_1756300000000.mp4",
 "clip_truncated": false,
 "mongo_ref": "665f1c2a9b3e4d5a6c7b8d9e"}
```

Yol değerleri `storage/` köküne **göreli** yazılır; mutlak host yolu
veritabanına girmez (container başka yerde bağlıyor).

Yetki: `require_role("admin", "operator")` — `vision/` servis jetonu admin
kullanıcısıyla alınır.

### 8.2 Kanıt ile olayın buluşması

Sıra garantisi yoktur: `vision/` kanıtı epizot biter bitmez gönderir, olay
satırı ise Spark gecikmesinden sonra doğar. **İki yön de denenir:**

1. `POST /api/evidence` geldiğinde: aynı `(camera_id, anomaly_type)` ve
   `|started_at - start_time| <= 3 sn` olan olay satırı aranır. Bulunursa
   `frame_path`/`clip_path`/`mongo_ref` doldurulur, `pose_sequences.event_id`
   güncellenir.
2. Bulunamazsa satır yeni `evidence` tablosuna yazılır (`event_id` NULL).
3. `api/workers/consumer.py` bir olay eklerken aynı toleransla bekleyen
   `evidence` satırını arar; bulursa olayı onunla doldurur ve kanıdı bağlar.

3 sn toleransı `spark_window_sec` ile aynıdır ve gerekçesi odur: aynı
epizodun iki ucu arasındaki en büyük fark oturum boşluğudur.

Eşleşmeyen kanıt satırı **silinmez**; `GET /api/evidence?unmatched=true` ile
listelenir. Eşleşmeme bir hata belirtisidir (klip adı, saat kayması, kamera
eşlemesi) ve görünür kalmalıdır.

`infra/postgres/init.sql`'e yeni tablo:

```sql
CREATE TABLE evidence (
    id             BIGSERIAL PRIMARY KEY,
    event_id       BIGINT REFERENCES events(id) ON DELETE CASCADE,
    camera_id      INT NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    anomaly_type   VARCHAR(30) NOT NULL,
    track_key      VARCHAR(50) NOT NULL,
    started_at     TIMESTAMPTZ NOT NULL,
    ended_at       TIMESTAMPTZ,
    frame_path     TEXT,
    clip_path      TEXT,
    clip_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    mongo_ref      VARCHAR(24),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_evidence_match ON evidence (camera_id, anomaly_type, started_at);
CREATE INDEX idx_evidence_event ON evidence (event_id);
```

**Uyarı (Aşama 5 hatası tekrar etmesin):** `init.sql` yalnızca boş veri
diziniyle çalışır. Çalışan veritabanına bu tablo **elle** uygulanmalı, aksi
halde API 500 verir. Rapora hangi yolun seçildiği yazılacak
(`docker compose down -v` mi, elle `CREATE TABLE` mi).

### 8.3 Kanıt dosyalarının sunumu

`GET /api/events/{id}/clip` ve `GET /api/events/{id}/frame` — `FileResponse`.
Yol veritabanından okunur, `storage/` köküyle birleştirilir ve **kökün
dışına çıkmadığı doğrulanır** (`Path.resolve().is_relative_to(root)`); yol
gövdesi dışarıdan gelen bir değerdir, doğrudan dosya sistemine verilemez.
Dosya yoksa 404.

### 8.4 `/ws/alerts` (yeni, `api/ws/alerts.py` ~90 satır + `api/ws/manager.py` ~50)

Kırmızı alarm yayını. Kaynak olarak **ikinci bir Kafka tüketicisi** kullanılır
(`anomaly-events`, `group.id="anomaly-ws-alerts"`), API açılışında başlar.

Gerekçe: `consumer` ile `api` ayrı container'lardır; aralarına bir kanal
(Redis pub/sub, HTTP callback) icat etmek yerine **zaten var olan** Kafka
topic'i ikinci kez okunur. Farklı `group.id` sayesinde iki tüketici
birbirinin offset'ini bozmaz.

Gövde: olayın kendisi + `camera_name`. Alarm WS'i veritabanı yazımını
beklemez; panel satır detayını `GET /api/events` ile ayrıca çeker.

`manager.py`: bağlı istemci kümesi, yayın (`broadcast`), kopan bağlantının
temizlenmesi. Tek sınıf, iki metot; `/ws/alerts` bugün tek kullanıcısıdır.

---

## 9. `spark_min_sec` bağlanması (Aşama 5 bilinen sınır 5)

`stream/spark_job.py` açılışta `GET /api/settings` (global satır) çağırır ve
`spark_min_sec` / `spark_min_hits` / `spark_window_sec` değerlerini oradan
alır; API'ye ulaşamazsa **mevcut ortam değişkeni varsayılanlarına** düşer ve
tek satır uyarı basar. `urllib.request` kullanılır — Spark imajına yeni
paket girmez.

**Sınır açıkça yazılacak:** bu değerler streaming DAG'ine gömülür; çalışırken
değişmezler. Panelden değiştirilen `spark_min_sec` ancak Spark yeniden
başlayınca geçerli olur. Sıcak yükleme yalnız kural eşiklerindedir (Aşama 5,
§7) ve öyle kalıyor — akış sorgusunun ortasında pencere ölçütünü değiştirmek
checkpoint uyumsuzluğu demektir.

---

## 10. Dosya düzeni ve satır bütçesi

```
vision/
├── ws_server.py        ~140   WebSocket sunucusu (ayri thread + asyncio)
├── evidence.py         ~140   epizot, klip, en iyi kare, pose_sequences
├── health_client.py     ~60   kalp atisi + camera_health
└── run.py           +~60      baglama (--ws, --evidence, --heartbeat-sec)

api/
├── ws/manager.py        ~50   bagli istemci kumesi, broadcast
├── ws/alerts.py         ~90   Kafka tuketicisi -> WS yayini
├── routers/evidence.py  ~90   POST /api/evidence, GET /api/evidence
└── routers/events.py +~40     /clip ve /frame uclari

stream/spark_job.py   +~30     esikleri API'den cek

infra/postgres/init.sql +~20   evidence tablosu
docker-compose.yml      +~5    ./storage:/storage:ro
```

---

## 11. Testler (brokersız, DB'siz, GPU'suz)

`tests/test_evidence.py` (~110 satır)
- epizot açma/kapama: adaylar akarken açık, `gap` süresince sessizlikte
  kapanır; `session_passes()` geçmeyen epizot kanıt üretmez
- klip aralığı seçimi: tampondaki kareler `[start-5, end+5]` dışında
  kalanları elemeli; tampon yetmezse `clip_truncated=True`
- en iyi kare: en yüksek skorlu adayın kare indeksi seçilir
- yazma kuyruğu dolduğunda en eski düşer, `dropped` artar

`tests/test_ws_units.py` (~90 satır)
- jeton doğrulama: geçerli/süresi geçmiş/imzasız üç durum
- "son değer kazanır" kutusu: art arda üç kare yazılınca okuyan sonuncuyu alır
- adaptif kalite: 10 ms'lik kodlamada kalite düşer, 2 ms'de yükselir,
  tabanın altına inmez / tavanın üstüne çıkmaz
- meta gövdesi: pozsuz iz `kp: null` alır, bölge poligonu normalize kalır

`tests/test_evidence_match.py` (~70 satır)
- kanıt önce gelirse: eşleşmeyen satır yazılır, sonra gelen olay onu bağlar
- olay önce gelirse: kanıt geldiğinde olay bulunur ve doldurulur
- 3 sn toleransının dışındaki kanıt eşleşmez (bağlanmaz, silinmez)

---

## 12. Zorunlu ölçümler (rapora ve `docs/DURUM.md`'ye girer)

1. **Tarayıcı FPS.** Panel açıkken `/ws/live` üzerinden alınan kare sayısı
   (10 saniyelik pencerede). **Hedef 20+.** Ölçüm hem `--source` dosya hem
   webcam için verilir.
2. **Uçtan uca gecikme.** Meta gövdesindeki `ts` ile istemcinin kareyi
   çizdiği an arasındaki fark; p50 ve p95. **Hedef 300 ms altı.** Ölçüm
   yöntemi (tarayıcı konsolu / küçük bir istemci betiği) rapora yazılır.
3. **Yayının görü döngüsüne maliyeti.** `--ws` kapalı / açık (0 istemci) /
   açık (1 istemci) üç koşumda FPS. Sıfır istemcide maliyet **sıfıra yakın
   olmalı** (kodlama hiç çağrılmıyor); değilse yazılır.
4. **Alarm gecikmesi (Aşama 4'ten kalan açık soru).** Adayın üretildiği an
   (`vision` log) → kırmızı alarmın `/ws/alerts`'ten çıktığı an. Tasarım
   beklentisi: oturum boşluğu 3 sn + damga 2 sn + mikro-toplu. Ölçülen değer
   beklentinin üstündeyse **beklenti düzeltilmez, ölçüm yazılır.**
5. **Kanıt.** Pilot kliplerin bir geçişinde üretilen klip ve kare sayısı;
   `events` tablosunda `clip_path`/`frame_path`/`mongo_ref` dolu satır sayısı;
   eşleşmeyen `evidence` satırı sayısı. Bir klip **gerçekten oynatılıp**
   doğrulanır (süre, olayın klipte görünüp görünmediği).
6. **`pose_sequences`.** Yazılan belge sayısı, belge başına kare sayısı,
   `event_id` bağlanmış belge oranı.
7. Aşama 5'te düşen FPS (36.5 → 12–15) bu aşamada da ölçülür: Docker
   altyapısı + WebSocket + kanıt yazımı birlikte açıkken gerçek FPS nedir.

---

## 13. Kapsam dışı (bilinçli, Aşama 6'da YAPILMAYACAK)

- LLM ihbar metni ve Telegram bildirimi — Aşama 7
- Panelin kendisi: `sablon/` HTML'lerinin React'e taşınması ve bağlanması —
  Aşama 8. Bu aşamada panel yerine **küçük bir test istemcisi** yazılır
  (`scripts/ws_client.py`, ~80 satır): bağlanır, kare sayar, gecikme ölçer.
  Tasarıma dokunulmaz.
- Olay bazlı ReID galerisi (`storage/gallery/`) — Aşama 9
- TCN ve `decided_by` çeşitlenmesi — Aşama 9
- Çoklu kamera toplu çıkarım — Aşama 10; bu aşamanın WS sunucusu kamera
  başına anahtarlanmış olarak yazılır, ama tek kamerayla ölçülür
- Kanıt dosyalarının temizliği/rotasyonu — TTL yok, disk dolabilir; Aşama 10
