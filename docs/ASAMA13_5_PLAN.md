# Aşama 13.5 — Yön ihlali ve bölgede koşma: uygulama planı (2026-11-26)

Kapsam ve kabul: `docs/YOL_HARITASI.md` §13.5, bulgu E2
(`docs/ASAMA13_PLAN.md`). İki olay tipi her yerde hazır ama kuralları yok:
veritabanı şeması (`zone_type = 'direction'`, `direction_vector`), önem
tablosu (`RUN_ZONE` high, `WRONG_DIRECTION` medium), LLM eylem cümlesi,
panel etiketi, şema doğrulaması. Bu aşama kuralları yazar ve panelde yön
bölgesi çizimini açar.

**Uygulayıcıya not:** burada yazmayan davranış değişikliği yapılmaz. Var
olan eşikler ve kurallar (FALL, RUN, ZONE, FIGHT, LOITER) değişmez. Yeni
sabitler §2'deki değerlerle yazılır; kliplere bakılarak ayarlanmaz.

---

## 0. Okurken bulunan eksik: panelde çizilen bölgeler görüye ulaşmıyor

Görü hattı bölgeleri **yalnız** `--zones` JSON dosyasından okuyor
(`vision/camera.py` `load_zones`). `SettingsClient` API'den yalnız
eşikleri çekiyor. Panelde çizilen, değiştirilen veya silinen bölge
veritabanına yazılıyor ama çalışan kurala hiç ulaşmıyor. Bugün tutarlı
görünmesinin tek sebebi, pilot bölgelerin aynı JSON'dan veritabanına
tohumlanması (`scripts/seed_pilot.py`).

Yön bölgesi çizimini açmak bu yol olmadan işe yaramaz (bolgeler.js'teki
not tam bunu söylüyor). Bu yüzden 13.5'in kapsamına girer (§4): görü,
`--settings-url` verildiğinde bölgeleri de API'den çeker. Dosya
değerlendirme ve çevrimdışı koşu için kalır.

Okurken bulunan ikinci hata: `LoiterRule` bölge modunu "herhangi bir
bölge varsa" seçiyor. Kamerada yalnız yön bölgesi varsa kural bölge
moduna geçer ama `_matching_zone` yön bölgelerini atladığı için oyalanma
hiç tetiklenmez. Düzeltme §3.4.

## 1. Tanımlar

- **`WRONG_DIRECTION` (ters yön):** ayağı bir `direction` bölgesinin
  içinde olan kişi, bölgenin izin verilen yönünün **tersine** yürüyor.
- **`RUN_ZONE` (bölgede koşma):** RUN adayı üreten kişinin ayağı o karede
  bir yasak bölgede (`forbidden` ya da saati etkin `restricted_hours`).
  RUN'ın daha özel, daha ağır hâli: aday `RUN`'dan `RUN_ZONE`'a çevrilir.
  `ZONE_VIOLATION` değişmez, kendi yolunda üretilmeye devam eder.

**Neden RUN_ZONE yalnız RUN'ın yerine geçer:** ZONE_VIOLATION bölgede
bulunmanın kaydıdır, koşmaktan bağımsızdır; ikisini birleştirmek bölge
kuralının ölçümünü (Aşama 3, 4) bozar. Bedeli: koşarak yasak bölgeye giren
biri hem `ZONE_VIOLATION` hem `RUN_ZONE` olayı üretir (ikisi de high).
Olay birleştirme bu aşamanın konusu değil.

## 2. Ters yön kuralı: `vision/rules/direction.py` (yeni)

```python
DIR_SEC = 1.0             # yer degistirmenin olculdugu pencere
MIN_AGAINST_SPEED = 0.25  # boy/sn; ters yondeki hiz bileseninin alt siniri
MAX_ANGLE_DEG = 60.0      # hareket, izin verilen yonun tersinden en fazla bu kadar sapabilir

class DirectionRule:
    def __init__(self, zones: Sequence[Zone], clock: Callable[[], float]) -> None: ...
    def check(self, window: TrackWindow, th: Thresholds) -> Candidate | None: ...
```

**Gerekçeler:**
- `DIR_SEC = 1.0`: bir adım döngüsü (sağ + sol) yetişkinde ~1 sn sürer
  (yürüme döngüsü). Bir döngü boyunca ölçülen net yer değiştirme, adım
  içindeki yanal salınımı ve ayak noktası titremesini götürür.
- `MIN_AGAINST_SPEED = 0.25` boy/sn: rahat yürüme hızı yetişkinde
  ~1,3–1,4 m/sn, yaşlılarda yavaş yürüme ~0,6–0,8 m/sn; 1,7 m boyda
  sırasıyla ~0,8 ve ~0,4 boy/sn. Eşik yavaş yürüyenin de altında
  (~0,43 m/sn): yürüyen herkes geçer, yerinde salınan ve ayak noktası
  titreyen kişi geçmez. Hız boy cinsinden: kameradan uzaklık etkisizdir
  (RUN'ın `norm_speed` ilkesi).
- `MAX_ANGLE_DEG = 60`: yolun eğriliğine ve köşegen yürüyüşe pay.
  Tam dik (90°) geçiş ters yön sayılmaz.

Kaynak notu: yürüme hızları genel biyomekanik değerlerdir; tezde kaynak
gösterilmeli (ör. Bohannon 1997, rahat yürüme hızı normları). Değerler
saha kaydında (14) doğrulanacak.

**Algoritma** (her poz'lu iz için, `ZoneRule` deseni):

1. `zone_type == "direction"`, `direction_vector` dolu, `zone.active_at(self.clock())`
   ve `zone.contains(last.foot)` olan ilk bölge. Yoksa `None`.
2. `win = window.covering(DIR_SEC)`; `None` ise aday yok (iz bir saniyeden
   genç).
3. Yer değiştirme **piksel uzayında**: işlenen kare sabit 960×540
   (`vision.stages.preprocess.FRAME_W/FRAME_H`), `foot` ve
   `direction_vector` 0–1 normalize. İkisi de `(x·FRAME_W, y·FRAME_H)` ile
   piksele çevrilir; böylece açı 16:9 sıkışmasından etkilenmez.
   - `d = foot_px(last) - foot_px(win[0])`, `dt = last.ts - win[0].ts`
   - `u = birim(v_px)`; `v_px` sıfırsa bölge atlanır
4. `along = (d · u) / dt / h`; `h` = penceredeki `height` ortancası (px).
   `against = -along`.
5. `|d| > 0` ve `cos = (d · u) / |d|`. Şart: `against >= MIN_AGAINST_SPEED`
   ve `cos <= -cos(MAX_ANGLE_DEG)`.
6. Aday: `anomaly_type="WRONG_DIRECTION"`, `score = min(-cos, 1.0)`,
   `metrics = {"against_speed", "cos", "dx_px", "dy_px"}`,
   `thresholds_used = {"min_against_speed", "max_angle_deg"}`,
   `zone_name = zone.name`.

Kare hızından bağımsız: pencere saniye, hız boy/sn (13.3 ilkesi).

## 3. Görü tarafı bağlantılar

### 3.1 `vision/rules/engine.py`

- `RuleEngine.__init__` `DirectionRule(self.zones, self.clock)` kurar;
  `__call__` döngüsüne eklenir (`fall, run, zone, loiter, direction`).
- `set_zones(zones: Sequence[Zone]) -> None`: `self.zones` ve bölge
  kullanan üç kural **yeni nesne** olarak kurulur (`ZoneRule`,
  `LoiterRule`, `DirectionRule`), sonra tek tek atanır. Ana döngü o anda
  eski nesneleri kullanıyorsa sorun yok; yarım güncellenmiş liste
  görülmez. Oyalanma sayaçları sıfırlanır (bölge tanımı değişti, eski
  sayaç anlamını yitirdi). Yalnız bölgeler gerçekten değiştiyse çağrılır
  (§4).

### 3.2 `vision/rules/arbiter.py`

- `RULE_ONLY`'ye `"WRONG_DIRECTION"` eklenir (model bu tipi üretmez).
- `set_zones(zones)` → `self.engine.set_zones(zones)` (`SettingsClient`
  hakemle de çalışsın).

### 3.3 `vision/rules/zone.py` — RUN_ZONE

```python
def upgrade_run_in_zone(candidates: list[Candidate], windows: dict[int, TrackWindow],
                        zones: Sequence[Zone], now: float) -> list[Candidate]:
    """RUN adayinin izinin son ayagi yasak / saati etkin bolgedeyse aday RUN_ZONE olur
    (yerinde degistirilir, zone_name yazilir). Digerleri aynen."""
```

- Bölge seçimi `ZoneRule` ile aynı: `forbidden` veya
  `restricted_hours` + `active_at(now)`; `contains(window.last.foot)`.
- `vision/camera.py` `consume()`: `candidates = self.rule_engine(windows)`
  satırından hemen sonra, `now` hesaplandıktan sonra ve `event_time`
  atanmadan önce çağrılır (`self.rule_engine.zones`, `now`).
- **Neden kural motorunda değil kamerada:** hakem RUN'ı modelle de
  üretiyor; çeviri hakemden sonra yapılınca model RUN'ı da kapsanır.
  Değerlendirme betikleri (`tcn_eval`, `pilot_eval`) motoru doğrudan
  çağırır ve çeviriyi görmez: RUN ölçümü önceki aşamalarla aynı kalır.

### 3.4 `vision/rules/loiter.py`

- Bölge modu yalnız `forbidden` / `restricted_hours` bölgelerine bakar:
  `self.zones = [z for z in zones if z.zone_type in ("forbidden", "restricted_hours")]`.
  Kamerada yalnız yön bölgesi varsa çapa modu kullanılır (bugün oyalanma
  hiç tetiklenmiyordu).

### 3.5 `vision/camera.py` `load_zones`

- JSON girdisindeki `direction_vector` okunur (`tuple` ya da `None`).

## 4. Bölgeler API'den: `vision/settings_client.py`

- Her yoklamada eşiklere ek olarak
  `GET {base}/api/zones?camera_id={camera_id}` (aynı başlık, aynı zaman
  aşımı). `camera_id` ad ya da sayı olabilir (§5.1).
- Saf fonksiyon `zones_from_api(items: list[dict]) -> list[Zone]`:
  - `is_active` false olan atlanır
  - `polygon` → `np.array(..., float32)`; `active_from/to` "HH:MM[:SS]"
    → `datetime.time` (yoksa `None`); `direction_vector` → `tuple` ya da
    `None`
  - bozuk öğe atlanır ve sayılır (`failures`, `last_error`); tek bozuk
    bölge ötekileri düşürmez
- `apply_zones(items) -> bool`: imza = bölgelerin (ad, tip, poligon,
  saatler, vektör) sıralı demeti. İmza son uygulanandan farklıysa
  `engine.set_zones(...)` çağrılır, `zones_applied` artar, stdout'a tek
  satır basılır (`bolgeler guncellendi: N bolge`). Aynıysa hiçbir şey
  yapılmaz.
- **Öncelik:** `--settings-url` verilmişse ilk başarılı yanıttan sonra
  bölgelerin kaynağı API'dir; boş liste de geçerli bir yanıttır
  (operatör bütün bölgeleri silmiş olabilir). Yanıt alınamazsa son
  bilinen bölgeler (ilk başta dosyadakiler) kalır.
- Bölge yoklaması başarısız olursa eşik yoklaması etkilenmez (ayrı
  `try`).
- `CameraPipeline` değişmez: `SettingsClient(..., self.rule_engine, ...)`
  zaten motoru/hakemi alıyor.

## 5. API ve panel

### 5.1 `api/routers/zones.py`

- `list_zones(camera_id: str | None = None, ...)`: `camera_id` verilirse
  `cameras.resolve_camera_id(db, camera_id)` ile çözülür (sayı ya da ad;
  görü kamerayı adıyla tanır). Çözülemezse **404**. (Uygulamada
  düzeltildi: ilk sürüm boş liste döndürüyordu. Görü boş listeyi "bölge
  yok" diye okur ve dosyadan gelen bölgeleri silerdi; veritabanında kaydı
  olmayan bir kamerada bölgeler sessizce kaybolurdu. 404'te görü hata
  sayar, son bilinen bölgeleri korur.)
- Panelin bugünkü sayısal kullanımı aynı sonucu verir.

### 5.2 `api/schemas.py`

- `ZoneIn._check_direction`'a ek: `direction_vector` verilmişse tam 2
  sonlu sayı ve uzunluğu > 1e-6; değilse `ValueError`
  ("direction_vector [dx, dy] olmali ve sifir olmamali").

### 5.3 `stream/filters.py` ve `infra/postgres/init.sql`

- `MIN_SEC_DEFAULT_MAP`'e `"RUN_ZONE": 1.0`, `"WRONG_DIRECTION": 1.0`.
  Bugün de varsayılan 1,0 uygulanıyordu (eşlemede yoktu); açık yazılır.
- `init.sql` `spark_min_sec` varsayılan JSON'u aynı iki anahtarla. Var
  olan kurulumda göç gerekmez: anahtar yoksa Spark aynı 1,0'ı kullanır.

### 5.4 Panel: `frontend/js/bolgeler.js`

- Tip seçimine `<option value="direction">Yön (ters yön)</option>`.
  Baştaki "direction arayüzde YOK" notu kaldırılır, yerine kısa bir not:
  yön bölgesi `vision/rules/direction.py`'yi besler.
- Çizim: poligon bugünkü gibi çizilir. Tip `direction` ise poligon
  kapandıktan sonra **iki tıklama** ile ok çizilir (başlangıç, bitiş);
  `direction_vector = [bx - ax, by - ay]` (0–1 normalize). Form ipucu:
  "İzin verilen yönü iki tıklamayla çizin".
- Kaydetmede `zone_type === "direction"` ise vektör zorunlu; yoksa
  kaydetmez ve uyarı gösterir (`direction_vector: null` yalnız öteki
  tiplerde gönderilir).
- Gösterim: yön bölgelerinde poligonun ağırlık merkezinden vektör
  yönünde bir ok (SVG `line` + `marker-end`); seçili bölge düzenlenirken
  ok yeniden çizilebilir. Var olan bölgeler için vektör API'den gelir.
- Saat alanı yalnız `restricted_hours`'ta görünür (bugünkü gibi).
- `python scripts/build_frontend.py` ile `?v=` etiketleri yenilenir.

## 6. Testler

**Görü** (`tests/test_asama13_5_yon.py`, yeni; sentetik `FrameFeatures`):
1. Bölge vektörü sağa; kişi sola yürür (0,5 boy/sn) → `WRONG_DIRECTION`,
   25 / 10 / 5 FPS.
2. Aynı yönde yürür → aday yok.
3. Dik yürür (yukarı) → aday yok.
4. Yerinde salınır (±0,05 boy, 2 Hz) → aday yok.
5. Ters yönde ama 0,15 boy/sn → aday yok.
6. Ayak bölge dışında → aday yok; iz 1 sn'den genç → aday yok.
7. 16:9 doğruluğu: normalize uzayda 45° görünen ama piksel uzayında 60°'yi
   aşan bir hareket (vektör ve hareket öyle seçilir) → aday yok; piksel
   uzayında tam ters → aday var.
8. Saatli yön bölgesi (`active_from/to`) saat dışında → aday yok (sahte
   saat).
9. `upgrade_run_in_zone`: RUN adayı, ayak yasak bölgede → `RUN_ZONE` ve
   `zone_name`; bölge dışında → `RUN`; saati etkin olmayan
   `restricted_hours` → `RUN`; yön bölgesi → `RUN`; FALL adayına dokunmaz.
10. `LoiterRule`: yalnız yön bölgesi varken çapa modunda oyalanma
    tetikleniyor.
11. `RuleEngine.set_zones`: yeni bölge sonraki çağrıda etkili; hakem
    üzerinden de.
12. `SettingsClient.apply_zones` / `zones_from_api`: pasif bölge atlanır;
    bozuk öğe atlanır, ötekiler uygulanır; aynı yanıt ikinci kez
    `set_zones` çağırmaz; boş liste bölgeleri temizler.
13. `load_zones`: `direction_vector` okunur.

**API ve panel** (`tests/test_asama13_5_bolge.py`, yeni):
- `ZoneIn`: `[0, 0]`, 3 elemanlı, `NaN` vektör reddedilir; geçerli kabul.
- `list_zones` ad ile, sayı ile, bilinmeyen adla (boş liste) — veritabanı
  yoksa atlanır.
- `filters.MIN_SEC_DEFAULT_MAP` iki yeni anahtarı içeriyor ve
  `init.sql` varsayılanıyla aynı.
- `bolgeler.js`: `"direction"` seçeneği var, vektör zorunluluğu var.
  `tests/test_frontend_8_5b.py::test_bolgeler_does_not_offer_direction_zone_type`
  artık geçersiz: ters çevrilir (seçenek var) ve adı düzeltilir.

## 7. İş bölümü

| paket | dosyalar |
|---|---|
| **V — görü** | `vision/rules/direction.py` (yeni), `vision/rules/engine.py`, `vision/rules/arbiter.py`, `vision/rules/zone.py`, `vision/rules/loiter.py`, `vision/camera.py`, `vision/settings_client.py`, `tests/test_asama13_5_yon.py` |
| **A — API, akış, panel** | `api/routers/zones.py`, `api/schemas.py`, `stream/filters.py`, `infra/postgres/init.sql`, `frontend/js/bolgeler.js`, `frontend/*.html` (yalnız `build_frontend` çıktısı), `tests/test_asama13_5_bolge.py`, `tests/test_frontend_8_5b.py` |

Sözleşme: §4'teki istek (`/api/zones?camera_id=<ad|id>`) ve `ZoneOut`
alanları (değişmiyor).

## 8. Doğrulama (ana dizinde)

1. Tam test paketi yeşil (eski `test_asama8_6` hatası hariç, DURUM'da);
   paket sonrası `git status` temiz.
2. **Çevrimdışı duman testi — yön:** geçici bir bölge dosyası,
   `zone_01`'in yürüme alanını kaplayan bir `direction` bölgesi. Bir kez
   vektör bir yöne, bir kez ters yöne. `vision.run --rules --zones <dosya>`
   iki koşu: `WRONG_DIRECTION` aday sayıları ve hangi izlerde çıktığı.
   Beklenen: iki yönde farklı izler; aynı iz iki koşuda birden çıkmaz.
   Doğruluk iddiası değil, mekanizma.
3. **Çevrimdışı duman testi — RUN_ZONE:** `zone_01` `eval/zones.json` ile:
   bölgedeki RUN adaylarının `RUN_ZONE`'a dönüştüğü görülür (bilinen sahte
   RUN 13.3'ten beri burada).
4. **Uçtan uca:** API'ye (`POST /api/zones`) `zone_01` için bir yön
   bölgesi eklenir; `vision.run --settings-url ... --kafka` ile
   `bolgeler guncellendi` satırı ve `WRONG_DIRECTION` olayı veritabanında
   (`severity = medium`). Bölge sonra silinir; görü bir sonraki yoklamada
   bölgeyi bırakır.
5. Panel tarayıcıda görülmeden önce statik testler; görsel denetim
   yapılamazsa DURUM'a yazılır.

## 9. Kabul

1. Testler yeşil (§6).
2. §8'deki duman testleri ve uçtan uca koşu ham sayılarla DURUM'da.
3. Var olan kuralların ve değerlendirme sayılarının değişmediği: `tcn_eval`
   ve `pilot_eval` motoru doğrudan çağırır; yeni kural yalnız `direction`
   bölgesinde çalışır, `eval/zones.json`'da yok.
4. Saha doğrulaması 14'teki yön ihlali kaydında.
5. `docs/TEZ.md`'ye kısa §4.7 taslağı.

**Commit:** `feat: asama 13.5 - yon ihlali ve bolgede kosma kurallari`

## 10. Kapsam dışı (kayıt)

- Olay birleştirme (aynı kişinin aynı anda `ZONE_VIOLATION` +
  `RUN_ZONE` + `RUN`).
- Canlı görüntü üstünde yön okunun çizimi (`kamera-detay`, WS meta):
  panelin bölge ekranı oku gösteriyor, canlı katman 13.6 ile.
- Yön bölgesi için ayrı eşik ayarı (panelden); sabitler kodda, öteki kural
  sabitleri gibi.

## 11. Ortak kurallar

- Yorumlar ASCII, kısa, "neden"i anlatır; yeni sabitin yanında gerekçesi
  tek satırda.
- Paketler birbirinin dosyasına dokunmaz.
- Uzun koşular arka planda ve `logs/`'a kayıtla.
