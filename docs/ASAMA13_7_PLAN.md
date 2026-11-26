# Aşama 13.7 — Kalan küçükler: uygulama planı (2026-11-26)

Kapsam ve kabul: `docs/YOL_HARITASI.md` §13.7, bulgular B3, B5, E5
(`docs/ASAMA13_PLAN.md`). Kabul: her biri için test. Ayrıca 13.4'ten beri
düşen eski `test_asama8_6` testi karara bağlanır (§4).

**Uygulayıcıya not:** burada yazmayan davranış değişikliği yapılmaz.

---

## 1. B3 — Giriş deneme sınırı

**Bugün:** `POST /api/auth/login` sınırsız deneme kabul ediyor; parola
kaba kuvvete açık.

**Tasarım** (`api/routers/auth.py`, yeni küçük sınıf aynı dosyada ya da
`api/ratelimit.py`):

```python
class LoginLimiter:
    def __init__(self, max_per_user: int = 10, max_per_ip: int = 30,
                 window_sec: float = 900.0, clock=time.monotonic) -> None: ...
    def retry_after(self, username: str, ip: str) -> float:
        """0 = deneme serbest; > 0 = kac sn sonra."""
    def failed(self, username: str, ip: str) -> None: ...
    def succeeded(self, username: str) -> None: ...
```

- Kayan pencere: son `window_sec` içindeki başarısız denemelerin zaman
  damgaları (`deque`); eskiler her çağrıda budanır.
- **Hesap başına 10, IP başına 30 başarısız deneme / 15 dk.** Biri
  dolunca `429 Too Many Requests`, `Retry-After` başlığı (sn, yukarı
  yuvarlanmış), mesaj "cok fazla basarisiz deneme; N sn sonra tekrar
  deneyin". Sınır doluyken parola **denetlenmez** (doğru parola da 429
  alır; aksi hâlde sınır bir kâhin olurdu).
- Başarılı giriş o hesabın sayacını sıfırlar; IP sayacı kendi süresiyle
  düşer.
- Kullanıcı adı küçük harfe çevrilip kırpılarak anahtar olur. IP:
  `request.client.host`.
- **Gerekçe:** NIST SP 800-63B §5.2.2 ardışık başarısız denemeyi en fazla
  100 ile sınırlamayı ister. 10 / 15 dk günde en çok 960 deneme demek,
  NIST tavanının çok altında; unutkan bir operatörü kalıcı kilitlemeden
  kaba kuvveti durdurur. IP sınırı (30) birden çok hesabın taranmasına
  karşı; aynı ofisteki birkaç operatörün yanlış yazmasına pay bırakır.
- Bellek içi: API tek süreç (`uvicorn`, işçi sayısı 1). Yeniden başlayınca
  sayaçlar sıfırlanır. `ponytail:` notu: birden çok işçide ortak depo
  (Redis / veritabanı) gerekir.
- Kilitlenme `audit_log`'a yazılır mı: hayır (kullanıcı kimliği yok);
  `print` ile tek satır.

## 2. B5 — WebSocket jetonunun iptali

**Bugün:** `/ws/alerts` (API) ve görünün `/ws/live|meta` sunucusu jetonu
yalnız imzasıyla doğruluyor. Pasifleştirilen kullanıcı, jetonu (12 sa)
dolana kadar canlı görüntüyü ve alarmları izleyebiliyor. Açık bağlantı
hiç yeniden denetlenmiyor.

**İptal gecikmesi hedefi: ≤ 60 sn** (`REVALIDATE_SEC = 60`). Bugün 12 sa.
Dakikada jeton başına bir sorgu ihmal edilebilir.

### 2.1 API (`api/auth.py`, `api/ws/alerts.py`)

- `active_user_for_token(db, token) -> dict | None`: imza + `users`
  satırı var + `is_active`. `current_user`'ın denetiminin aynısı, istisna
  yerine `None`.
- `alerts_ws`: bağlanırken bu fonksiyon (veritabanı çağrısı
  `run_in_threadpool` ile, olay döngüsü bloklanmaz). Geçersizse bugünkü
  gibi `1008`.
- Açık bağlantı: `receive_text()` `asyncio.wait_for(..., REVALIDATE_SEC)`
  ile beklenir; zaman aşımında yeniden denetim, geçersizse
  `close(1008, "oturum gecersiz")`.

### 2.2 Görü (`vision/ws_server.py`, `vision/run.py`)

Görü hattı API'ye bağımlı olmamalı (ws_server.py başlık notu). Bu yüzden:

- `StreamServer(..., api_url: str | None = None)`. `vision/run.py`
  `--settings-url`'i geçirir; verilmezse davranış bugünkü gibi (yalnız
  yerel imza).
- Jeton denetimi `async _check(token) -> bool`:
  1. yerel imza (bugünkü); geçersizse `False`
  2. `api_url` yoksa `True`
  3. önbellek: jeton → (sonuç, zaman); `REVALIDATE_SEC` içindeyse önbellek
  4. `GET {api_url}/api/auth/me`, `Authorization: Bearer`, zaman aşımı
     2 sn (`httpx.AsyncClient`). 200 → `True`; 401 / 403 → `False`;
     ağ hatası ya da 5xx → **yerel sonuç** (`True`), `api_failures`
     sayacı artar, ilk hatada tek satır uyarı. Gerekçe: API düşünce canlı
     görüntü kesilmemeli (görünün bağımsızlığı); iptal API ayaktayken
     işler.
- `_handler`: bağlanırken `_check`.
- `_stream`: her gönderimden önce son denetimden bu yana `REVALIDATE_SEC`
  geçtiyse `_check`; `False` ise `close(1008, "oturum gecersiz")`.
  Kare gelmeyen kamerada denetim yok; zaten veri akmıyor.
- Önbellek budanır (süresi geçmiş girdiler her denetimde ya da en çok
  1000 girdi).

## 3. E5 — Olayların CSV dışa aktarımı

### 3.1 API (`api/routers/events.py`)

- `GET /api/events/export.csv`: `list_events` ile **aynı filtreler**
  (`camera_id`, `anomaly_type`, `status`, `severity`, `decided_by`,
  `from`, `to`). Filtre kurma ortak bir yardımcıya taşınır; iki uçta
  kopya olmaz. `current_user` yeter.
- Rota `/{event_id}`'den **önce** tanımlanır (yoksa "export.csv" kimlik
  sanılıp 422 döner).
- Satır tavanı 50 000 (`EXPORT_MAX_ROWS`); aşılırsa ilk 50 000 ve
  `X-Truncated: true` başlığı. `started_at` azalan sırada.
- Sütunlar (Türkçe başlık): `id, kamera, bolge, tip, onem, karar_veren,
  baslangic, bitis, sure_sn, guven, durum, dusme_sonucu, iz`. Zaman ISO
  8601, yerel saat (`TZ`, `api/llm.py`'deki dönüşüm). `iz`: `track_ids`
  `;` ile.
- Kodlama UTF-8 **BOM'lu** (Excel Türkçe karakteri doğru açsın), ayraç
  `,`, `csv` modülü (`QUOTE_MINIMAL`).
- **CSV formül enjeksiyonu:** `=`, `+`, `-`, `@`, sekme, satır başı ile
  başlayan metin hücresinin başına `'` konur (kamera ve bölge adı
  kullanıcı girdisi). Saf fonksiyon `csv_safe(value) -> str`.
- `Content-Disposition: attachment; filename="olaylar_YYYYMMDD_HHMM.csv"`.
- `StreamingResponse` gerekmez; 50 000 satır bellekte birkaç MB.

### 3.2 Panel (`frontend/js/olaylar.js`)

- Filtre çubuğuna "CSV indir" düğmesi (var olan düğme sınıflarıyla).
- Tıklamada o anki filtrelerle (`limit` / `offset` hariç) `fetch`
  (`Authorization` başlığı; `_fetchAuthedBlobUrl` deseni), blob → geçici
  `<a download>` → tıklama → `URL.revokeObjectURL`. Hata metni var olan
  hata gösterimiyle.
- `python scripts/build_frontend.py`.

## 4. Eski `test_asama8_6` hatası

`test_settings_camera_id_accepts_name_against_real_db` ilk kameranın
kendi ayar satırı olduğunu varsayıyor. Uç tasarım gereği kamera satırı
yoksa küresel ayarı (`camera_id = None`, `scope = "global"`) döndürüyor
(`api/routers/settings.py`). Testin amacı "ad ve kimlik aynı sonucu
verir". **Karar: test yanlış, uç doğru.** Test `by_name == by_id`
(aynı `camera_id` ve aynı `scope`) diye düzeltilir; kamera satırı varsa
`camera_id == cam.id` ayrıca denetlenir.

## 5. Testler

`tests/test_asama13_7_api.py` (yeni):
- `LoginLimiter`: 10. başarısızdan sonra hesap kilitli, `retry_after > 0`;
  pencere geçince açılır (sahte saat); başarılı giriş hesabı sıfırlar; IP
  sınırı farklı hesaplarla dolar; kullanıcı adı büyük/küçük harf aynı.
- Giriş ucu (TestClient, `authenticate_user` yerine sahte): 11. denemede
  429 + `Retry-After`; kilitliyken doğru parola da 429.
- `active_user_for_token`: imzasız / süresi geçmiş / olmayan kullanıcı /
  pasif kullanıcı → `None`; etkin → sözlük (veritabanı yoksa atlanır).
- `alerts_ws`: pasif kullanıcının jetonuyla bağlantı `1008` (veritabanı
  yoksa atlanır).
- `csv_safe`: `=1+1` → `'=1+1`; `-5` sayı değil metinse önekli; normal
  metin aynen; `None` → boş.
- CSV ucu: BOM, başlık satırı, filtre uygulanıyor, rota sırası
  (`/api/events/export.csv` 200, `/api/events/123` hâlâ çalışıyor)
  (veritabanı yoksa atlanır).

`tests/test_asama13_7_ws.py` (yeni): `StreamServer._check`:
- `api_url` yok → yerel imza yeter
- API 200 → kabul; 401 → ret; ağ hatası → yerel sonuç ve `api_failures`
- önbellek: 60 sn içinde ikinci denetim API'ye gitmez (sahte saat / sayaç)
- imza geçersizse API'ye hiç gidilmez
- API çağrısı sahte bir asenkron fonksiyonla değiştirilir; gerçek ağ yok

`tests/test_asama13_7_panel.py` (yeni, statik): `olaylar.js`'te CSV
düğmesi, `export.csv` isteği, `Authorization` başlığı, `revokeObjectURL`.

`tests/test_asama8_6.py`: §4.

## 6. İş bölümü

| paket | dosyalar |
|---|---|
| **A — API** | `api/routers/auth.py` (ve isterse `api/ratelimit.py`), `api/auth.py`, `api/ws/alerts.py`, `api/routers/events.py`, `tests/test_asama13_7_api.py`, `tests/test_asama8_6.py` |
| **G — görü ve panel** | `vision/ws_server.py`, `vision/run.py` (yalnız `StreamServer` kurulumu), `frontend/js/olaylar.js`, `frontend/*.html` (yalnız `build_frontend`), `tests/test_asama13_7_ws.py`, `tests/test_asama13_7_panel.py` |

## 7. Doğrulama (canlı)

Worktree API'si yerelde (8001), konteyner API'si deneme süresince durur
(13.6 ile aynı düzen).

1. Tam test paketi yeşil, eski hata dahil.
2. Giriş: olmayan bir kullanıcıyla 11 yanlış deneme → 11.'de 429 ve
   `Retry-After`. Gerçek hesaplara dokunulmaz.
3. CSV: jetonla `GET /api/events/export.csv?camera_id=2` → başlık, satır
   sayısı veritabanı sayımıyla aynı, Excel'de açılacak BOM.
4. İptal: geçici bir test kullanıcısı (veritabanına, rastgele parola, hiç
   kullanılmaz), jetonu süreç içinde üretilir. `/ws/alerts`'e bağlanılır,
   kullanıcı pasifleştirilir; bağlantı ≤ 60 sn içinde `1008` ile kapanır.
   Aynı jetonla görünün `/ws/meta`'sına bağlanılır (görü `--ws
   --settings-url` 8001); pasifleştirince ≤ 60 sn içinde kapanır. Test
   kullanıcısı sonra silinir.

## 8. Kabul

1. Testler yeşil (§5), `test_asama8_6` dahil.
2. §7 canlı denemeler DURUM'da.

**Commit:** `feat: asama 13.7 - giris deneme siniri, ws jeton iptali, csv disa aktarma`

## 9. Ortak kurallar

- Yorumlar ASCII, kısa, "neden"i anlatır.
- Paketler birbirinin dosyasına dokunmaz.
