# Aşama 13.2 — Hızlı düzeltmeler: uygulama planı (2026-11-23)

Bulgular: `docs/ASAMA13_PLAN.md` bölüm B ve C; ek iki madde 13.1'de
görüldü. Birbirinden bağımsız sekiz düzeltme, üç iş paketi. Burada
yazmayan davranış değişikliği yapılmaz.

**Uygulayıcıya not:** her madde için bir regresyon testi; ölçüm
gerektirenler §5'te. Kötü sonuç saklanmaz.

---

## 1. Paket A — API

Dosyalar: `api/llm.py`, `api/routers/health.py`, `api/routers/evidence.py`,
`tests/test_llm.py`, `tests/test_api_units.py` (veya yeni bir test dosyası).

**B4 — Gemini anahtarı URL'de.** `generate_report` anahtarı `?key=` ile
URL'ye koyuyor; vekil sunucu ve erişim kayıtlarına düşebilir. Anahtar
`x-goog-api-key` başlığına taşınır: `_post(url, body, headers)` başlık
alır, URL'de `key=` kalmaz. Hata yolları (`print`) URL'yi basıyorsa
anahtar sızmadığı da testle denetlenir.
Test: üretilen istekte URL `key=` içermiyor, başlıkta anahtar var
(`_transport` zaten sahte taşıma ile test ediliyor — `tests/test_llm.py`).

**C1 — sağlık sorgusu.** `api/routers/health.py` toplamada `$sort: {ts: -1}`
kullanıyor; dizin `{camera_id: 1, ts: -1}` olduğu için MongoDB
`DISTINCT_SCAN` kullanamıyor ve bütün koleksiyonu tarıyor (ölçülen: bir
haftalık veride 483.840 belge, 445 ms). Sıralama `{camera_id: 1, ts: -1}`
olur; `$group` + `$first` aynen kalır, sonuç değişmez.
Test: boru hattının ilk aşaması tam olarak `{"$sort": {"camera_id": 1,
"ts": -1}}`.

**C3 — kanıt listesi sayfalamasız.** `GET /api/evidence` bütün satırları
döndürüyor (saatte ~60 satır büyüyor). `events.py` ile aynı desen:
`limit: int = 50`, `offset: int = 0`, `limit = min(max(limit, 1), 500)`.
Yanıt yine liste (geriye uyumlu); panel bu ucu kullanmıyor.
Test: `limit`/`offset` sorguya yansıyor, tavan 500.

## 2. Paket F — panel ve derleme

Dosyalar: `frontend/js/*.js`, `scripts/build_frontend.py`, üretilen
`frontend/*.html`, `tests/test_frontend_*.py` (ilgili olan).

**B1 — kalıcı XSS.** `frontend/js/olaylar.js` ~105: kamera adı ve konumu
kaçışlanmadan `innerHTML`'e basılıyor. `app.js`'teki `_escXml` kullanılır.
Ayrıca `frontend/js/` altındaki **bütün** `innerHTML` atamaları taranır:
API'den gelen her metin (kamera / bölge / kullanıcı adı, konum, hata
mesajı) `_escXml`'den geçmeli veya `textContent` ile basılmalı. Sabit HTML
şablonları ve sayılar dokunulmadan kalır. Rapor, her atama için tek
satırlık hüküm içerir (güvenli / düzeltildi).
Test: statik test — `olaylar.js`'teki kamera adı/konum satırı `_escXml`
kullanıyor; taramada düzeltilen her yer için benzer satır denetimi.

**Önbellek etiketi satır sonuna bağlı.** `build_frontend.py` `?v=`
özetini dosyanın ham baytlarından alıyor; aynı içerik CRLF/LF ile farklı
özet veriyor, test paketi her koşuda izlenen `frontend/*.html`'leri
değiştiriyor. Özet `data.replace(b"\r\n", b"\n")` üzerinden hesaplanır;
`frontend/*.html` bir kez yeniden üretilir ve değişiklik pakete girer.
Kabul: yeniden üretimden sonra tam test paketi koşunca `git status`'ta
`frontend/` temiz.

## 3. Paket G — görü ve altyapı

Dosyalar: `vision/ws_server.py`, `vision/camera.py`, `vision/run.py`
(yalnız rapor satırı gerekiyorsa), `docker-compose.yml`,
`scripts/seed_pilot.py`, `tests/test_ws_units.py`, gerekirse yeni test.

**C2 — JPEG kodlaması küresel istemci sayısına bağlı.** Tek süreçte
çoklu kamera varken, bir kamerayı izleyen tek istemci bütün kameralara
her karede JPEG kodlatıyor. Sayaç `(tür, kamera)` başına tutulur:
`StreamServer.clients(kind: str, camera_id: str) -> int`. `camera.py`'deki
iki kapı `self.stream_server.clients("meta"/"live", self.camera_id) > 0`
olur. `live_clients` / `meta_clients` özellikleri toplam olarak kalır
(rapor satırı ve geriye uyum).
Test: iki kameralı sunucuda yalnız `cam_a`'ya bağlanan istemci
`clients("live", "cam_a") == 1`, `clients("live", "cam_b") == 0`; bağlantı
kapanınca 0. (Mevcut `tests/test_ws_units.py` deseni izlenir.)

**B2 — veritabanları ve Kafka bütün arayüzlere açık.** Postgres, Mongo
ve Kafka host portları `127.0.0.1:` önekiyle bağlanır
(`"127.0.0.1:${POSTGRES_PORT:-5432}:5432"` vb.). Kafka kimliksiz; yerel
ağdan tek bir ileri tarihli mesaj sistemi susturabiliyordu (13.1'de
Spark tarafı da kapatıldı). API portu (`8000`) panel için açık kalır.
Görü süreci host'ta, `localhost:9092`'ye bağlandığı için etkilenmez.

**Kamera kaynağı mutlak yol.** `scripts/seed_pilot.py` kaynağı mutlak
yol yazıyor; proje taşınınca dosya kameraları açılamadı (13.1). Kaynak
proje köküne göreli yazılır (`data/pilot/<ad>.mp4`, `/` ayraçlı).
`run_pilot_cameras.py` görü sürecini `cwd=ROOT` ile başlattığı için
göreli yol çözülür. Var olan pilot kamera satırının kaynağı göreli yoldan
farklıysa seed onu günceller ve basar (yalnız seed'in kendi pilot
kameraları; `source_type='file'`).
Test: seed'in yazacağı kaynak göreli ve `ROOT` ile birleşince dosyaya
çıkıyor (veritabanısız birim test; seed fonksiyonu gerekirse saf bir
yardımcıya ayrılır).

---

## 4. Ortak kurallar

- Dokunulan her `.py` dosyasında yorumlar ASCII, kısa ve "neden"i anlatır.
- Paketler birbirinin dosyasına dokunmaz.
- Testler: ilgili test dosyaları + tam paket; veritabanı gerektirenler
  Docker kapalıyken atlanır.

## 5. Kabul — ana dizinde, Docker açıkken

1. API imajı yeniden derlenir (`docker compose up -d --build api consumer`);
   Postgres / Mongo / Kafka yeni port bağlamasıyla yeniden oluşturulur.
2. **B2:** `localhost`'tan 5433 / 27018 / 9092 açık; makinenin yerel ağ
   IP'sinden kapalı. Görü süreci Kafka'ya yazabiliyor (`check_kafka.py`).
3. **C1:** gerçek `camera_health` verisinde `explain` → `DISTINCT_SCAN`;
   uç süresi öncesi / sonrası.
4. **Seed:** `seed_pilot.py` yeniden koşar, pilot kamera kaynakları göreli
   olur; `run_pilot_cameras.py` kameraları açar.
5. **B4:** bir olay sonrası Gemini çağrısı başarılı (anahtar başlıkta);
   anahtar yoksa şablona düşüş aynen.
6. **Önbellek etiketi:** tam test paketi sonrası `git status` temiz.
