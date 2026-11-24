# Proje Durumu

Bu dosya her aşama sonunda güncellenir. Yeni oturumda okuma sırası: bu
dosya → `docs/YOL_HARITASI.md` (kalan işin sırası ve kabul ölçütleri) →
başlanacak aşamanın plan dosyası. Aşama 0–12.6'nın ölçümleri ve bulguları
`docs/DURUM_ARSIV.md`'de, mimari `docs/PLAN.md`'de.

**Son güncelleme:** 2026-11-24

---

## Şu an neredeyiz

**Aşama 13.3 tamamlandı.** (2026-11-24) Sıradaki 13.4.

Hibrit holdout ham F1:
- 10 FPS: 0,17–0,24 → 0,59–0,62
- 5 FPS: 0 → 0,47–0,54
- özgün hız: 0,67 → 0,67

Özgün hızda süzgeçli F1 0,57 → 0,48. Düşüşün tamamı FIGHT'tan: holdout
FIGHT klipleri (1,2–2,9 sn) yeni 1,96 sn'lik pencereye sığmıyor.
Kullanıcı bunu kabul etti.

Ayrıntı: "Aşama 13.3 — B2" ve "Aşama 13.3 sonucu".

Plan: `docs/ASAMA13_3_PLAN.md`.

- **B0** (değişiklikten önce) sorunun büyüklüğünü ölçtü. Holdout'ta
  hibritin F1'i özgün hızda 0,67, 10 FPS'te ~0,2, 5 FPS'te 0. 5 FPS'te
  59 klibin hiçbirinde aday yok.
- **13.3b:** kural, öznitelik ve izleyici sabitleri saniyeye çevrildi.
- **B1:** kural modunda holdout F1 10 FPS'te 0,20 → 0,34 (özgün hızda
  0,37), 5 FPS'te 0 → 0,16.
- **13.3c:** TCN girdisi 25 Hz zaman ızgarasına alındı (1,96 sn). Model
  kare düşürme artırımıyla yeniden eğitildi.
- **B2:** sonuçlar yukarıda.

Ayrıntı aşağıda: "Aşama 13.3 — B0", "Aşama 13.3b", "Aşama 13.3 — B1",
"Aşama 13.3c", "Aşama 13.3 — B2", "Aşama 13.3 sonucu".

**Aşama 13.2 tamamlandı.** (2026-11-23)

Sekiz hızlı düzeltme canlı yığında doğrulandı (ayrıntı aşağıda "Aşama 13.2
sonucu"): XSS (9 yer), veritabanı ve Kafka portları yalnız geri dönüşe,
Gemini anahtarı başlıkta, sağlık sorgusu dizine uygun, JPEG kapısı kamera
başına, kanıt sayfalama, göreli kamera kaynağı, satır sonundan bağımsız
önbellek etiketi. Yolda: yalnız `127.0.0.1`'e bağlanan portlar Windows'ta
her yeni bağlantıya 2–3 sn ekliyordu (`localhost` önce `::1`'e çözülüyor);
portlar `[::1]`'e de bağlandı.

**Aşama 13.1 tamamlandı.** (2026-11-23)

Spark akışının iki sessiz olay kaybı giderildi ve canlı deneylerle
doğrulandı (ayrıntı aşağıda "Aşama 13.1 sonucu"):

- **A1 — sessiz sahnede tek düşme:** önce 45 sn olay yok; şimdi 7,5–7,9 sn
- **A2 — çoklu kamerada kayıp:** önce `fall_01` adaylarının %80'i,
  `run_01`'inkilerin %75'i geç sayılıp atılıyordu; şimdi 0
- **Alarm gecikmesi:** 13,99 → **7,58 sn** (medyan, 11/11 düşme)
- Yolda bulunan üçüncü kök neden: Spark'ın varsayılan 200 shuffle bölümü
  her yığını 4–5 sn yapıyordu; 2 bölümle < 1 sn

`docs/TEZ.md` §3.7 yeni sayılarla yazıldı. §3.5'in (8 saatlik koşu) olay
sayıları hâlâ geçersiz; düzeltilmiş sayılar 24 saatlik koşudan (18) gelecek.

**Açık kritik bulgu — canlı kamerada doğruluk kare hızına bağlı (13.3).**
Kural pencereleri (`fall.py`, `run.py`, `zone.py`, `loiter.py`,
`features.py`), TCN girdisi (50 kare) ve izleyici tamponu (`track_buffer`,
Ultralytics 8.4'te FPS'e göre ölçeklenmiyor) kare sayısıyla tanımlı.
Çevrimdışı değerlendirme her kareyi işler (25–30 FPS, 50 kare = 2 sn); tam
yığında canlı kamera ~10 FPS'te çalışır ve aynı pencere ~5 sn'ye uzar.
**Koddan çıkarım**; büyüklüğü 13.3'ün ilk adımında alt örneklenmiş
değerlendirmeyle ölçülecek.

**Çalışma ortamı notları:**

- Proje dizini: `C:\Users\pc\OneDrive\Masaüstü\projeler\videoAnomaliTespiti`
- Terminal bazen cmd.exe, bazen Windows PowerShell 5.1: komutlar
  zincirlenmeden (`;`, `&&` yok), her biri ayrı satırda çalıştırılır.
- Ölçümden önce GPU'yu kullanan oyun / tarayıcı kapatılır: 13.1'de açık
  kalan bir oyun görü FPS'ini üçte bire düşürdü ve bir FPS karşılaştırmasını
  geçersiz kıldı.
- `api/` değiştiğinde API imajı yeniden derlenir
  (`docker compose up -d --build api`); konteyner kodu imajın içindedir,
  `stream/` ise bağlanmış klasördür, yeniden başlatmak yeter.

## Aşama durumu

| # | Aşama | Durum |
|---|---|---|
| — | Plan ve mimari (`docs/PLAN.md`) | Tamamlandı |
| 0 | Ortam hazırlığı | Tamamlandı |
| 1 | Altyapı (Docker, veritabanı şeması) | Tamamlandı |
| 2 | Kaynak ve görü çekirdeği | Tamamlandı |
| 2.1 | YOLOv8 → YOLO26 geçişi | Tamamlandı |
| 3 | Öznitelik ve kural motoru | Tamamlandı |
| 4 | Kafka ve Spark | Tamamlandı |
| 5 | Veri katmanı ve API | Tamamlandı |
| 6 | Canlı görüntü (WebSocket) | Tamamlandı |
| 7 | LLM ve Telegram | Tamamlandı |
| 8 | Panel (kullanıcı şablonu) | Tamamlandı (8.1–8.6) |
| 9 | TCN modeli ve yeni sınıflar | Tamamlandı (9.1–9.5) |
| 10 | Ölçek ve tez çıktıları | **tamam** — 10.5 dahil: 8.0 saat, 4 kamera, kesintisiz |
| 11 | ReID ölçümü ve FIGHT kök nedeni | Tamamlandı — ReID ölçüldü (F1 0.15), hatta bağlanmadı; FIGHT duyarlılığı 0.07 → 0.80 |
| 12 | İşletim sağlamlaştırma | Tamamlandı (12.1–12.6) |
| 13 | Bütünsel inceleme ve düzeltmeler | 13.0–13.3 tamam; sıradaki 13.4 |
| 14–19 | Saha verisi, olay doğrulaması, yüz tanıma, hız, kamera geometrisi, 24 sa koşu, tez | Planlandı (`docs/YOL_HARITASI.md`) |

---

## Aşama 0–12.6 sonuçları

Ölçümler, kök nedenler ve plandan sapmalar: `docs/DURUM_ARSIV.md`.

---

## Aşama 13 — Bütünsel inceleme (2026-11-10)

Proje baştan, koddan okundu (`api/`, `vision/`, `stream/`, `models/`,
`frontend/js/`, `infra/`, `docker-compose.yml`). Bulgular, kanıt düzeyleri
(ölçüldü / koddan / hipotez) ve düzeltme tasarımı `docs/ASAMA13_PLAN.md`'de;
burada yalnızca kayıt.

### Ölçülenler

| bulgu | ölçüm |
|---|---|
| A1 — sessiz sahnede tek düşme | 3 FALL adayı, sonra sessizlik: **45 sn olay yok**; ilgisiz tek aday basılınca 5,3 sn ve 6,7 sn sonra geldi (iki bağımsız koşu) |
| A2 — çoklu kamerada kayıp, gerçek veri | 8 saatlik koşuda `fall_01` ve `run_01` ilk ~20 dk'dan sonra **7 saat sıfır olay**; `zone_01` saatte ~60 |
| A2 — kontrollü deney | 3 dosya kamerası, 4 dk: zone_01 (25 FPS) ortak saati sürükledi; fall_01 adaylarının %80'i, run_01'inkilerin %75'i su işaretinin altında (anlık yaklaşım, üst sınır) |
| C1 — sağlık sorgusu | 1 haftalık sentetik veride (483.840 belge) **445 ms → 1 ms**; dizinle eşleşen sıralama `DISTINCT_SCAN`'e geçiyor |

### Neden şimdiye kadar görülmedi

Bütün ölçümler döngüdeki kliplerle yapıldı: sürekli aday geldi, su işareti
hep ilerledi (A1 gizlendi). `scripts/soak_test.py` yalnız **toplam** olay
sayısını izliyordu; toplam, tek kamera sayesinde düzgün arttı (A2
gizlendi). 12.4'teki 13,99 sn gecikmesi de büyük olasılıkla A1'in ürünü:
her düşme, su işaretini ilerletecek bir sonraki klip döngüsünü bekledi
(7,9 sn döngü + 5 sn taban ≈ 14 sn) — hipotez. **13.1'de ölçüldü: kısmen
doğru.** Gecikmenin bir kaynağı A1'di, öteki Spark'ın 200 shuffle bölümü;
ikisi giderilince 7,58 sn.

### Deney betikleri depoda

`eval/stream_probe.py` — `tek-dusme` ve `saat-kaymasi`. Çıkış kodu hatayı
kodlar; bugün `tek-dusme` 1 döner, 13.1'den sonra 0 dönmeli. Veritabanına
dokunmazlar.

---

## Aşama 13.0 sonucu — belge düzeni (2026-11-23)

- Aşama 0–12.6 sonuçları `docs/DURUM_ARSIV.md`'ye **aynen** taşındı
  (2980 satır, satır satır denetlendi); bu dosya birkaç yüz satıra indi
- Kalan iş `docs/YOL_HARITASI.md`'de sıralandı: 13.0–19, her aşamanın
  kabul ölçütü ve commit mesajıyla. Yeni aşamalar: **13.3 zaman tabanlı
  pencereleme** ve **14.5 olay doğrulaması**; yüz tanıma (Faz 2) artık
  kapsamda (15)
- Açık sorular ayıklandı, her birine kapatılacağı aşama yazıldı
- Plan belgelerinin ve iki kod yorumunun dili sadeleştirildi

---

## Aşama 13.1 sonucu — akış doğruluğu (2026-11-23)

Uygulama sözleşmesi `docs/ASAMA13_1_PLAN.md`. Yazılan:

- ortak duvar saati: `Candidate.event_time`; `CameraPipeline.consume()`
  kare başına bir kez `time.time()` atar. Süre ölçütü yine sahne zamanı `ts`
- kamera başına saniyede bir `_TICK` nabzı (`--tick-sec`, 0 = kapalı)
- Spark: iç tipler toplama sütunu `internal` ile çıkıştan elenir; gelecek
  tarihli ret (`SPARK_FUTURE_SEC` 30); tetik 1 sn; shuffle bölümü 2;
  `AGG_VERSION` 4
- değerlendirme yalıtımı: `spark-eval` servisi (`--profile eval`),
  `eval-candidates` / `eval-events` konuları
- kamera başına aday sayacı sağlık belgesinde; `soak_test.py` kamera
  başına aday / olay artışı ve "aday üretiyor, olay üretmiyor" uyarısı
- `eval/stream_probe.py gelecek` deneyi

Testler: 252 geçti, 7 atlandı.

### Ölçümler (ana dizin, Docker yığını, 2026-11-23)

| deney | önce | sonra |
|---|---|---|
| A1 — sessiz sahnede tek düşme (`stream_probe tek-dusme`) | nabız kapalı: 45 sn olay yok, ilgisiz aday gelince 7,7 sn sonra (çıkış 1) | nabız açık: **7,5 / 7,7 / 7,9 sn** (çıkış 0) |
| gelecek tarihli ret (`stream_probe gelecek`, +3600 sn) | — | ret çalışıyor; ardından düşme 7,8 sn'de (çıkış 0) |
| A2 — 3 dosya kamerası, 280 sn (`saat-kaymasi`) | `fall_01` adaylarının %80'i, `run_01`'inkilerin %75'i geç | geç aday **0**; Spark olayı fall_01 10, run_01 13, zone_01 8 |
| tespit → alarm (`latency_watch`, `fall_01` gerçek zamanlı) | 13,99 sn (12.4, n=4) | **7,58 sn** medyan, 7,23–8,09 (n=11, 11 düşmenin 11'i) |
| değerlendirme yalıtımı (`spark-eval` + `spark_eval --from-cache`) | canlı su işaretini ~1,4 sa ileri itiyordu | Aşama 4 tablosu birebir (F1 0,50 → 0,60); hemen ardından canlı `tek-dusme` 9,1 sn (çıkış 0) |
| 30 dk kısa koşu, 3 kamera (`soak_test`) | 8 sa koşuda iki kamera 7 sa sıfır olay | kamera başına olay artışı fall_01 72, run_01 74, zone_01 35; uyarı yok; toplam FPS 29,3 sabit, düşen kare 0 |
| kap ↔ Spark konteyneri saat kayması | — | 0,32 sn |

### Yolda bulunan üçüncü kök neden: 200 shuffle bölümü

İlk A1 koşusu düzeltmeyle geçti ama olay **15,2 sn**'de geldi, beklenen
5–7 değil. Spark kayıtları: her mikro-yığın 4–5 sn sürüyor ve tetik
aralığını (1 sn) aşıyordu; Spark sürekli **~%294 CPU** yakıyordu. Sebep
Spark'ın varsayılan `spark.sql.shuffle.partitions = 200`'ü: durumlu
toplama, `local[2]`'de her yığında 200 görev koşuyordu. Nabız Spark'a her
saniye veri getirdiği için bu maliyet artık sürekliydi.

Ayrı bir test konteyneriyle (`--conf spark.sql.shuffle.partitions=2`,
ayrı checkpoint) ölçüldü: yığın < 1 sn, CPU **~%68**, A1 olayı 15,2 →
**7,5–7,9 sn**. Ayar `stream/spark_job.py`'ye kondu; bölüm sayısı
checkpoint'e yazıldığı için `AGG_VERSION` 4. 12.4'te "ayrıştırılmadı"
denen ~9 sn'lik Spark payı buydu.

### Nabzın maliyeti

| durum | Spark CPU |
|---|---|
| boşta (kamera yok) | ~%0,5 |
| yalnız nabız (aday üretmeyen tek kamera) | ~%33–42 |
| 3 dosya kamerası, adaylarla | ~%45–77 (nabız açık / kapalı ayırt edilmedi) |

Görü FPS'ine etkisi **ölçülemedi**: aynı ayarla ardışık koşularda toplam
FPS 36,3 → 24,9 → 11,8 → 11,3 → 11,2'ye kaydı. Sebep sonradan bulundu:
ölçüm sırasında GPU'da bir oyun açıktı (GPU %51, 87 °C, 3,3 GB). Oyun
kapatılınca 3 kamera 30 dakika boyunca 29,3 FPS'te sabit kaldı. Nabzın
FPS etkisi temiz koşullarda 16'da yeniden ölçülecek.

### Yolda bulunan diğer arızalar

1. **Veritabanındaki kamera kaynakları eski dizini gösteriyordu.**
   `scripts/seed_pilot.py` mutlak yol yazıyor; proje 2026-11'de
   `projeler\` altına taşınınca 6 dosya kamerası açılamadı ("kaynak
   açılamadı"). Yerel veritabanında yollar yeni dizine çevrildi (6 satır);
   kalıcı çözüm 13.2'de (göreli yol).
2. **API konteyneri eski koddu.** `api/` imaja gömülü (`build: ./api`);
   yeni `candidates` alanı imaj yeniden derlenene kadar dönmedi. Derleme
   ilk denemede Docker Hub TLS zaman aşımına düştü, ikincide geçti.
3. Docker Desktop ölçüm sırasında bir kez kapandı;
   `docker desktop start` ile açıldı, yığın kendiliğinden kalktı.

### Sınırlar

- Ölçümler gerçek zamanlı akıtılan dosya kliplerle; kameranın önünde
  gerçek bir olayla gecikme hâlâ ölçülmedi (14).
- Bir süreç kapanırken attığı `_EOS` su işaretini ~13 sn ileri iter; aynı
  anda çalışan **başka** bir görü sürecinin adayları o süre geç sayılır.
  Tek süreçli dağıtımda geçerli değil.
- `Zone.active_at` dosya kaynağında hâlâ sahne saniyesiyle çağrılıyor
  (ASAMA13_PLAN D1) — 13.3'te.

---

## Aşama 13.2 sonucu — hızlı düzeltmeler (2026-11-23)

Sözleşme `docs/ASAMA13_2_PLAN.md`. Testler: 261 geçti, 7 atlandı; tam
paket iki kez koşunca `frontend/` farkı birebir aynı (testler artık izlenen
dosyaları değiştirmiyor).

| madde | yapılan | canlı doğrulama |
|---|---|---|
| B1 XSS | `olaylar.js`'teki kamera adı/konum açığı + taramada bulunan, sunucu hata mesajını kaçışlamadan basan 8 yer `_escXml`'den geçiyor; kalan `innerHTML`'ler sabit metin veya zaten kaçışlı | statik testler |
| B2 portlar | Postgres / Mongo / Kafka yalnız `127.0.0.1` ve `[::1]` | yerel ağ adresinden (192.168.1.104) 5433 / 27018 / 9092 **kapalı**, `localhost`'tan açık; API 8000 ağa açık kaldı |
| B4 Gemini | anahtar URL'den `x-goog-api-key` başlığına; hata çıktılarına sızmadığı testli | tüketici konteynerinde gerçek çağrı `mod=llm`, 0,76 sn |
| C1 sağlık sorgusu | sıralama `{camera_id: 1, ts: -1}` | gerçek veride (1108 belge) plan `IXSCAN` → `DISTINCT_SCAN`, 3 → 2 ms, sonuç aynı; uç kalıcı bağlantıda 6 ms |
| C2 JPEG kapısı | istemci sayacı `(tür, kamera)` başına, `StreamServer.clients()` | birim testi (gerçek sunucu, iki kamera) |
| C3 kanıt | `limit` (50, tavan 500) / `offset` | `limit=3` → 3 satır, `limit=9999` → 500 |
| kamera kaynağı | seed göreli yazar (`data/pilot/<ad>.mp4`), var olanı günceller | 6 satır güncellendi; başlatıcı kamerayı göreli yolla açtı |
| önbellek etiketi | özet CRLF → LF normalleştirilerek | iki tam koşu sonrası `frontend/` değişmedi |

### Yolda bulunan: yalnız `127.0.0.1` bağlaması 2–3 sn gecikme ekledi

Portlar yalnız `127.0.0.1`'e bağlanınca ana makinedeki her istemci önce
`::1`'i denedi — Windows `localhost`'u önce IPv6'ya çözer, kapalı porta
bağlanma denemesi de hemen reddedilmez:

| bağlantı | yalnız `127.0.0.1` | `127.0.0.1` + `[::1]` |
|---|---|---|
| Kafka gidiş-dönüş (`check_kafka.py`) | 2906 ms, her istemcide `Connect to ipv6#[::1]:9092 failed` | **734 ms**, hata yok |
| Postgres | `::1` için 3 sn zaman aşımı, sonra IPv4 | doğrudan |

Atılacak bir konteynerle Docker Desktop'ın `[::1]` bağlamasını desteklediği
önce sınandı (`localhost` 8 ms). Üç port iki adrese de bağlandı; yerel ağ
adresinden yine kapalı.

### Ölçülen ama sorun olmayan

- Sağlık ucu yeni bir HTTP bağlantısıyla ~270 ms, kalıcı bağlantıyla 6 ms;
  `/health` da aynı. Maliyet istemcinin her istekte bağlantı (ve TLS
  bağlamı) kurmasında, uçta değil. Panel bağlantıyı açık tutar.
- Seed betiği modül olarak ve `.env` değişkenleriyle koşar (aşağıda
  "Sistemi açmak").

---

## Aşama 13.3a sonucu — kare hızı tarama aracı (2026-11-23)

Sözleşme `docs/ASAMA13_3_PLAN.md` §2. Hat koduna dokunulmadı; B0 bugünkü
davranışı ölçecek.

- `models/tcn.py`: `FrameDropper` (düzenli / düzensiz kare düşürme, tohumlu).
  13.3c'de eğitim artırımı da bunu kullanacak.
- `eval/tcn_eval.py`:
  - `--fps`, `--drop`, `--seeds`, `--out`, `--compare` bayrakları
  - Spark süzgecinden geçmiş ikinci puan (`session_filter`,
    `stream.filters.session_passes` ile)
  - pilot kümede `eval_end_sec` artık uygulanıyor (önce atlanıyordu)
  - etiketsiz pilot klipler (`police_run`) ham aday sayısıyla raporlanıyor
- `eval/pilot_eval.py`: ortak `load_annotation`.
- Testler: **274 geçti, 7 atlandı** (13 yeni); paket sonrası `git status`
  temiz.

**Duman koşusu** (gerçek GPU; `fall_01` + `police_run`, sınıf başına 1
holdout klibi; kural ve hibrit; özgün ve 5 FPS):

- Araç beklendiği gibi çalışıyor. Etkin FPS 5,0 / 5,1 / 5,2.
  Tutulan kareler: `fall_01` 236 → 40, `police_run` 300 → 100.
- **İlk gözlem (6 klip, ölçüm değil):** 5 FPS'te iki modda da **hiç aday
  yok**. Özgün hızda `fall_01` FALL'ı, holdout RUN ve FIGHT'ı buluyordu.
- `fall_01`'de neden kare kare görüldü. İz 5 FPS'te de var, takip
  çalışıyor:
  - eğim 5,61 sn'de 45,3°
  - iz 5,81 sn'de kayboluyor (özgün hızda da düşüşün hemen ardından
    kayboluyor)
  - dikey hız 5 kare geriye bakılarak hesaplanıyor; 5 FPS'te bu 1 sn
    demek ve düşüş −0,06'ya yayılıyor. Özgün hızda son görülen karede
    1,68 (eşik 1,20).

  `VELOCITY_SEC` dönüşümü (13.3b) tam bunu hedefliyor.
- Hibrit, 5 FPS'te holdout'ta modelden aday almadı. Holdout klipleri
  1,5–13,6 sn; 50 karelik pencere 5 FPS'te 10 sn sürüyor ve dolmuyor.

## Aşama 13.3 — B0: kare hızına karşı doğruluk, değişiklikten önce (2026-11-23)

Komut (ana dizinde, `46a48b8`, ~1 sa):

    venv/Scripts/python.exe -m eval.tcn_eval --modes rule,hybrid --limit 15 --fps 0,10,5 --drop regular,jitter --seeds 0,1,2 --out logs/fps_b0.json

Ham sonuçlar `logs/fps_b0.json` ve `logs/fps_b0.log` dosyalarında (git dışı).
Küme: 6 pilot klip (5'i etiketli, 4 olay) ve 59 holdout klip (44 olaylı +
15 NORMAL). Düzensiz kare kaybı üç tohumla koşuldu; aşağıda ortalama
[min–maks] verildi.

**Araç doğrulaması.** Özgün hız satırları önceki ölçümleri birebir verdi:
- holdout kural: F1 0,41 (TP 13 / FP 6 / FN 31, Aşama 9.5 ile aynı)
- holdout hibrit: F1 0,67 (Aşama 11 ile aynı)

Seyreltme olmadığında araç hattı değiştirmiyor.

**F1, ham adaylar:**

| mod | küme | özgün (24–27) | 10 düzenli | 10 düzensiz | 5 düzenli | 5 düzensiz |
|---|---|---|---|---|---|---|
| kural | holdout | **0,41** | 0,20 | 0,16 [0,12–0,24] | **0,00** | 0,00 |
| hibrit | holdout | **0,67** | 0,24 | 0,17 [0,12–0,24] | **0,00** | 0,00 |
| kural | pilot | 0,50 | 0,33 | 0,36 [0,33–0,40] | 0,40 | 0,40 |
| hibrit | pilot | 0,32 | 0,27 | 0,27 [0,25–0,31] | 0,18 | 0,26 [0,20–0,33] |

**F1, Spark süzgecinden sonra** (`min_hits = 2`, tipe göre `min_sec`):

| mod | küme | özgün | 10 düzenli | 10 düzensiz | 5 düzenli | 5 düzensiz |
|---|---|---|---|---|---|---|
| kural | holdout | 0,32 | 0,13 | 0,10 [0,09–0,13] | 0,00 | 0,00 |
| hibrit | holdout | 0,57 | 0,17 | 0,10 [0,09–0,13] | 0,00 | 0,00 |

**Ham sayılar:**

- Holdout'ta aday üreten klip sayısı (59 klip içinde):

  | mod | özgün | 10 FPS | 5 FPS |
  |---|---|---|---|
  | kural | 19 | 6 | **0** |
  | hibrit | 34 | 7 | **0** |

- Holdout'ta hibritin bulduğu olaylar (TP):

  | | özgün | 10 FPS | 5 FPS |
  |---|---|---|---|
  | FALL | 9 | 3 | 0 |
  | RUN | 7 | 3 | 0 |
  | FIGHT | 12 | 0 | 0 |

  FIGHT 10 FPS'te tamamen kayboluyor.
- **Pilot F1 yanıltıcı.** Küme 4 olaydan oluşuyor: FALL 1, RUN 2, ZONE 1.
  10 ve 5 FPS'te yalnız ZONE bulunuyor; FALL ve RUN kaçıyor. Kuralın
  duyarlılığı 0,75 → 0,25. F1 5 FPS'te 0,40'a "çıkıyor", çünkü
  RUN adayları (385 → 0) ve onlarla birlikte sahte RUN'lar da yok oluyor.
- Hibrit, pilotta 5 FPS'te **6 sahte FALL** üretiyor. Uzun kliplerde 50
  karelik pencere 10 sn'de doluyor ve model 10 sn'lik hareketi 2 sn'lik
  gibi okuyor.

**Açık soruların karşılığı:**

- `zone_01`'in sahte RUN'ı 10 FPS'te kayboluyor, ama gerçek RUN da
  kayboluyor. Bu bir düzeltme değil, kör nokta.
- `police_run` hiçbir hızda aday üretmiyor, özgün 15 FPS'te de. Sorun
  düşük kare hızı değil; derinlik yönündeki hız (17) olarak kalıyor.

**Yan bulgu: Spark süzgeci özgün hızda bile holdout duyarlılığını
düşürüyor.**
- hibrit duyarlılık 0,64 → 0,45; FIGHT TP 12 → 6
- Holdout klipleri kısa (FIGHT ortanca 2,8 sn). Oturum `min_hits` /
  `min_sec`'i doldurmadan klip bitiyor.
- Canlıda olay sürdükçe aday akmaya devam eder; bu kısmen kısa kliplerin
  yarattığı yapay bir durum. Kayıt olarak burada.

**Mekanizma** (koddan ve `fall_01` kare dökümünden). Kare sayısıyla
tanımlı bakışlar 5 FPS'te 5 kat uzuyor:
- hız 1 sn'ye yayılıyor (düşüş tepesi 1,68 → −0,06)
- adım ritmi 10 sn'lik pencere istiyor (holdout RUN klipleri ortanca
  4,5 sn)
- uzuv hızı 0,6 sn'ye yayılıyor
- TCN 10 sn'lik pencere istiyor

**Sonuç.** Sorun ölçüldü ve büyük:
- 10 FPS'te holdout F1: hibrit 0,67 → ~0,2
- 5 FPS'te her iki mod da 0

Canlı yığın ~10 FPS'te çalıştığı için bugünkü canlı doğruluk çevrimdışı
tablolardan belirgin biçimde düşük olmalı (çıkarım; canlıda ölçülmedi).

## Aşama 13.3b — kural, öznitelik ve izleyici sabitleri saniyeye (2026-11-23)

Sözleşme `docs/ASAMA13_3_PLAN.md` §1 ve §4. Hiçbir eşik değişmedi. Her
sabit bugünkü 25 FPS karşılığından türetildi (dönüşüm tablosu plan §1'de).

- `features.py`:
  - `TrackWindow` zamanla budanıyor (`RETAIN_SEC = 2.0`; bellek tavanı
    250 kare)
  - iki yeni erişim: `since(sn)` ve `covering(sn)`
  - hız (`VELOCITY_SEC = 0.2`) ve uzuv hızı (`LIMB_SEC = 0.12`) saniyeyle
    geri bakıyor
  - iz yaşı `STALE_SEC = 3.6` ile; bu sabit tek kaynak, düzleyici ve
    loiter buradan alıyor
- Kurallar:
  - FALL `HOLD_SEC 0.08`, `VY_SEC 0.56`
  - RUN `SPEED_SEC 0.36` + %60 isabet; `GAIT_SEC 1.96`
  - ZONE `HOLD_SEC 0.08`, `SCORE_SEC 0.16`
  - FIGHT: dizinin başladığı `ts` tutuluyor (`HOLD_SEC 0.08`)
  - LOITER `ts` tabanlı
- **D1 kapandı:** `RuleEngine(clock=time.time)`. `restricted_hours`
  bölgeleri artık kare zamanına değil duvar saatine bakıyor; dosya
  kaynağında 1970'e çözülmüyor.
- `arbiter.py`: model `idx % 5` yerine zamana göre (`MODEL_EVERY_SEC 0.2`)
  koşuyor. Eski koşulda canlıda kare atlanınca `idx` evresi 5'in katını hiç
  tutturmayabiliyordu.
- `tracker.py`:
  - `update(result, image, ts)`; `ts` zorunlu
  - Ultralytics 8.4.127 kayıp iz tamponunu kare sayısıyla tutuyor
    (`max_frames_lost`). Tampon artık ölçülen kare aralığından
    `TRACK_BUFFER_SEC = 2.4`'e göre her karede yeniden hesaplanıyor: 25 FPS'te
    60, 10'da 24, 5'te 12 kare.
- `tracker.update`'i çağıran altı değerlendirme betiği ve `camera.py`
  güncellendi. `extract_sequences.split_runs` boşluğu saniyeyle ölçüyor.
- Testler:
  - **306 geçti, 7 atlandı**; 32'si yeni (`tests/test_asama13_3_zaman.py`)
  - boşluksuz 25 FPS'te eski davranışla eşdeğerlik
  - aynı fiziksel hareketin 25, 10 ve 5 FPS'te tetiklemesi (RUN, FALL,
    ZONE, FIGHT)
  - iz yaşı, model sıklığı, izleyici tamponu, D1
- Var olan testlerden yalnız `test_fight_rule` değişti. Test aynı kareyi
  (`ts = 0`) üç kez veriyordu; eski kare sayacıyla çalışıyordu. Artık
  `ts` 0,04 sn ilerliyor; beklenen sonuç aynı.
- Duman koşusu (`fall_01` + `police_run`, sınıf başına 1 holdout klibi,
  kural, özgün ve 5 FPS):
  - `police_run` özgün hızda (15 FPS) artık **7 RUN adayı** üretiyor;
    B0'da hiç üretmiyordu. Hız eskiden 5 kare = 0,33 sn geriye
    bakıyordu, şimdi 0,2 sn.
  - `fall_01` 5 FPS'te yine bulunmuyor. İz düşüşten hemen sonra
    kayboluyor: 5 FPS'te son iki karede eğim 41,3° ve 45,3°, eşik 45°.
  - B1 kümenin tamamında ölçecek.

## Aşama 13.3 — B1: kurallar saniyeye çevrildikten sonra (2026-11-23)

Komut (ana dizinde, `89bad51`):

    venv/Scripts/python.exe -m eval.tcn_eval --modes rule --limit 15 --fps 0,10,5 --drop regular,jitter --seeds 0,1,2 --out logs/fps_b1.json

Ham sonuçlar `logs/fps_b1.json` ve `logs/fps_b1.log` dosyalarında. Küme
B0 ile aynı: holdout klip listesi birebir aynı, `--compare` uyarı
vermedi.

**Kural modu, holdout, F1 (ham) — B0 → B1:**

| | özgün | 10 düzenli | 10 düzensiz | 5 düzenli | 5 düzensiz |
|---|---|---|---|---|---|
| F1 | 0,41 → 0,37 | 0,20 → **0,34** | 0,16 → **0,32** [0,31–0,34] | 0,00 → **0,16** | 0,00 → **0,13** [0,12–0,15] |
| duyarlılık | 0,30 → 0,25 | 0,11 → 0,23 | 0,09 → 0,21 | 0,00 → 0,09 | 0,00 → 0,08 |
| süzgeçli F1 | 0,32 → 0,32 | 0,13 → 0,35 | 0,10 → 0,27 | 0,00 → 0,12 | 0,00 → 0,08 |

- 10 FPS'te kural, özgün hızdaki F1'ine neredeyse geri döndü (0,37'ye
  karşı 0,34).
  - RUN TP 3 → 7; özgün hızda da 7.
  - Aday üreten holdout klibi 6 → 14; özgün hızda 16.
- 5 FPS'te 0'dan çıktı; aday üreten klip 0 → 7. Hâlâ özgün hızın çok
  altında.
- FALL 10 FPS'te 3/14 (özgün 4/14). Pilot `fall_01` 10 ve 5 FPS'te hâlâ
  bulunmuyor: iz düşüşten hemen sonra kayboluyor. Hibritte FALL'ın
  çoğunu model buluyordu (özgün 9/14); 13.3c'de görülecek.
- FIGHT kural modunda her hızda 0. Kural tabanlı FIGHT zaten zayıftı
  (Aşama 11); asıl yükü model taşıyor.
- Pilot: RUN 10 ve 5 FPS'te yeniden bulunuyor; duyarlılık
  0,25 → 0,50.

**Özgün hızdaki fark (0,41 → 0,37) aday düzeyinde açıklandı.** Değişen 18
klip var.

- **25 FPS'lik kliplerde dönüşüm doğrulandı.** `zone_01` ve
  `casia_angleview_p01_faint_a1` eski (`e4fd3c9`) ve yeni kodla aynı
  algılayıcıyla kare kare koşuldu.
  - İzler birebir aynı.
  - Farklı çıkan 21 adayın **21'i de** izde son ~2 sn içinde boşluk olan
    karelerde: eski pencere gözlenen kareyi, yeni pencere süreyi sayıyor
    (plan §1).
  - Boşluksuz pencerede tek fark yok.
- **Kaybedilen 2 TP ikisi de 30 FPS'lik klipte:**
  - `urfd_fall-25-cam0`: tek FALL adayı vardı
  - `bitint_kick_0016`: tek FIGHT adayı vardı

  30 FPS'te eski pencereler zamanca %17 kısaydı. Örneğin FALL'ın eğim
  tutması 3 kare = 0,067 sn idi, şimdi 0,08 sn (4 kare). İki aday da
  sınırdaydı. Eşik oynatılmadı.
- Bir FP gitti: `bitint_bend_0007` (NORMAL, 30 FPS), tek RUN adayı.
- Kabul ölçütü (özgün hızda gerileme yok) B2 için tanımlı. B1 bir ara
  noktadır; bu fark B2'de kural satırında yine görülecek.

## Aşama 13.3c — TCN girdisi zaman ızgarasına, kod (2026-11-24)

Sözleşme `docs/ASAMA13_3_PLAN.md` §6.

- `models/tcn.py`:
  - `resample` (25 Hz, 50 nokta = 1,96 sn), güven puanını hesaba katan
    ara değerle. Satırlar yine `frame_vector`'dan geçiyor.
  - pencereleme artık eğitim sırasında yapılıyor: `split_runs`,
    `clip_windows`
  - kare düşürme artırımı (`augment_keep`, 15 / 10 / 5 FPS)
  - `build_split`: doğrulama hız başına ayrı tutuluyor
  - sabit tohum
  - `TCNClassifier`, meta verisinde `grid_hz` yoksa `ValueError` atıyor;
    eski ağırlık yeni girdiyle sessizce çalışmıyor. `camera.build_engine`
    bunu yakalayıp yalnız kurala düşüyor.
- `arbiter.window_tensor` → `resample(..., t_end=son kare)`.
  `TrackWindow.recent` kalktı.
- `eval/extract_sequences.py` artık ham iz yazıyor:
  `data/tracks/<SINIF>/<klip>.npz`. Alanlar: kare indeksi, iz, bbox,
  eklemler, poz bayrağı, URFD olay kareleri. Pencere kurmuyor.
- `tcn_eval`, `conf_sweep`, `domain_gap`: `--sequences` → `--tracks`.
- Testler: **318 geçti, 8 atlandı**. 13 yeni test var; holdout listesi
  testi `data/tracks` olmayan dizinde atlanıyor. Testlerin kapsadıkları:
  - 25 FPS'e oturan girdi, eski kare kare vektörleri 1e-5 içinde veriyor;
    düşük güvenli eklem ve pozsuz kare dahil
  - sabit hızlı iz 10 ve 5 FPS'te 25 FPS'tekine yakın çıkıyor
  - bölme klip bazında, sızıntı yok
- `resample` pencere başına 0,44 ms.

**Gözden geçirmede bulunan iki sorun, ikisi de düzeltildi:**

1. **Pencere sonu hedeften önceki örneğe çekiliyordu.** 30 FPS'lik
   klipte ilk hedef 1,96 sn; ondan önceki örnek 1,933 sn'de kalıyordu ve
   pencere 1,96 sn'yi kapsamadığı için `resample` `None` döndürüyordu.
   Sonuç: 2,6 sn'lik FIGHT klibinden **hiç pencere çıkmıyordu**. Son artık
   hedeften sonraki ilk örnek; kapsam garanti.
2. **Kaydırma bütün sınıflarda 0,4 sn** (plan: FALL 0,4, diğerleri 1,0).
   - Eski pencere 50 gözlenmiş kareydi: 30 FPS klipte 1,67 sn. Yeni
     pencere 1,96 sn.
   - 1 sn kaydırmayla kısa klipler yarı pencere veriyordu
     (`bitint_box_0002`: 10 → 5). FIGHT kliplerinin ortancası 2,8 sn.
   - 0,4 sn ile deneme kliplerinin hepsinde pencere sayısı eskiye eşit
     veya üstünde (FIGHT 4 / 10 = eski; FALL 20 / 15 / 5, eski 17 / 14 / 5;
     RUN 2, eski 1).
   - Sınıf dengesizliği zaten ağırlıklı kayıpla karşılanıyor.

Kod commit'li ve `main`'de: `461338e`. Eski model
`runs/tcn_kare_tabanli/` altında; özet sağlaması aynı.

**Yeniden çıkarım yarıda kesildi** (2026-11-24): oturum kapandı. Durum:
- 1080 klipten 218'i yazılı: NORMAL 218/600; FALL, RUN, FIGHT 0.
- Son dosya yarım yazılmıştı (`casia_angleview_p08_walk_a2.npz`, "not a
  zip file"); silindi.
- `extract_sequences` artık önce `.tmp` dosyasına yazıp sonra yerine
  koyuyor (`os.replace`), böylece kesinti bozuk dosya bırakmıyor. Bu
  düzeltme `fix: asama 13.3 - iz cikariminda atomik yazim` commit'iyle
  girdi. Testler: 318 geçti, 8 atlandı.

### İz çıkarımı sonucu (2026-11-24)

Kaldığı yerden sürdü (01:51–03:08, ~7 klip/dk). Kayıt:
`logs/extract_tracks.log`.

| Sınıf | Klip | Örnek | İz | İzsiz klip | Eski izsiz (9.2) |
|---|---|---|---|---|---|
| NORMAL | 600 | 102 508 | 1147 | 104 | 185 |
| FALL | 66 | 5 696 | 111 | 7 | 28 |
| RUN | 144 | 8 582 | 124 | 40 | 65 |
| FIGHT | 270 | 55 205 | 750 | 13 | 40 |

- İzsiz klip eskisinden az. Eski çıkarım 50 gözlenmiş karelik pencere
  istiyordu; ham iz her uzunlukta tutuluyor.
- İzsiz kliplerin 36'sı hiç açılmıyor (`n_frames = 0`: NORMAL 22,
  FIGHT 13, RUN 1). Bunlar 9.2'de bulunan, kaynakta bozuk dosyalar
  (`moov atom not found`).
- Kalanlarda kare okunuyor ama kimse algılanmıyor: RUN 39 (CASIA ve
  UCARG), NORMAL 82 (çoğu CASIA), FALL 7 (hepsi CASIA `faint`).
  CASIA'da kişi uzak ve küçük. 9.2'de de vardı.

### Eğitim sonucu (2026-11-24)

Ana dizinde `models.tcn --train`. Kayıt: `logs/tcn_train.log`. Epoch
başına ~3 sn. 30. epoch en iyi; 40'ta erken durdu.

- Eğitim 25 002 pencere, doğrulama 5 997 pencere. Her klip özgün hızda
  ve 15 / 10 / 5 FPS'e düşürülmüş halde.
- `tcn_meta.json`: `grid_hz = 25.0`, `window_sec = 1.96`.
- Pencere başına çıkarım 1,14 ms (eski 1,20).

**Hız başına doğrulama makro F1'i:**

| Hız | Makro F1 | Pencere |
|---|---|---|
| özgün | 0,719 | 1553 |
| 15 FPS | 0,702 | 1521 |
| 10 FPS | 0,714 | 1498 |
| 5 FPS | 0,707 | 1425 |

Model hıza duyarsız: 5 FPS ile özgün hız arasındaki fark 0,012. 13.3c'nin
amacı buydu.

**Sınıf başına** (dört hız birlikte; eski model 9.3, yalnız özgün hız):

| Sınıf | Kesinlik | Duyarlılık | F1 | Pencere | Eski F1 |
|---|---|---|---|---|---|
| NORMAL | 0,877 | 0,858 | 0,868 | 4149 | 0,760 |
| FALL | 0,421 | 0,356 | **0,385** | 284 | 0,568 |
| RUN | 0,838 | 0,927 | 0,880 | 317 | 0,817 |
| FIGHT | 0,683 | 0,738 | 0,709 | 1247 | 0,649 |
| **makro** | | | **0,711** | | 0,698 |

Karışıklık matrisi (satır = gerçek, sütun = tahmin):

| | NORMAL | FALL | RUN | FIGHT |
|---|---|---|---|---|
| **NORMAL** | 3561 | 123 | 45 | 420 |
| **FALL** | 176 | 101 | 0 | 7 |
| **RUN** | 15 | 8 | 294 | 0 |
| **FIGHT** | 307 | 8 | 12 | 920 |

**Bulgu — FALL zayıfladı.** F1 0,568 → 0,385. FALL pencerelerinin
%62'si NORMAL tahmin ediliyor. Karşılaştırma kesin değil: doğrulama
kümeleri farklı (eski 71 pencere, yeni hız başına ~70). FALL doğrulaması
~13 klip, bu yüzden oynaklığı yüksek. Belirleyici ölçüm B2'nin holdout
FALL satırları. Orada da düşüş görülürse aşama kapanmaz (plan §8.3);
klip klip incelenir ve karar kullanıcıya sorulur.

Eski model `runs/tcn_kare_tabanli/` altında.

## Aşama 13.3 — B2: TCN zaman ızgarasından sonra (2026-11-24)

Komut (ana dizinde, `8203e58` ve yeni model; ~37 dk):

    venv/Scripts/python.exe -m eval.tcn_eval --modes rule,hybrid --limit 15 --fps 0,10,5 --drop regular,jitter --seeds 0,1,2 --out logs/fps_b2.json

Ham sonuçlar `logs/fps_b2.json` ve `logs/fps_b2.log` dosyalarında.
Holdout listesi B0 ile birebir aynı: 59 klip, `meta.holdout` eşit.

**Kural satırları B1 ile birebir aynı** (bütün hız ve tohumlar). Beklenen
sonuç: 13.3c kural yoluna dokunmadı. Özgün hızdaki 0,41 → 0,37 farkı
13.3b'den geliyor ve B1 bölümünde aday düzeyinde açıklandı.

**Hibrit, holdout, F1 — B0 → B2:**

| | özgün | 10 düzenli | 10 düzensiz | 5 düzenli | 5 düzensiz |
|---|---|---|---|---|---|
| ham F1 | 0,67 → 0,67 | 0,24 → **0,62** | 0,17 → **0,59** [0,58–0,60] | 0,00 → **0,54** | 0,00 → **0,47** [0,42–0,51] |
| süzgeçli F1 | 0,57 → **0,48** | 0,17 → 0,44 | 0,10 → 0,35 [0,31–0,39] | 0,00 → 0,28 | 0,00 → 0,24 [0,22–0,26] |

Tip başına ham F1 (düzensiz satırlarda üç tohumun ortalaması):

| | özgün | 10 düzensiz | 5 düzensiz |
|---|---|---|---|
| FALL | 0,78 → 0,83 | 0,25 → 0,58 | 0,00 → 0,55 |
| RUN | 0,48 → 0,52 | 0,25 → 0,53 | 0,00 → 0,14 |
| FIGHT | 0,75 → **0,67** | 0,00 → 0,66 | 0,00 → 0,65 |

- 13.3'ün amacı tuttu: hibrit 10 FPS'te özgün hızına neredeyse döndü,
  5 FPS'te sıfırdan 0,47–0,54'e çıktı.
- **FALL holdout'ta gerilemedi.** Özgün hızda TP 9 → 10. Eğitim
  doğrulamasındaki FALL düşüşü (0,568 → 0,385) holdout'ta görülmüyor.
- RUN 5 FPS'te kuralla aynı (0,14). Model RUN'a bu hızda bir şey
  katmıyor.
- Pilot hibrit: özgün 0,32 → 0,57 ham, 0,35 → 0,60 süzgeçli.

**Gerileme — özgün hızda FIGHT.** Ham ve süzgeçli TP/FP/FN, B0 → B2:

| Tip | ham | süzgeçli |
|---|---|---|
| FALL | 9/0/5 → 10/0/4 | 8/0/6 → 8/0/6 |
| RUN | 7/7/8 → 7/5/8 | 6/3/9 → 6/3/9 |
| FIGHT | 12/5/3 → 10/5/5 | **6/3/9 → 2/3/13** |

Süzgeçli toplamdaki 0,57 → 0,48 düşüşünün tamamı FIGHT'tan.

**Kök neden: holdout FIGHT klipleri pencereden kısa.** Klip klip:

- Holdout FIGHT klipleri BIT-Interaction'dan, 30 FPS, 1,2–2,9 sn.
- Eski pencere 50 gözlenmiş kareydi: 30 FPS'te 1,67 sn. Yeni pencere
  1,96 sn. Model ancak iz 1,96 sn yaşlanınca koşuyor.
  - Bu yüzden klip başına model koşusu kısalıyor. **Her FIGHT klibinde**
    aday sayısı düştü. Örnek: `box_0016` 2,57 sn'de 20 → 11,
    `box_0001` 2,63 sn'de 6 → 2.
  - 1,96 sn'den kısa klipler artık hiç aday vermiyor: `box_0046`
    (1,90 sn, 3 → 0) ve `kick_0016` (1,73 sn, 2 → 0). Ham FN 3 → 5'in
    ikisi bunlar.
- Süzgeç FIGHT'ta iz çifti başına en az 2 aday ve en az 0,5 sn süre
  istiyor. Model 0,2 sn'de bir koşuyor. 2,4 sn'lik bir klipte bu süre
  için kalan pay eskiden ~0,7 sn'ydi, şimdi ~0,4 sn; 0,5 sn'lik süreye
  yetmiyor. Süzgeçli TP 6 → 2.
- Mekanizma B1'deki kural farkıyla aynı: 30 FPS'te eski kare tabanlı
  pencereler zamanca %17 kısaydı.

Canlı kamerada etkisi: kavga en az ~2 sn sürmeden model koşmuyor;
öncekine göre ~0,3 sn daha geç. Değerlendirmede bu, kısa klip yapaylığı
olarak görünüyor.

Plan §8.3'e göre aşama bu gerilemeyle kapanmaz; karar kullanıcıya
soruldu. **Karar (2026-11-24): kabul.** Pencere 1,96 sn kalıyor.
Gerekçe:

- Gerileme klip uzunluğu yapaylığı; mekanizma klip klip açıklandı.
- Canlıdaki bedeli ~0,3 sn daha geç model kararı.
- Pencereyi holdout sonucuna bakarak kısaltmak holdout'u ayar kümesine
  çevirirdi.

Saha verisiyle (14) yeniden bakılabilir.

## Aşama 13.3 sonucu — kapanış (2026-11-24)

**Canlı duman testi.** Ana dizinde koşuldu, 80 sn. Kayıt:
`logs/smoke_13_3c.log`.

    venv/Scripts/python.exe -m vision.run --source data/pilot/fall_01.mp4 --rules --realtime --loop --max-frames 2400

- Çökme yok. 2400 kare 80,3 sn'de işlendi: 29,9 FPS, kaynak 30 FPS,
  düşen kare 6.
- TCN 79 kez koştu. Model çıkarımı medyan 1,5 ms, p95 2,9 ms.
- 20 FALL adayı, 10 döngüde 10 izde. İlk tetik 5,8 sn'de.
- İzleyici tamponu 72 kare: 2,4 sn × 30 FPS. İşlenen FPS ile tutarlı.

Rapor, TCN koşu sayısını ve izleyici tamponunu basmıyordu. Sayaç
(`HybridArbiter.model_runs`) rapor için konmuştu ama bağlanmamıştı.
`vision/run.py` raporuna iki satır eklendi. Duman testi ana dizinin
kodunu koştu; iki satır bir sarmalayıcıyla aynen basıldı.

**Testler:** worktree'de 318 geçti, 8 atlandı. Ana dizinde 319 geçti,
7 atlandı; holdout listesi testi gerçek veriyle koştu. Atlananlar
veritabanı testleri (Docker kapalıydı). Paket koştuktan sonra
`git status` temiz.

**Kabul (plan §8):**

1. Testler yeşil.
2. B0, B1, B2 tabloları bu dosyada.
3. Özgün hızda FIGHT gerilemesi var. Klip klip açıklandı ve kullanıcı
   kabul etti.
4. 10 ve 5 FPS önce / sonra raporlandı.
5. Holdout listesi aynı.
6. Duman testi geçti.
7. `docs/TEZ.md` §4.5 taslağı yazıldı.

**Plandan sapma:** yol haritasındaki hız artırımı (0,5x–2x)
uygulanmadı. Gerekçe plan §6.2'de.

---

## Bir sonraki adım

**Aşama 13.4 — düşme sonrası hareketsizlik** (`docs/YOL_HARITASI.md`).
Önce uygulama planı yazılır (`docs/ASAMA13_4_PLAN.md`). Süreler saniye
cinsinden; N, kayıtlara bakmadan önce gerekçesiyle seçilir.

Sonraki sıra, veri bekleyen işler ve yapılamayacaklar:
`docs/YOL_HARITASI.md`. Tez metni 19'da; **§3.5'in olay sayıları
teze aktarılmamalı** (24 saatlik koşu, 18).

### Sistemi açmak

```bash
docker compose up -d
venv/Scripts/python.exe scripts/run_pilot_cameras.py --cameras webcam_01,zone_01,run_01,fall_01
```

`--cameras` boş bırakma: varsayılan **3** kamera açar, 4 kameralık
ölçümlerle karşılaştırılamaz.

`api/` değiştiyse imaj yeniden derlenir: `docker compose up -d --build api
consumer`. Pilot kamera satırları (`scripts/seed_pilot.py`) proje kökünden,
`.env` değişkenleri yüklü olarak modül şeklinde koşar
(`venv/Scripts/python.exe -m scripts.seed_pilot`); tekrar koşmak güvenli.

Yığın kontrolü konteyner sağlığıyla bitmez — ana makineden gerçek istek at:

```powershell
Invoke-WebRequest http://localhost:8000/health -UseBasicParsing
```

Panel `http://localhost:8000`, kullanıcı `admin`, şifre `.env`'deki
`ADMIN_PASSWORD`.

---

## Karar günlüğü

| Tarih | Karar | Gerekçe |
|---|---|---|
| 2026-08-24 | Sıfırdan v2 yazılacak, v1 yalnızca referans | v1'in 13 zayıf noktası mimari düzeyde; yamayla değil tasarımla çözülüyor |
| 2026-08-24 | Tek model: `yolov8s-pose` | v1'de detect + pose iki ayrı geçişti, yaklaşık %40 GPU israfı |
| 2026-08-24 | BoT-SORT, DeepSORT değil | ReID + kamera hareketi telafisi hazır gelir; v1'deki ~250 satır elle yama hiç doğmaz |
| 2026-08-24 | Eşikler bbox yüksekliğine normalize | İnsan boyu sabit; kamera açısı ve derinlikten bağımsız eşik |
| 2026-08-24 | Eşikler veritabanında, `.env`'de değil | v1'de 40+ eşik `.env`'deydi, değişiklik restart istiyordu |
| 2026-08-24 | Temiz kare + ayrı metadata, overlay istemcide | Katman aç-kapa, keskin ölçekleme, doğru ROI koordinatı |
| 2026-08-24 | `vision/` host'ta native, geri kalan Docker'da | Windows'ta Docker'a GPU geçirmek zaman kaybı |
| 2026-08-24 | Python 3.11 venv | Sistemde 3.13 varsayılan; CV yığını 3.11'de daha oturmuş |
| 2026-08-24 | LLM: Gemini Flash + şablon yedeği | Ücretsiz kota yeterli, Türkçesi akıcı; yedek sayesinde API çökünce alarm durmaz |
| 2026-08-24 | Bildirim: Telegram Bot (şimdilik) | Token + chat_id yeterli, mobil uygulama gerekmiyor |
| 2026-08-24 | `yolov8s-pose` kesinleşti | Ölçümde `n` ile aynı süreyi verdi (13.3 vs 13.2 ms); darboğaz GPU değil sabit çağrı yükü, yani `s` bedava |
| 2026-08-24 | FP16 için `quantize=16` | ultralytics 8.4'te `half=True` kullanımdan kalktı |
| 2026-08-24 | Kafka KRaft, Zookeeper yok | Bir servis eksilir, tek broker için Zookeeper'ın getirisi yok |
| 2026-08-24 | Kafka log'u kalıcı değil | Olaylar zaten PostgreSQL/MongoDB'ye yazılıyor; restart'ta yalnızca consumer offset'i kaybolur |
| 2026-08-24 | `spark` ve `api` compose'a Aşama 4-5'te girer | Kodları henüz yok; boş servis tanımı sağlığı yanlış raporlar |
| 2026-08-24 | Host portları 5433 / 27018 | v1 konteynerleri açılışta 5432/27017'yi tutuyor; v1 durdurulmadı |
| 2026-08-24 | Admin şifresi `pgcrypto` ile init.sql içinde hash'lenir | Depoda açık şifre yok, yerel bcrypt bağımlılığı da yok |
| 2026-08-24 | `.gitattributes` ile `eol=lf` | CRLF ile yazılan `topics.sh` Linux konteynerde çalışmıyor |
| 2026-08-24 | Docker AI (`EnableDockerAI`) kapatıldı | Docker Desktop 4.79.0 Inference manager soketi yüzünden açılışta çöküyordu |
| 2026-08-24 | `model.track()` değil doğrudan `BOTSORT` sarmalayıcı | ultralytics'in track yolu toplu çıkarımda tüm kareler için tek tracker kullanır; çoklu kamerada her kameranın kendi tracker'ı olmak zorunda |
| 2026-08-24 | ReID: `with_reid: True` + `model: auto` | Dedektörün kendi öznitelikleri kullanılıyor — ek model, ek VRAM, ek çıkarım maliyeti yok |
| 2026-08-24 | GMC varsayılan `none` | Altı klipte açık/kapalı ID sonuçları aynı; `sparseOptFlow` kare başına ~18 ms alıp FPS'i yarıya düşürüyor. Sabit kamerada telafi edilecek hareket yok |
| 2026-08-24 | CLAHE koşullu | Kare başına 8–9 ms; iyi ışıkta kazanç yok. 1/8 boyutta gri standart sapması kapısı ~0.1 ms |
| 2026-08-24 | Canlı kaynak en yeni kareyi tutar, dosya hiç kare atmaz | Canlıda gecikme birikmemeli; kayıtta değerlendirme tekrar edilebilir olmalı |
| 2026-08-24 | Canlı kaynakta okuma zaman aşımı akış sonu sayılmaz | Webcam açılışı bu makinede ~5 sn; ilk sürüm 2 sn'de pes edip "hiç kare okunamadı" diyordu |
| 2026-08-24 | FPS sayacı ilk karede başlar | Webcam/RTSP açılış süresi FPS'i yanlış düşük gösteriyordu |
| 2026-08-24 | `--cv-threads` ayarı eklendi ve kaldırıldı | 0/4/8/16 arasında ölçülebilir fark çıkmadı (~2 FPS gürültü) |
| 2026-08-25 | Dedektör `yolo26s-pose` | End2end (NMS yok): çift tespit ve kutu birleştirme sorunu mimari olarak doğamaz, ayarlanacak `iou` eşiği kalmaz. Bedeli çıkarımda +4 ms |
| 2026-08-25 | ReID: `yolo26s-reid.onnx` | YOLO26 end2end olduğu için dedektörün bedava öznitelikleri ReID'e bağlanamıyor (ultralytics bunu açıkça dışlıyor). Karşılığı amaca özel eğitilmiş ağ, kare başına ~7 ms |
| 2026-08-25 | `onnxruntime-gpu==1.22.0` sabit | 1.23+ CUDA 13 ister; bizde cu121 var. Sabitlenmezse hata vermeden CPU'ya düşüp FPS'i yarıya indiriyor |
| 2026-08-25 | Tracker cihazı `cuda:0` | Çıplak `"cuda"` ONNX Runtime'a `device_id=None` gidiyor, CUDA sağlayıcısı reddedilip CPU'ya düşülüyor |
| 2026-08-25 | Varsayılan `conf` 0.35 → 0.25 | End2end kafa aynı tespite daha düşük skor veriyor; `police_run` izli kare 132 → 191 (v8 @0.35: 193) |
| 2026-08-25 | ReID batch 2'nin katına yuvarlanır | ONNX şekil değişiminde ~50 ms yeniden ayarlama var ve ısıtma çözmüyor. Yuvarlama p95'i 50.4 → 13.4 ms indiriyor |
| 2026-08-25 | `yolo26m-pose` reddedildi | Çıkarım `s`'nin iki katı (60.9 ms); `n`/`s` eşitliği `m` ölçeğinde tutmuyor |
| 2026-08-25 | YOLO12 ve RTMPose/ViTPose reddedildi | YOLO12 dikkat tabanlı, FlashAttention'sız GPU'da riskli; RTMPose/ViTPose top-down iki aşamalı, v1 zayıf nokta 1'e geri dönüş olurdu |
| 2026-08-25 | Düşme ölçütü `body_tilt = max(iskelet açısı, bbox eğimi)` | İskelet omurga açısı tepesi `fall_01`'de 20.2 derece, eşik 45 — kamera eksenine doğru düşende kalça→omuz vektörü görüntüde dik kalıyor. bbox eğimi her karede var ve `aspect 1.0` tam 45 dereceye düşüyor, yani eşik birimi değişmiyor |
| 2026-08-25 | Eksik keypoint'te `spine_angle = -1.0` | Önceki `0.0` "dimdik" demekti; kalça kaybolunca düşme sessizce yanlış negatife dönüyordu |
| 2026-08-25 | `centroid` her zaman bbox merkezi, mid_hip değil | Kalça kaybolunca merkez kaynağı değişiyor ve iki nokta arası sabit fark tek karede hız gibi okunuyordu (`fall_01` 5.61 sn: 2.46 / -2.79) |
| 2026-08-25 | RUN'a ikinci kanıt: adım ritmi | Yatay görüntü hızı kamera ekseni boyunca harekette veya kamera özneyi takip ederken ölçülemiyor (run_01 tepe 0.41, mixed_01 1.04, sabit kamerada police_run 1.77 — eşik 1.80). Adım döngüsü kamera geometrisinden bağımsız |
| 2026-08-25 | Adım medyanı 50 kare, `run_gait_speed` 1.20 | 10 karelik pencerede ayrım yok (yürüyüş p95 1.28, koşu 1.45); 50 karede yürüyüş 1.00'a inerken koşu 1.46'da kalıyor. Bedeli 2 sn tespit gecikmesi |
| 2026-08-25 | `window_frames` 30 → 50 | Adım medyanı 2 saniyelik pencere istiyor; bedeli iz başına 50 `FrameFeatures` |
| 2026-08-25 | Türev, tampon dolmadan hesaplanmaz | Kısa pencerede `dt` tek kareye düşüp kutunun oturma titremesini hız yapıyordu: `normal_01` 0.4 sn'de 25 sahte RUN. Bedeli iz başına 0.2 sn sessizlik |
| 2026-08-25 | `zone_01` değerlendirmesi 28. saniyede kesiliyor | Klip kurgu: 28. sn'de kamera değişiyor, bölge poligonu kameraya bağlı olduğu için otopark sahnesindeki yayaların üstüne düşüyordu. 20 yanlış pozitif saniyenin tamamı buradandı |
| 2026-08-27 | Kayan pencere değil `session_window` | Kayan pencere `run_01`'in 11 sn'lik tek koşusu için 11 ayrı doğrulanmış olay yazardı; tekrarı Aşama 5'te ayıklamak yama yığını olurdu. Oturum penceresi episodu tek satır yapıyor: 333 aday → 1 olay |
| 2026-08-27 | Süzgeç iki ölçütlü ve tipe göre | Gerçek FALL 2 aday, sahte RUN 11 aday üretiyor. Tek `hits` eşiği ya FALL'ı eler ya gürültüyü geçirir. FALL darbe, RUN/ZONE durum |
| 2026-08-27 | `min_sec` süre cinsinden, kare cinsinden değil | `police_run` 15 FPS, diğerleri 25–30. Kare sayan eşik 15 FPS'lik kamerada iki katı süre talep eder |
| 2026-08-27 | `spark_min_hits` varsayılanı 5 → 2 | 5, `fall_01`'in 2 adaylık gerçek düşmesini elerdi |
| 2026-08-27 | `spark_min_sec` JSONB sütunu | Tip başına ayrı sütun yeni kural tipinde şema göçü ister; JSONB istemez |
| 2026-08-27 | Akış sonu işaretçisi `_EOS` | Dosya bitince damga ilerlemiyor ve klibin son oturumu hiç yazılmıyordu. Toplamadan önce elenmez, yoksa damgayı da ilerletmez |
| 2026-08-27 | Pencerelenen zaman sahne zamanı | 25 FPS'lik klip 35 FPS'te işlenirse duvar saatiyle 3 sn'lik pencere 4 sn'lik sahneyi kapsar; ölçüm tekrarlanabilir olmaz |
| 2026-08-27 | `confluent-kafka`, `kafka-python` değil | `produce()` kuyruğa atıp dönüyor; ölçülen maliyeti 0.0 ms. Saf Python istemci GPU döngüsünün içinde GIL altında protokol işi yapardı |
| 2026-08-27 | RUN `min_sec` 1.0 kaldı, 2.0 reddedildi | 2.0 toplam precision'ı 1.00'a çıkarıyor ama tek klipteki tek yanlış pozitife göre seçilmiş olur ve RUN gecikmesini 2 sn'den 4 sn'ye çıkarır |
| 2026-08-25 | Eşikler pilot kliplere uydurulmadı | `mixed_01`'in koşusu adım kanıtında normal yürüyüşle örtüşüyor (0.69 vs 0.66). Ayıracak eşik yok; zorlanırsa `zone_01`'in normal yürüyüşü de RUN olurdu. Beş klibe uydurmak test kümesini ezberlemektir |
| 2026-08-28 | Alembic kurulmadı, şema tek kaynak `init.sql` | Üzerinde veri olmayan bir veritabanında göç aracının getirisi yok; şema iki yerde tanımlanınca kaçınılmaz olarak ayrışıyor. Drift'i 46 satırlık bir test yakalıyor. Gerçek ihtiyaç Aşama 9'da (yeni sınıflar + birikmiş `telemetry`) doğacak |
| 2026-08-28 | Şifre doğrulaması `pgcrypto crypt()` ile veritabanında | Hash zaten `init.sql`'de bcrypt'lendi; Python'a `passlib`/`bcrypt` sokmak ikinci bir hash yolu ve ikinci bir hata kaynağı demek |
| 2026-08-28 | Senkron SQLAlchemy + `def` uçlar | 4 kameralık sistemde asenkron sürücünün ölçülebilir getirisi yok; tüketici aynı `sessionmaker`'ı paylaşınca ikinci bir veri katmanı yazılmıyor. WebSocket işleyicileri yine `async` kalabilir |
| 2026-08-28 | `camera_id` çözümü `id::text = :cid OR name = :cid` | Panel sayısal id ile, pilot değerlendirme klip adıyla yayın yapıyor; tek sorgu ikisini de karşılıyor. Bulunamayan kamerada satır yaratılmıyor, mesaj atlanıyor |
| 2026-08-28 | `idx_events_dedup` + `ON CONFLICT DO NOTHING`, offset elle commit | Kafka en-az-bir-kez teslim ediyor. Oturum penceresi bir episodu tek satır yazdığı için (camera, tip, başlangıç, izler) doğal anahtar. Offset DB yazımından sonra commit edilirse en kötü ihtimal tekrar, kayıp değil |
| 2026-08-28 | `IntegrityError` yeniden denenmez, atlanır | CHECK/FK ihlali yeniden denemeyle düzelmez; tüketiciyi arkasındaki tüm olaylarla kilitler. Tekrar kaydı zaten `ON CONFLICT` ile eleniyor |
| 2026-08-28 | `MongoClient` ilk kullanımda kurulur | Import anında kurulunca `consumer` modülü ortam değişkeni olmayan her yerde içe aktarılırken patlıyor; saf fonksiyon testi Mongo'ya bağlanmak zorunda kalıyordu |
| 2026-08-28 | Spark `failOnDataLoss=false` | Kafka log'u kalıcı değil ama checkpoint kalıcı; broker yeniden kurulunca sorgu "offset 12'den 0'a düştü" diye ölüyor. Kalıcı olmayan log'da veri kaybı zaten kabul edilmiş bir maliyet, olaylar PostgreSQL'de yaşıyor |
| 2026-08-28 | `PUT /api/settings` kısmi gövde kabul eder | Tek eşik için 13 alanın tamamını göndermek, formda dokunulmamış alanı eski değerine geri yazma (lost update) riski demek. Yeni kamera satırı global'den miras alır |
| 2026-08-28 | Sıcak yükleme yalnız kural eşiklerini kapsar | `pose_conf`/`track_conf` model ve tracker kurulumunda, `window_frames` öznitelik tamponunda donuyor. API yanıtı `restart_required` listesini taşıyor ki panel yalan söylemesin |
| 2026-08-28 | Şiddet (severity) tipten türetilir, skordan değil | Kural skorları tipler arasında karşılaştırılabilir bir ölçekte değil (her kural kendi eşiğine normalize ediyor); skoru şiddete çevirmek uydurma bir hassasiyet olurdu |
| 2026-08-28 | `api/requirements.txt` ayrı | Kök dosya torch + ultralytics + onnxruntime-gpu içeriyor; API imajının hiçbirine ihtiyacı yok. İkinci bir dosya 2 GB'lık gereksiz imajdan ucuz |
| 2026-09-09 | WS yayını yoklama değil olay güdümlü | 5 ms yoklama iki bağlantıda saniyede 400 uyanma demekti; CPU'su dolu görü döngüsüyle GIL yarışı teslimi 1 FPS'e düşürdü — daha sık yoklamak daha az kare teslim ediyordu |
| 2026-09-09 | Kalp atışı ucu ad **veya** id kabul eder | vision/ kamerayı adıyla tanır; int bekleyen uç her atımda 422 döndü ve cameras.status hiç güncellenmedi |
| 2026-09-09 | Bildirim tetiği `consumer.py`'de, kuyruk + tek worker thread | Olay kimliği ve kanıt yolu yalnız orada birlikte var; gönderim inline olsaydı 3–8 sn'lik LLM+Telegram turu offset commit'i ve arkadaki olayların yazımını geciktirirdi (ölçüldü: `enqueue` 2.90 µs) |
| 2026-09-09 | Eylem ifadesi kodda (`action_phrase`), üslup LLM'de | v1'de model, bölgeyle ilgisi olmayan RUN olayına "yasaklı alana giriş yaptı" yazdı — güvenlik sisteminde gerçeğe aykırı ihbar kabul edilemez |
| 2026-09-09 | Gemini/Telegram için yeni bağımlılık yok, ham REST | `httpx` zaten kurulu; iki servisin de tek uç noktası var, SDK bakım yükü getirirdi |
| 2026-09-09 | Ayrı `TELEGRAM_ENABLED`/`LLM_ENABLED` bayrağı yok | Token boşsa kanal kapalıdır; v1'de bayrak ile token ayrı ayrı yanlış ayarlanabiliyordu |
| 2026-09-09 | `consumer` container'ına `TZ: Europe/Istanbul` | Rapordaki saat operatörün yerel saatidir; container UTC doğduğu için 3 saat geri yazıyordu |
| 2026-09-09 | Sayı biçimleme `_sayi()` ile, tür denetimiyle değil | Ham SQL `NUMERIC` sütununu `Decimal` döndürüyor; `isinstance(..., float)` bunu eleyip metne "bilinmiyor" yazdı — düzeltme çağıranda değil ortak yerde |
| 2026-09-09 | Uçtan uca gecikme ve alarm gecikmesi yalnız canlı kaynakta ölçülür | Dosya kaynağında ikisi de hattın hızını değil, 64 karelik ileri okumayı ve oturumun akış sonuyla kapanmasını ölçüyor |
| 2026-09-09 | Kanıt satırı eşleşse de yazılır | events tablosunda clip_truncated kolonu yok; satır atlanırsa klibin kırpıldığı bilgisi tamamen kaybolur |
| 2026-09-09 | `login.html`de "2FA Aktif" rozeti ve "Oturumu 8 saat açık tut" onay kutusu pasif bırakılmadı, silindi | Sistemde iki adımlı doğrulama yok; jeton süresi sunucuda `JWT_EXPIRE_MINUTES` ile sabitlenir, istemci değiştiremez. İkisi de gerçek olmayan bir vaat -- diğer bağlanmayan öğelerin (Parolamı Unuttum, NODE/WSS/FPS altbilgisi) aksine "arayüzde var ama pasif" bırakmak burada yanıltıcı olurdu |
| 2026-09-09 | Panel React'siz, derleme adımı yok | Şablon düz HTML + Tailwind CDN geldi; React'e taşımak 11 ekranı elle yeniden yazmak, yani "tasarıma dokunulmaz" kuralını fiilen ihlal etmek demekti. Node/bundler zinciri de projeye girmiyor. PLAN.md'deki Recharts maddesi düştü: analitik grafikleri şablonda zaten `div` genişlikleriyle çizili, veriden hesaplanan tek şey yüzde |
| 2026-09-09 | Panel API ile aynı origin'den, `StaticFiles` ile sunuluyor | Ayrı nginx konteyneri CORS, ikinci port ve ikinci yapılandırma demekti; tek `app.mount` ile jeton, kanıt dosyaları ve göreli yollar tek origin'de kalıyor. Mount router'lardan sonra: `/` tüm yolları yakalar |
| 2026-09-09 | Şablon `frontend/`e elle değil `build_frontend.py` ile kopyalanıyor | Kullanıcı şablonu güncellerse 12 dosyadaki href ve betik satırı düzeltmesi elle tekrarlanamaz; betik idempotent ve testte "tasarım korunuyor" kanıtının kaynağı |
| 2026-09-09 | `require_admin` yazılmadı, mevcut `require_role("admin")` kullanıldı | `api/auth.py`'de Aşama 5'ten beri duruyordu, `cameras.py`/`zones.py`/`settings.py` zaten kullanıyor; ikinci bir rol bağımlılığı kod tekrarı olurdu |
| 2026-09-09 | `GET /api/health/cameras` kamera başına ayrı Mongo sorgusu değil, tek `aggregate` | N kamera için N round-trip yerine `$group` ile en son belgeyi tek seferde çeker; ham `camera_id` -> gerçek kamera id eşlemesi sonra `resolve_camera_id` ile bellek içinde yapılır, ikinci bir ad-veya-id sorgusu yazılmaz |
| 2026-09-09 | `/api/analytics/quality`'de recall/f1 hesaplanmadı, `null` + `note` | Ground-truth etiketi çalışma zamanında yok, kaçırılan olay bilinmiyor; uydurma bir sayı üretmek yerine gerçek sinyal (`events.status` geri bildirimi) üzerinden yalnız precision döner |
| 2026-09-09 | Kullanıcı `DELETE` gerçek silme değil `is_active=false` | `audit_log.user_id` ve `zones.created_by` FK'leri var; kullanıcı gerçekten silinirse "kim yaptı" denetim izi kopar |
| 2026-09-09 | Admin yetkisi kaybı tek yerde denetlenir (`_yetki_kaybi`) | Guard önce yalnız `is_active=false` yolunu koruyordu; `role: "viewer"` aynı sonucu doğuruyor ve sistemi admin'siz bırakıyordu. İki yolu ayrı ayrı korumak yerine "yetkiyi kaldıran değişiklik" tek predikatta toplandı |
| 2026-09-09 | Tekrar eden kullanıcı adı 409, 500 değil | `users.username` UNIQUE; yakalanmayan `IntegrityError` panele 500 olarak döner ve formda gösterilecek bir mesaj kalmaz |
| 2026-09-09 | Şablonun uzak görselleri yerel yer tutucuyla değiştirildi | `lh3.googleusercontent.com` bağlantıları 404 dönüyor; ayrıca "kamera görüntüsü" diye konmuş stok fotoğraflar sahte veridir. Tek `re.sub` ile `build_frontend.py`'de değiştiriliyor, yerleşim ve sınıflar aynı kalıyor |
| 2026-09-09 | Ölçülen Değerler tablosu sabit satır değil, telemetriden üretiliyor | Metrik kümesi kural tipine göre değişiyor (RUN'da hız, FALL'da eğim); sabit dört satır yazmak, olmayan metriği uydurmak ya da olanı gizlemek demekti. Eşleşen eşik yoksa durum `—` |
| 2026-09-09 | Sayfa betiği `build_frontend.py`'de dosya varsa eklenir | Sayfa listesini ikinci bir yerde tutmak, betiği ekleyip listeye yazmayı unutmak demekti; olmayan betiğe `<script>` koymak da konsola 404 dökerdi |
| 2026-09-09 | 8.3 iki paralel iş paketine bölündü, paylaşımlı dosyalar tek elde | `app.js`, `build_frontend.py` ve ortak test iki paketin de yolundaydı; birleştirme tek elde toplandı |
| 2026-09-10 | Canlı kutu "AKTİF"i `onopen`'da değil ilk karede yazar | `ws_server` jeton ve yol geçerliyse yayıncısı olmayan bir `camera_id`'ye de bağlanmayı kabul ediyor; açılışa güvenmek hiç yayın olmayan kamerayı yeşil gösteriyordu |
| 2026-09-10 | Görünürlük/gizlenme yönetimi `element.hidden` ile değil `style.display` ile | Tailwind'in `.flex` sınıfı tarayıcının `[hidden]` kuralını eziyor; `hidden = true` sessizce hiçbir şey yapmıyordu |
| 2026-09-10 | Ortak canlı akış mantığı `live.js`'te, sayfa betiklerinde değil | Canlı izleme ve kamera detay aynı WS + çizim işini yapıyor; iki kopya, ölçek dönüşümü gibi ince bir hatayı iki kez düzeltmek demekti. `build_frontend.py` canlı sayfalara ikinci betiği ekliyor |
| 2026-09-10 | Panel FPS'i hedefin altına düşerse önce görü döngüsüne bakılır | Ölçüm: tarayıcı FPS'i sunucu döngü FPS'iyle örtüşüyor (25.2 / 25.1). İstemci kare atlamıyor; düşüş her seferinde hattın kendisinde (CPU rekabeti) |
| 2026-09-10 | Postgres `connect_timeout=3`, Mongo `serverSelectionTimeoutMS=3000` | Docker kapalıyken test paketi 8 sn yerine 5+ dakika sürüyordu: her canlı-veritabanı testi işletim sisteminin varsayılan bağlantı zaman aşımını bekliyordu. Sağlık ucu da aynı sebeple asılı kalırdı |
| 2026-11-23 | Spark pencereleme saati adayın **işlendiği anın duvar saati**, sahne zamanı değil (2026-08-27 kararının yerine) | Su işareti bütün kameralar için ortak; sahne zamanında yavaş akan dosya kamerası geride kalıp adayları "geç veri" diye atılıyordu (A2). Süre ölçütü (`min_sec`) yine sahne zamanı `ts` ile, kuralların anlamı değişmedi |
| 2026-11-23 | Kamera başına saniyede bir `_TICK` nabzı, işleme döngüsünden | Su işareti yalnız veriyle ilerliyor; sessiz sahnede düşme oturumu hiç kapanmıyordu (A1). Ayrı zamanlayıcı değil döngü: hat donarsa nabız da durur, oturum yanlışlıkla kapanmaz |
| 2026-11-23 | İç tipler çıkıştan **toplama sütunuyla** (`internal`) elenir | Yalnız `anomaly_type`'a bakan `where`'i Catalyst toplamanın ve `withWatermark`'ın altına iter; iç tipler su işaretine ulaşmaz ve düzeltme sessizce çalışmaz |
| 2026-11-23 | `spark.sql.shuffle.partitions` 200 → 2 | `local[2]`'de 200 görevlik yığın 4–5 sn sürüyordu; nabızla Spark ~%290 CPU yaktı, gecikme 15,2 sn oldu. 2 bölümle yığın < 1 sn, gecikme 7,58 sn |
| 2026-11-23 | Gelecek tarihli aday `withWatermark`'tan önce reddedilir (30 sn pay) | Tek bir ileri tarihli mesaj su işaretini sıçratıp sistemi susturabiliyordu. 30 sn = `_EOS` önü (15 sn) + saat kayması payı; ölçülen kap/konteyner kayması 0,32 sn |
| 2026-11-23 | Değerlendirme ayrı Spark servisi (`spark-eval`, `--profile eval`) ve ayrı konular | `spark_eval.py` su işaretini ~1,4 saat ileri itiyordu ve checkpoint kalıcı olduğu için canlı hattı susturuyordu (A3). Eşik API'si bu servise bağlanmadı: değerlendirme eşikleri ortam değişkeniyle verilir |
| 2026-11-23 | Postgres / Mongo / Kafka portları yalnız geri dönüşe: `127.0.0.1` **ve** `[::1]` | Kimliksiz Kafka ve veritabanları yerel ağa açıktı. Yalnız `127.0.0.1` yetmedi: Windows `localhost`'u önce `::1`'e çözüyor, her yeni bağlantı 2–3 sn bekledi (Kafka gidiş-dönüş 2906 → 734 ms) |
| 2026-11-23 | Gemini anahtarı `x-goog-api-key` başlığında | URL vekil sunucu ve erişim kayıtlarına düşer |
| 2026-11-23 | WebSocket istemci sayacı `(tür, kamera)` başına | Tek süreç çoklu kamerada bir kamerayı izleyen istemci bütün kameralara her karede JPEG kodlatıyordu |
| 2026-11-23 | Kamera kaynağı proje köküne göreli | Mutlak yol, proje taşınınca bütün dosya kameralarını açılmaz yaptı (13.1) |
| 2026-11-23 | Önbellek etiketi CRLF → LF normalleştirilmiş içerikten | Aynı içerik farklı satır sonuyla farklı etiket veriyor, test paketi her koşuda izlenen HTML'leri değiştiriyordu |
| 2026-11-24 | TCN penceresi 1,96 sn kalıyor; özgün hızdaki FIGHT gerilemesi (süzgeçli TP 6 → 2) kabul | Holdout FIGHT klipleri 1,2–2,9 sn, pencereden kısa: yapaylık. Canlıda bedeli ~0,3 sn. Holdout'a bakarak pencere seçmek sızıntı olurdu (13.3, B2) |

## Açık sorular

Her maddenin yanında kapatılacağı aşama (`docs/YOL_HARITASI.md`).

- **Kare hızı bağımlılığı** (→ 13.3): kural pencereleri, TCN girdisi ve
  izleyici tamponu kare sayısıyla tanımlı; canlı 5–10 FPS'te zaman ölçeği
  2,5–5 kat uzuyor. Çevrimdışı değerlendirme her kareyi işlediği için
  görmüyor (bkz. "Şu an neredeyiz")
- **Gerçek kamerada alarm gecikmesi** (→ 14): 13.1'de gerçek zamanlı
  akıtılan klipte 7,58 sn ölçüldü; kameranın önünde gerçek bir olayla hâlâ
  ölçülmedi (14'ün çekim oturumunda)
- **`zone_01`'in sahte RUN'ı** (→ 13.3): 35 vuruş, 1.80 sn, Spark'tan
  geçiyor. Süzgeç gürültüyü eler, kural hatasını düzeltmez — kök neden RUN
  kuralının kendisinde
- **`police_run` hiç aday üretmiyor** (→ 13.3, 17): 15 FPS, hız tepesi 1.77
  (eşik 1.80), adım medyanı 0.52. Düşük kare hızının adım kanıtını bastırıp
  bastırmadığı 13.3'ün FPS taramasında görülecek; derinlik yönündeki hız
  17'nin zemin kalibrasyonuyla. 13.1 yan gözlemi: aynı klip gerçek zamanlı
  döngüde (`--realtime --loop`) 41 aday üretti, hiçbiri olaya dönüşmedi —
  kaynağı (döngü sarımı mı, kare düşmesi mi) incelenmedi
- **Olay 1023 (RUN) çelişkisi** (→ 14): telemetride `norm_speed_max` 0.142,
  eşik 1.8 — panelde "EŞİK ALTINDA" görünen bir metrikle olay üretilmiş.
  Kuralın hangi kanıtla tetiklendiği (adım ritmi mi) telemetriden
  okunamıyor; tetikleyen kanıt telemetriye yazılmalı
- **Sabit kameralı, etiketli koşu klibi yok** (→ 14): iki etiketli koşu
  klibi de stok görüntü (birinde kamera koşucuyu takip ediyor, diğerinde
  kişi kameraya doğru koşuyor)
- **LOITERING duyarlılığı; FIGHT / LOITERING `min_sec`** (→ 14): geçerli
  olumlu oyalanma örneği yok (12.6); `min_sec` 0.5 / 2.0 ölçüme değil akıl
  yürütmeye dayanıyor
- **ReID kalabalık / kesişmeli sahnede ölçülmedi** (→ 15): pilot kliplerde
  `--no-reid` ID sayılarını değiştirmiyor; olay galerisi Aşama 11'de
  çalışmadı (F1 0.15)
- **CPU rekabeti** (→ 16): Docker yığını ayaktayken görü FPS'i 36.5'ten
  12–15'e düşüyor, profillenmedi. `--kafka` açıkken 36.5 → 31.8 kaybının
  librdkafka'nın arka plan iş parçacığından geldiği de varsayım
- **Denetim kaydı ve bildirim sekmelerinin filtre kutuları bağlı değil**
  (→ 13.7): uçlar filtreleri destekliyor, bağlanmayan yalnız arayüz
- **Tek tüketici süreci** (→ 18): 4 kamerada yetip yetmediği ölçülmedi;
  Kafka tarafı ölçeklenebilir (aynı `group.id` ile ikinci konteyner),
  veritabanı tarafı ölçülmeli

Kapanan sorular:

- ~~Sayfa betiklerinde kopyalanan yardımcılar~~ — `_fetchAuthedBlobUrl`,
  `ROLE_ADI`, `DECIDED_BY_ADI`, `CAMERA_STATUS_ADI`, `num()`,
  `FORBIDDEN_MSG` artık yalnız `frontend/js/app.js`'te (2026-11-23 denetimi)
- ~~`spark_min_sec` Spark'a ortam değişkeninden gidiyor~~ — Aşama 6 / 12.2:
  Spark açılışta `GET /api/settings` çağırıyor. Değer DAG'e açılışta
  gömülür; panelden değişiklik Spark yeniden başlayınca geçerli olur
  (bilinçli sınır)
- ~~ReID'in kare başına ~7 ms maliyeti çoklu kamerada~~ — Aşama 10.4: 4
  kamerada ReID kapalıyken kamera başına 11.7 → 15.2 FPS, pilot doğruluk
  değişmedi; varsayılan değiştirilmedi, bayrak olarak kaldı
- ~~Kadrajdan çıkıp giren kişiyi aynı kimliğe bağlama~~ — Aşama 11: olay
  galerisi ölçüldü, çalışmıyor (F1 0.15); 15'te ham kareden yeniden
  denenecek
- ~~Çoklu kamera toplu çıkarımı gerçek FPS'te~~ — Aşama 10.3: 4 kamera tek
  süreç, çıkarım kare başına 14.45 → 10.5 ms
- ~~Şablon ekranları API'yi karşılıyor mu~~ — Aşama 8.1–8.6: 11 ekran
  gerçek veriye bağlandı
- ~~FIGHT kuralının gerçek doğruluğu~~ — Aşama 9.5 / 11: holdout'ta FIGHT
  duyarlılığı 0.80 (15 klibin 12'si)
- ~~Bölge poligonu kameraya bağlı~~ — kapsam sınırı (12.6): bölge kuralları
  yalnız sabit kamerada anlamlı; hareketli kamera koruması 17'de
- ~~Host'tan API'ye ~600 ms sabit taban~~ — **Aşama 8.1'de ölçüldü, taban
  yok.** 25 istekle host'tan: `/health` medyan 13.8 ms, `/api/cameras` 13.8,
  `/api/events?limit=20` 11.1, `/api/analytics/summary` 18.0; konteyner
  içinden `/health` 1.8 ms. Port yönlendirmesinin maliyeti ~12 ms
- 4 GB VRAM'de `yolov8s-pose` sığıyor mu — evet, 49 MiB tepe kullanım
- Gerçek döngüde FPS ne olacak — YOLO26 + ReID ile 27–37 FPS (4K olmayan
  kliplerde), webcam 24.3
- BoT-SORT ReID çalışıyor mu — evet; YOLO26'da `yolo26s-reid.onnx` üzerinden
- YOLO26'nın daha az kişi bulması gerçek kaçırma mı — hayır, güven eşiği
  kalibrasyonuydu; `conf=0.25` v8 davranışını yakalıyor
- Host'ta çalışan `vision/` `localhost:9092`'ye yazabiliyor mu — evet,
  `scripts/check_kafka.py` gidiş-dönüş 781 ms
- Spark tek kare gürültüsünü eliyor mu — evet, ama tek eşikle değil: vuruş
  sayısı + tipe göre süre gerekti (`docs/DURUM_ARSIV.md`, Aşama 4)

---

## Test videoları

`data/pilot/` altında (v1 projesinden kopyalandı, `.gitignore`'da):
`normal_01`, `run_01`, `fall_01`, `zone_01`, `mixed_01`, `police_run`.

Kaynak:
`C:\Users\pc\OneDrive\Masaüstü\projeler\VideoAnomalySystem\datasets\pilot\videos`

Yeniden kopyalamak için:

```bash
mkdir -p data/pilot
cp "C:/Users/pc/OneDrive/Masaüstü/projeler/VideoAnomalySystem/datasets/pilot/videos/"*.mp4 data/pilot/
```
