# Aşama 7 — LLM Raporu ve Telegram Bildirimi (uygulama sözleşmesi)

Bu belge `docs/PLAN.md` § 7 "Aşama 7 — LLM ve Telegram" maddesinin uygulama
sözleşmesidir. Kod yazan ajan bu dosyayı ve `docs/DURUM.md`'yi okur.

**Onay kriteri (PLAN.md'den):** telefona fotoğraflı Türkçe ihbar geliyor;
LLM API çökse bile alarm zinciri sürüyor.

---

## 0. Girdi durumu

Aşama 6 sonunda zincirin son iki halkası boş:

- `api/workers/consumer.py:73` — `"llm_report_tr": None` sabit yazılıyor.
- `notifications` tablosu (`infra/postgres/init.sql:138`) hiç satır almıyor.

Hazır olanlar:

| Ne | Nerede | Aşama 7'de nasıl kullanılır |
|---|---|---|
| Olay satırı | `api/workers/consumer.py::_insert_with_retry` | Bildirim tetiği bu INSERT'in dönen `new_id`'sidir |
| Kanıt eşleşmesi | `consumer.py::_match_pending_evidence` | `events.frame_path` bu çağrıdan sonra doludur; fotoğrafın kaynağı |
| Kanıt karesi | `storage/frames/{cam}_{tip}_{ms}.jpg`, veritabanında **köke göreli** | `sendPhoto` bu dosyayı yükler |
| Yol güvenliği | `api/routers/events.py::_safe_storage_path` | Ortak modüle taşınır, kopyalanmaz |
| Alıcı kimliği | `users.telegram_chat_id` (`api/db/models.py:29`) | Bildirim hedefi |
| Kayıt tablosu | `notifications` (event_id, channel, target, status, error) | Her gönderim denemesi bir satır |
| Ortam değişkenleri | `.env.example` içinde `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` zaten ayrılmış | `api/config.py`'ye okunur |
| HTTP istemcisi | `httpx` — `api/requirements.txt` içinde mevcut | Gemini ve Telegram REST çağrıları |

**Yeni bağımlılık kurulmayacak.** `google-generativeai` SDK'sı, `python-telegram-bot`
ve benzeri paketler eklenmez; iki servisin de tek uç noktası vardır ve `httpx`
zaten kurulu.

---

## 1. En kritik karar: bildirimi kim tetikler

Üç aday vardı:

1. `api/ws/alerts.py` (alarm yayıncısı) — Kafka'yı zaten okuyor, ama olay
   kimliğini ve kanıt yolunu bilmiyor; ikisini de DB'den ayrıca aramak
   gerekirdi ve yazım henüz bitmemiş olabilir.
2. Ayrı bir üçüncü Kafka tüketicisi — yeni bir servis, yeni bir offset,
   olayın DB'ye yazılmasıyla yarışır.
3. **`api/workers/consumer.py`** — olayı yazan, kimliği üreten ve kanıtı
   bağlayan yer. Bildirim için gereken her şey bu noktada elde.

**Seçim: 3.** Tetik `consumer.py`'de, `_match_pending_evidence` çağrısından
hemen sonra, `new_id is not None` (yani gerçekten yeni olay) dalında.

Ama gönderim **orada yapılmaz.** Tüketici döngüsü senkrondur ve offset commit
etmeden önce bekler; 3–8 sn'lik bir Gemini + Telegram turu, arkadaki olayların
veritabanına yazılmasını geciktirir. Bu yüzden:

```
consumer döngüsü ──enqueue(event_id)──> Queue ──> tek worker thread
   (bloklanmaz, μs)                                  LLM + Telegram
```

Kırmızı alarm zaten `api/ws/alerts.py`'den ayrı bir process olarak yayınlandığı
için bildirim gecikmesi operatörün ekranını hiçbir koşulda geciktirmez.

---

## 2. Dosya düzeni ve satır bütçesi

| Dosya | Durum | Bütçe |
|---|---|---|
| `api/llm.py` | yeni | ~160 |
| `api/notify.py` | yeni | ~180 |
| `api/storage_paths.py` | yeni | ~20 |
| `api/routers/events.py` | düzenleme | −8 / +4 |
| `api/workers/consumer.py` | düzenleme | +14 |
| `api/config.py` | düzenleme | +10 |
| `docker-compose.yml` | düzenleme | +8 |
| `.env.example` | düzenleme | +8 |
| `tests/test_llm.py` | yeni | ~120 |
| `tests/test_notify.py` | yeni | ~140 |

**Not — modül yeri:** `PLAN.md` bunları `api/workers/llm.py` ve
`api/workers/notify.py` diye yazmıştı. `api/workers/` bugün *çalıştırılabilir
servisleri* barındırıyor (`python -m api.workers.consumer`). Bu ikisi servis
değil kütüphanedir; `api/llm.py` ve `api/notify.py` olarak konulur, plandan
sapma `docs/DURUM.md` karar günlüğüne yazılır.

---

## 3. `api/llm.py` — Türkçe ihbar metni

### 3.1 Eylem ifadesi tek doğruluk kaynağıdır

v1'de gerçek bir yanlış ihbar üretildi: model, örnek cümledeki "yasaklı alana
giriş yaptı" kalıbını bölgeyle ilgisi olmayan `RUN` olaylarına da uyguladı
(`VideoAnomalySystem/backend/llm/reporter.py::_build_prompt` yorumu). Güvenlik
sisteminde gerçeğe aykırı ihbar kabul edilemez.

Bu yüzden `action_phrase(ctx) -> str` yazılır ve **hem şablon hem LLM istemi**
onu kullanır. Modelin görevi yalnızca üsluptur; olay ifadesini değiştiremez.

| `anomaly_type` | ifade |
|---|---|
| `FALL` | `düşme hareketi sergiledi` |
| `RUN` | `hızlı koşma hareketi sergiledi` |
| `ZONE_VIOLATION` | `yasaklı alana giriş yaptı` |
| `RUN_ZONE` | `koşarak yasaklı alana giriş yaptı` |
| `FIGHT` | `karşılıklı saldırgan hareket sergiledi` |
| `LOITERING` | `alanda uzun süre oyalandı` |
| `WRONG_DIRECTION` | `izin verilen yönün tersine hareket etti` |
| bilinmeyen | `{anomaly_type} olayı tespit edildi` |

Bilinmeyen tip düşürülmez: `consumer.py::SEVERITY`'nin bilinmeyen tipe
"medium" vermesiyle aynı gerekçe — yeni bir kural eklendiğinde bildirim
zinciri sessizce kırılmamalı.

### 3.2 Rapor bağlamı

Worker, olayı DB'den okuyup düz bir sözlük kurar (`ctx`):

```python
{"event_id", "camera_name", "anomaly_type", "zone_name" | None,
 "confidence", "duration_sec", "started_at" (TZ'li datetime),
 "track_count", "severity"}
```

`camera_name` ve `zone_name` tek `JOIN`'li sorgudan gelir. `ctx` saf veridir;
`template_report(ctx)` ve `build_prompt(ctx)` DB'ye dokunmaz — test bunları
doğrudan çağırır.

### 3.3 Şablon (yedek yol, her zaman çalışır)

```
Ana Giriş kamerasında 09.09.2026 14:32:05'te bir kişi düşme hareketi
sergiledi. Olay 1.8 saniye sürdü, güven skoru 0.87.
```

- Kişi sayısı 2+ ise "bir kişi" yerine "2 kişi".
- `zone_name` doluysa cümleye " (Depo Girişi bölgesi)" eklenir.
- Saat `started_at`'ın **yerel** karşılığıdır (`datetime.astimezone()`);
  veritabanı UTC saklar, operatör yerel saat okur.
- Şablon asla istisna fırlatmaz: eksik alan varsa yerine `bilinmiyor` yazar.

### 3.4 Gemini çağrısı

- Uç: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=...`
- Model: `GEMINI_MODEL`, varsayılan `gemini-flash-lite-latest`.
- `generationConfig`: `temperature 0.3`, `maxOutputTokens 300`; model adında
  `lite` geçmiyorsa ek olarak `thinkingConfig.thinkingBudget = 0`.
  **v1 dersi:** düşünme jetonu tüketen modeller cümleyi `MAX_TOKENS` ile
  yarıda kesiyor.
- Zaman aşımı `LLM_TIMEOUT_SEC`, varsayılan 8 sn.
- Metin çıkarımı: `candidates[0].content.parts` içinden `thought` işaretli
  parçalar atılır, kalan `text` birleştirilir.

**Kabul süzgeci `usable(text)`** — aşağıdakilerden biri bile tutmazsa şablona
düşülür (sessizce, tek satır uyarı ile):

1. metin boş,
2. `finishReason == "MAX_TOKENS"`,
3. son karakter `.!?…` değil (yarım cümle),
4. uzunluk 40 karakterden kısa veya 400 karakterden uzun.

Devam turu (v1'deki `_gemini_complete`) **yazılmaz**: tek cümlelik ihbar
300 jetona rahat sığar, ikinci tur gecikme ve kota harcar.

### 3.5 Kota soğutması

Yanıtta `429` veya gövdede `quota`/`rate` geçiyorsa `LLM_COOLDOWN_SEC`
(varsayılan 600) boyunca **hiç HTTP yapılmaz**, doğrudan şablon döner.
Soğutma modül düzeyinde tek bir zaman damgasıdır; worker tek iş parçacığı
olduğu için kilide gerek yoktur (yoksa gerekirdi — bunu yorumda belirt).

`GEMINI_API_KEY` boşsa hiç istek kurulmaz.

### 3.6 İstem

```
Sen bir güvenlik izleme sistemisin. Aşağıdaki olayı tek cümlelik, resmi bir
Türkçe ihbar metnine çevir.
KURALLAR:
- "Eylem" alanındaki ifadeyi anlamını değiştirmeden kullan; yeni bir olay
  türü UYDURMA.
- Sadece verilen alanları kullan, başka bilgi ekleme.
- Tek cümle, en fazla 200 karakter, nokta ile bitir.
- {bölge kuralı}
Kamera: ...
Eylem: {action_phrase}
Kişi sayısı: ...
Süre: ... saniye
Güven: ...
Zaman: ...
```

`{bölge kuralı}`: `zone_name` doluysa `Kişi "{zone_name}" bölgesinin
içindedir.`; boşsa `Olay bir bölge ihlali DEĞİLDİR — "yasaklı alan",
"bölge ihlali" gibi ifadeler KULLANMA.`

### 3.7 Dış arayüz

```python
def generate_report(ctx: dict) -> tuple[str, str]:
    """(metin, mod) döner; mod: "llm" | "template". Asla istisna fırlatmaz."""
```

---

## 4. `api/notify.py` — Telegram

### 4.1 Alıcılar

```sql
SELECT telegram_chat_id FROM users
WHERE is_active AND telegram_chat_id IS NOT NULL AND telegram_chat_id <> ''
```

Sonuç boşsa `.env`'deki `TELEGRAM_CHAT_ID` tek alıcı olarak kullanılır (tez
demosunda kullanıcı tablosuna dokunmadan test edilebilsin diye). O da boşsa
kanal yapılandırılmamıştır: `notifications` satırı **yazılmaz** (bu bir hata
değil, bir tercih), tek satır log basılır.

`TELEGRAM_BOT_TOKEN` boşsa aynı şekilde: rapor yine üretilir ve
`events.llm_report_tr` yine dolar; yalnız gönderim atlanır.

### 4.2 Gönderim

- `frame_path` dolu **ve dosya diskte varsa**: `POST /bot{token}/sendPhoto`,
  multipart `photo` alanı dosyanın kendisi, `caption` rapor metni.
  Caption sınırı 1024 karakterdir; metin 1000'de kırpılır (`…` eklenir).
- Aksi halde: `POST /bot{token}/sendMessage`, `text` = rapor.
- Biçimlendirme kullanılmaz (`parse_mode` gönderilmez). **v1 dersi:** Markdown
  özel karakterleri (`_ * [`) kamera adında geçtiğinde Telegram 400 döndürüyor.
- Metnin başına `🚨 {severity büyük harf} — {camera_name}` başlığı ve yeni
  satır eklenir.

### 4.3 Yeniden deneme ve hız sınırı

| Durum | Davranış |
|---|---|
| ağ hatası / zaman aşımı / HTTP 5xx | yeniden dene (3 deneme, 1 → 2 → 4 sn) |
| HTTP 429 | yanıttaki `parameters.retry_after` kadar bekle (tavan 30 sn), sonra dene |
| diğer 4xx | **kalıcı hata**, denenmez, `failed` yazılır |
| 200 ve `ok: true` | `sent` |

Hız sınırı: worker tek iş parçacığıdır ve iki gönderim arasında en az
`NOTIFY_MIN_INTERVAL_SEC` (varsayılan 1.0 sn) bekler. Telegram aynı sohbete
saniyede ~1 mesaja izin verir; kuyruk bu sınırı yapısal olarak dayatır.

### 4.4 `notifications` kaydı

Her alıcı için bir satır: `channel='telegram'`, `target=chat_id`,
`status='sent'|'failed'`, `error` = son hata metni (240 karakterde kırpılır;
sütun `TEXT` ama log okunabilir kalsın).

### 4.5 Kuyruk ve iş parçacığı

```python
_queue: queue.Queue[int | None] = queue.Queue(maxsize=200)

def enqueue(event_id: int) -> None      # consumer'ın çağırdığı tek fonksiyon
def start() -> None                     # daemon thread başlatır
def stop(timeout: float = 15.0) -> None # sentinel None + join
```

- Kuyruk doluysa **en eski** öğe düşürülür (`get_nowait` + `put_nowait`) ve
  `dropped` sayacı artar. Gerekçe: kırmızı alarm operatöre WebSocket'ten
  zaten gitti; burada kaybolan yalnızca telefon bildirimidir, ve eski bir
  bildirim yenisinden değersizdir.
- Worker döngüsü tek bir olayda **asla ölmez**: gövde `except Exception`
  ile sarılır, sayaç artar, döngü sürer. (Geniş yakalama bilinçlidir ve
  yorumda gerekçelendirilir — bu iş parçacığının ölmesi bildirimlerin
  sessizce kesilmesi demektir.)
- Kapanışta sayaçlar `consumer.py`'nin `finally` özetiyle aynı biçimde
  basılır: `bildirim gonderilen / basarisiz / dusen / llm-sablon`.

### 4.6 Worker'ın bir olay için sırası

1. Olayı ve kamera/bölge adını oku (tek sorgu).
2. `generate_report(ctx)` → metin, mod.
3. `UPDATE events SET llm_report_tr = :text WHERE id = :id` + commit.
   **Bu adım gönderimden öncedir**: Telegram tamamen kapalı olsa bile panel
   raporu görür.
4. Alıcıları çöz, her birine gönder, `notifications` satırlarını yaz.

---

## 5. `api/storage_paths.py` — yol çözümü tek yerde

`api/routers/events.py::_safe_storage_path` bugün doğru işi yapıyor ama
`HTTPException` fırlatıyor; worker'da HTTP istisnası anlamsızdır. Fonksiyon
taşınır:

```python
def storage_path(relative: str) -> Path | None:
    """storage/ kökü altındaki mutlak yol; kök dışına çıkan girdide None."""
```

`events.py` bunu çağırıp `None` gelirse kendi `HTTPException(400)`'ünü atar.
Davranış birebir korunur; **yeni bir kopya yazılmaz** (kök dizin dışına çıkma
denetimi iki yerde ayrı ayrı yaşarsa biri günün birinde geride kalır).

---

## 6. `api/config.py` ekleri

```python
GEMINI_API_KEY, GEMINI_MODEL (gemini-flash-lite-latest),
LLM_TIMEOUT_SEC (8.0), LLM_COOLDOWN_SEC (600.0),
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, NOTIFY_MIN_INTERVAL_SEC (1.0)
```

`TELEGRAM_ENABLED` / `LLM_ENABLED` gibi ayrı açma bayrağı **konmaz**: token
boşsa kanal kapalıdır, bu tek ve yeterli sinyaldir (v1'de bayrak ile token
ayrı ayrı yanlış ayarlanabiliyordu).

---

## 7. `docker-compose.yml` — `consumer` servisi

Bildirim artık `consumer` içinde çalıştığı için o container'a şunlar eklenir:

```yaml
    environment:
      STORAGE_DIR: /storage
      GEMINI_API_KEY: ${GEMINI_API_KEY:-}
      GEMINI_MODEL: ${GEMINI_MODEL:-gemini-flash-lite-latest}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}
      TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID:-}
    volumes:
      - ./storage:/storage:ro
```

`api` servisine de aynı LLM/Telegram değişkenleri eklenmez — API bu iki
servisi çağırmıyor.

---

## 8. Testler (ağsız, DB'siz, jetonsuz)

Mevcut düzenle aynı: `pytest tests/` tek komutta geçmeli, hiçbir test dış ağa
çıkmamalı. `httpx.MockTransport` kullanılır.

**`tests/test_llm.py`**

1. `action_phrase` yedi tipin her biri için beklenen ifadeyi döner; bilinmeyen
   tip `... olayı tespit edildi` verir.
2. Bölgesiz `RUN` şablonunda "yasaklı" kelimesi **geçmez** (v1 hatasının testi).
3. Bölgeli `ZONE_VIOLATION` şablonunda bölge adı geçer.
4. `build_prompt` çıktısı `action_phrase` sonucunu birebir içerir.
5. `extract_text` `thought: true` parçalarını atar; hepsi thought ise boş döner.
6. `usable`: yarım cümle, boş metin, 400+ karakter reddedilir; normal cümle geçer.
7. Anahtar boşken `generate_report` HTTP yapmaz (transport çağrı sayacı 0) ve
   `("...", "template")` döner.
8. 429 sonrası ikinci çağrı HTTP yapmaz (soğutma), yine şablon döner.
9. Gemini yarım cümle döndürünce sonuç şablondur — mod `"template"`.

**`tests/test_notify.py`**

1. `frame_path` mevcut dosyayı gösterince `sendPhoto` çağrılır; dosya yoksa
   veya `frame_path` `None` ise `sendMessage`.
2. 1000 karakterden uzun metin caption'da kırpılır.
3. HTTP 500 → üç deneme, sonuç `failed`; bekleme fonksiyonu test içinde
   yamalanır (test uyumaz).
4. HTTP 400 → tek deneme, `failed`.
5. HTTP 429 + `retry_after: 2` → beklenen süre okunur, sonra yeniden denenir.
6. `ok: true` → `sent`.
7. Kuyruk `maxsize` dolunca en eski öğe düşer, `dropped` sayacı artar.
8. Worker gövdesinde istisna fırlayan bir olay iş parçacığını öldürmez —
   sonraki olay yine işlenir.

Sıra ve zamanlama testleri gerçek `time.sleep` çağırmaz.

---

## 9. Zorunlu ölçümler (`docs/DURUM.md`'ye girer)

Aşama 6'nın dersi: **testin geçmesi doğrulama değildir.** Aşağıdakiler
ölçülmeden aşama kapanmaz.

1. **Fotoğraflı ihbar geldi mi.** Gerçek bir Telegram botuyla, gerçek bir
   olayda telefona düşen mesajın kanıtı (metin + fotoğrafın varlığı).
2. **LLM çökse de zincir sürüyor mu.** `GEMINI_API_KEY` boşken bir olay
   koşulur: `events.llm_report_tr` şablon metniyle **dolu** olmalı ve
   bildirim yine gitmeli.
3. **Rapor üretim süresi.** Gemini açıkken 5 olayda medyan ms, ve kaç
   tanesinin şablona düştüğü.
4. **Bildirim gecikmesi.** `events.created_at` → `notifications.sent_at`
   farkı, 5 olayın medyanı. (Dosya kaynağında bu sayı hattın hızını değil
   akışın bitişini de içerir — Aşama 6 § Ölçüm 2/4'teki uyarının aynısı
   geçerlidir, ölçüm bu sınırla birlikte yazılır.)
5. **`notifications` sayımı.** `sent` / `failed` dağılımı ve varsa hata metni.
6. **Tüketici yavaşladı mı.** 5 olaylık aynı klip bildirim kapalı ve açıkken
   koşulur; `consumer` özetindeki işlenen olay sayısı ve toplam süre
   karşılaştırılır. Kuyruk çalışıyorsa fark ölçülemeyecek kadar küçük olmalı.

---

## 10. Bilinen sınır (baştan kabul edilen)

Bildirim tetiği `consumer.py`'dedir ve fotoğraf, olay yazıldığı anda kanıtın
**zaten bağlanmış** olmasına dayanır. Aşama 6'da ölçüldüğü gibi baskın yön
budur (kanıt epizot kapanır kapanmaz gider, olay Spark gecikmesinden sonra
doğar). Ters sırada — kanıt olaydan sonra gelirse — o olayın bildirimi
fotoğrafsız gider. `api/routers/evidence.py` tarafına ikinci bir tetik
konmaz: iki tetik, iki kez gönderme riskini ve bir tekilleştirme mekanizmasını
birlikte getirirdi. Kodda `ponytail:` yorumu ile işaretlenir; ölçüm 1'de
fotoğrafsız bildirim çıkarsa oran `docs/DURUM.md`'ye yazılır.

---

## 11. Kapsam dışı (bilinçli, Aşama 7'de YAPILMAYACAK)

- **FCM / SMS.** `notifications.channel` CHECK'i `fcm`'e izin veriyor ama
  Aşama 7 yalnızca Telegram yazar.
- **Bildirim bastırma** (Evde/Koruma modu, bilinen kişi listesi) — v1'den
  taşınacak fikir, panelde ayar gerektirir, Aşama 8'e ait.
- **Günlük özet raporu** — tez çıktısı, Aşama 10.
- **`GET /api/llm/status` benzeri uç** — panelde gerekirse Aşama 8'de eklenir.
- **Severity'ye göre bildirim süzgeci** — şimdilik doğrulanmış her olay
  bildirilir; eşik ayarı panelle birlikte gelir.
- **`llm_report_tr` için yeniden üretme ucu** — YAGNI.
