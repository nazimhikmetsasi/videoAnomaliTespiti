# Aşama 3 — Öznitelik ve Kural Motoru (uygulama sözleşmesi)

Bu dosya Aşama 3'ün uygulama planıdır. `docs/PLAN.md` mimariyi,
`docs/DURUM.md` ilerlemeyi tutar; burada yalnızca **ne yazılacağı ve hangi
imzalarla** yazılacağı vardır. Aşama bitince bu dosya silinmez, uygulanan
sözleşme olarak kalır.

Kod stili mevcut dosyalarla aynı: modül başında neden-açıklaması, ASCII
karakterler (kod ve yorumlarda Türkçe harf yok), `from __future__ import
annotations`, tip ipuçları, aşama başına 150 satır sınırı.

---

## 0. Girdi durumu

Hazır olan: `Track(track_id, bbox, conf, keypoints (17,3), height)` —
`vision/stages/tracker.py`. Keypoint'ler letterbox'lanmış 960x540 kare
uzayındadır, COCO-17 sırasındadır.

Altı pilot klipte pozsuz iz sayısı 0 ölçüldü; yine de "pose yoksa anomali
üretilmez" kuralı yazılacak (PLAN.md zayıf nokta 7).

---

## 1. Değiştirilecek mevcut dosyalar

### `vision/source.py`
- `VideoSource` içine `self.fps: float` eklenecek. Dosya kaynağında
  `cv2.CAP_PROP_FPS`, geçersiz/0 ise 25.0; canlı kaynakta 25.0.
- **Neden:** öznitelikler video zamanına göre hesaplanmalı. Klip 25 FPS
  kayıtken 37 FPS'te işlenirse duvar saati (`frame.ts`) hızları 1.5 kat
  şişirir ve tüm eşikler kayar.

### `vision/stages/tracker.py`
- `Track` dataclass'ına `keypoints_smoothed: np.ndarray | None = None`
  alanı eklenecek. `Smoother` bunu doldurur.
- Başka değişiklik yok.

---

## 2. `vision/stages/smoother.py` (yeni, ~90 satır)

One-Euro filtresi (PLAN.md zayıf nokta 5). Ham keypoint doğrudan türeve
girerse titreme hıza karışır ve yanlış alarm üretir.

```python
class Smoother:
    def __init__(self, *, min_cutoff: float = 1.0, beta: float = 0.05,
                 d_cutoff: float = 1.0, kp_conf: float = 0.5) -> None: ...
    def __call__(self, tracks: list[Track], ts: float) -> list[Track]:
        """Her izin keypoints_smoothed alanini doldurur, ayni listeyi dondurur."""
```

Kurallar:

- **Vektörleştirilmiş.** İz başına durum `(17, 2)` dizileridir
  (`x_prev`, `dx_prev`, `t_prev`). Keypoint başına ayrı filtre nesnesi
  yaratılmayacak — 17 x 2 = 34 nesne/iz gereksiz.
- `dt = ts - t_prev`; `dt <= 0` veya iz ilk kez görülüyorsa ham değer
  aynen kopyalanır ve durum kurulur.
- **Düşük güvenli keypoint** (`conf < kp_conf`): filtreye sokulmaz, son
  düzleştirilmiş değer korunur (`hold`). Güven sütunu ham değeriyle
  taşınır — düzleştirilmiş dizi de `(17, 3)`'tür.
- Formül: `alpha(c) = 1 / (1 + (1/(2*pi*c)) / dt)`,
  `dx = (x - x_prev) / dt`, `dx_hat = lowpass(dx, alpha(d_cutoff))`,
  `cutoff = min_cutoff + beta * |dx_hat|`, `x_hat = lowpass(x, alpha(cutoff))`.
- **Durum temizliği:** `STALE_FRAMES = 90` karedir görülmeyen iz durumu
  düşer. Sayaç `__call__` içinde artar.
- `min_cutoff` ve `beta` yapıcı argümanıdır, sabit değil: farklı kamera ve
  farklı FPS farklı ayar ister.

---

## 3. `vision/stages/features.py` (yeni, ~150 satır)

Ölçek-normalize kinematik (PLAN.md zayıf nokta 4). Tüm hız ve mesafeler
**bbox yüksekliğine bölünür**; birim `1/sn`'dir ve kamera açısından,
çözünürlükten, kişinin uzaklığından bağımsızdır.

```python
KP = {"nose":0, "l_sho":5, "r_sho":6, "l_wri":9, "r_wri":10,
      "l_hip":11, "r_hip":12, "l_knee":13, "r_knee":14,
      "l_ank":15, "r_ank":16}          # COCO-17

@dataclass
class FrameFeatures:
    idx: int
    ts: float
    has_pose: bool
    height: float            # bbox yuksekligi, px (normalizasyon birimi)
    centroid: np.ndarray     # (2,) px — mid_hip, yoksa bbox merkezi
    foot: np.ndarray         # (2,) 0-1 normalize — mid_ankle, yoksa bbox alt orta
    aspect: float            # bbox genislik / yukseklik
    norm_speed: float        # |yatay hiz| / height        (1/sn)
    norm_vy: float           # dikey hiz / height, ASAGI POZITIF (1/sn)
    spine_angle: float       # mid_hip -> mid_sho vektorunun dikeyle acisi, derece
    knee_angle: float        # kalca-diz-ayak bilegi acisi, derece (180 = duz bacak)
    limb_speed: float        # bilek+ayak bilegi icinde en yuksek normalize hiz

class TrackWindow:
    """Tek izin son `window_frames` karesi."""
    track_id: int
    frames: collections.deque[FrameFeatures]
    @property
    def last(self) -> FrameFeatures: ...
    def recent(self, n: int) -> list[FrameFeatures]: ...

class FeatureEngine:
    def __init__(self, *, window_frames: int = 30, kp_conf: float = 0.5,
                 velocity_lookback: int = 5) -> None: ...
    def __call__(self, tracks: list[Track], idx: int, ts: float,
                 frame_shape: tuple[int, int]) -> dict[int, TrackWindow]:
        """Pencereleri gunceller ve BU karede gorulen izlerin pencerelerini dondurur."""
```

Hesap kuralları:

- **Girdi `keypoints_smoothed`'dur**; yoksa `keypoints`'e düşülür.
- `has_pose = keypoints is not None`. `False` ise açı/hız alanları `nan`
  değil `0.0` yazılır ve kural motoru bu kareyi zaten dışlar (bkz. §4).
- **Hız `velocity_lookback` kare geriden** hesaplanır (varsayılan 5),
  kareden kareye değil: tek karelik gürültü hızı ikiye katlıyor.
  `dt = last.ts - old.ts`, `dt <= 0` ise hız 0. Pencere kısaysa mevcut en
  eski kare kullanılır.
- `norm_vy` **aşağı pozitiftir** (görüntü y ekseni aşağı büyür). Düşme
  aşağı hızdır.
- `spine_angle = degrees(atan2(|dx|, |dy|))`, vektör `mid_hip -> mid_sho`.
  Dik duran kişi 0 derece, yatan kişi 90 derece.
- `knee_angle`: iki bacaktan güveni yeterli olanların **en küçüğü**;
  hiçbiri yoksa 180.0.
- `limb_speed`: sol/sağ bilek ve sol/sağ ayak bileğinin son 3 karedeki
  yer değiştirmesi / dt / height — en büyüğü. Kavga kuralının girdisi.
- **Durum temizliği:** `STALE_FRAMES = 90` kare görülmeyen izin penceresi
  düşer.

---

## 4. `vision/rules/` (yeni)

### `vision/rules/engine.py` (~120 satır)

```python
@dataclass
class Thresholds:            # infra/postgres/init.sql detection_settings ile birebir
    pose_conf: float = 0.25
    track_conf: float = 0.30
    fall_spine_deg: float = 45.0
    fall_norm_vy: float = 1.20
    run_norm_speed: float = 1.80
    loiter_sec: int = 30
    fight_proximity: float = 1.20
    window_frames: int = 30

@dataclass
class Zone:
    name: str
    zone_type: str                    # forbidden / restricted_hours / direction
    polygon: np.ndarray               # (N, 2) 0-1 normalize
    active_from: datetime.time | None = None
    active_to: datetime.time | None = None
    direction_vector: tuple[float, float] | None = None
    def contains(self, point: np.ndarray) -> bool: ...      # cv2.pointPolygonTest
    def active_at(self, ts: float) -> bool: ...             # saat araligi; None = hep aktif

@dataclass
class Candidate:
    anomaly_type: str        # FALL / RUN / ZONE_VIOLATION / LOITERING / FIGHT
    track_ids: list[int]
    score: float             # 0-1
    idx: int
    ts: float
    metrics: dict[str, float]          # kurala giren olculen degerler
    thresholds_used: dict[str, float]  # o an gecerli esikler (tez ablation icin)

class RuleEngine:
    def __init__(self, thresholds: Thresholds = Thresholds(),
                 zones: Sequence[Zone] = ()) -> None: ...
    def __call__(self, windows: dict[int, TrackWindow]) -> list[Candidate]: ...
```

**Poz yoksa anomali üretilmez kuralı tek noktada uygulanır:** `RuleEngine`
kurallara vermeden önce `window.last.has_pose is False` olan pencereleri
eler. Kural dosyalarında bu kontrol tekrarlanmaz. (Aynı korumayı beş yere
kopyalamak, PLAN.md'nin v1'den kaçındığı yama yığınının ta kendisidir.)

`Candidate.thresholds_used` **doldurulmak zorundadır**: Aşama 5'te eşikler
veritabanından gelip sıcak yeniden yüklenecek, Aşama 9 ablation tablosu
"karar hangi eşikle verildi" sorusunu buradan okuyacak.

Kural nesneleri `RuleEngine.__init__` içinde bir kez kurulur. Sıra:
`FallRule, RunRule, ZoneRule, LoiterRule, FightRule`.

### Kural arayüzü

Tek kişilik kurallar:

```python
class XRule:
    def check(self, window: TrackWindow, th: Thresholds) -> Candidate | None: ...
```

Bölge gerektirenler yapıcıda `zones` alır. Çoklu kişi kuralı:

```python
class FightRule:
    def check_all(self, windows: dict[int, TrackWindow], th: Thresholds) -> list[Candidate]: ...
```

### `vision/rules/fall.py` — FALL

Tetik: son `HOLD = 3` karenin **hepsinde** `spine_angle >= fall_spine_deg`
**ve** son 15 karede `max(norm_vy) >= fall_norm_vy`.

İki koşul birlikte gerekir: tek başına yatay omurga eğilmedir (öne eğilen
kişi), tek başına aşağı hız çömelmedir. Düşme = hızlı iniş + sonrasında
yatay kalış.

`score = clamp(0.5 * min(spine/esik, 2) + 0.5 * min(vy_max/esik, 2), 0, 1)`.
`metrics`: `spine_angle`, `norm_vy_max`, `aspect`.

### `vision/rules/run.py` — RUN

Tetik: son 10 karenin en az 6'sında `norm_speed >= run_norm_speed`.
Süreklilik şartı, tek karelik sıçramayı eler.

`score = clamp(median(norm_speed) / esik, 0, 1)`.
`metrics`: `norm_speed_median`, `norm_speed_max`.

### `vision/rules/zone.py` — ZONE_VIOLATION

`ZoneRule(zones)`. Tetik: `foot` noktası, `zone_type == "forbidden"` veya
`active_at(ts)` doğru olan `restricted_hours` bölgesinin içinde, son 3
karenin hepsinde.

Ayak noktası kullanılır, bbox merkezi değil: kişi bölgenin kenarında
dururken gövdesi içeri sarkabilir; ihlali belirleyen ayağın nerede
durduğudur.

`score` = son 5 karenin içeride geçen oranı.
`metrics`: `foot_x`, `foot_y`.

Bölge adı `metrics`'e girmez (`metrics` yalnızca sayısal kalır);
`Candidate`a `zone_name: str | None = None` alanı eklenir. Aşama 5'te
`events.zone_id` bu addan çözülecek.

### `vision/rules/loiter.py` — LOITERING

Durum tutar (`dict[int, float]`). İki mod:

1. Bölge tanımlıysa: iz bölgede kesintisiz `loiter_sec` saniyeden uzun
   kaldıysa tetikler.
2. Bölge yoksa: iz son `loiter_sec` saniyedir `centroid`'ini kendi
   yüksekliğinin 1 katından fazla değiştirmediyse (sabit dolaşma).

Pencere 30 kare = ~1.2 sn; `loiter_sec` 30 sn. Pencere bunu tutamaz,
bu yüzden kural kendi girişi (`enter_ts`) ve çıpasını (`anchor`) saklar.
İz kaybolunca (`STALE_FRAMES`) durumu düşer. Aynı iz için tetikledikten
sonra `RETRIGGER_SEC = 10` boyunca susar; yoksa 30 sn'lik bekleyiş her
karede yeni aday üretir.

`metrics`: `dwell_sec`, `drift`.

### `vision/rules/fight.py` — FIGHT

`check_all` ile ikili tarama. Bir çift için tetik:

- `|c_i - c_j| / mean(h_i, h_j) < fight_proximity`, **ve**
- her ikisinde de `limb_speed >= FIGHT_LIMB_SPEED` (varsayılan 2.0, modül
  sabiti, yapıcı argümanı), **ve**
- bu iki koşul son `HOLD = 3` karede sürüyor (çift bazlı sayaç, kuralın
  kendi durumunda).

PLAN.md risk 3: kural tabanlı kavga tespiti yaklaşık %70'tir; gerçek çözüm
Aşama 9 TCN modelidir. Bu kural o zamana kadar taban çizgisidir.

`track_ids` iki elemanlıdır. `metrics`: `proximity`, `limb_speed_min`.

---

## 5. `vision/run.py` — bağlama

- `--rules` bayrağı: açıkken `Smoother -> FeatureEngine -> RuleEngine`
  zinciri döngüye girer, kapalıyken Aşama 2 davranışı birebir korunur
  (ölçüm karşılaştırılabilir kalsın).
- `--zones PATH`: bölge JSON'u (§7 formatı). Verilmezse bölge kuralları
  boş bölge listesiyle sessiz kalır.
- Aşama süreleri raporuna iki satır eklenir: `duzleme` ve `oznitelik+kural`.
- Rapor sonuna aday olay özeti: tip başına aday sayısı, tetikleyen
  benzersiz iz sayısı, ilk tetik saniyesi.
- `draw()` içinde aktif adayı olan izin kutusuna tip etiketi yazılır.
- **Video zamanı:** dosya kaynağında `ts = frame.idx / source.fps`, canlı
  kaynakta `ts = frame.ts`. Bu değer `Smoother` ve `FeatureEngine`'e
  verilen tek zaman kaynağıdır.

---

## 6. `eval/pilot_eval.py` (yeni, ~150 satır)

Aşama 3 onay kriteri: "pilot kliplerde doğru aday olay; ilk
precision/recall ölçümü tabloda".

```bash
venv/Scripts/python.exe -m eval.pilot_eval --clips data/pilot --zones eval/zones.json
```

- Her klip için hattı koşar, adayları `(tip, saniye)` kümesine indirir.
- Gerçek referans `eval/annotations/*.json` (v1'den kopyalanır, format
  aynı: `events: [{type, start_sec, end_sec}]`).
- Saniye bazlı eşleşme. `--tolerance-sec` (varsayılan 1.0) ile aralık
  sınırları gevşetilir; el ile etiketlenmiş sınırlar kesin değildir.
- `NORMAL` aralığında üretilen her aday yanlış pozitiftir.
- Çıktı: tip başına TP / FP / FN / precision / recall / F1 markdown
  tablosu + klip başına ham aday sayısı.
- **Ham aday sayısı ayrıca raporlanır:** Aşama 4'te Spark'ın süzeceği
  gürültü tabanı budur, öncesi/sonrası karşılaştırması buradan yapılacak.
- `police_run` klibinin etiketi yok; eval dışında bırakılır ve rapor
  sonunda "etiketsiz" olarak listelenir.

---

## 7. `eval/zones.json` (yeni)

Bölge poligonları **0-1 normalize** ve letterbox'lanmış kare uzayındadır
(zone_01 640x360 = 16:9, dolgu yok, doğrudan eşleşir).

```json
{
  "zone_01": [
    {
      "name": "bina girisi",
      "zone_type": "forbidden",
      "polygon": [[0.30,0.26],[0.52,0.235],[0.94,0.325],[0.93,0.905],[0.30,0.91]]
    }
  ]
}
```

Bu poligon klibin üzerine gömülü olan (ihlalde kırmızıya dönen) dörtgenden
okundu. Kaba bir okumadır; eval sonucu kenarda kalan tespitlerden
etkileniyorsa rakamlar rapora yazılıp poligon rafine edilir.

---

## 8. `tests/test_features_rules.py` (yeni, assert tabanlı, GPU'suz)

`tests/test_vision_core.py` ile aynı desen: çerçeve yok, `sys.exit` ile
sonuç, sentetik iskeletler.

Zorunlu kontroller:

1. One-Euro gürültüyü düşürür: sabit noktaya eklenen gürültünün standart
   sapması düzleştirmeden sonra en az yarıya iner.
2. One-Euro basamağı geciktirmez: 10 karelik basamak yanıtında son değer
   hedefin %10'u içine girer (aşırı yumuşatma testi).
3. `spine_angle`: dik iskelet ~0 derece, yatay iskelet ~90 derece.
4. `knee_angle`: düz bacak ~180 derece, dik açılı bacak ~90 derece.
5. **Ölçek değişmezliği:** aynı hareket iki kat büyük iskelet ve iki kat
   piksel yer değiştirmesiyle tekrarlandığında `norm_speed` **aynı**
   çıkar (%5 tolerans). Bu test PLAN.md zayıf nokta 4'ün kanıtıdır.
6. `FallRule` sentetik düşme dizisinde tetikler, yürüyüş dizisinde
   tetiklemez.
7. `RunRule` hızlı dizide tetikler, yavaşta tetiklemez.
8. `ZoneRule` poligon içindeki ayakta tetikler, dışındakinde tetiklemez.
9. `LoiterRule` `loiter_sec` aşılınca tetikler, altında tetiklemez.
10. `FightRule` yakın + hızlı uzuvlu çiftte tetikler; uzak çiftte ve
    yakın ama sakin çiftte tetiklemez.
11. **Poz yoksa aday yok:** `keypoints=None` izlerle `RuleEngine` boş
    liste döndürür.

---

## 9. Kapsam dışı (bilinçli)

- **TCN ve HybridArbiter** — Aşama 9. `vision/stages/decision.py` bu
  aşamada yazılmaz; `RuleEngine` doğrudan `run.py`'den çağrılır.
- **Eşiklerin veritabanından okunması ve sıcak yeniden yükleme** —
  Aşama 5. Şimdilik `Thresholds()` varsayılanları koddadır ve
  `init.sql` ile birebir aynıdır.
- **Kafka yayını** — Aşama 4. Adaylar şimdilik yalnızca rapora ve eval'e
  gider.
- **WRONG_DIRECTION** — `Zone.direction_vector` alanı şemada var ama
  kuralı yazılmıyor; PLAN.md Aşama 3 listesinde yok.

---

## 10. Ölçüm sonrası düzeltmeler (2026-08-25, ilk eval koşusundan sonra)

İlk uygulama plana sadıktı ama pilot kliplerde FALL ve RUN hiç tetiklemedi,
ZONE precision 0.05 çıktı. Kural kodu değil, **öznitelik tanımları** yanlıştı.
Kanıtlar aşağıdadır; düzeltmeler bunlardan türetilmiştir.

### 10.1 `spine_angle` -> `body_tilt` (FALL'ın kök nedeni)

Ölçüm, `fall_01`, düşme 5.2-6.8 sn:

```
    sn  nspeed     nvy  spine  aspect
  5.21    0.57    0.31    1.2    0.61
  5.34    0.44    0.75    5.1    1.01   <- kisi yatmis, spine hala 5 derece
  5.47    0.38    0.33   16.7    0.98
  5.61    2.46   -2.79    0.0    1.08   <- kalca kaybolunca spine 0.0
```

Klip boyunca `spine_angle` tepe değeri 20.2 derece, eşik 45. İki ayrı kusur:

1. **Kamera eksenine doğru düşen kişide** kalça->omuz vektörü görüntü
   düzleminde dik kalır. Görüntüden ölçülen omurga açısı bu geometride
   düşmeyi göremez.
2. **Kalça veya omuz keypoint'i güven eşiğini geçemeyince** fonksiyon `0.0`
   döndürüyor. `0.0` "dimdik" demektir; doğrusu "bilinmiyor"dur. Sessiz
   yanlış negatif.

Buna karşılık `aspect` (bbox genişlik/yükseklik) ayrımı temiz veriyor:
yürürken 0.35-0.51, yerdeyken 1.01-1.30.

**Düzeltme:** `FrameFeatures.spine_angle` yerine iki alan:

- `body_tilt: float` — gövdenin dikeyden sapması, derece. Kural bunu kullanır.
  `body_tilt = max(skeleton_tilt, box_tilt)` :
  - `skeleton_tilt` = mevcut `atan2(|dx|, |dy|)` hesabı, **yalnızca** hem
    kalça hem omuz güvenliyse; değilse hesaba girmez.
  - `box_tilt = degrees(atan2(bbox_w, bbox_h))` — her zaman vardır.
    `aspect 1.0` tam 45 dereceye düşer, yani mevcut eşik birimiyle uyumludur.
- `spine_angle: float` — yalnızca iskeletten, bilinmiyorsa `-1.0`. Kural
  kullanmaz; telemetriye ve teze gider (iskelet tek başına neden yetmiyor,
  tabloda görünsün).

`Thresholds.fall_spine_deg` -> `fall_tilt_deg` olarak yeniden adlandırılır,
`infra/postgres/init.sql` içindeki `fall_spine_deg` sütunu da. Aşama 5 henüz
ORM yazmadı; isim şimdi düzeltilmezse kalıcı yanlış ad olur.

**Yanlış pozitif kontrolü (bu düzeltmenin bedeli ölçüldü):** `mixed_01`
8-14 sn arası kadına yakın plandır, `aspect` 1.21'e çıkar, yani `box_tilt`
50 derece. Aynı aralıkta `norm_vy` -0.08 ile 0.16 arasındadır. FALL kuralı
**iki koşulu birlikte** aradığı için (yatay gövde VE aşağı hız zirvesi)
bu kare FALL üretmez. Yakın plan riski gerçek, koruma da gerçek.

### 10.2 `centroid` artık her zaman bbox merkezi

Yukarıdaki dökümde 5.61 sn satırı `nspeed 2.46 / nvy -2.79` gösteriyor.
Bu gerçek hareket değil: kalça keypoint'i kaybolunca `centroid` mid_hip'ten
bbox merkezine atlıyor, iki nokta arasındaki sabit fark tek karede hız
olarak okunuyor.

**Düzeltme:** `centroid` her karede bbox merkezidir, mid_hip yolu kaldırılır.
bbox her zaman vardır ve keypoint'ten daha az titrer. `norm_vy`nin düşmeyi
hâlâ görüp görmediği ölçülüp raporlanacaktır (§10.5).

### 10.3 RUN'a ikinci, geometriden bağımsız kanıt

Ölçülen `norm_speed` tepe değerleri:

| klip | kamera | norm_speed tepe | eşik |
|---|---|---|---|
| run_01 | koşucuyu takip ediyor | 0.41 | 1.80 |
| mixed_01 | kişi kameraya doğru koşuyor | 1.04 | 1.80 |
| police_run | sabit, kişi kadrajı kesiyor | 1.77 | 1.80 |

Yatay görüntü hızı, özne kamera ekseni boyunca hareket ettiğinde veya kamera
özneyi takip ettiğinde **gözlemlenemez**. Sabit kamerada bile (police_run)
eşiğin kıl payı altında kalıyor.

Buna karşılık `limb_speed` (bilek/ayak bileğinin normalize hızı) `run_01`
boyunca 1.0-1.9 bandında sabit kalıyor ve `knee_angle` 81-150 derece
arasında salınıyor — koşu adım döngüsü kamera geometrisinden bağımsızdır.

**Düzeltme:** `RunRule` iki kanıttan **herhangi biri** ile tetikler:

- yer değiştirme: mevcut `norm_speed` koşulu (sabit kamerada geçerli), veya
- adım: son `LOOKBACK` karenin `limb_speed` **medyanı** >= `run_gait_speed`.

Medyan alınır, tepe değil: tek karelik keypoint sıçraması yürüyüşte de 3.0'a
çıkabiliyor (`fall_01` 5.34 sn: 3.26).

`Thresholds`a `run_gait_speed` eklenir, `init.sql` `detection_settings`
tablosuna da. **Değeri tahminle konmaz, ölçülür** (§10.5) — Aşama 2.1'de
`conf` eşiğinin ölçümle 0.35'ten 0.25'e çekilmesiyle aynı yöntem.
`run_norm_speed` de aynı tabloyla yeniden kalibre edilir.

### 10.4 `zone_01` tek kamera değil, kurgu

28. saniyede görüntü tamamen değişiyor (koridor -> otopark), 54. saniyede
koridora dönüyor. Bölge poligonu 0-1 normalize ve **kameraya bağlıdır**;
sahne değişince aynı koordinatlar otoparktaki yayanın üstüne düşüyor. İlk
koşudaki 20 yanlış pozitif saniyenin kaynağı budur, kural değil.

**Düzeltme:** `eval/annotations/zone_01.json` dosyasına
`"eval_end_sec": 28.0` alanı ve nedenini yazan bir `"_not"` alanı eklenir.
`eval/pilot_eval.py` bu alanı destekler: hem gerçek referans hem adaylar bu
saniyeden sonrası için değerlendirmeye alınmaz. Alan yoksa davranış değişmez.

Bu bir eşik ayarı değil, ölçüm alanının düzeltilmesidir: bölge kuralı
kameraya bağlı bir kavramdır, kamera değiştikten sonra o bölge yoktur.

### 10.5 Zorunlu ölçümler (düzeltmelerle birlikte raporlanacak)

1. **Klip başına öznitelik tepe tablosu:** `body_tilt` tepe, `norm_vy` tepe
   (bbox merkezli yeni hesapla), `limb_speed` medyanı — gerçek referansın
   `NORMAL` aralıkları ile olay aralıkları **ayrı satırlarda**.
2. **Eşik seçimi ölçümle:** `run_gait_speed` ve `run_norm_speed` için
   NORMAL aralıklarının 90. yüzdeliği ile olay aralıklarının 10. yüzdeliği
   raporlanır, eşik ikisinin ortasına 0.05 adımına yuvarlanarak konur.
   İki dağılım örtüşüyorsa eşik konmaz, örtüşme raporlanır.
3. **Düzeltme sonrası `eval/pilot_eval.py` tam koşusu:** yeni
   precision/recall tablosu + klip başına ham aday sayısı.
4. `tests/test_features_rules.py` yeni alan adlarına göre güncellenir ve
   `body_tilt`in iskelet yokken bbox'tan hesaplandığını doğrulayan bir
   assert eklenir (12 kontrol).
