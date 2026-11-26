# Aşama 13.6 — Operatör deneyimi: uygulama planı (2026-11-26)

Kapsam ve kabul: `docs/YOL_HARITASI.md` §13.6, bulgular E3 + E4
(`docs/ASAMA13_PLAN.md`). Ayrıca önceki aşamaların 13.6'ya bıraktığı üç
küçük iş (§5).

**Uygulayıcıya not:** burada yazmayan davranış değişikliği yapılmaz. Şablon
tasarımına dokunulmaz; yeni öğeler var olan sınıf jetonlarıyla JS'te
eklenir (bolgeler.js'teki saat alanı deseni). Sahte veri bırakılmaz.

---

## 0. Bugünkü durum (koddan)

- Kırmızı alarm `/ws/alerts` ile geliyor (`api/ws/alerts.py`,
  `anomaly-events`'i ayrı bir grupla okuyor). Canlı izleme ekranı
  (`frontend/js/index.js`) toast'ı gösterip kutuyu kırmızı yakıyor. **Ses
  yok.**
- Toast'ta yalnız "kapat" düğmesi var. Olayı onaylamak için Olaylar
  ekranına gitmek gerekiyor. Alarm gövdesinde olay kimliği yok: alarm
  veritabanı yazımını beklemiyor.
- Olay durumu ucu hazır: `PATCH /api/events/{id}` (`acknowledged` /
  `false_positive`, operatör ve admin).
- Sistem sağlığı (`sistem-sagligi.js`) kamera başına FPS, düşen kare,
  çıkarım süresi ve belge yaşını gösteriyor; sayfa bir kez yükleniyor.
  Sağlık belgesinde birikimli aday sayacı var (13.1, `candidates`) ama
  panel kullanmıyor. 13.1'deki A2 arızası (kamera saatlerce aday üretip
  olay üretmedi) panelde görünmezdi.

## 1. Alarm sesi (`frontend/js/index.js`)

- **Ses dosyası yok:** Web Audio API ile kısa bip dizisi
  (`OscillatorNode` + `GainNode`, yumuşak başlangıç/bitiş).
  - `critical` (FALL, FIGHT) ve kalkamadı (§3): 3 bip, 880 Hz, 150 ms,
    aralık 120 ms
  - `high` (ZONE_VIOLATION, RUN_ZONE): 2 bip, 660 Hz
  - `medium` / `low`: ses yok (kırmızı alarm değil)
- **Tarayıcı kilidi:** `AudioContext` kullanıcı etkileşimi olmadan ses
  çalamaz. Bağlam ilk tıklama / tuş basımında oluşturulur ya da
  `resume()` edilir. Kilitliyken alarm gelirse toast'a tek satır:
  "Sesli alarm için sayfaya bir kez tıklayın".
- **Sessize alma:** ızgara düğmelerinin yanına bir hoparlör düğmesi
  (`volume_up` / `volume_off` simgesi, `title` "Alarm sesi"). Durum
  `localStorage` `alarmMuted`'ta (kişisel tercih; okuma/yazma `try` içinde).
- Aynı saniyede birden çok alarm gelirse ses bir kez çalar (en ağır
  önemle; 1 sn içinde ikinci çalma yok).

## 2. Tek tıkla onay (`frontend/js/index.js`)

- Toast'a iki düğme: **Görüldü** (`acknowledged`) ve **Yanlış Alarm**
  (`false_positive`), şablondaki kapat düğmesinin sınıflarıyla.
- Olay kimliği tıklamada bulunur:
  `GET /api/events?camera_id=<id>&anomaly_type=<tip>&from=<t-2s>&to=<t+2s>&limit=5`.
  `t` = alarmın `start_time`'ı (olayın `started_at`'i aynı Spark
  mesajından gelir). Kamera kimliği `_cameras`'ta ada göre bulunur
  (`alert.camera_name` ya da ham `camera_id`). En yakın `started_at`
  seçilir.
- Olay henüz yoksa (tüketici yazmadı) 1,5 sn arayla 3 deneme; yine yoksa
  toast'ta "Olay henüz kaydedilmedi; Olaylar ekranından onaylayın".
- `PATCH` başarılıysa düğmeler kalkar, toast'ta "Görüldü ✓" / "Yanlış
  alarm olarak işaretlendi", 2 sn sonra toast kapanır. 403'te "Bu işlem
  için operatör yetkisi gerekiyor".
- Toast yalnız son alarmı gösterir; düğmeler o alarmın olayına bağlıdır.
  Yeni alarm gelince toast ve düğmeler yenisine geçer.

## 3. Düşme sonucu alarm penceresinde (13.4'ten)

- `api/ws/alerts.py`: yayıncı `fall-outcomes`'u da okur (aynı tüketici,
  iki konu). Sonuç mesajı panele şu gövdeyle gider (saf fonksiyon
  `outcome_alert(msg, camera_name)`):

  ```json
  {"kind": "fall_outcome", "camera_id": "<ham>", "camera_name": "<ad|null>",
   "track_id": 7, "fall_time": 1764000000.1, "outcome": "down",
   "metrics": {"...": 0.0}}
  ```

  `unknown` yayımlanmaz. Var olan alarm gövdesi değişmez (`kind` alanı
  yok; panel `kind` yoksa alarm sayar).
- Panel (`index.js`):
  - `down`: kırmızı toast "Kalkamadı — <kamera>", alt satır
    "Düşmeden <n> sn sonra hâlâ yerde" (ya da 13.4 bildirim şablonundaki
    görünmüyor varyantı, `last_seen_ago_sec > 3.6`), critical sesi.
    Görüldü / Yanlış Alarm düğmeleri FALL olayına bağlanır (tip `FALL`,
    `t = fall_time`, ±3 sn: `fall_time` ilk adayın saati, olay başlangıcı
    oturumun en erken adayı).
  - `recovered`: olay akışına bilgi kartı "Kalktı" (ses yok, toast yok).
  - Olay akışı kartı da eklenir (her iki sonuç için).

## 4. Kamera nabzı: "aday var, olay yok"

### 4.1 API (`api/routers/health.py`, `api/schemas.py`)

- `GET /api/health/cameras?window_min=10` (1–60, varsayılan 10).
- `CameraHealthOut`'a: `window_min: int`, `candidates_window: int | None`,
  `events_window: int`, `stalled: bool`.
- `candidates_window`: `camera_health`'te `ts >= now - W` belgelerinden,
  kamera başına ilk ve son `candidates`. `son - ilk`; sayaç süreç yeniden
  başlayınca sıfırlanır, `son < ilk` ise `son` alınır. Pencerede belge
  yoksa veya `candidates` alanı yoksa `None`. Tek aggregate (`$match` ts,
  `$sort {camera_id:1, ts:1}`, `$group` `$first` / `$last`), ham kimlik
  bugünkü gibi `resolve_camera_id` ile çözülür.
- `events_window`: `SELECT camera_id, count(*) FROM events WHERE
  started_at >= now - W GROUP BY camera_id`.
- `stalled = candidates_window >= STALL_MIN_CANDIDATES and events_window == 0
  and age_sec <= 60`.
  - `STALL_MIN_CANDIDATES = 20`. Gerekçe: Spark bir oturumu en az 2 adayla
    kabul eder (`spark_min_hits`); 10 dk'da 20 aday üretip hiçbirini olay
    yapamayan kamera, ya birbirinden 3 sn'den uzak 20 tek-aday gürültüsü
    üretmiştir ya da akış bozuktur. İlki ölçülmedi; değer ölçülmüş bir
    sınır değil, 18'deki 24 saatlik koşunun verisiyle gözden geçirilecek.
  - `age_sec <= 60`: belgesi bayat kamera zaten "Bayat" görünüyor.
  - **Doğrulamada eklendi:** penceredeki ilk ve son sağlık kaydı arası
    ≥ `MIN_SPAN_SEC = 60`. `run_01` saniyede ~4 aday üretiyor, 20'ye 5
    sn'de ulaşıyor; Spark'ın ilk olayı ~7,5 sn sonra geliyor. Şart
    olmadan her kamera açılışında birkaç saniye yanlış işaret görünüyordu.
- Saf fonksiyon `pulse(cand_first, cand_last, events, age_sec) -> (candidates_window, stalled)`;
  testler bunu doğrudan çağırır.

### 4.2 Panel (`frontend/js/sistem-sagligi.js`)

- Şablonun boş "TREND" sütunu: `"<N> aday · <M> olay"` (son 10 dk;
  `candidates_window` `None` ise "—"). Sütun başlığı metni "SON 10 DK".
- Durum sütunu: `stalled` ise "Aday var, olay yok" (hata rengi, yanıp
  sönen nokta) ve `title`: "son 10 dk: N aday, 0 olay — akış (Kafka /
  Spark) denetlenmeli". Öncelik: Bağlantı Yok > Bayat > Aday var olay yok >
  Canlı.
- Sayfa 15 sn'de bir yenilenir (yalnız kartlar ve tablo; satır şablonu
  bir kez yakalanır, her yenilemede tablo temizlenip yeniden doldurulur).

## 5. Önceki aşamalardan kalan küçükler

- **Canlı katmanda yön oku (13.5):** `vision/camera.py` `build_meta`
  bölge öğesine `direction_vector` ekler (`list` ya da `None`).
  `frontend/js/live.js` `drawOverlay`, `direction_vector`'ı olan bölgede
  poligon ağırlık merkezinden ok çizer (piksel uzayında, sabit uzunluk;
  bolgeler.js'teki hesapla aynı). API'den gelen bölgelerde de
  (`zonesFor` yedeği) aynı alan var.
- **Ölü ayar `window_frames` (13.3):** görü okumuyor (pencereler
  saniyede). `ayarlar.js`'te alan gizlenir; kayıtta bugünkü değer aynen
  gönderilmeye devam eder (bugünkü "0 gönderme" korumasına dokunulmaz).
  Veritabanı sütunu ve API alanı kalır (göç yok).
- **Panelde canlı "yerde: 12 sn" sayacı (13.4):** yapılmaz. Görünün WS
  meta akışına izleme durumu eklemek gerekir; değeri saha kaydında
  görülmeden belirsiz. 14'e kayıt.

## 6. Testler

`tests/test_asama13_6_api.py` (yeni):
- `pulse`: 30 aday 0 olay canlı → stalled; 30 aday 1 olay → değil; 10
  aday → değil; bayat (age 120) → değil; sayaç sıfırlanmış (son < ilk) →
  `son`; `None` girdiler.
- `cameras_health` (Mongo ve Postgres varsa; yoksa atlanır): `window_min`
  sınırları (0 ve 61 → 422).
- `outcome_alert`: `down` / `recovered` gövdesi; `unknown` → `None`;
  bozuk mesaj → `None`.
- `build_meta`: yön bölgesinde `direction_vector` liste, ötekinde `None`.

`tests/test_asama13_6_panel.py` (yeni, statik):
- `index.js`: `AudioContext`, sessize alma `localStorage` anahtarı,
  `acknowledged` ve `false_positive` PATCH çağrısı, `fall_outcome` işleme,
  `try` ile sarılı `localStorage`.
- `sistem-sagligi.js`: `stalled`, `candidates_window`, periyodik yenileme.
- `live.js`: `direction_vector` ok çizimi.
- `ayarlar.js`: `window_frames` alanı gizli, değer yine gönderiliyor.

## 7. İş bölümü

| paket | dosyalar |
|---|---|
| **A — API ve görü** | `api/routers/health.py`, `api/schemas.py`, `api/ws/alerts.py`, `vision/camera.py` (yalnız `build_meta`), `tests/test_asama13_6_api.py` |
| **F — panel** | `frontend/js/index.js`, `frontend/js/sistem-sagligi.js`, `frontend/js/live.js`, `frontend/js/ayarlar.js`, `frontend/*.html` (yalnız `build_frontend` çıktısı), `tests/test_asama13_6_panel.py` |

Sözleşmeler: §3'teki WS gövdesi, §4.1'deki alanlar, §5'teki meta alanı.

## 8. Doğrulama (kabul: tarayıcıda uçtan uca)

API imajı ana dizinden derlendiği için worktree API'si yerelde 8001'de
koşar (paneli de o servis eder). Alarm yayıncısının Kafka grubu ortak
olduğu için deneme sırasında konteyner API'si durdurulur, sonra yeniden
başlatılır.

1. Tam test paketi yeşil (eski `test_asama8_6` hariç).
2. **Yapay kesinti:** Spark durdurulur (`docker stop anomaly-spark`);
   `fall_01` döngüde, kalp atışı ve Kafka açık. `GET
   /api/health/cameras?window_min=2` birkaç dakika içinde `fall_01` için
   `stalled = true`; panelde "Aday var, olay yok". Spark başlatılınca olay
   gelir, işaret kalkar.
3. **Alarm:** panel açıkken `fall_01` düşmesi: toast, ses fonksiyonu
   çağrıldı (`AudioContext` durumu), "Görüldü" → veritabanında
   `status = acknowledged`, `acked_by` dolu. Kalkamadı sonucu
   (`--postfall-sec 10`) toast'ta.
4. Canlı katmanda yön oku: yön bölgesi olan kamerada (geçici bölge).
5. Tarayıcı oturumu: jeton süreç içinde üretilir ve sayfanın
   `localStorage`'ına konur; parola girilmez.

## 9. Kabul

1. Testler yeşil.
2. §8'deki üç senaryo tarayıcıda; ekran görüntüsü ya da sayfa metni ve
   veritabanı sorgusu DURUM'da.
3. Ses gerçekten duyulmadı (otomatik test); yalnız çalma fonksiyonunun
   çağrıldığı ve `AudioContext`'in `running` olduğu doğrulanır. DURUM'da
   böyle yazılır.

**Commit:** `feat: asama 13.6 - alarm sesi, tek tik onay ve kamera nabzi`

## 10. Ortak kurallar

- Yorumlar ASCII, kısa, "neden"i anlatır. Kullanıcı metinleri Türkçe.
- `innerHTML`'e veri konmaz; `textContent` ya da `_escXml`.
- Paketler birbirinin dosyasına dokunmaz.
