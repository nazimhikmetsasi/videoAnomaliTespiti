# Aşama 13 — Bütünsel İnceleme ve Geliştirme Planı (2026-11-10)

Projenin tamamı baştan okundu: `api/`, `vision/`, `stream/`, `models/`,
`frontend/js/`, `infra/`, `docker-compose.yml`, ölçüm betikleri. Hafızadan ya
da önceki belgelerden değil koddan. Kuşkulu her iddia ya **çalıştırılarak
ölçüldü** ya da açıkça "koddan çıkarım" diye işaretlendi.

Her bulgunun yanında kanıt düzeyi yazılıdır:

- **ölçüldü** — deney veya gerçek veriyle doğrulandı
- **koddan** — kod okunarak kesinleşti, çalıştırılmadı
- **hipotez** — düzeltmeden sonra ölçülecek

---

## A. Kritik — olaylar sessizce kayboluyor

Bu bölümdeki iki hata sistemin **asıl işini** bozuyor ve bugüne kadarki hiçbir
test bunları göremezdi: bütün ölçümler döngüdeki kliplerle yapıldı, sürekli
aday geldi, Spark'ın su işareti hep ilerledi.

### A1. Sessiz sahnede tek düşme hiç alarm üretmiyor — **ölçüldü**

Spark Structured Streaming'de su işareti (watermark) **yalnızca yeni veri
gelince** ilerler. Oturum penceresi, su işareti oturum sonunu (son aday + 3 sn)
geçince yazılır. Düşmeden sonra hiçbir kameradan aday gelmezse olay hiç
yazılmaz.

Deney (veritabanı kirletilmeden — kamera adı veritabanında yok, Spark'ın
çıktısı doğrudan `anomaly-events` konusundan okundu):

```
[0,0 sn]  3 FALL adayı basıldı, sonra sessizlik
          45 sn boyunca olay GELMEDİ
[45,5 sn] tek bir ilgisiz aday basıldı
          olay bundan 5,3 sn SONRA geldi (düşmeden 50,8 sn sonra)
```

**Sonuç:** tek kameralı bir evde düşüp hareketsiz kalan biri için alarm
**hiç** çalmaz. Bu, sistemin birinci kullanım senaryosudur.

`vision/publish.py` bu sorunu **dosya kaynağı için** biliyor ve çözmüş: akış
bittiğinde `_EOS` işaretçisi basıyor. Ama `_EOS` yalnızca `close()` sırasında
gidiyor. Canlı kamerada (asıl dağıtım) su işaretini ilerleten periyodik bir
mesaj yok.

### A2. Çoklu kamerada olaylar kayboluyor — **ölçüldü**

Dosya kaynağında olay zamanı `T0 + kare/FPS`, yani **sahne zamanıdır**.
Kameralar paylaşılan GPU'da eşit hızda işlenir; klibin kendi FPS'i düşük
olanın sahne saati **daha hızlı** akar. Spark'ın su işareti bütün kameralar
için **ortaktır** (görülen en büyük olay zamanı − 2 sn). Saati geride kalan
kameranın adayları su işaretinin altına düşer ve Spark onları **geç veri
diye atar**.

**Gerçek veri — Aşama 10.5'in 8 saatlik koşusu, saat başına olay:**

| saat | fall_01 (29,97 FPS) | run_01 (30 FPS) | zone_01 (25 FPS) | webcam_01 |
|---|---|---|---|---|
| 15:00 | 10 | 15 | 9 | 0 |
| 16:00 | 2 | 3 | 61 | 0 |
| 17:00–23:00 | **0** | **0** | ~60 / saat | 0 |

İki kamera ilk ~20 dakikadan sonra **7 saat boyunca tek olay üretmedi**.
Görüntü hatları çalışıyordu; olaylar Spark'ta kayboldu.

**Kontrollü deney** — üç dosya kamerası birlikte, 4 dakika, Kafka'nın iki
konusu birden dinlendi:

| kamera | kendi FPS'i | aday | su işaretinin altında | Spark olayı | geride kalma |
|---|---|---|---|---|---|
| zone_01 | 25 | 1285 | **0** | 8 | 0 sn (saati o sürüklüyor) |
| fall_01 | 29,97 | 20 | **16 (%80)** | 7 | 5 → 19,5 sn |
| run_01 | 30 | 2175 | **1636 (%75)** | 11 | 6 → 16 sn |

Sahne saatleri tahmin edilen hızda ayrışıyor (11,1/25 = 0,44 ile
11,1/30 = 0,37) ve geride kalma **doğrusal büyüyor**. 4 dakikada %75–80
kayıp; saatler içinde %100.

**Tez etkisi:** `docs/TEZ.md` §3.5'teki "8 saat, 4 kamera, kesintisiz,
506 olay" sonucunun görüntü hattı kısmı doğru (FPS, bellek, kararlılık),
ama olay üretimi kısmı **yanlış**: olayların neredeyse tamamı tek kameradan.
Düzeltmeden sonra koşu tekrarlanmalı ve tablo düzeltilmeli.

### A3. Aynı mekanizmanın iki yüzü daha — **koddan**

Su işareti Spark'ın checkpoint'inde **kalıcıdır**. Dolayısıyla:

- **Değerlendirme canlı hattı zehirliyor.** `eval/spark_eval.py` 6 klibi
  `şimdi + i × 1000 sn` dilimlerine basar ve su işaretini yaklaşık **1,4
  saat ileriye** iter. Kodun kendi yorumu bunu biliyor ve sonraki
  değerlendirme koşusu için çözmüş, ama aynı Spark sorgusunu paylaşan canlı
  hat için çözmemiş. Bir değerlendirmeden sonra canlı kameralar ~1,4 saat
  susar. Çalıştırılarak doğrulanmadı — doğrulamak canlı Spark'ı saatlerce
  susturur.
- **Ağdan tek mesajla susturma.** Kafka `9092` portu düz metin ve kimliksiz
  olarak bütün arayüzlere açık (`docker-compose.yml`). Yerel ağdaki herhangi
  biri olay zamanı ileri tarihli **tek bir** aday basarsa, su işareti oraya
  sıçrar ve sonraki **bütün** gerçek adaylar geç sayılır. Sistem, checkpoint
  sıfırlanana kadar sessizdir.

### A4. Ölçülen 13,99 sn gecikme büyük olasılıkla şişkin — **hipotez**

Aşama 12.4'te gecikme, döngüdeki `fall_01` klibiyle (7,9 sn) ölçüldü. A1'e
göre her düşme olayı, su işaretini ilerletecek **bir sonraki döngünün**
adaylarını bekledi. 7,9 sn döngü + 5 sn tasarım tabanı + ~1 sn ≈ 14 sn —
ölçülen 13,99 ile örtüşüyor. Düzeltmeden sonra gerçek gecikmenin ~5–6 sn'ye
inmesi beklenir; **ölçülecek, iddia edilmeyecek.**

### A5. Uzun koşu testi neden göremedi — **koddan**

`scripts/soak_test.py` yalnızca **toplam** olay sayısını izliyor. Toplam,
zone_01 sayesinde düzgün arttı. Kamera başına olay oranı izlenmiyordu.

### Düzeltme tasarımı (A1–A5 birlikte)

Kök neden tek: **Spark'ın pencereleme saati.** Kamera başına sahne saatleri
ortak bir su işaretiyle birleştirilemez ve su işareti yalnız anomali olunca
ilerliyor.

1. **Tek ortak saat.** Pencereleme saati (`event_time`) her kaynak için
   adayın **işlendiği an** (`time.time()`) olur. Aynı süreçteki bütün
   kameralar aynı saati paylaşır; hiçbiri geride kalamaz. `Candidate`'e
   `event_time` alanı eklenir ve **yalnız** `CameraPipeline` doldurur; boşsa
   eski davranış (`epoch_base + ts`) — böylece `eval/spark_eval.py` aynen
   çalışır.
   - **Süreler değişmez.** Spark'taki `min_sec` süzgeci `ts` (sahne zamanı)
     alanından hesaplanır, `event_time`'dan değil. Kural anlamı korunur.
   - **Kanıt eşleşmesi aynı saate geçer.** `vision/evidence.py`'nin POST
     ettiği başlangıç zamanı adayların `event_time`'ından alınır. Halka
     tampondan klip seçimi `frame.ts` ile kalır (doğru saat odur).
2. **Su işareti nabzı.** Her kamera, işlenen karelerden saniyede bir
   `_TICK` adayı basar. Sessiz sahnede de su işareti ilerler. Nabız
   **işleme döngüsünden** çıkar, ayrı bir zamanlayıcıdan değil: hat
   donarsa nabız da durur ve su işareti yanlışlıkla oturum kapatmaz.
3. **Spark'ta açık süzgeç.** Toplamadan sonra `_` ile başlayan iç tipler
   (`_TICK`, `_EOS`) açıkça elenir. Bugün `_EOS` yalnızca `hits < 2`
   yüzünden düşüyor; biri panelden `spark_min_hits = 1` yaparsa iç
   işaretçiler olay olarak yazılır ve kırmızı alarm olarak panele düşerdi.
4. **Gelecekten gelen veri reddi.** Spark, olay zamanı işlem saatinden
   ileride olan adayları su işaretine ulaşmadan eler. Tek bir bozuk ya da
   kötü niyetli mesaj sistemi susturamaz.
5. **Değerlendirme yalıtımı.** `spark_eval.py` ayrı konu ve ayrı checkpoint
   kullanır; canlı su işaretine dokunamaz.
6. **Kamera başına izleme.** `soak_test.py` kamera başına olay oranını
   kaydeder ve aday üreten ama olay üretmeyen kamerayı işaretler.

**Doğrulama:** iki deney betiği `eval/stream_probe.py` olarak kalıcılaşır
(tek düşme + çoklu kamera kayması) ve düzeltmeden sonra **aynı deneyler**
koşar. Beklenen: tek düşme ~5–6 sn içinde yayılır; üç kamerada geç aday
sıfıra iner. Ardından gecikme ve kısa bir çoklu kamera koşusu yeniden
ölçülür, `docs/TEZ.md` §3.5 ve §3.7 düzeltilir.

---

## B. Güvenlik

| # | bulgu | kanıt | ağırlık |
|---|---|---|---|
| B1 | **Kalıcı XSS:** `frontend/js/olaylar.js:105` kamera adını ve konumunu kaçışlamadan `innerHTML`'e basıyor. `app.js`'teki `_escXml` yardımcısı diğer ekranlarda kullanılıyor, burada unutulmuş. Jeton `localStorage`'da; kamera adına konan betik olay listesini açan her operatörün oturumunu çalabilir | koddan | orta (yönetici yetkisi gerekir) |
| B2 | PostgreSQL, MongoDB ve Kafka bütün ağ arayüzlerine açık. Kafka kimliksiz — A3'teki susturma saldırısının kapısı | koddan | orta |
| B3 | Giriş ucunda deneme sınırı yok; parola kaba kuvvete açık | koddan | düşük–orta |
| B4 | Gemini anahtarı URL sorgu parametresinde (`?key=`); Google'ın önerdiği başlık (`x-goog-api-key`) değil. Vekil sunucu ve erişim kayıtlarına düşebilir | koddan | düşük |
| B5 | WebSocket jetonları veritabanına bakmadan yerel doğrulanıyor; pasifleştirilen kullanıcı jeton süresi (12 saat) dolana kadar canlı görüntüyü izlemeye devam edebilir | koddan | düşük |

---

## C. Performans

| # | bulgu | kanıt | etki |
|---|---|---|---|
| C1 | **Sistem sağlığı sorgusu** her çağrıda bütün `camera_health` koleksiyonunu tarıyor. Sıralama dizinle eşleşmediği için MongoDB `DISTINCT_SCAN` kullanamıyor. Bir haftalık veride: **483.840 belge, 445 ms** → düzeltmeyle **4 belge, 1 ms**. Tek satır | ölçüldü | 445× |
| C2 | Canlı görüntünün JPEG/meta kodlaması **küresel** istemci sayısına bağlı. Aşama 10'da tek süreç çoklu kameraya geçildi ama sayaç kamera başına yapılmadı: bir kamerayı izleyen tek operatör **dört kameranın hepsine** her karede JPEG kodlatıyor | koddan | kamera başına birkaç ms/kare |
| C3 | `GET /api/evidence` sayfalamasız; bütün kanıt satırlarını döndürüyor (saatte ~60 satır büyüyor) | koddan | zamanla büyür |

---

## D. Doğruluk — küçük

| # | bulgu | kanıt |
|---|---|---|
| D1 | `Zone.active_at(ts)` saati `datetime.fromtimestamp(ts)` ile hesaplıyor. Dosya kaynağında `ts` sahne saniyesi (ör. 12,3) → 1970'in ilk saniyeleri. Dosya kameralarında "kısıtlı saat" bölgeleri hep gece ~02:00'ye göre değerlendiriliyor. A'daki ortak saat düzeltmesi bunu da çözer | koddan |

---

## E. Yeni özellikler

Okurken görülen, değer/emek oranı yüksek eklemeler:

**E1. Düşme sonrası hareketsizlik — "kalkamadı" doğrulaması.** Bugün FALL
anlık bir darbe olarak tetikleniyor. Düşmeden sonra kişi N saniye yatay ve
hareketsiz kalırsa olay **kritik ve doğrulanmış** olur; hızla kalkarsa önem
düşer. İki kazanç: yaşlı bakımındaki asıl tehlikeyi (kalkamamak) yakalar ve
sandalyeye hızlı oturma gibi yanlış pozitifleri ayırır. Mevcut öznitelikler
(`body_tilt`, `norm_speed`) yeterli, yeni model gerekmez. Tez için güçlü
bir bölüm.

**E2. Yön ihlali (WRONG_DIRECTION) ve bölgede koşma (RUN_ZONE).** İkisi de
**her yerde hazırlanmış, yalnızca kural eksik:** veritabanı şeması
(`zone_type='direction'`, `direction_vector`), önem tablosu, LLM eylem
cümlesi, panel etiketi, şema doğrulaması. `bolgeler.js` yön bölgesi çizimini
bilerek kapatmış çünkü onu besleyen kural yok. Sınıf sayısı fiilen 5'ten
7'ye çıkar.

**E3. Panelde alarm sesi ve doğrudan onay.** Kırmızı alarm bugün sessiz;
operatör olayı onaylamak için Olaylar ekranına gitmek zorunda. Alarm
penceresinden tek tıkla "Görüldü / Yanlış Alarm".

**E4. Kamera başına uçtan uca nabız.** Sistem sağlığı ekranı bugün FPS ve
GPU gösteriyor. Kamera başına "aday üretiyor ama olay üretmiyor"
göstergesi eklenirse A2 gibi sessiz kayıplar panelde görünür.

**E5. Olay dışa aktarma (CSV).** Filtrelenmiş olay listesini indirmek;
hem operasyon hem tez tabloları için.

---

## F. Sıralama

| aşama | içerik | neden bu sırada |
|---|---|---|
| **13.1** | A — akış doğruluğu: ortak saat, nabız, süzgeç, gelecek reddi, değerlendirme yalıtımı, kamera başına izleme; deneylerle doğrulama; gecikme ve çoklu kamera yeniden ölçümü; TEZ düzeltmesi | sessiz veri kaybı; tezdeki iki sonucu etkiliyor |
| **13.2** | Hızlı düzeltmeler: B1, B2, B4, C1, C2, C3 | her biri küçük ve bağımsız |
| **13.3** | E1 — düşme sonrası hareketsizlik | en yüksek alan değeri |
| **13.4** | E2 — yön ihlali ve bölgede koşma | altyapı hazır |
| **13.5** | E3 + E4 — panel alarm sesi/onay ve kamera nabzı | operatör deneyimi |
| sonra | B3 giriş sınırı, B5, E5 dışa aktarma, alan farkı için pilot alan verisi | |

Her aşamanın sonunda durulur, durum `docs/DURUM.md`'ye yazılır, commit
mesajı verilir.
