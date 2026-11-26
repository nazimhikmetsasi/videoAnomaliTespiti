# Aşama 13.4 — Düşme sonrası izleme ("kalkamadı"): uygulama planı (2026-11-26)

Kapsam ve kabul: `docs/YOL_HARITASI.md` §13.4, bulgu E1
(`docs/ASAMA13_PLAN.md`). Bugün FALL anlık bir darbe olarak tetikleniyor;
düşmeden sonra ne olduğuna bakılmıyor. Bu aşamada düşen kişi bir süre
izlenir ve olaya bir **düşme sonucu** eklenir: kalkamadı, kalktı veya
belirsiz. Sonuç olayın önemini değiştirir ve Telegram'a ikinci bir mesaj
olarak gider.

**Uygulayıcıya not:** burada yazmayan davranış değişikliği yapılmaz.
Var olan eşikler (`Thresholds`, FALL kuralı, Spark süzgeci) değişmez. Yeni
sabitler §1'deki değerlerle yazılır; kliplere bakılarak ayarlanmaz. Kötü
sonuç saklanmaz, ham sayı raporlanır.

---

## 0. Ön ölçüm: düşmeden sonra iz sürüyor mu?

Tasarımdan önce elde var olan iz dosyalarına bakıldı
(`data/tracks/FALL/*.npz`, 13.3'te çıkarılan ham izler). Geçici bir
betikle, salt okuma. Sabitlerin hiçbiri bu sayılardan seçilmedi; yalnız
tasarımın neyi karşılaması gerektiği görüldü.

- **URFD (30 klip):** düşmeden sonra klipte kalan görüntü 1,2–3,1 sn.
  Düşen iz 14 klipte sonuna kadar sürüyor. 16 klipte daha önce
  kayboluyor. Bunların 6'sında kısa süre sonra yakında (düşen izin son
  kutu yüksekliğinin 0,10–0,42 katı uzakta) **yeni bir iz kimliği** doğuyor.
  Yerde yatan kişi yeniden algılanıyor, izleyici ona yeni kimlik veriyor.
- **CASIA angleview (12 klip):** düşme anı kutu eğimiyle 8 klipte
  bulundu. Düşmeden sonra 4,6–13 sn görüntü var. Düşen iz 4 klipte
  **düşme anında** kayboluyor. Bunların 2'sinde ~4 sn sonra aynı yerde
  (0,12–0,20 kat) yeni iz çıkıyor, 2'sinde kimse görünmüyor.
- Yatay ve tepeden görünüm kliplerinde kutu eğimi düşme anını bulamadı.
  Bu ölçüm onlar için bir şey söylemiyor.

**Sonuç:**
1. Aynı iz kimliğini izlemek yetmez. İz kaybolunca aynı yerde doğan yeni
   iz devralınmalı (§2.3).
2. Yerde yatan kişi uzun süre hiç algılanmayabilir. Karar "son görülen
   duruş" üzerinden verilir (§2.4).
3. Eldeki veri kararı doğrulayamaz: en uzun düşme sonrası görüntü 13 sn,
   karar süresi 25 sn. Doğrulama 14'teki saha kayıtlarında. Burada birim
   testleri ve mekanizmayı gösteren duman testi var.

## 1. Sabitler ve gerekçeleri

Hepsi saniye veya oran. Kare sayısı yok, FPS'ten bağımsız (13.3 ilkesi).

| sabit | değer | gerekçe |
|---|---|---|
| `DECIDE_SEC` | **25.0** | Karar süresi. Gerçek düşmelerde (FARSEEING, bele takılı sensör) düşmeden sonra yerde dinlenme süresi kalkabilenlerde ortanca 10,5 sn, kalkamayanlarda 34,5 sn. **24,5 sn'den uzun dinlenme kalkamamayı öngörüyor (AUC 0,796)** [Schwickert 2018]. 0,5 sn yukarı yuvarlandı. |
| `UPRIGHT_SEC` | 2.0 | "Kalktı" demek için kişinin kesintisiz bu kadar ayakta görülmesi gerekir. Kaynaklı değil: sistemin bir davranışı gözlediği pencere bu (TCN 1,96 sn, `RETAIN_SEC` 2,0). Tek karelik dik görüntü, kalkma denemesinin bir anı olabilir. |
| `STAND_RATIO` | 0.88 | Ayakta sayılmak için kutu yüksekliği / düşmeden önceki ayakta yükseklik. Vücut oranlarından [Winter 2009]: sandalyede oturan kişinin baş tepesi yerden ~0,76 boy (diz yüksekliği 0,285 + kalça–tepe 0,47). Diz üstü ~0,72, yerde oturma ~0,52. Ayakta 1,0. Eşik, oturma ile ayakta durmanın ortası. |
| `ADOPT_DIST` | 1.0 | Kaybolan izin yerine geçecek yeni iz: ilk görüldüğü yerin, düşen izin son merkezine uzaklığı ≤ 1,0 × ayakta yükseklik. `LoiterRule`'un "yerinde" tanımıyla aynı ölçü (merkez kendi yüksekliğinden fazla kaymamış). |

"Yatay" için yeni eşik yok: FALL kuralının kendi şartı kullanılır,
`body_tilt >= th.fall_tilt_deg` (45°). Eşik panelden değişirse izleme de
değişir.

**Neden 25 sn, neden 5 değil.** Yol haritasındaki literatür örneği (>3 sn
yatay + >2 sn düşük hareket) [ElderFallGuard 2025] bir **düşme onayı**
kuralı: düşme olup olmadığına karar veriyor. Bizde düşmeye kural/TCN ve
Spark süzgeci zaten karar veriyor; burada sorulan "kişi kalkabildi mi".
5 sn ile kalkabilenlerin çoğu (ortanca 10,5 sn dinleniyorlar) "kalkamadı"
diye işaretlenirdi.

**Plandan sapma: hareketsizlik şartı yok.** Yol haritası "yatay ve
hareketsiz" diyor. Gerçek düşme videolarında düşme sonrası evre çoğu kez
hareketsizlik değil, kişiye göre değişiyor [BMC Geriatr 2013]. Kalkmayı deneyip
başaramayanlar, kalkabilenlerden **daha çok** gövde hareketi yapıyor
(ortanca 308° ve 76°) [Schwickert 2018]. Hareket şartı tam da yerde
çabalayan kişiyi kaçırırdı. Bu yüzden karar yalnız duruşa bakar (yerde mi,
ayakta mı). Hareket yalnız raporlanır (`limb_speed_med`). Aşamanın adı yol
haritasındaki gibi kalır.

**Bilinen sınırlar (kabul edilen, tezde yazılır):**
- Sabitler sensör çalışmasından ve vücut oranlarından; kameraya özgü
  doğrulama 14'te. 0,796 AUC orta düzeyde bir ayrım.
- Kamera yukarıdan bakıyorsa kutu yüksekliği oranı bozulur. `STAND_RATIO`
  bir kalibrasyon düğmesidir; zemin kalibrasyonu 17'de.
- Sandalyeye hızlı oturma (düşme sanılan oturma) "kalktı" sayılmaz, çünkü
  oturan kişi ~0,76 oranda kalır. Bu bilinçli: hatanın iki yönü eşit
  değil. Yerde oturup kalkamayan biri "kalktı" sayılırsa acil durum
  kaçar; oturan biri "kalktı" sayılmazsa olay bugünkü gibi kritik kalır.
  Oturan kişi "belirsiz" sonucunu alır (§2.4).
- Yerde dik oturan (gövdesi yatay olmayan) ve kalkamayan kişi
  "kalkamadı" değil "belirsiz" alır. İlk alarm zaten kritik gitmiştir.
- İz kaybolunca yakına gelen bir yardımcı devralınıp ayakta görülürse
  sonuç "kalktı" olur. Devralma yalnız düşen iz o karede görünmüyorken
  ve yeni iz ilk kez düşme yerinde görülürse olur (§2.3). Kapıdan gelen
  biri ilk kez kapıda görülür, devralınmaz.

## 2. İzleyici: `vision/rules/postfall.py` (yeni)

### 2.1 Arayüz

```python
DECIDE_SEC = 25.0
UPRIGHT_SEC = 2.0
STAND_RATIO = 0.88
ADOPT_DIST = 1.0

@dataclass
class FallOutcome:
    track_id: int              # dusen iz (ilk FALL adayinin izi)
    fall_ts: float             # sahne zamani; sureler bununla
    fall_time: float | None    # duvar saati = ilk adayin event_time'i; olay eslesmesi bununla
    outcome: str               # "down" / "recovered" / "unknown"
    decided_ts: float
    metrics: dict[str, float]
    adopted: list[int]         # devralinan iz kimlikleri, siralı

class PostFallMonitor:
    def __init__(self, decide_sec: float = DECIDE_SEC) -> None: ...
    def update(self, windows: dict[int, TrackWindow], candidates: list[Candidate],
               ts: float, th: Thresholds) -> list[FallOutcome]:
        """Her karede bir kez. windows: FeatureEngine ciktisi (bu karede gorulen
        BUTUN izler, pozsuzlar dahil). Bu karede kesinlesen sonuclari dondurur."""
    def pending(self) -> list[tuple[int, float]]:
        """(track_id, izlenen sure) -- akis biterken rapor icin."""
```

Durum `LoiterRule` gibi kuralın kendi içinde tutulur: `TrackWindow` yalnız
2 sn saklıyor, izleme 25 sn sürüyor.

### 2.2 Başlatma

- Bu karedeki her `anomaly_type == "FALL"` adayı için (kural, model veya
  hibrit; ayrım yok): adayın izi zaten bir izlemenin takip ettiği iz
  değilse yeni izleme açılır.
- `ref_height`: o izin penceresindeki (`windows[tid].frames`, son 2 sn)
  `body_tilt < th.fall_tilt_deg` olan karelerin en büyük `height`'ı. Hiç
  dik kare yoksa (iz yatarken doğmuş) bütün karelerin en büyüğü.
- `fall_ts = cand.ts`, `fall_time = cand.event_time` (eval betiklerinde
  `None` olabilir).
- Aynı izden gelen sonraki FALL adayları yeni izleme açmaz; tek düşme,
  tek sonuç.

### 2.3 Takip ve devralma

Her karede, her açık izleme için:

- **Takip edilen iz bu karede görülüyorsa** son karesinden duruş
  sınıflanır:
  - `lying`: `body_tilt >= th.fall_tilt_deg`
  - `standing`: `body_tilt < th.fall_tilt_deg` ve
    `height >= STAND_RATIO * ref_height`
  - `other`: ikisi de değil (oturma, diz üstü, çömelme)

  Son görülme `ts`'i, son merkez ve son duruş saklanır.
- **Devralma:** monitör, gördüğü iz kimliklerini son görülme zamanıyla
  tutar ve `STALE_SEC`'ten eski olanları budar (`FeatureEngine._last_seen`
  deseni). Bu karede **ilk kez** görülen bir iz, takip ettiği iz bu karede
  görünmeyen bir izlemeye devredilir, iki şartla:
  - yeni izin merkezi ile izlemenin son merkezi arasındaki uzaklık
    `<= ADOPT_DIST * ref_height`
  - birden çok aday izleme varsa en yakını alır; bir iz tek izlemeye
    gider

  Devralınan iz artık takip edilen izdir ve `adopted`'a eklenir.
  `ref_height` değişmez.

### 2.4 Karar

- **`recovered` (kalktı):** takip edilen iz `standing` olduğu ilk karede
  `stand_since = ts` yazılır. `standing` olmayan bir karede silinir. Takip
  edilen iz o karede görünmüyorsa dokunulmaz. Sonuç yalnız **görülen**
  bir ayakta karede, `ts - stand_since >= UPRIGHT_SEC - EPS` olunca
  verilir ve izleme kapanır. (Uygulamada düzeltildi: ilk sürüm görülmeyen
  karede de karar veriyordu; 1 sn ayakta görünüp yeniden yere yığılan ve
  algılanmayan kişi "kalktı" sayılırdı.)
- **Süre dolunca** (`ts - fall_ts >= decide_sec - EPS`):
  - son görülen duruş `lying` ise **`down`** (kalkamadı). Kişi son 20 sn
    hiç görülmemiş olsa da: düştü, yerde görüldü, kalktığı görülmedi.
    Ne kadar zamandır görülmediği `last_seen_ago_sec`'te.
  - değilse **`unknown`** (belirsiz): son görüldüğünde oturuyordu veya
    ayağa kalkıp yeterince durmadı.

  Kayıp iz görülmeyen karelerde hiçbir şeyi değiştirmez. Kural adayında
  düşme karesi her zaman `lying`'dir (FALL kuralı eğimi şart koşar), yani
  düşer düşmez kaybolan ve bir daha görülmeyen kişi `down` alır. Bilinçli:
  güvenli taraf alarmdır. Yalnız modelden gelen FALL adayında eğim şartı
  yok; düşme karesi `other` olabilir ve aynı durumda sonuç `unknown` olur.

### 2.5 Ölçütler (`metrics`)

Hepsi raporlanır, hiçbiri karara girmez:

- `decided_after_sec`: `decided_ts - fall_ts`
- `last_seen_ago_sec`: karar anı − son görülme
- `seen_ratio`: düşmeden sonra takip edilen izin görüldüğü kare / işlenen
  kare
- `lying_ratio`: görülen kareler içinde `lying` oranı
- `max_height_ratio`: düşmeden sonra görülen en büyük `height / ref_height`
- `limb_speed_med`: `lying` karelerdeki `limb_speed` ortancası (yerde
  çabalama mı, hareketsizlik mi; tez için)
- `recovered_after_sec`: yalnız `recovered`'da, `stand_since - fall_ts`
- `ref_height`: piksel

Numpy skalerleri `float()` ile çevrilir (JSON).

## 3. Görü hattı bağlantısı

### 3.1 `vision/camera.py`

- `start()`: `args.rules` açıksa
  `self.postfall = PostFallMonitor(getattr(args, "postfall_sec", DECIDE_SEC))`.
- `consume()`: `cand.event_time = now` döngüsünden **sonra**:

  ```python
  outcomes = self.postfall.update(windows, candidates, ts, self.rule_engine.thresholds)
  self.all_outcomes.extend(outcomes)
  if self.publisher is not None:
      for o in outcomes:
          self.publisher.outcome(o)
  ```

  `self.rule_engine.thresholds` hem `RuleEngine`'de hem `HybridArbiter`'da
  var; sıcak yükleme izlemeye de yansır.

### 3.2 `vision/publish.py`

- `OUTCOME_TOPIC = "fall-outcomes"`
- `outcome_to_dict(o: FallOutcome, camera_id: str) -> dict` (saf
  fonksiyon, testli):

  ```json
  {"schema": 1, "camera_id": "...", "track_id": 7,
   "fall_time": 1764000000.12, "fall_ts": 12.4,
   "outcome": "down", "decided_ts": 37.4,
   "adopted": [9], "metrics": {"decided_after_sec": 25.0, "...": 0.0}}
  ```

  `fall_time` `None` ise mesaj basılmaz (eşleşme imkânsız); yayıncı
  sayacı `outcomes_skipped` artar.
- `CandidatePublisher.outcome(o)`: aynı üretici, `OUTCOME_TOPIC`'e,
  anahtar `camera_id:track_id`. Bloklamaz, hata fırlatmaz (`_produce`
  deseni; konu parametresi eklenir).

### 3.3 `vision/run.py`

- `--postfall-sec` (float, varsayılan 25.0). Saha kaydını ve duman
  testini kısa süreyle koşturmak için. Varsayılan değişmez.
- Rapor, `TCN kosusu` satırının altına:
  - `dusme sonrasi        : down a / recovered b / unknown c, bekleyen m`
  - her sonuç için bir satır: iz, sonuç, `decided_after_sec`,
    `last_seen_ago_sec`, `adopted`, `max_height_ratio`
  - bekleyen her izleme için iz ve izlenen süre (klip bitti, karar yok)

### 3.4 Dokunulmayanlar

Spark, kural motoru, arbiter, kanıt yazıcı, WebSocket çizimi değişmez.
FALL olayı bugünkü yoldan, bugünkü gecikmeyle (~7,6 sn) gider. İzleme onu
geciktirmez.

## 4. Olaya yazma: Kafka → tüketici

### 4.1 Neden bu yol

Sonuç olayı **günceller**, yeni olay açmaz. Bildirim kuyruğu tüketici
sürecinde (`notify.start()` orada). Spark'tan geçirmek yeni bir
`anomaly_type` ve ikinci bir olay satırı demekti.

### 4.2 Altyapı

- `infra/kafka/topics.sh`: `create fall-outcomes 3 86400000`. Otomatik
  konu açma kapalı (`KAFKA_AUTO_CREATE_TOPICS_ENABLE: "false"`); var olan
  yığında bir kez `docker compose run --rm kafka-init` gerekir (§7).
- `infra/postgres/init.sql`, `events`:
  ```sql
  fall_outcome  VARCHAR(10)
                CHECK (fall_outcome IN ('down', 'recovered', 'unknown')),
  ```
  NULL = FALL değil ya da sonuç henüz yok.
- `api/db/migrate.py` (var olan kurulum): `ADD COLUMN IF NOT EXISTS`, sonra
  `DROP CONSTRAINT IF EXISTS events_fall_outcome_check` ve `ADD CONSTRAINT`
  (`notifications.status` deseni).
- `api/db/models.py` `Event.fall_outcome: Mapped[str | None]`;
  `api/schemas.py` `EventOut.fall_outcome: str | None`.
  `tests/test_schema_sync.py` canlı veritabanında bunu denetler.

### 4.3 `api/workers/consumer.py`

- `consumer.subscribe([TOPIC, OUTCOME_TOPIC])`; mesaj `msg.topic()`'e göre
  ayrılır. Olay yolu değişmez.
- `outcome_to_update(msg: dict) -> dict | None`: saf, `event_to_row`
  deseni. Zorunlu alanlar `camera_id`, `track_id`, `fall_time`, `outcome`.
  Bilinmeyen `outcome` veya bozuk alan → `None` (mesaj atlanır, `malformed`).
- **Eşleşme** `_apply_outcome(db, camera_id, upd) -> int | None`:
  ```sql
  UPDATE events SET fall_outcome = :o,
         severity = CASE WHEN :o = 'recovered' AND severity = 'critical'
                         THEN 'high' ELSE severity END
  WHERE id = (SELECT id FROM events
              WHERE camera_id = :cam AND anomaly_type = 'FALL'
                AND fall_outcome IS NULL
                AND track_ids && ARRAY[:tid]
                AND started_at BETWEEN :t - tol AND :t + tol
              ORDER BY abs(extract(epoch FROM started_at - :t)) LIMIT 1)
  RETURNING id, status
  ```
  `tol` = `api.matching.tolerance()` (kanıt eşleşmesiyle aynı gerekçe:
  oturum boşluğu). `fall_outcome IS NULL` tekrar teslimde ikinci
  güncellemeyi önler.
- **Önem:**
  - `down` → önem değişmez (FALL zaten `critical`); sonuç "doğrulanmış
    kritik" demektir
  - `recovered` → `critical` ise `high`'a iner (bir kademe)
  - `unknown` → değişmez
- **Sıra yarışı.** `recovered` hızlı gelebilir (düşme + ~2,5 sn), olay ise
  Spark'tan ~7,6 sn'de gelir. Eşleşmeyen sonuç bellekte bekletilir
  (`PendingOutcomes`, kamera başına liste, `PENDING_SEC = 60`). Her FALL
  olayı eklendikten sonra o kameranın bekleyenleri yeniden denenir;
  süresi dolan atılır ve sayılır (`outcome_unmatched`). Offset hemen
  commit edilir.
  - Sınır: tüketici bu 60 sn içinde yeniden başlarsa bekleyen sonuç
    kaybolur. Kayıp yalnız ikinci mesajdır; olay ve ilk alarm durur.
  - Sınır: Spark FALL oturumunu elediyse (tek aday, `min_hits = 2`) olay
    yoktur, sonuç eşleşmez ve sayılır. Sonuçtan olay açmak bu aşamada
    yok; sayaç bunun ne sıklıkla olduğunu 14'te gösterir.
- Eşleşince:
  - Mongo `telemetry` belgesine `{"$set": {"fall_outcome": <mesaj>}}`
    (`event_id` ile). Hata sayılır, tüketici durmaz.
  - `down` ve `recovered` için, olayın `status`'ü `false_positive` değilse
    `notify.enqueue_outcome(event_id, outcome, metrics)`.
- Sayaçlar kapanış satırına: `outcome_applied`, `outcome_pending`,
  `outcome_unmatched`.

### 4.4 `api/notify.py`

- Kuyruk öğesi `(tur, event_id, ek)` olur. `enqueue(event_id)` aynen
  kalır (`tur = "event"`); yeni `enqueue_outcome(event_id, outcome,
  metrics)`. İşçi türe göre ayırır. Tek işçi, sıra korunur: alarm önce,
  sonuç sonra.
- `_process_outcome`:
  - **LLM çağrısı yok.** Sabit Türkçe şablon; kota harcanmaz, gecikme
    yok.
  - Kur/Bırak denetimi aynen (`_is_armed`; evde modunda `skipped` kaydı).
  - Alıcılar `_process_event`'teki gibi. Her gönderim bir `notifications`
    satırı.
- Şablonlar (`{saat}` olayın `started_at`'i, yerel saat, `SS:DD:ss`):
  - `down`, `last_seen_ago_sec <= STALE_SEC`:
    `⚠️ KALKAMADI — {kamera}` / `{saat}'teki düşmeden {n} sn sonra kişi hâlâ yerde.`
  - `down`, daha uzun süredir görülmüyor:
    `⚠️ KALKAMADI — {kamera}` / `{saat}'teki düşmeden sonra kişinin kalktığı görülmedi. Son {m} sn'dir kamerada görünmüyor; son görüldüğünde yerdeydi.`
  - `recovered`:
    `✅ KALKTI — {kamera}` / `{saat}'teki düşmeden {k} sn sonra kişi ayağa kalktı. Önem yüksek'e indirildi.`
  - `unknown`: mesaj yok.

  `n` = `decided_after_sec`, `m` = `last_seen_ago_sec`, `k` =
  `recovered_after_sec`, tamsayıya yuvarlanır.

### 4.5 Panel

- `frontend/js/app.js`: `DUSME_SONUCU = {down: "kalkamadı", recovered:
  "kalktı", unknown: "belirsiz"}`.
- `frontend/js/olaylar.js`: tip rozetinin metni `fall_outcome` varsa
  `"Düşme · kalkamadı"` gibi. `textContent` ile, kaçışlama gerekmez.
- `python scripts/build_frontend.py`: `?v=` önbellek etiketleri yenilenir.
- Alarm penceresi, ses ve tek tık onay 13.6'da; burada yok.

## 5. Testler

İki yeni dosya (§6). İzleyici testleri sentetik `FrameFeatures` dizileriyle;
her senaryo 25, 10 ve 5 FPS'te koşulur.

**İzleyici** (`test_asama13_4_izleme.py`):
1. Düşme, sonra hep yatay → `down`; karar `fall_ts + 25`'te, bir kare
   aralığı içinde; her FPS'te.
2. +5 sn'de kalkıp ayakta kalır → `recovered`, karar ~+7 sn,
   `recovered_after_sec` ≈ 5.
3. 1 sn ayakta, sonra yine yatay → kalktı sayılmaz → `down`.
4. Kalkıp 0,7 × yükseklikte (oturma) kalır → `unknown`.
5. İz +1 sn'de kaybolur, +4 sn'de 0,3 × yükseklik uzakta yeni iz doğar,
   yatay → devralınır, `down`, `adopted == [yeni]`.
6. Aynı kayıp, yeni iz 2 × yükseklik uzakta doğar ve ayakta → devralınmaz;
   `down`, `last_seen_ago_sec` ≈ 24.
7. Düşen iz hâlâ görünürken yakında yeni iz doğar ve ayakta durur →
   devralınmaz; düşen iz yatay kaldıkça `down`.
8. Aynı izden üst üste 5 FALL adayı → tek izleme, tek sonuç.
9. Yatarken doğan iz → `ref_height` bütün karelerin en büyüğü; ayakta
   sayılmak için yine eğim < 45° gerekir.
10. İz düşer düşmez kaybolur ve hiç görülmez → `down`, `seen_ratio` ≈ 0.
11. `th.fall_tilt_deg` çağrılar arasında değişince duruş yeni eşikle
    sınıflanır.
12. FPS bağımsızlığı: 1–5 numaralı senaryolarda sonuç üç hızda aynı,
    karar zamanları bir kare aralığı içinde.

**Yayıncı:** `outcome_to_dict` numpy skalerlerle `json.dumps`'tan geçer;
`fall_time = None` mesaj basmaz.

**Tüketici** (`test_asama13_4_olay.py`, `test_consumer.py` deseni,
veritabanısız):
- `outcome_to_update`: eksik alan, bilinmeyen sonuç, bozuk tür → `None`
- `PendingOutcomes`: ekle → eşleştir → kaldır; 60 sn sonra düşer ve sayılır
- güncelleme SQL'i (veritabanı varsa, yoksa atlanır): `recovered`
  `critical`'i `high`'a indirir, `high`'ı değiştirmez; ikinci uygulama
  değişiklik yapmaz; zaman toleransı dışı ve farklı iz eşleşmez

**Bildirim:** üç şablonun metni (sabit `started_at` ile); evde modunda
`skipped` kaydı ve gönderim yok; `unknown` kuyruğa hiç girmez.

**Göç:** `migrate.py`'de iki ifade var ve idempotent (aynı listeyi iki kez
koşmak hata vermez; veritabanı varsa).

**Panel:** `olaylar.js` ve `app.js` statik denetim; rozet metni üç sonuç
için.

## 6. İş bölümü

İki paket, dosyaları ayrık; sözleşmeleri §3.2'deki mesaj gövdesi. Paralel
uygulanabilir.

| paket | dosyalar |
|---|---|
| **V — görü** | `vision/rules/postfall.py` (yeni), `vision/camera.py`, `vision/publish.py`, `vision/run.py`; testlerin izleyici ve yayıncı kısmı |
| **A — API, altyapı, panel** | `infra/kafka/topics.sh`, `infra/postgres/init.sql`, `api/db/migrate.py`, `api/db/models.py`, `api/schemas.py`, `api/workers/consumer.py`, `api/notify.py`, `frontend/js/app.js`, `frontend/js/olaylar.js`, `frontend/*.html` (yalnız `build_frontend` çıktısı); testlerin tüketici, bildirim, göç ve panel kısmı |

Testler iki dosyada, her paket kendi dosyasına yazar:
`tests/test_asama13_4_izleme.py` (V) ve `tests/test_asama13_4_olay.py` (A).

## 7. Doğrulama (ana dizinde, kod `main`'e alındıktan sonra)

1. Tam test paketi yeşil; paket koştuktan sonra `git status` temiz.
2. **Çevrimdışı duman testi** (Docker gerekmez). Önce `nvidia-smi`: GPU'yu
   kullanan oyun veya tarayıcı kapalı.
   - `vision.run --rules --source data/train/FALL/casia_angleview_p02_faint_a1.mp4 --postfall-sec 5`:
     ön ölçümde iz düşme anında kayboluyor, ~4 sn sonra yakında yeni iz
     doğuyordu. Beklenen: devralma görülür (`adopted` dolu).
   - aynısı `data/train/FALL/casia_angleview_p24_faint_a1.mp4` (iz sürüyor)
     ve `data/pilot/fall_01.mp4` ile
   - 25 sn'lik varsayılanla `fall_01 --loop`: karar gelir, döngü başında
     ayakta görülen kişi uzakta doğduğu için devralınmaz.
   - Ana oturum her klipte kare kare dökümle (duruş, yükseklik oranı,
     devralma) karara bakar; yalnız rapor satırına bakmak yetmez.
     5 sn'lik değer yalnız mekanizmayı görmek için; doğruluk iddiası
     değildir.
3. **Uçtan uca canlı** (Docker yığını):
   - `docker compose run --rm kafka-init` (yeni konu), `up -d --build api
     consumer` (göç açılışta koşar)
   - `vision.run --source data/pilot/fall_01.mp4 --rules --realtime --kafka
     localhost:9092 --postfall-sec 10` (+ kanıt ve ayar bayrakları, 13.1
     ölçümündeki gibi)
   - Beklenen: FALL olayı ~7,6 sn'de; ~10 sn sonra `events.fall_outcome`
     dolu; `down` ise `notifications`'ta iki satır (alarm + sonuç);
     tüketici kapanışında `outcome_unmatched = 0`
   - Postgres: `SELECT id, severity, fall_outcome FROM events ORDER BY id DESC LIMIT 5`
4. Yarış testi: tüketici durdurulup sonuç mesajı olaydan **önce** verilir
   (ör. sonucu elle basan küçük bir komut), sonra olay. Bekleyen sonuç
   olay eklenince uygulanır.

## 8. Kabul

1. Testler yeşil (§5 bütün maddeler).
2. Duman testi ve uçtan uca koşu §7'deki gibi; ham döküm DURUM'da.
3. FALL olayının gecikmesi değişmedi (izleme olay yolunun dışında).
4. `docs/TEZ.md`'ye §4.6 taslağı: sorun, sabitlerin kaynakları, hareket
   şartının neden düştüğü, bilinen sınırlar, ön ölçümdeki iz sürekliliği
   sayıları. Saha sonuçları 14'te eklenecek.
5. `docs/YOL_HARITASI.md` §14'teki kayıt listesi N'ye göre güncel (plan
   yazılırken güncellendi: yerde en az 35 sn).
6. Saha doğrulaması 14'te: "düşüp kalkamama", "düşüp hızla kalkma",
   "düşüp yerde oturma", "sandalyeye hızlı oturma" kayıtlarında sonuç ve
   karar süresi raporlanır. Sabitler o kayıtlara göre değiştirilecekse
   bu ayrı bir karar olarak yazılır.

**Commit:** `feat: asama 13.4 - dusme sonrasi hareketsizlik dogrulamasi`

## 9. Kapsam dışı (kayıt)

- **Sonuçtan olay açmak:** Spark'ın elediği FALL'dan sonra kişi 25 sn
  yerdeyse bu tek başına güçlü bir işaret. Şimdilik yalnız sayılır
  (`outcome_unmatched`); 14'teki sayıya göre karar.
- **Yatak / koltuk muaf bölgesi:** yol haritasında isteğe bağlı. Bölge
  altyapısı var, ama muaf bölgede FALL'ın kendisi de susmalı; bu FALL
  kuralını değiştirir. 14'te yanlış alarm görülürse.
- **Panelde canlı "yerde: 12 sn" sayacı ve alarm penceresinde sonuç:**
  13.6.
- **LLM raporunun sonucu anlatması:** rapor olay anında yazılıyor, sonuç
  sonra geliyor. Telegram mesajı şablonla bunu karşılıyor.
- **Yanıt zinciri** (Telegram'da ikinci mesajın ilkine yanıt olarak
  gitmesi): ilk mesajın kimliği saklanmıyor; olay saati metinde.

## 10. Ortak kurallar

- Yorumlar ASCII, kısa, "neden"i anlatır. Her yeni sabitin yanında kaynağı
  tek satırda (ör. `# Schwickert 2018: >24.5 sn dinlenme kalkamamayi ongorur`).
- Paketler birbirinin dosyasına dokunmaz.
- Uzun koşular arka planda ve `logs/`'a kayıtla; artık python süreçleri
  ölçüm sonunda temizlenir.

## Kaynaklar

- **[Schwickert 2018]** Schwickert L., Klenk J., Zijlstra W., Forst-Gill
  M., Sczuka K., Helbostad J. L., Chiari L., Aminian K., Todd C., Becker C.
  "Reading from the Black Box: What Sensors Tell Us about Resting and
  Recovery after Real-World Falls." *Gerontology* 64(1):90–95, 2018.
  doi:10.1159/000478092. (Özetten: kalkabilen / kalkamayan dinlenme
  ortancası 10,5 / 34,5 sn, p = 0,045; >24,5 sn, AUC 0,796; gövde hareketi
  ortancası 76° / 308°, p = 0,06. Düşme sayısı özette yok; tam metin
  okunmadı.)
- **[BMC Geriatr 2013]** "Fall incidents unraveled: a series of 26
  video-based real-life fall events in three frail older persons." *BMC
  Geriatrics* 13:103, 2013. doi:10.1186/1471-2318-13-103. (Düşme sonrası
  evre çoğu kez hareketsizlik değil. Yazar listesi doğrulanmadı.)
- **[ElderFallGuard 2025]** Riahi T., Bappy M. A. H., Islam M. M.
  "ElderFallGuard: Real-Time IoT and Computer Vision-Based Fall Detection
  System for Elderly Safety." arXiv:2505.11845. (Yatay poz >3 sn + düşük
  hareket >2 sn; ampirik, bağımsız doğrulaması yok.)
- **[Winter 2009]** Winter D. A. *Biomechanics and Motor Control of Human
  Movement*, 4. baskı, Wiley. Vücut parçası uzunlukları boyun oranı olarak
  (Drillis ve Contini 1966'dan).

Tezde kullanılmadan önce Schwickert 2018 ve BMC Geriatr 2013'ün tam
metni okunmalı, Winter'daki oranlar sayfa numarasıyla doğrulanmalı;
burada yalnız özetler ve bilinen oranlar kullanıldı.
