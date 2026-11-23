# Yol Haritası — Aşama 13.0–19 (2026-11-23)

Kalan işin **tek sıra kaynağı** bu dosyadır. 13.1–13.2'nin bulguları, kanıt
düzeyleri ve düzeltme tasarımı `docs/ASAMA13_PLAN.md`'dedir; oradaki §F
sıralama tablosunun yerini bu dosya alır (numaralar aşağıdaki gibi
yeniden düzenlendi).

**Çalışma kuralı:** her aşama kendi plan dosyasıyla başlar (dosya listesi,
imzalar, kabul ölçütü), uygulanır, ham sayılarla doğrulanır,
`docs/DURUM.md` güncellenir ve durulur. Commit aşama sonunda, aşağıdaki
tek satırlık mesajla atılır. Eşikler test kliplerine uydurulmaz; kötü sayı
saklanmaz.

| aşama | içerik | bağımlılık |
|---|---|---|
| 13.0 | hazırlık: durum arşivi, belge düzeni | — |
| 13.1 | akış doğruluğu — **KRİTİK** | 13.0 |
| 13.2 | hızlı güvenlik / performans düzeltmeleri | 13.0 |
| 13.3 | zaman tabanlı pencereleme — **YENİ** | 13.1 |
| 13.4 | düşme sonrası hareketsizlik ("kalkamadı") | 13.3 |
| 13.5 | yön ihlali ve bölgede koşma | 13.3 |
| 13.6 | panel: alarm sesi / tek tık onay, kamera nabzı | 13.1 |
| 13.7 | giriş deneme sınırı, WS jeton iptali, CSV | — |
| 14 | saha çekim oturumu + TCN ince ayarı | 13.3–13.5 |
| 14.5 | Gemini ile olay doğrulaması — **YENİ** | 14 |
| 15 | yüz tanıma (Faz 2) + ReID yeniden denemesi | 14 |
| 16 | hız: CPU rekabeti, TensorRT FP16, 4K donanımla çözme | 13.3 |
| 17 | kamera geometrisi: hareketli kamera koruması, zemin kalibrasyonu | 14 |
| 18 | 24 saatlik koşu | 13–17 |
| 19 | tez | 18 |

Gerekçeli sıra değişikliği: **13.3, 14'ten önce gelir.** Kurallar, TCN
penceresi ve izleyici tamponu kare sayısıyla tanımlı; canlı kamera 5–10
FPS'te çalışırken aynı 50 karelik pencere 2 sn yerine 5–10 sn kapsıyor.
14'te toplanacak etiketler ve TCN ince ayarı pencere tanımına bağlı;
önce pencere zamana bağlanmalı.

---

## 13.0 — Hazırlık ve belge düzeni

- `docs/DURUM.md` (~3300 satır) ikiye ayrılır: `docs/DURUM.md` yalnız
  "şu an / sıradaki / sistemi açmak / açık sorular / karar günlüğü";
  aşama sonuçları **aynen** `docs/DURUM_ARSIV.md`'ye taşınır.
- Plan belgelerinin ve kod yorumlarının dili sadeleştirilir: iş bölümüne
  dair ifadeler nötr dile çevrilir; anlam ve ölçümler değişmez.
- `docs/ASAMA13_PLAN.md` §F, bu dosyaya işaret eden notla değiştirilir.
- DURUM.md'deki "Açık sorular" ayıklanır: kapananlar "Kapanan sorular"a,
  açık kalanlara ilgili aşama numarası.

**Kabul:** DURUM.md tek okumada okunuyor; arşiv taşınan bloğun birebir
kopyası (satır satır denetim); test paketi yeşil.

**Commit:** `docs: asama 13.0 - durum arsivi ve belge duzeni`

## 13.1 — Akış doğruluğu (KRİTİK)

`ASAMA13_PLAN.md` bölüm A:

- ortak pencereleme saati: `Candidate.event_time` = işlenme anı; `ts`
  sahne zamanı olarak kalır, `min_sec` süzgeci `ts`'ten hesaplanır
- kamera başına saniyede bir `_TICK` (işleme döngüsünden)
- Spark: `_` ile başlayan iç tiplerin açık süzgeci, gelecek tarihli adayın
  reddi
- `eval/spark_eval.py` ayrı konu ve ayrı checkpoint
- `scripts/soak_test.py` kamera başına olay oranı, olay üretmeyen kamerayı
  işaretler
- `vision/evidence.py` eşleşmesi aynı saate geçer

**Kabul:**
- `eval/stream_probe.py tek-dusme` çıkış kodu 0, olay ~5–6 sn içinde
- `saat-kaymasi`: su işaretinin altında kalan aday 0
- kısa çoklu kamera koşusunda her kamera olay üretiyor
- gecikme yeniden ölçüldü; `docs/TEZ.md` §3.5 / §3.7 uyarıları gerçek
  sayılarla değiştirildi

**Commit:** `fix: asama 13.1 - ortak saat, su isareti nabzi, spark suzgeci ve degerlendirme yalitimi`

## 13.2 — Hızlı düzeltmeler

- B1 XSS: `frontend/js/olaylar.js` kamera adı/konumu kaçışlanır
- B2 Postgres / Mongo / Kafka portları `127.0.0.1`'e bağlanır
- B4 Gemini anahtarı URL'den `x-goog-api-key` başlığına
- C1 sağlık sorgusu dizine uygun sıralama (ölçülen 445 → 1 ms)
- C2 JPEG / meta kodlaması kamera başına istemci sayısına bağlanır
- C3 `GET /api/evidence` sayfalama
- `scripts/seed_pilot.py` kamera kaynağını mutlak yol yazıyor; proje
  taşınınca dosya kameraları açılmadı (13.1'de görüldü, veritabanı elle
  düzeltildi). Kaynak proje köküne göreli yazılmalı
- `scripts/build_frontend.py` önbellek etiketi (`?v=`) satır sonundan
  bağımsız hesaplanır; testler izlenen dosyaları değiştirmez

**Kabul:** her madde için bir regresyon testi; C1 süre ölçümü; test paketi
koştuktan sonra `git status` temiz.

**Commit:** `fix: asama 13.2 - xss, port baglama, api anahtari basligi, saglik sorgusu, jpeg kapisi, kanit sayfalama`

## 13.3 — Zaman tabanlı pencereleme (YENİ)

Uygulama planı: `docs/ASAMA13_3_PLAN.md`.

**Önce ölçüm (değişiklikten önce):** çevrimdışı değerlendirme kümesi 25 /
10 / 5 FPS'e alt örneklenir (düzenli ve düzensiz kare kaybıyla); kural
ve hibrit F1'in FPS'e karşı eğrisi çıkarılır. Bu, sorunun büyüklüğünün
kanıtıdır.

Değişiklik:
- kural sabitleri saniyeye çevrilir (`fall.py` HOLD / VY_LOOKBACK,
  `run.py` LOOKBACK / GAIT_LOOKBACK, `zone.py` HOLD, `features.py`
  velocity_lookback / STALE, `loiter.py` STALE); değerler bugünkü 25
  FPS karşılıklarından türetilir, kliplere göre seçilmez
- TCN girdisi: izin anahtar noktaları zaman damgasına göre sabit hızlı
  ızgaraya (25 Hz, 2 sn) güven bilinçli doğrusal enterpolasyonla yeniden
  örneklenir; eğitimde hız (0,5x–2x) ve rastgele kare düşürme artırımı;
  model yeniden eğitilir
- izleyici `track_buffer` süreden ve ölçülen FPS'ten hesaplanır
  (Ultralytics 8.4 tamponu kare sayısıyla tutuyor)

**Kabul:** FPS'e karşı F1 eğrisi öncesi / sonrası aynı tabloda; 25
FPS'teki değerler gerilemiyor; 10 ve 5 FPS'teki düşüş raporlanır
(küçülmesi beklenir, hedef sayı önceden konmaz).

**Commit:** `feat: asama 13.3 - zaman tabanli pencereleme ve fps bagimsiz model girdisi`

## 13.4 — Düşme sonrası hareketsizlik (E1)

FALL adayından sonra kişi N sn yatay ve hareketsiz kalırsa olay **kritik
ve doğrulanmış**; hızla kalkarsa önem düşer. Süreler saniye cinsinden; N
kayıtlardan önce, gerekçesiyle seçilir (literatür örneği: >3 sn yatay +
>2 sn düşük hareket). İsteğe bağlı: yatak / koltuk "muaf bölge".

**Kabul:** birim testleri; saha doğrulaması 14'teki "düşüp kalkamama" ve
"düşüp hızla kalkma" kayıtlarında.

**Commit:** `feat: asama 13.4 - dusme sonrasi hareketsizlik dogrulamasi`

## 13.5 — Yön ihlali ve bölgede koşma (E2)

`WRONG_DIRECTION` ve `RUN_ZONE` kuralları (şema, önem tablosu, LLM eylem
cümlesi ve panel etiketi hazır); panelde yön bölgesi çizimi açılır.

**Kabul:** birim testleri; saha doğrulaması 14'teki yön ihlali kaydında.

**Commit:** `feat: asama 13.5 - yon ihlali ve bolgede kosma kurallari`

## 13.6 — Operatör deneyimi (E3 + E4)

Kırmızı alarmda ses; alarm penceresinden "Görüldü / Yanlış Alarm";
sistem sağlığında kamera başına "aday var, olay yok" göstergesi.

**Kabul:** tarayıcıda uçtan uca; nabız göstergesi yapay bir kesintide
olay üretmeyen kamerayı işaretliyor.

**Commit:** `feat: asama 13.6 - alarm sesi, tek tik onay ve kamera nabzi`

## 13.7 — Kalan küçükler

B3 giriş deneme sınırı, B5 WS jetonunun veritabanından doğrulanması, E5
filtrelenmiş olayların CSV dışa aktarımı.

**Kabul:** her biri için test.

**Commit:** `feat: asama 13.7 - giris deneme siniri, ws jeton iptali, csv disa aktarma`

## 14 — Saha çekim oturumu + TCN ince ayarı

Sabit dizüstü kamerası ve telefonla, tek oturumda (kayıtlar `data/`
altında kalır, depoya yalnız etiket JSON'ları girer):

- oyalanma: aynı yerde / bölgede ≥ 30 sn (LOITERING duyarlılığı ilk kez)
- düşme + 15–30 sn yerde kalma; düşüp hızla kalkma (13.4)
- kadrajı keserek koşma; kameraya doğru / kameradan uzağa koşma (17)
- yön ihlali (13.5)
- yanlış pozitif sınaması: hızlı oturma, eğilme, yere bir şey bırakma
- karanlık oda / gece kaydı (CLAHE açık-kapalı karşılaştırması)
- isteğe bağlı, gönüllü iki kişiyle itişme canlandırması (FIGHT)
- yüz kaydı ve 1–6 m mesafe taraması (15)
- telefonu IP kameraya çeviren uygulama ile RTSP akışı (ilk gerçek RTSP
  denemesi, yeniden bağlanma dahil)

Sonra: etiketleme (`eval/annotations/`); TCN ince ayarı (klip bazında
ayrık eğitim / test, 13.3'teki artırımlar); FIGHT için iki kişi arası
öznitelikler (göreli mesafe, yaklaşma hızı, bilek / ayak bileği hızı);
`conf_sweep` ve pilot ablation yeniden.

**Kabul:** etiketli kayıt kümesi; ince ayar öncesi / sonrası tablo;
LOITERING duyarlılığı ilk kez ölçüldü; 13.4 ve 13.5 sahada doğrulandı.

**Commit:** `feat: asama 14 - saha kayit kumesi, etiketler ve tcn ince ayari`

## 14.5 — Gemini ile olay doğrulaması (YENİ)

Mevcut Gemini çağrısına yapılandırılmış (JSON) doğrulama alanı: evet /
hayır / belirsiz + güven. Yalnız "açıkça hayır"da olay iptal edilir,
"belirsiz"de önem düşer, her iptal kaydedilir. Model kimliği sabitlenir,
açılışta model listesi kontrol edilir. Kişi kırpımı ile tam kare
karşılaştırılır.

**Gizlilik:** ücretsiz katmanda gönderilen görüntüler sağlayıcı
tarafından ürün geliştirme için kullanılabilir. Yüz içeren kareler için
ücretli katman veya yüz bulanıklaştırma kararı bu aşamada verilir.

**Kabul:** 14 kayıtlarında iptal sonrası yanlış alarm azalması ve iptal
yüzünden kaçırılan gerçek olay sayısı **ayrı ayrı** raporlanır; kaçırma
varsa iptal kapalı kalır, yalnız önem düşürme kullanılır.

**Commit:** `feat: asama 14.5 - olay dogrulama katmani`

## 15 — Yüz tanıma (Faz 2) + ReID yeniden denemesi

- Yalnız olay anında: izin en net kareleri → **ham kareden** baş kırpımı →
  yüz tespiti ve hizalama → gömme → kayıtlı kişi galerisiyle eşleşme
- en küçük yüz boyu kapısı (~40–50 px) ve kalite süzgeci; altında
  "tanınmayan"
- iz başına gömme ortalaması; "bilinen / belirsiz / tanınmayan";
  belirsiz tanınmayan sayılır
- Kur/Bırak ile birlikte: Evde modunda bilinen kişi bildirim üretmez
- panelden kişi kaydı; yalnız gömme saklanır, kişi silinince gömmesi de
  silinir; yalnız rıza veren gönüllüler (KVKK: biyometrik veri)
- gövde ReID: ham kareden tam çözünürlüklü kırpım ve iz başına en iyi k
  kare ile yeniden ölçülür; bağlanması ölçüme bağlı

**Kabul:** mesafe taraması tablosu (yüz piksel boyu → doğru eşleşme);
eşik, yabancıyı "bilinen" sayma oranı düşük kalacak şekilde seçilir;
FPS'e ölçülebilir etkisi yok; ReID için aynı / farklı kişi kosinüs
dağılımı gerçek kamera kaydında.

**Commit:** `feat: asama 15 - yuz tanima, bilinen kisi ve kur/birak entegrasyonu`

## 16 — Hız

- **CPU rekabeti:** tam yığın açıkken görü FPS'i ~36'dan 12–15'e
  düşüyor, profillenmedi. Süreç başına CPU ölçümü; Docker servislerine
  CPU sınırı. Spark'ın yığın payı 13.1'de çözüldü (shuffle bölümü 2).
  13.1'de görülen: aynı ayarla ardışık koşularda FPS 36 → 11'e kaydı
  (makinenin kendi sürüklenmesi — ısınma veya arka plan yükü); ölçüm
  düzeni bunu ayırmalı
- **TensorRT FP16:** önce aynı klipte PyTorch FP16 ile karşılaştırma;
  kazanç yoksa vazgeçilir. INT8 kullanılmaz (pose modelinde doğruluk
  çöküyor)
- **4K donanımla çözme:** OpenCV donanım hızlandırma bayrağı → olmazsa
  ffmpeg NVDEC; kare bir kez küçültülür (hat ve tampon için tek `resize`)

**Kabul:** tam yığında canlı FPS öncesi / sonrası; TensorRT için ms/kare
ve FALL F1 farkı; `run_01` (4K) gerçek zamanlı akarken `pace_lag` < 0,5
sn ve 4K gecikmesi ölçüldü.

**Commit:** `perf: asama 16 - cpu rekabeti, tensorrt fp16 ve 4k donanimla cozme`

## 17 — Kamera geometrisi

- **Hareketli kamera koruması:** küçültülmüş karede ucuz genel hareket
  ölçümü; kamera dönerken / kayarken ZONE ve LOITERING askıya alınır
- **Zemin kalibrasyonu:** sabit kamerada panelden 4 nokta ile zemin
  homografisi; ayak noktasından m/s hız. Kameraya doğru / kameradan uzağa
  koşmanın kaçması bununla çözülür

**Kabul:** `zone_01`'in hareketli kısmında (28 sn sonrası) bölge adayı 0,
sabit kısımda davranış değişmiyor; 14'teki derinlik yönündeki koşu
kayıtlarında RUN duyarlılığı öncesi / sonrası.

**Commit:** `feat: asama 17 - hareketli kamera korumasi ve zemin kalibrasyonu`

## 18 — 24 saatlik koşu

Bitmiş sistemle; kamera başına olay oranı ve ana makineden port erişimi
izlenerek. Öncesinde: uyku kapalı, Windows Update yeniden başlatması
ertelenmiş, kanıt saklama tavanı açık.

**Kabul:** 24 sa kesintisiz; FPS sapması yok; RSS platoda; her kamera
olay üretiyor; disk tavanın altında.

**Commit:** `docs: asama 18 - 24 saatlik kosu`

## 19 — Tez

18'in sayılarıyla §3.5 ve §3.7; 12.4–18 sonuçları `docs/TEZ_METIN.md`'ye;
`docs/TEZ_UYUM.md` ile kapsam denetimi (Faz 2 artık yapıldı).

**Commit:** `docs: asama 19 - tez metni ve olcum tablolari`

---

## İsteğe bağlı — gelecek çalışma

- **Poz tabanlı denetimsiz anomali skoru** (STG-NF / STEP ailesi):
  yalnız ikincil sıralayıcı olarak, alarm kaynağı değil. 14'ün normal
  kayıtlarıyla tek deneme; kazanç kanıtı zayıf, tezde gelecek çalışma.

## Yapılamayacaklar — iddia edilmeyecek

- **PTZ ön ayarına göre bölge seçimi:** gerçek PTZ kamera yok (17 yalnız
  hareket anında bölge kurallarını susturur)
