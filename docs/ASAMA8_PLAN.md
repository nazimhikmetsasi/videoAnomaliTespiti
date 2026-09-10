# Aşama 8 — Panel

Bu aşamanın işi tasarım yapmak değil, **hazır tasarıma veri bağlamak.**
`sablon/` altındaki 11 ekran kullanıcı tarafından sağlandı; renk, tipografi,
yerleşim ve sınıf adlarına dokunulmaz. Yapılacak tek biçimsel değişiklik,
JavaScript'in tutunacağı `id` / `data-*` niteliklerinin eklenmesi ve
şablondaki sahte satırların şablon (template) olarak kullanılıp veriyle
çoğaltılmasıdır.

## 1. Yığın kararı

**Derleme adımı yok.** Şablon, Tailwind CDN + Material Symbols kullanan düz
HTML. React'e taşımak 11 ekranın tamamını elle yeniden yazmak demektir; bu hem
"tasarıma dokunulmaz" kuralını fiilen ihlal eder hem de node/vite/bundler
zincirini projeye sokar. Bunun yerine:

- `frontend/` = şablon HTML dosyaları (birebir kopya) + sayfa başına bir
  `js/<sayfa>.js` + ortak `js/app.js`
- `app.js`: `fetch` sarmalayıcı (JWT başlığı, 401'de girişe yönlendirme),
  gezinme çubuğunun aktif sekmesi, ortak biçimleyiciler (tarih, süre, tip
  adları), `renderRows(tbody, veri, doldur)` yardımcısı
- Grafik kütüphanesi **yok**: analitik ekranındaki dağılım grafiği ve ısı
  haritası şablonda zaten `div` genişlikleri ve renk sınıflarıyla çizilmiş;
  veriden hesaplanacak tek şey yüzde. Recharts (PLAN.md'de anılıyor) React
  gerektirir ve bu ekranlar için karşılığı yok.
- Servis: API konteynerine `./frontend:/frontend:ro` bağlanır,
  `app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True))`. Aynı
  origin → CORS yok, jeton `localStorage`'da, kanıt dosyaları göreli yolla
  açılır. Ayrı nginx konteyneri eklenmez.
- Canlı görüntü ayrı origin'dedir (`vision/ws_server.py`, port 8001);
  WebSocket CORS'a tabi değildir, jeton `?token=` ile gider — Aşama 6'daki
  sözleşme değişmez.

## 2. Ekran → uç haritası (Aşama 8.1'de doğrulanacak açık soru)

| Ekran | Uç | Durum |
|---|---|---|
| Canlı İzleme | `ws://…:8001/ws/live/{cam}`, `/ws/meta/{cam}`, `GET /api/cameras`, `WS /ws/alerts` | var |
| Kameralar | `GET/POST/PUT/DELETE /api/cameras` | var |
| Kamera Detay | `GET /api/cameras/{id}`, canlı WS, `GET /api/events?camera_id=` | var |
| Olaylar | `GET /api/events` (filtre + sayfalama), `PATCH /api/events/{id}` | var |
| Olay Detay | `GET /api/events/{id}`, `/clip`, `/frame` | var |
| Bölgeler | `GET/POST/PUT/DELETE /api/zones` | var |
| Analitik | `GET /api/analytics/summary`, `/ablation` | var |
| Ayarlar | `GET/PUT /api/settings[/{camera_id}]` | var |
| Sistem Sağlığı | `GET /health` + kamera başına FPS / düşen kare / gecikme | **eksik** |
| Kullanıcılar | kullanıcı CRUD | **eksik** |
| Denetim Kaydı | `audit_log` listesi | **eksik** |
| Giriş | `POST /api/auth/login` | uç var, **ekran yok** |

Şablonda giriş ekranı yok. Sistemin tamamı JWT istiyor, dolayısıyla tek yeni
ekran `login.html` olacak: şablonun kabuğundan (aynı renk jetonları, aynı
yazı tipleri, `sentinel_control_system/DESIGN.md`) türetilmiş, tek kart, tek
form. Yeni tasarım üretilmiyor, var olan jetonlar kullanılıyor.

## 3. Alt aşamalar

Her alt aşama sonunda `docs/DURUM.md` güncellenir ve commit mesajı verilir.

### 8.1 — İskelet, kimlik, uç denetimi
- `frontend/` kurulur, 11 şablon birebir kopyalanır, `login.html` yazılır
- `app.js`: jeton saklama, `api()` sarmalayıcı, 401 yönlendirmesi, gezinme
  bağlantılarının gerçek dosyalara bağlanması, aktif sekme
- API'ye `StaticFiles` bağlanır, compose'a `./frontend` bağlanır
- Yukarıdaki tablo ekran ekran doğrulanır; eksikler 8.2'nin kapsamıdır
- **Ölçüm:** DURUM.md'deki açık soru — Windows host'tan API uçlarına ~600 ms
  taban gecikme. Panel geliştirmeye başlamadan ölçülür; gerçekse ekranların
  kaç istek attığı bir tasarım kısıtına dönüşür
- **Onay:** giriş yapılıyor, 11 ekran arasında gezilebiliyor, jeton
  süresi dolunca girişe düşüyor

### 8.2 — Eksik uçlar
- `api/routers/users.py`: liste / ekle / güncelle / pasifleştir. Rol denetimi
  `admin`; şifre değişimi `crypt()` ile veritabanında (Aşama 5 kararıyla aynı)
- `api/routers/audit.py`: `GET /api/audit` — kullanıcı, eylem, varlık, tarih
  filtreleri + sayfalama
- `GET /api/health/cameras`: Mongo `camera_health` koleksiyonundan kamera
  başına son belge (FPS, çıkarım süresi, düşen kare). Veri Aşama 6'dan beri
  yazılıyor, okuyan uç yok
- **Onay:** üç ekranın da alanları gerçek veriyle dolabiliyor, her uç için
  `tests/` altında bir kontrol

### 8.3 — Okuma ekranları
Kameralar, kamera detay, olaylar (filtre + sayfalama), olay detay (kanıt
karesi, klip, LLM raporu, güven skoru), analitik, sistem sağlığı,
kullanıcılar, denetim kaydı.
- **Onay:** her ekran gerçek veritabanı içeriğini gösteriyor, sahte satır
  kalmadı, boş durum (veri yok) ekranı bozmuyor

### 8.4 — Canlı izleme
- `/ws/live/{cam}` ikili JPEG → `<img>` (blob URL), `/ws/meta/{cam}` → üst
  katman `<canvas>`
- Katman aç-kapa: kutu / iskelet / bölge / ID. Bölge katmanı `GET /api/zones`
  poligonlarını normalize koordinattan çizer
- Izgara 1 / 2x2 / 3x3; yalnızca görünen kameralar WS açar (Aşama 6'nın
  `live_clients` kapısı bunun için var)
- `/ws/alerts` → kırmızı toast + sağdaki canlı olay akışı
- **Onay:** tarayıcıda 20+ FPS, alarm geldiğinde ilgili kamera karesi kırmızıya
  dönüyor, WS koptuğunda yeniden bağlanıyor

### 8.5 — Yazma ekranları
- Kamera ekle / düzenle / sil
- Bölge poligon çizimi: canlı kare üzerine tıklayarak nokta ekleme, 0–1
  normalize kayıt, düzenleme ve silme
- Ayarlar formu: global / kamera bazlı, kısmi `PUT` (Aşama 5'teki lost-update
  kararı), `restart_required` alanı kullanıcıya gösterilir
- Olay durumu: görüldü / yanlış alarm, toplu işaretleme
- **Onay:** panelden değiştirilen eşik, `vision/` yeniden başlatılmadan
  davranışı değiştiriyor (sıcak yükleme Aşama 5'te yazıldı, panelden ilk kez
  tetikleniyor)

### 8.6 — Uçtan uca demo
- Gerçek kamera açık, gerçek olay üretilir; panelde alarm, olay kaydı, kanıt
  ve Telegram bildirimi birlikte doğrulanır
- **Kamera donanımı yok: demo kaynağı `data/pilot/` videolarıdır.** Kameralar
  veritabanında `source_type='file'` olarak zaten tanımlı; her kamera için
  bir `vision.run` süreci o kameranın videosunu oynatır. Panelde hiçbir yerde
  sahte/stok görüntü kalmaz — yayın yoksa "Bağlantı Yok" görünür, yayın
  varsa videodan gelen gerçek kare
- Birden çok kamerayı tek komutla ayağa kaldıran küçük bir yardımcı gerekir
  (`scripts/run_pilot_cameras.py`): her pilot klibi için `--ws --rules
  --camera-id <ad>` ile süreç başlatır, Ctrl+C ile hepsini durdurur.
  Videolar kısa olduğu için demo boyunca döngü seçeneği de gerekir
- Ölçülecek: panel canlı FPS (hedef ≥ 20, v1: 0.67), alarmın ekranda görünme
  gecikmesi, ekran açılış süresi
- **Onay kriteri:** PLAN.md § 8 tablosundaki panel satırları gerçek ölçümle
  doldurulur

## 4. Bilinçli sınırlar

- Sunucu tarafı sayfa üretimi yok; her ekran kendi verisini `fetch` eder
- Durum yönetimi kütüphanesi yok; sayfa başına bir betik, paylaşılan durum
  yalnızca jeton
- Tema anahtarı (şablondaki `dark_mode` düğmesi) bağlanmaz: tasarım tek temalı
  (koyu) verildi, açık tema jetonları yok
- Arama kutusu, PTZ, "aktarım feed'i" gibi karşılığı olmayan şablon
  öğelerine dokunulmaz; sahte veri de bırakılmaz, pasif görünürler

## 5. 8.1 uç denetimi sonucu

§ 2 tablosu, her ekranın `sablon/*/code.html`'deki gerçek alanlarıyla
`api/schemas.py` karşılaştırılarak doğrulandı (kod yazılmadı, 8.2'nin işi):

- **Sistem Sağlığı, Kullanıcılar, Denetim Kaydı** — tablodaki "eksik" işareti
  doğru: üç ekran için de router yok. `UserOut` (schemas.py) kullanıcılar
  ekranının alanlarını (`username`, `role`, `telegram_chat_id`, `last_login`)
  zaten karşılıyor, yalnızca CRUD router eksik. Denetim Kaydı ve Sistem
  Sağlığı için ise henüz schema da yok — `audit_log` tablosu (user_id,
  action, entity, ip, created_at) ekranın "Kullanıcı/İşlem/IP Adresi/Zaman"
  sütunlarıyla birebir örtüşüyor, `AuditOut` 8.2'de yazılmalı. Kamera başına
  FPS/düşen kare/gecikme Mongo `camera_health` koleksiyonunda duruyor
  (Aşama 6'dan beri yazılıyor) ama hiçbir pydantic şeması yok.
- **events.status dörtlü, üçlü değil** — görev tanımındaki `DURUM_ADI`
  taslağı `new/acknowledged/false_positive` idi; `infra/postgres/init.sql`
  CHECK kısıtı dördüncü bir değer daha tanımlıyor: `resolved`. `frontend/js/app.js`
  bunu 4 değerle yazdı (Yeni/Görüldü/Yanlış Alarm/Çözüldü); 8.2/8.3 bu haritayı
  kullanmalı, üçlü versiyon eksik kalırdı.
- **Analitik ekranının algoritma karşılaştırma tablosu — gerçek eksik.**
  Şablon "Algoritma/Kaynak, Doğruluk, Kesinlik, Duyarlılık, F1 Skoru"
  sütunlarını bekliyor. `GET /api/analytics/summary` ve `/ablation` yalnızca
  `decided_by`/`anomaly_type`/`status` kırılımında SAYI döndürüyor;
  precision/recall/F1/accuracy hiçbir uçta yok. Bu metrikler bugün yalnızca
  `eval/pilot_eval.py` ve `eval/spark_eval.py`'nin ürettiği çevrimdışı
  markdown raporlarında var (ground-truth etiketine ihtiyaç duyuyorlar).
  Plan tablosunda bu satır "var" görünüyordu ama ekranın gerçek ihtiyacının
  karşılığı yok — § 2 tablosuna eklenmesi ve 8.2 kapsamına alınması gerekir
  (ya API'ye bir metrik ucu eklenir ya da ekran yalnızca sayı kırılımlarını
  gösterecek şekilde daraltılır).
- **`/api/analytics/ablation` response_model'siz** — `list[dict]` döndürüyor,
  `schemas.py`'de karşılığı yok. İşlevsel bir engel değil (OpenAPI/Swagger
  belgesinde tip görünmüyor); 8.2'de küçük bir `AblationRowOut` eklenmesi ucuz
  bir iyileştirme.
- Geri kalan ekranlar (Canlı İzleme, Kameralar, Kamera Detay, Olaylar, Olay
  Detay, Bölgeler, Ayarlar) — tablodaki alan adları ile `CameraOut`, `ZoneOut`,
  `EventOut`/`EventDetailOut`, `SettingsOut`/`SettingsPatch` alanları birebir
  eşleşiyor, isim uyuşmazlığı bulunmadı.
