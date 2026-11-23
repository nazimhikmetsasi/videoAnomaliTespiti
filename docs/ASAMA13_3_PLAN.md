# Aşama 13.3 — Zaman tabanlı pencereleme: uygulama planı (2026-11-23)

Kapsam ve kabul: `docs/YOL_HARITASI.md` §13.3. Sorun (koddan): kural
pencereleri, TCN girdisi, iz yaşı ve izleyici tamponu **kare sayısıyla**
tanımlı. Çevrimdışı değerlendirme her kareyi işler (25–30 FPS); canlı
kamera ~10 FPS'te çalışır ve aynı pencere 2,5–5 kat uzar. Bu plan önce
sorunun büyüklüğünü ölçer, sonra sabitleri saniyeye çevirir, en son TCN
girdisini zamana bağlayıp modeli yeniden eğitir.

**Uygulayıcıya not:** burada yazmayan davranış değişikliği yapılmaz.
Eşikler (`Thresholds`, `FIGHT_LIMB_SPEED` vb.) **değişmez**; kliplere göre
ayar yapılmaz. Kötü sonuç saklanmaz, ham sayı raporlanır.

---

## 0. Sıra, ölçüm noktaları, commit'ler

| adım | iş | ölçüm | commit mesajı |
|---|---|---|---|
| 13.3a | Paket Ö — kare hızı tarama aracı (§2) | **B0**: değişiklikten önce, kural + hibrit | `feat: asama 13.3 - kare hizi tarama araci` |
| 13.3b | Paket K — kural, öznitelik, izleyici saniyeye (§4) | **B1**: yalnız kural | `feat: asama 13.3 - kural pencereleri ve iz yasi saniyeye` |
| 13.3c | Paket T — TCN zaman ızgarası, yeniden çıkarım ve eğitim (§6) | **B2**: kural + hibrit | `feat: asama 13.3 - zaman tabanli pencereleme ve fps bagimsiz model girdisi` |

Ölçümler ana dizinde koşar (veri, ağırlıklar, `venv` orada). Her adımın
kodu ölçümden önce commit'lenip `main`'e alınır. Paketler sırayla
uygulanır; K, Ö'nün aracını, T ise K'nin pencere tanımını kullanır.

B1'de hibrit ölçülmez: K'den sonra öznitelik penceresi zamana bağlıdır,
eski model ise 50 gözlenmiş kare ister. Düşük FPS'te eski model hiç
koşmaz ve hibrit satırı kural satırına eşit çıkar. Bu ölçüm bilgi vermez.

## 1. Ortak tanımlar

**Dönüşüm ilkesi.** Her sabit, bugünkü **25 FPS** karşılığından
türetilir. Bu yüzden 25 FPS'te boşluksuz bir izde davranış birebir aynı
kalır (K'nin testleri bunu denetler). Kliplere bakarak değer seçilmez.
Tek fark izde boşluk olduğunda çıkar: eski pencere *gözlenen* kareyi
sayıyordu, yeni pencere süreyi sayar.

- "Son N kare" penceresi → kapsadığı süre `(N - 1) / 25` sn
- "N kare geri" başvurusu → `N / 25` sn
- `EPS = 1e-6`: zaman karşılaştırmalarındaki kayan nokta payı

**İki pencere erişimi** (`TrackWindow`, `vision/stages/features.py`):

```python
def since(self, sec: float) -> list[FrameFeatures]:
    """ts >= last.ts - sec - EPS olan kareler; en az son kare. Kismi pencere serbest."""

def covering(self, sec: float) -> list[FrameFeatures] | None:
    """Son kareden geriye, son kareden en az `sec` once alinmis ilk kareye
    kadar (o da dahil). Iz o kadar eski degilse None."""
```

`covering`, eski "`recent(N)` + `len < N` ise çık" deseninin karşılığıdır.
25 FPS'te `covering((N-1)/25)` tam N kare döndürür. 5 FPS'te en az iki
kare döndürür, çünkü son karenin kendisi sınırı karşılamaz. Böylece tek
karelik dedektör sıçraması hiçbir FPS'te tutma şartını tek başına
geçemez.

**Dönüşüm tablosu:**

| yer | eski | yeni | erişim |
|---|---|---|---|
| `fall.py` | `HOLD = 3` | `HOLD_SEC = 0.08` | `covering` |
| `fall.py` | `VY_LOOKBACK = 15` | `VY_SEC = 0.56` | `since` |
| `run.py` | `LOOKBACK = 10`, `MIN_HITS = 6` | `SPEED_SEC = 0.36`, `MIN_HIT_RATIO = 0.6` | `covering` |
| `run.py` | `GAIT_LOOKBACK = 50` | `GAIT_SEC = 1.96` | `covering` |
| `zone.py` | `HOLD = 3` | `HOLD_SEC = 0.08` | `covering` |
| `zone.py` | `SCORE_LOOKBACK = 5` | `SCORE_SEC = 0.16` | `since` |
| `fight.py` | `HOLD = 3` (ardışık kare serisi) | `HOLD_SEC = 0.08` (serinin başladığı `ts`) | — |
| `features.py` | `velocity_lookback = 5` | `VELOCITY_SEC = 0.2` | §4.1 |
| `features.py` | `LIMB_HIST = 3` | `LIMB_SEC = 0.12` | §4.1 |
| `features.py`, `smoother.py`, `loiter.py` | `STALE_FRAMES = 90` (üç kopya) | `STALE_SEC = 3.6` (tek kaynak: `features.py`) | son görülme `ts`'i |
| `features.py` | `window_frames = 50` (deque uzunluğu) | `RETAIN_SEC = 2.0` | §4.1 |
| `arbiter.py` | `EVERY = 5` (`idx % 5`) | `MODEL_EVERY_SEC = 0.2` | son model koşusunun `ts`'i |
| `tracker.py` | `track_buffer = 60` | `TRACK_BUFFER_SEC = 2.4` | §4.3 |
| `models/tcn.py` | 50 gözlenmiş kare | 25 Hz'de 50 ızgara noktası (1,96 sn) | §6.1 |
| `models/tcn.py` | `STRIDE = 25`, FALL için `--stride 10` | `STRIDE_SEC = 0.4` (bütün sınıflar; §6.2) | §6.2 |

`run.py`'deki isabet oranı `hits >= ceil(MIN_HIT_RATIO * len - EPS)` ile
hesaplanır. 25 FPS'te 10 karede 6 isabet, eskisiyle aynı.

## 2. Paket Ö — kare hızı tarama aracı (13.3a)

Dosyalar: `models/tcn.py` (yalnız `FrameDropper`), `eval/tcn_eval.py`,
`eval/pilot_eval.py` (yalnız ortak yardımcı),
`tests/test_asama13_3_olcum.py` (yeni). Bu pakette hat koduna dokunulmaz:
B0 bugünkü davranışı ölçer.

**`FrameDropper`** (`models/tcn.py`; T'de eğitim artırımı da bunu
kullanır, tek uygulama):

```python
class FrameDropper:
    def __init__(self, target_fps: float, mode: str = "regular", seed: int = 0) -> None: ...
    def __call__(self, ts: float) -> bool:
        """Bu kare islenir mi? Cagrilar ts sirasiyla yapilir."""
```

- `target_fps <= 0`: her kare tutulur (özgün hız)
- `regular`: ilk kare tutulur, `next_t = ts0`. `ts >= next_t - EPS` ise
  kare tutulur ve `next_t += 1 / target_fps` olur. Ortalama hız tam
  hedefte kalır; 29,97 → 10 gibi tam bölünmeyen oranlarda da çalışır.
  `next_t` hâlâ `ts`'in gerisindeyse (kaynakta boşluk var demektir)
  `next_t = ts + adım` yapılır. Böylece boşluktan sonra kareler patlama
  hâlinde tutulmaz.
- `jitter`: aynısı, ama adım `(1 / target_fps) * U(0.5, 1.5)`. Değişken
  işleme süresini taklit eder. Ortalama hız yine hedefte.
  `np.random.default_rng(seed)` ile üretilir.
- Kaynak hızı hedefin altındaysa kare atılmaz (ör. `police_run`, 15 FPS).

**`eval/tcn_eval.py`:**

- Yeni bayraklar:
  - `--fps 0,10,5` (0 = özgün hız)
  - `--drop regular,jitter`
  - `--seeds 0,1,2` (yalnız `jitter`'a uygulanır)
  - `--out <json>`
  - `--compare a.json b.json`
- Varsayılanlar (`--fps 0 --drop regular --seeds 0`) bugünkü
  çalıştırmayı verir. Tek fark aşağıdaki `eval_end_sec` düzeltmesidir.
- Klip başına tohum `seed + zlib.crc32(stem)`. Sonuç klip sırasından
  bağımsız ve tekrarlanabilir olur.
- `run_clip`, `FrameDropper` `False` döndüren kareyi **algılamadan önce**
  atlar. İzleyici yalnız tutulan kareleri görür, canlıda olduğu gibi.
  `ts = frame.idx / source.fps` aynen kalır, çünkü sahne zamanı gerçek
  zamandır.
- Pilot kümede `eval_end_sec` uygulanır, `pilot_eval.py` ile aynı
  biçimde. Bugün `tcn_eval` bunu atlıyor; `zone_01`'in 28. sn'den sonraki
  sahne değişimi FP gürültüsü üretiyordu. Ortak yardımcı
  `pilot_eval.load_annotation(path) -> (events, eval_end)` ikisinde de
  kullanılır.
- Etiketsiz pilot klipler de koşulur (`police_run`). Tip başına ham aday
  sayısı raporlanır, puanlanmaz.
- **İki puan** hesaplanır. İkisi de mevcut `to_second_set` + `score` ile:
  1. ham: bütün adaylar (bugünkü tablo)
  2. süzgeç sonrası: adaylar `(iz anahtarı, tip)` başına sahne
     zamanında, `gap = 3.0` sn ile oturumlara ayrılır.
     `stream.filters.session_passes(hits, son.ts - ilk.ts, tip, min_hits=2)`
     geçen oturumların adayları puanlanır. Spark'ın önündeki gerçek
     süzgeç budur: `min_hits` kare sayısıdır ve FPS düşünce oturumu
     eleyebilir. Bu ancak böyle görülür.
- Her yapılandırma (mod, küme, fps, drop, tohum) için şunlar ölçülür:
  - TP / FP / FN, kesinlik, duyarlılık, F1 (toplam ve tip başına), hem
    ham hem süzgeçli
  - küme başına **etkin FPS** (tutulan kare / klip süresi): araç
    denetimi
- Çıktı:
  - koşu sonunda tek özet tablo (markdown)
  - `--out` JSON'u: satır başına sayılar, klip başına tutulan kare ve
    tip başına ham aday
- `--compare`: iki JSON'u aynı satır anahtarıyla yan yana basar
  (F1 önce → sonra, ham ve süzgeçli). `jitter` satırlarında tohumlar
  arası ortalama ve [min, maks] verilir.

**Testler (`tests/test_asama13_3_olcum.py`):**

- `regular` 25 → 5: idx 0, 5, 10, … tutulur
- `regular` 30 → 10: her 3. kare tutulur
- `regular` 29,97 → 10: 300 karede 100 ± 1 kare tutulur
- `target_fps` kaynak hızının üstünde: hepsi tutulur
- `jitter`: aynı tohum aynı diziyi verir; 10 000 karede ortalama hız
  hedefin ±%5'i içinde
- süzgeç: tek adaylı oturum (`hits = 1`) elenir; iki adaylı ve FALL olan
  geçer; RUN'da süre < 1 sn ise elenir
- `load_annotation`: `eval_end_sec` sonrası olaylar düşer

## 3. Ölçüm B0 — değişiklikten önce

Ana dizinde, 13.3a commit'i `main`'e alındıktan sonra. Önce
`nvidia-smi`: GPU'yu kullanan oyun veya tarayıcı kapalı olmalı.

```bash
venv/Scripts/python.exe -m eval.tcn_eval --modes rule,hybrid --limit 15 \
    --fps 0,10,5 --drop regular,jitter --seeds 0,1,2 --out logs/fps_b0.json
```

- `--limit 15`: Aşama 9.5 / 11'deki holdout kümesi (sınıf başına 15
  klip, 60 klip)
- Kaba süre: özgün hızda iki küme ~15 bin kare; dokuz yapılandırma × iki
  mod, toplam ~1 saat (arka planda)
- Ana oturum ham sayılara bakar: klip başına aday listesi ve etkin FPS.
  Yalnız tabloya bakmak yetmez.
- `docs/DURUM.md`'ye B0 tabloları yazılır, sorunun büyüklüğünün kanıtı
  olarak. Gözlenecekler:
  - `zone_01`'in sahte RUN'ı FPS ile nasıl değişiyor
  - `police_run` hangi hızda aday üretiyor

## 4. Paket K — kurallar, öznitelikler, izleyici (13.3b)

Dosyalar:
- `vision/stages/features.py`, `smoother.py`, `tracker.py`
- `vision/rules/fall.py`, `run.py`, `zone.py`, `fight.py`, `loiter.py`,
  `engine.py`
- `vision/rules/arbiter.py` (yalnız koşu sıklığı)
- `vision/camera.py` (yalnız `tracker.update` çağrısı)
- `tracker.update` çağıran değerlendirme betikleri: `pilot_eval`,
  `tcn_eval`, `extract_sequences`, `domain_gap`, `feature_stats`,
  `loiter_probe`
- `tests/test_features_rules.py`, `tests/test_arbiter.py` (ad
  değişiklikleri)
- `tests/test_asama13_3_zaman.py` (yeni)

### 4.1 Öznitelikler (`features.py`)

- `EPS`, `STALE_SEC`, `VELOCITY_SEC`, `LIMB_SEC`, `RETAIN_SEC` bu
  modülde tanımlanır. `smoother.py` ve `loiter.py` `STALE_SEC`'i buradan
  alır (bugün üç ayrı 90 var).
- `TrackWindow` zamanla budanır:
  - ekleme sonrası `len >= 2 and frames[1].ts <= last.ts - RETAIN_SEC + EPS`
    oldukça soldan atılır, yani sınırın ötesinde tam bir kare kalır
  - bellek güvencesi olarak `deque(maxlen=250)`
  - `since` / `covering` eklenir; `recent(n)` T'ye kadar kalır
    (`window_tensor` kullanıyor)
- `RETAIN_SEC = 2.0`, `GAIT_SEC`'ten (1,96) ve TCN penceresinden (1,96)
  büyük olmalı. Test bunu denetler.
- `_velocity`: başvuru, `ts <= now - VELOCITY_SEC + EPS` olan **en yeni**
  önceki karedir; yoksa `(0, 0)`. Bu, "pencere dolmadan hız yok" kuralının
  aynısıdır. 25 FPS'te `frames[-5]`.
- `_limb_speed`: `(ts, kp)` geçmişinde, `len >= 2 and hist[1].ts <= now - LIMB_SEC + EPS`
  oldukça soldan atılır; başvuru `hist[0]`. 25 FPS'te 3 kare geri. İz
  doğarken eski kod nasıl en eskiyi kullanıyorsa yine öyle.
- `FeatureEngine(velocity_lookback=...)` → `velocity_sec=...`.
  `window_frames` parametresi kalkar.
- `_cleanup` artık kare sayısıyla değil, son görülme zamanıyla çalışır:
  `ts - son_gorulme > STALE_SEC` olan iz düşer. `__call__` zaten `ts`
  alıyor.

### 4.2 Kurallar

- **`fall`, `run`, `zone`:** §1 tablosu. Kısa pencere (`covering` →
  `None`) bugünkü `len < N` ile aynı sonucu verir, yani aday yok.
- **`fight`:** `_streak: dict[pair, int]` → `_since: dict[pair, float]`.
  - şart ilk sağlandığında başlangıç `ts`'i yazılır
  - şart sağlanmazsa veya çift bu karede görülmezse kayıt silinir (bugünkü
    sıfırlama)
  - `ts - since >= HOLD_SEC - EPS` olunca aday üretilir
- **`loiter`:** `last_seen_idx` / `away_since_idx` → `last_seen_ts` /
  `away_since_ts`; `_prune(ts)`. Bugün `idx` farkı kaynak karesi sayıyor;
  canlıda atlanan kareler yüzünden işlenen kareyle aynı şey değil. Bu
  tutarsızlık da gider. Modül notundaki `window_frames=30` ifadesi
  düzeltilir.
- **D1 (`ASAMA13_PLAN.md`) — `Zone.active_at`:** dosya kaynağında `ts`
  sahne saniyesi olduğu için 1970'e çözülüyordu.
  - `RuleEngine(..., clock=time.time)` saati `ZoneRule` ve `LoiterRule`'a
    geçirir
  - iki kural `zone.active_at(self.clock())` çağırır
  - canlıda davranış aynı kalır (`ts` zaten duvar saatiydi)
  - `eval/zones.json`'da `restricted_hours` bölgesi yok, ölçüm
    etkilenmez
- **`arbiter`:** `idx % every` → zamana bağlı sıklık. Son model
  koşusunun `ts`'i tutulur; `ts - last >= every_sec - EPS` ise model
  koşar. Parametre `every: int` → `every_sec: float = MODEL_EVERY_SEC`.
  Bugünkü kodun bir sessiz hatası da gider: canlıda kare atlandığında
  `idx` dizisinin evresi 5'in katına hiç denk gelmeyebilir, örneğin 2, 7,
  12, … Bu durumda model hiç koşmaz.

### 4.3 İzleyici (`tracker.py`)

Ultralytics 8.4.127'de `max_frames_lost = args.track_buffer`; FPS'e
göre ölçeklenmiyor (doğrulandı: `byte_tracker.py`).

- `Tracker.update(result, image, ts: float)`: `ts` **zorunlu**. Bir
  çağıranın sessizce eski davranışta kalması önlenir; bütün çağıranlar
  güncellenir.
- Kare aralığı üstel ortalamayla izlenir: `dt_ema = 0.9 * dt_ema + 0.1 * dt`.
  Başlangıç 0,04; yalnız `0 < dt < 1.0` alınır, böylece kopma ve yeniden
  bağlanma ortalamayı bozmaz.
- Her çağrıda `self._tracker.max_frames_lost = max(1, round(TRACK_BUFFER_SEC / dt_ema))`.
  `OVERRIDES["track_buffer"]` başlangıç değeri olarak 60'ta kalır.
- `camera.py`: `self.tracker.update(result, image, ts)`. `ts` aynı satırda
  zaten hesaplanıyor; satırı bir yukarı taşımak yeter.

### 4.4 Testler (`tests/test_asama13_3_zaman.py`)

- `covering` / `since`:
  - 25 FPS'te `covering(0.08)` 3 kare, `covering(1.96)` 50 kare
  - 5 FPS'te `covering(0.08)` 2 kare
  - kısa izde `None`
- **25 FPS eşdeğerliği** (sentetik, boşluksuz iz):
  - FALL: tilt 3 karede tutuyor ve 2 karede tutmuyor; tetikleme bugünkü
    kare sayısıyla
  - RUN: 10 karede 6 isabet tetikliyor, 5 isabet tetiklemiyor
  - zone: 3 karelik tutma
  - fight: 3 karelik seri
- **FPS bağımsızlığı:** aynı fiziksel hareket (sabit hızla koşu, düşme
  profili, bölgede bekleme, kavga çifti) 25, 10 ve 5 FPS'te
  örneklenir. Her hızda aday üretilir. Hız öznitelikleri 25 FPS'tekinin
  ±%10'u içinde kalır.
- iz yaşı:
  - 5 FPS'te 3,6 sn görünmeyen iz düşer, 3,4 sn görünmeyen düşmez
    (öznitelik, düzleyici ve loiter için ayrı ayrı)
  - eski kodda 5 FPS'te bu süre 18 sn'ydi
- arbiter: `ts` 0,04 adımla gelince model her 5. çağrıda koşar; `idx`
  2, 7, 12, … gelse de koşar
- izleyici: `ts` 5 FPS adımla gelince `max_frames_lost == 12`, 25 FPS'te
  60
- D1: sahte saat 03:00 → `restricted_hours` (22:00–06:00) etkin; 12:00 →
  etkin değil; `FrameFeatures.ts`'ten bağımsız
- değişmez: `RETAIN_SEC >= GAIT_SEC`

Var olan testler yeni adlara geçer (`GAIT_LOOKBACK` → `GAIT_SEC`,
`STALE_FRAMES` → `STALE_SEC`, `velocity_lookback` → `velocity_sec`). 25
FPS'teki beklenen sonuçları değişmez.

## 5. Ölçüm B1 — kurallar sonrası

13.3b `main`'e alındıktan sonra, aynı komut `--modes rule --out logs/fps_b1.json`
ile. `--compare logs/fps_b0.json logs/fps_b1.json`.

- 25 FPS'lik klipler (`mixed_01`, `zone_01`): özgün hız satırı B0 ile
  aynı veya çok yakın olmalı. Fark ancak izdeki boşluklardan gelebilir
  (§1); her fark aday düzeyinde açıklanır. Açıklanamayan fark dönüşüm
  hatası sayılır ve T'ye geçilmez.
- 30 / 24 / 15 FPS'lik klipler (`fall_01`, `run_01`, `normal_01`,
  `police_run`) özgün hızda da değişebilir: eski pencere orada da kare
  sayısıyla kısalıyor ya da uzuyordu. Değişim klip klip açıklanır.

## 6. Paket T — TCN girdisi zamana (13.3c)

Dosyalar:
- `models/tcn.py`, `vision/rules/arbiter.py` (`window_tensor`),
  `vision/camera.py` (`build_engine`'in yakaladığı hata)
- `eval/extract_sequences.py`, `eval/tcn_eval.py` (holdout listesi)
- `tests/test_arbiter.py`, `tests/test_asama13_3_tcn.py` (yeni)

### 6.1 Yeniden örnekleme (`models/tcn.py`)

```python
GRID_HZ = 25.0
WINDOW_SEC = (WINDOW - 1) / GRID_HZ      # 1.96

def resample(ts: np.ndarray, bbox: np.ndarray, kp: np.ndarray,
             has_pose: np.ndarray, t_end: float | None = None) -> np.ndarray | None:
    """Tek izin ornekleri (ts artan) -> (WINDOW, CHANNELS); kapsam veya poz yetersizse None."""
```

- `t_end` verilmezse `ts[-1]` alınır. Izgara `t_k = t_end - (WINDOW-1-k) / GRID_HZ`.
  `ts[0] > t_0 + EPS` ise `None` döner (iz 1,96 sn'yi kapsamıyor).
- Her ızgara noktası için iki komşu bulunur: `a` (`ts <= t`) ve `b`
  (sonraki). Ağırlık `w`. Hesap `np.searchsorted` ile vektörel yapılır,
  Python döngüsü olmaz.
- bbox: doğrusal ara değer.
- Poz:
  - **iki komşuda da poz varsa:** x, y ve güven doğrusal ara değerle
    hesaplanır. Bir eklem iki komşudan birinde `KP_CONF = 0.5`'in
    altındaysa ara değer alınmaz; o eklemin x, y'si güveni yüksek olan
    komşudan kopyalanır. Güveni düşük konuma doğru ara değer almak
    eklemi uydurur.
  - **yalnız biri pozluysa:** en yakın komşu pozluysa onun eklemleri
    kopyalanır, değilse o nokta pozsuz sayılır.
- Pozlu ızgara noktası oranı `< MIN_POSE_RATIO` ise `None`.
- Satırlar yine `frame_vector`'dan geçer:
  `frame_vector(bbox_k, kp_k, bbox_{k-1}, 1 / GRID_HZ)`; ilk satırda
  `prev = None`. Kanal düzeni ve tek kaynak ilkesi korunur.
- Özellik: 25 FPS'te ızgaraya oturan girdi, eski `window_tensor`'ın
  çıktısını 1e-5 içinde verir. Test eder.

`arbiter.window_tensor(window)`: `window.frames`'ten dizileri kurar,
`resample(..., t_end=last.ts)` çağırır. bbox'ı olmayan kare varsa `None`
(bugünkü şart). `TrackWindow.recent` başka yerde kullanılmıyorsa kalkar.

### 6.2 Eğitim verisi

Bugün `data/sequences` hazır 50 karelik pencereler tutuyor. Hız ve kare
düşürme artırımı için ham iz gerekir; YOLO'yu her eğitimde yeniden
koşmak (1080 klip, dakikada 7–10 klip, ~2 sa) kabul edilemez.

- **`eval/extract_sequences.py` → `data/tracks/<SINIF>/<klip>.npz`:**
  - alanlar: `fps`, `n_frames`, `ts (n,)`, `track (n,)`, `bbox (n,4)`,
    `kp (n,17,3)` (pozsuzda sıfır), `has_pose (n,)`,
    `event_ts (m,)` (URFD'nin FALL karelerinin `ts`'i; diğerlerinde boş)
  - klip başına tek dosya; iz yoksa boş dosya. Bugünkü kural: yeniden
    başlatılan koşu baştan işlemez, bölme sırası değişmez
  - pencere kurma bu betikten çıkar
  - `split_runs` ve `clip_windows` `models/tcn.py`'ye taşınır
- **Pencereleme (`models/tcn.py`):**
  - iz, `STALE_SEC`'ten uzun boşlukta koşulara bölünür
    (`vision.stages.features`'tan alınır)
  - pencere sonları `koşu_başı + WINDOW_SEC` noktasından başlar ve
    `STRIDE_SEC` adımla ilerler
  - her son, hedeften **sonraki ilk gerçek örneğe** çekilir. Çalışma
    zamanında da pencere sonu hep gerçek bir karedir. Aynı örneğe çekilen
    sonlar bir kez sayılır. (Uygulamada düzeltildi: ilk sürüm sonu
    hedeften önceki örneğe çekiyordu. Pencere 1,96 sn'yi kapsamıyordu ve
    30 FPS'lik kısa kliplerden hiç pencere çıkmıyordu.)
  - URFD'de pencere `[t_end - WINDOW_SEC, t_end]` aralığına düşen bir
    `event_ts` içermiyorsa düşer
  - `STRIDE_SEC = 0.4`, bütün sınıflarda. Plan FALL için 0,4,
    diğerleri için 1,0 diyordu; uygulamada değişti. Sebep: pencere 1,67
    sn'den (30 FPS'te 50 kare) 1,96 sn'ye uzadı ve 1 sn kaydırmayla kısa
    FIGHT klipleri yarı pencere veriyordu (`docs/DURUM.md`, 13.3c).
- **Artırım:** her klip özgün hıza ek olarak 15, 10 ve 5 FPS'e
  `FrameDropper(mode="jitter", seed=crc32(stem))` ile seyreltilir. Kareler
  klip düzeyinde atılır, yani o anki bütün izlerden birlikte. Seyreltici,
  klibin bütün kare zaman çizgisi (`arange(n_frames) / fps`) üzerinde
  koşar; yalnız iz görülen kareler üzerinde koşsaydı izsiz aralıklar
  boşluk sayılırdı. Seyreltilmiş
  örneklerden aynı pencereleme kurulur. Eğitim ve doğrulama aynı biçimde
  artırılır. Bölme hâlâ klip başına (`i % VAL_EVERY`); aynı klibin
  kopyaları aynı tarafta kalır, sızıntı olmaz.
- **Tekrarlanabilirlik:** `torch.manual_seed(0)`, artırım tohumu sabit.
- **Rapor:** eğitim sonunda doğrulama makro F1 hız başına ayrı basılır
  (özgün / 15 / 10 / 5). Eski 0,698 ile yalnız "özgün" satırı yan yana
  konur; pencere tanımı değiştiği için birebir karşılaştırma değildir,
  öyle yazılır.
- `load_split(root)` imzası korunur. `eval/conf_sweep.py` değişmeden
  çalışır.

**Bilinçli sapma — hız artırımı (0,5x–2x) uygulanmaz.** Yol haritası
bunu öneriyordu. Hız bu sınıflarda etiketin kendisidir: 2x hızlanmış
yürüyüş koşu temposuna, 0,5x yavaşlamış düşme oturmaya yaklaşır. Artırım
etiketi bozar. FPS bağımsızlığını yeniden örnekleme ve kare düşürme
sağlar; hız artırımına bunun için gerek yok. Gerekirse 14'te saha
verisiyle ayrıca denenir.

### 6.3 Model meta verisi ve güvenlik

- `tcn_meta.json`'a `"grid_hz": 25.0` ve `"window_sec": 1.96` yazılır.
- `TCNClassifier`, meta'da `grid_hz` yoksa veya farklıysa `ValueError`
  atar. Mesaj: "model kare tabanli girdiyle egitilmis; `models.tcn --train`
  ile yeniden egit". Eski ağırlıkla yeni girdi sessizce yanlış uzayda
  çalışmaz.
- `camera.build_engine`, `ValueError`'u da yakalar ve yalnız kurala
  düşer. Mesaj başlangıçta basılır.

### 6.4 Testler (`tests/test_asama13_3_tcn.py`)

- `resample`:
  - 25 FPS ızgara girdisi, doğrudan `frame_vector` dizisini 1e-5 içinde
    veriyor
  - sabit hızlı sentetik iz 25, 10 ve 5 FPS'te örneklenince çıktılar
    25 FPS'tekine yakın (x, y'de en büyük fark < 0,02; hız kanalı ±%10)
  - kısa iz → `None`
  - pozsuz çoğunluk → `None`
- güven bilinçli ara değer: bir komşuda güven < 0,5 olan eklem diğer
  komşunun konumunu alıyor
- pencereleme:
  - 4 sn'lik izde (stride 1 sn) pencere sayısı doğru
  - `STALE_SEC`'i aşan boşluk koşuyu bölüyor
  - URFD süzgeci çalışıyor
- artırım: aynı tohum aynı pencereleri veriyor; doğrulama kopyaları
  eğitime sızmıyor (klip adı kesişimi boş)
- meta: `grid_hz`'siz meta → `ValueError`
- holdout listesi: `data/tracks` ile `data/sequences` aynı sıralı klip
  listesini veriyor. Veri yoksa test atlanır.

## 7. Yeniden çıkarım, eğitim, B2

Ana dizinde, 13.3c `main`'e alındıktan sonra.

1. Eski model yedeklenir: `models/tcn.pt` ve `models/tcn_meta.json` →
   `runs/tcn_kare_tabanli/` (ikisi de git dışında). Geri dönüş yolu
   budur.
2. `eval.extract_sequences`: ~2 sa, arka planda, `logs/`'a kayıt. Sınıf
   başına iz ve örnek sayısı raporlanır.
3. `models.tcn --train`: hız başına doğrulama F1 ve karışıklık matrisi
   `docs/DURUM.md`'ye.
4. **B2:** §3'teki komut, `--out logs/fps_b2.json`. Sonra
   `--compare logs/fps_b0.json logs/fps_b2.json` ve
   `--compare logs/fps_b1.json logs/fps_b2.json` (yalnız kural
   satırları).
5. Holdout klip listesinin B0'dakiyle aynı olduğu doğrulanır
   (`tcn_eval`'in bastığı liste).
6. **Canlı duman testi:** `vision.run`, `fall_01` ile `--realtime --loop`
   ve TCN açık, ~2 dk. Beklenenler:
   - çökme yok
   - raporda `model_runs > 0`
   - aday üretiliyor
   - işlenen FPS ve izleyicinin `max_frames_lost` değeri tutarlı

## 8. Kabul

1. Tam test paketi yeşil; paket koştuktan sonra `git status` temiz.
2. `docs/DURUM.md`'de B0, B1 ve B2 tabloları var: mod × küme × FPS ×
   drop, ham ve süzgeçli, tip başına F1 ve ham TP/FP/FN.
3. **Özgün hız satırları:** B2'nin toplam F1'i (kural ve hibrit, pilot ve
   holdout, ham ve süzgeçli) B0'ın altında değil. Herhangi bir tipte
   düşüş varsa klip klip açıklanır. Gerileme varsa aşama kapanmaz:
   bulgu yazılır ve karar kullanıcıya sorulur. Eşik oynatılarak
   kapatılmaz.
4. 10 ve 5 FPS'teki düşüş öncesi / sonrası raporlanır. Hedef sayı
   önceden konmaz.
5. Holdout klip listesi B0 ile aynı.
6. Canlı duman testi §7.6'daki gibi.
7. Tez notu: `docs/TEZ.md`'ye 13.3 için kısa bir bölüm taslağı yazılır.
   Sorun, ölçüm ve FPS eğrisi; sayılar B tablolarından.

## 9. Kapsam dışı (kayıt)

- **`detection_settings.window_frames`** (veritabanı, panel ayarı):
  bugün de görü tarafından okunmuyor; `FeatureEngine` varsayılan 50'yi
  kullanıyor. Ölü ayar, bu aşamada dokunulmaz. 13.6'da (panel)
  kaldırılması veya saniyeye çevrilmesi önerilir; açık soru olarak
  DURUM'a yazılır.
- **Spark `min_hits = 2`:** kare sayısıdır. Süzgeçli tablo FPS'e bağlı
  elemeyi gösterecek; düzeltme gerekiyorsa ayrı karar.
- **`BUFFER_FRAMES = 300`** (kanıt tamponu): kaynak FPS'ine bağlı,
  işleme FPS'ine değil. 60 FPS'lik kamerada ±5 sn'lik klip tutmaz. Bu
  16'nın (hız, 4K) konusu.
- **Eğitimde izleyici bütün kareleri görüyor:** seyreltme algılamadan
  sonra yapılıyor. Canlıda izleyici yalnız işlenen kareyi görür; kimlik
  kopmaları biraz daha sık olabilir. Değerlendirme (Ö) seyreltmeyi
  algılamadan önce yaptığı için bu fark B2'de ölçülmüş olur.
- **`zone_01` sahte RUN ve `police_run`:** yalnız gözlenir ve raporlanır.
  Kural düzeltmesi 14'ün saha verisiyle.

## 10. Ortak kurallar

- Dokunulan her `.py` dosyasında yorumlar ASCII, kısa ve "neden"i anlatır.
  Saniye sabitinin yanında 25 FPS'teki kare karşılığı yazılır, örneğin
  `HOLD_SEC = 0.08  # 25 FPS'te 3 kare`.
- Paketler sırayla uygulanır; bir paket ötekinin dosyasına yalnız bu
  planda yazan yerde dokunur.
- Uzun koşular arka planda ve `logs/`'a kayıtla; artık python süreçleri
  ölçüm sonunda temizlenir.
