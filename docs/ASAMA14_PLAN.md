# Aşama 14 — Saha kayıtları ve TCN ince ayarı: uygulama planı (2026-11-26)

Kapsam ve kabul: `docs/YOL_HARITASI.md` §14. Aşama iki bölümlüdür:

- **14A — hazırlık (kayıtlardan önce, şimdi):** çekim protokolü (§1),
  kayıt aracı (§2), saha değerlendirme aracı (§3). Bunlar olmadan çekim
  günü kaybolan bir kayıt ya da eksik bir not geri gelmez.
- **14B — kayıtlardan sonra:** etiketleme, ölçüm, TCN ince ayarı, FIGHT
  için iki kişi arası öznitelikler, `conf_sweep` ve pilot ablation (§4).
  Kayıtları kullanıcı çeker; 14B kayıtlar gelince başlar.

**Uygulayıcıya not:** hat koduna (`vision/`, `api/`, `stream/`) bu
bölümde dokunulmaz. Araçlar var olan hattı çağırır, kopyalamaz.

---

## 1. Çekim protokolü (14A)

### 1.1 Düzen

- **Kamera:** dizüstü kamerası sabit (yaklaşık 1–1,5 m yükseklikte, hafif
  aşağı bakan), oyuncuya 3–5 m. Kişi baştan ayağa ve yer kadrajda
  görünmeli: düşme ve "yerde kalma" zeminin görünmesini ister.
  İkinci açı için telefon (RTSP sahnesi, §1.2 son satır).
- **Işık:** gündüz ya da tavan ışığı; karanlık sahnesi ayrı.
- **Kadraj sabit:** kamera oturum boyunca oynamaz. Oynarsa bölge
  poligonları ve yön okları geçersizleşir (`zone_01`'in 28. saniye
  dersi).
- **Gönüllüler ve gizlilik:** kayıtta görünen herkesin onayı alınır.
  Kayıtlar `data/field/` altında kalır, depoya girmez (yalnız etiket
  JSON'ları girer). Yüz sahnesi (15 için) ayrıca onay ister: biyometrik
  veri, KVKK'da özel nitelikli.
- **Güvenlik:** düşme sahneleri yumuşak bir yüzeyde (minder / yatak
  şiltesi) ve kontrollü (dizlerin üstüne, sonra yana) canlandırılır.

### 1.2 Sahne listesi

Her sahne ayrı dosya. "Tekrar" farklı yön / hızla. Süreler, olaydan önce
ve sonra pay içerir.

| anahtar | sahne | tekrar | süre | ne ölçülür |
|---|---|---|---|---|
| `dusme_kalkamama` | yürür, düşer, **en az 35 sn** yerde kalır (hareketsiz ya da kalkmaya çabalayarak, en az bir tekrar çabalayarak) | 3 (yana, kameraya doğru, kameradan uzağa) | 60 sn | FALL; 13.4 `down`, karar süresi |
| `dusme_hizli_kalkma` | düşer, **10 sn içinde** kalkar, yürüyüp gider | 3 | 30 sn | FALL; 13.4 `recovered` |
| `dusme_yerde_oturma` | düşer, doğrulup yerde **oturur**, 35 sn kalır | 2 | 60 sn | 13.4 bilinen sınır: `unknown` beklenir |
| `sandalye_oturma` | sandalyeye hızlı oturur, 15 sn oturur | 3 | 25 sn | yanlış FALL; varsa 13.4 sonucu |
| `egilme` | yerden bir şey alır / bağcık bağlar | 3 | 20 sn | yanlış FALL |
| `yere_birakma` | çantayı yere bırakıp gider | 2 | 20 sn | yanlış FALL / LOITER |
| `oyalanma` | aynı yerde **en az 40 sn** durur, hafif salınır | 2 | 55 sn | LOITERING (ilk kez); `loiter_sec` 30 |
| `yon_ihlali` | kadrajı bir yönden öbürüne yürüyerek geçer; sonra ters yönde | 3 + 3 | 20 sn | 13.5 `WRONG_DIRECTION` (yön oku kayıttan sonra tanımlanır) |
| `kosu_yanal` | kadrajı keserek koşar | 2 | 15 sn | RUN |
| `kosu_derinlik` | kameraya doğru / uzağa koşar | 2 + 2 | 15 sn | RUN (17'nin derinlik sorunu) |
| `karanlik` | loş ışıkta yürür ve düşer (35 sn yerde) | 2 | 60 sn | CLAHE açık / kapalı |
| `itisme` | isteğe bağlı, iki gönüllü, hafif itişme | 2 | 25 sn | FIGHT |
| `normal` | sıradan hareket: yürüme, oturma, telefon | 1 | 120 sn | yanlış pozitif tabanı |
| `yuz` | kameraya 6 m'den 1 m'ye yavaşça yürür | 2 | 30 sn | 15 (yüz boyu kapısı) |
| `rtsp` | telefon IP kamera uygulaması; 2 dk yayın, ortada Wi-Fi 10 sn kapatılır | 1 | 150 sn | ilk gerçek RTSP, yeniden bağlanma |

Toplam ~35 dk kayıt, kurulumla ~1,5 sa.

### 1.3 Çekim sırasında not

- Kayıt aracı (§2) her dosya için etiket iskeletini yazar. Çekimde
  yalnız sahnede beklenmedik bir şey olursa (oyuncu kadrajdan çıktı, ikinci
  kişi girdi) iskeletteki `_not` alanına bir satır.
- Olayların saniyeleri **çekimden sonra**, videoya bakarak doldurulur
  (§4.1). Çekim sırasında saat tutmaya çalışılmaz.

## 2. Kayıt aracı: `scripts/record_session.py` (14A)

```
venv\Scripts\python.exe -m scripts.record_session --list
venv\Scripts\python.exe -m scripts.record_session --source 0 --scene dusme_kalkamama
venv\Scripts\python.exe -m scripts.record_session --source rtsp://<telefon>/... --scene rtsp
```

- Sahne listesi §1.2 tek bir sözlükte (`SCENES`: anahtar → açıklama,
  tekrar, süre, beklenen olay tipleri, varsa beklenen 13.4 sonucu).
  `--list` tabloyu basar.
- `--scene` zorunlu (listede olmalı). Dosya adı
  `data/field/<YYYYMMDD>/<sahne>_<NN>.mp4`; `NN` o günün o sahne için
  sıradaki numarası (üzerine yazmaz).
- `--seconds` varsayılanı sahnenin süresi; `--out` varsayılanı
  `data/field`.
- Kayıt: 3 sn geri sayım, sonra kaynaktan okunan kareler **olduğu gibi**
  yazılır (yeniden ölçekleme, CLAHE yok; değerlendirme hattı kendisi
  uygular). Kaynağın FPS'i okunamazsa ölçülen FPS yazılır. Saniyede bir
  kalan süre basılır; Ctrl+C erken bitirir ve dosyayı düzgün kapatır.
- Kaynak açılamazsa ya da 5 sn kare gelmezse açık hata ve çıkış kodu 1
  (RTSP sahnesinde yeniden bağlanma değerlendirme hattının işidir; kayıt
  aracı bunu denemez).
- Bitince `eval/annotations/field/<sahne>_<NN>.json` iskeleti
  (`load_annotation` biçimi):

  ```json
  {"video": "data/field/20261201/dusme_kalkamama_01.mp4",
   "scene": "dusme_kalkamama",
   "description": "...",
   "fps": 30.0, "duration_sec": 60.2,
   "_not": "olay saniyelerini videoya bakarak doldurun",
   "events": [{"type": "FALL", "start_sec": null, "end_sec": null, "outcome": "down"}]}
  ```

  Beklenen olay yoksa `events` boş liste (yanlış pozitif sahnesi). Var
  olan iskeletin üstüne yazılmaz.

## 3. Saha değerlendirme aracı: `eval/field_eval.py` (14A)

```
venv\Scripts\python.exe -m eval.field_eval --clips data/field/20261201 --annotations eval/annotations/field --zones eval/zones_field.json --postfall-sec 25 --out logs/field_b0.json
```

- Her klip, **canlı hatla aynı yoldan** geçer: `vision.run`'ın
  `CameraPipeline`'ı (kural + hakem + RUN_ZONE çevirisi + düşme sonrası
  izleyici), gerçek zamanlı değil, Kafka / WS / kanıt kapalı. Hat kodu
  kopyalanmaz; `vision.run.parse_args` ile kurulan bir argüman nesnesi ve
  `CameraPipeline` kullanılır.
- Etiket: `eval.pilot_eval.load_annotation`. Saniyesi `null` olan olay
  (doldurulmamış iskelet) atlanır ve uyarılır.
- Puan (tip başına TP / FP / FN, kesinlik, duyarlılık, F1), iki biçimde:
  ham adaylar ve Spark süzgecinden sonra (`eval.tcn_eval.session_filter`).
  Puanlama `pilot_eval.to_second_set` + `score` ile; tolerans aynı.
- **Düşme sonucu:** `outcome` alanı olan her FALL etiketi için, iniş
  zamanı (`FallOutcome.fall_ts`) `[start_sec - tol, end_sec + tol]` içinde
  olan sonuç eşlenir. Tablo: beklenen × bulunan (`down` / `recovered` /
  `unknown` / sonuç yok) ve karar süresi (`decided_after_sec`). Eşleşmeyen
  sonuçlar ayrıca listelenir.
- `--postfall-sec` (varsayılan 25) ve `--no-tcn`, `--no-clahe` geçirilir
  (CLAHE karşılaştırması için).
- Çıktı: markdown özet (klip başına satır + toplam) ve `--out` JSON
  (klip başına aday listesi, sonuçlar, puanlar). Kötü sayı saklanmaz.
- **Bugün doğrulama:** pilot kliplerle (`--clips data/pilot
  --annotations eval/annotations --zones eval/zones.json`) koşar; tip
  puanları `pilot_eval`'in kural moduyla aynı mertebede çıkmalı (hakem
  ve RUN_ZONE çevirisi nedeniyle birebir değil; fark yazılır).

## 4. Kayıtlardan sonra (14B)

1. **Etiketleme:** iskeletlerin saniyeleri doldurulur; yön ve bölge
   poligonları kayıttan bir kareye bakarak `eval/zones_field.json`'a
   yazılır (normalize, 960×540 letterbox uzayı).
2. **B0 ölçümü:** `field_eval` bugünkü modelle; LOITERING duyarlılığı,
   13.4 sonuç tablosu, 13.5 ters yön.
3. **TCN ince ayarı:** saha klipleri klip bazında ayrık eğitim / test
   (aynı sahnenin tekrarları aynı tarafta), 13.3'ün kare düşürme
   artırımı. Önce / sonra tablosu (holdout ve saha testi).
4. **FIGHT iki kişi öznitelikleri:** göreli mesafe, yaklaşma hızı, bilek /
   ayak bileği hızı; holdout ve saha itişme kayıtlarında.
5. `conf_sweep` ve pilot ablation yeniden.
6. Sabitler (13.4 `DECIDE_SEC`, `STAND_RATIO`; 13.5 `MIN_AGAINST_SPEED`)
   sahaya göre değiştirilecekse ayrı karar olarak yazılır; holdout
   ayar kümesine dönüşmesin diye değişiklik sonrası yeni kayıtla
   doğrulanır.

**Kabul (yol haritası):** etiketli kayıt kümesi; ince ayar öncesi / sonrası
tablo; LOITERING duyarlılığı ilk kez ölçüldü; 13.4 ve 13.5 sahada
doğrulandı.

**Commit (14 sonunda):** `feat: asama 14 - saha kayit kumesi, etiketler ve tcn ince ayari`.
14A ayrı commit: `feat: asama 14a - cekim protokolu, kayit ve saha degerlendirme araclari`.

## 5. Testler (14A)

İki yeni dosya (§6): `tests/test_asama14_kayit.py` ve
`tests/test_asama14_degerlendirme.py`.
- `SCENES`: her sahnenin süresi > 0, beklenen tipler bilinen tipler,
  13.4 sonucu yalnız FALL'da ve geçerli değer
- dosya numaralama: aynı gün aynı sahne ikinci kayıt `_02`; var olan
  dosyanın üstüne yazılmaz
- iskelet: biçim `load_annotation` ile okunuyor, `null` saniyeli olay
  `field_eval`'de atlanıyor, var olan iskelet korunuyor
- kayıt: sahte bir kaynak (birkaç sentetik kare) ile kısa kayıt → dosya
  var, kare sayısı doğru (OpenCV ile geri okunur), geçici dizinde
- `field_eval` düşme sonucu eşleme: sentetik `FallOutcome` listesi ve
  etiketlerle beklenen × bulunan tablosu; zaman toleransı; sonuçsuz FALL

## 6. İş bölümü

| paket | dosyalar |
|---|---|
| **K — kayıt** | `scripts/record_session.py`, testlerin kayıt kısmı (`tests/test_asama14_kayit.py`) |
| **D — değerlendirme** | `eval/field_eval.py`, testlerin değerlendirme kısmı (`tests/test_asama14_degerlendirme.py`) |

Sözleşme: `SCENES` sözlüğü K'de; D yalnız etiket JSON biçimine (§2)
bağlı, `SCENES`'i içe aktarmaz.

## 7. Ortak kurallar

- Yorumlar ASCII, kısa, "neden"i anlatır. Kullanıcı metinleri Türkçe.
- Hat koduna dokunulmaz.
