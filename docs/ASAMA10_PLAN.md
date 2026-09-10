# Aşama 10 — Ölçek ve Tez

Bu aşamanın işi yeni yetenek eklemek değil, **var olanı N kameraya
taşıyıp ölçmek.** Onay kriteri tek cümle: 4 kamera 8 saat kesintisiz.

Bugün çoklu kamera N ayrı süreçtir (`scripts/run_pilot_cameras.py`,
Aşama 8.6): her süreç kendi model kopyasını VRAM'e yükler, her biri ayrı
WS portu dinler. 4 GB VRAM'de bu 3 kamerada tıkandı. Aşama 10 tek süreç,
tek model, N kare hedefliyor.

---

## 1. Ölçülen bütçe (plan yazılmadan önce koşuldu)

Temiz koşu, RTX 3050 Laptop 4 GB, başka iş yokken.

### Tek kamera, uçtan uca (`data/pilot/run_01.mp4`, 200 kare)

| Aşama | Medyan ms | p95 ms |
|---|---|---|
| ön işleme | **19.0** | 24.1 |
| çıkarım | 17.0 | 22.5 |
| takip | 8.4 | 10.0 |
| düzleme | 0.0 | 0.1 |
| öznitelik + kural | 0.2 | 2.3 |
| ↑ içinde TCN çıkarımı | 1.6 | 2.5 |
| **döngü toplam** | **44.9** | 56.5 |

Gerçek FPS 20.9. **Ön işleme çıkarımdan pahalı** — beklenmiyordu.

### Ön işlemenin kırılımı

`run_01.mp4` 1080p değil, **3840x2160**. Tek kare üzerinde ölçüm:

| İşlem | ms |
|---|---|
| tam ön işleme | 7.18 |
| yalnız `letterbox` (INTER_AREA) | 7.09 |
| CLAHE kapısı (std hesabı) | 0.06 |
| `letterbox` INTER_LINEAR ile | **0.15** |

Maliyetin tamamı `cv2.resize(..., INTER_AREA)`. INTER_LINEAR **47 kat**
ucuz. Ama INTER_AREA 4x küçültmede doğru seçimdir (aliasing'i önler);
değiştirmek poz tespitini bozabilir. **Ölçülmeden değiştirilmeyecek**
(§ 10.2).

Döngü içinde 19.0 ms, izole ölçümde 7.18 ms: fark kaynak çözme
iş parçacığıyla bellek bandı rekabetidir. Sıra tek kameradayken bile
ölçülmüş bir maliyet.

### Toplu çıkarım ve takip (960x540 kare)

| Batch | Çıkarım, kare başına ms |
|---|---|
| 1 | 14.45 |
| 2 | 12.37 |
| **4** | **10.45** |
| 8 | 10.42 |

Batch 4'ten sonra kazanç yok. Takip kare başına 0.40 ms (ReID açık) /
0.37 ms (kapalı) — ama bu ölçüm az kişili karelerde alındı; kalabalık
karede ReID kodlayıcısı devreye girer, tek kamera raporundaki 8.4 ms
medyan gerçek yükü gösterir.

### 4 kamera bütçesi — hedef gerçekçi mi

Kamera başına 20 FPS = 4 karelik turda **50 ms** bütçe.

| Kalem | Tur başına ms |
|---|---|
| çıkarım (batch 4) | 41.8 |
| takip (4 × 8.4, en kötü) | 33.6 |
| ön işleme (4 × 19.0, bugünkü hâliyle) | 76.0 |
| **toplam (bugün)** | **151.4** → kamera başına 6.6 FPS |

Yani **bugünkü kodla hedef tutmuyor** ve fark 3 kattan fazla. Ön işleme
düzeltilirse (4 × 0.2 ms) toplam 76 ms'e iner → 13 FPS/kamera. Kalan
farkı kapatacak bilinen düğmeler: `yolo26n-pose` (PLAN.md risk 1 zaten
bunu öngörüyor), ReID kapatma, `imgsz` düşürme. Bu aşama bir sayı vaat
etmiyor; **düğme tablosunu ölçüp** hangisinin hangi bedelle 20 FPS
verdiğini gösteriyor (§ 10.4).

---

## 2. Mimari karar: tek döngü, kamera başına nesne

`vision/run.py` bugün 582 satır ve tek kamera için yazılmış: kaynak,
ön işleme, takipçi, düzleyici, öznitelik, hakem, yayıncı, kanıt yazıcı,
sağlık istemcisi — hepsi `main()` içinde yerel değişken.

**İkinci bir `run_multi.py` yazılmayacak.** Yazılsaydı canlı yayın, kanıt,
kalp atışı, JPEG kalite denetleyicisi ve rapor mantığı iki kopyada
yaşardı; v1'in `pipeline.py` 435 satırının tekrarı olurdu.

Bunun yerine kamera başına durum tek sınıfa çıkarılır:

```
vision/camera.py   CameraPipeline
    .read()                 -> Frame | None      (kaynaktan tek kare)
    .preprocess(frame)      -> image
    .consume(result, image) -> candidates        (takip -> ... -> yayın)
    .report()               -> aşama metrikleri
```

`run.py` bundan sonra **sürücüdür**: N adet `CameraPipeline` kurar, hepsinden
birer kare toplar, tek `detector(images)` çağrısı yapar, sonuçları sahibine
dağıtır. N=1 aynı koddan geçer — tek kameralı davranış ayrı bir yol değildir,
dolayısıyla sessizce ayrışamaz.

Yan kazanç: PLAN.md § 8'deki "en büyük dosya < 150 satır" hedefi bugüne
kadar `—` işaretliydi; bu bölme onu ölçülebilir hâle getirir.

**Tek StreamServer, tek port.** 8.6'da her sürece ayrı port verilmişti ve
port kamera sağlığı üzerinden bildiriliyordu. Tek süreçte tek port yeter;
`ws_port` alanı aynen çalışır (artık hepsi aynı portu bildirir), panel
tarafında değişiklik gerekmez.

**Kamera biri düşerse diğerleri devam eder.** `CameraPipeline.read()` None
dönerse o kamera turu atlar; `VideoSource`'un üstel geri çekilmeli yeniden
bağlanması zaten var. Tek kameranın hatası turu düşürmez — 8 saatlik koşunun
onay kriteri buna bağlı.

---

## 3. Alt aşamalar

Her alt aşama sonunda `docs/DURUM.md` güncellenir ve commit mesajı verilir.

### 10.1 — `CameraPipeline` çıkarımı (davranış değişmez)

- `vision/camera.py`: yukarıdaki sınıf. `run.py` yalnızca sürücü kalır.
- Mekanik taşıma: yeni özellik yok, eşik yok, karar yok.
- **Onay kriteri:** 199 test yeşil; `run_01.mp4` 200 kare koşusunda aday
  sayısı, benzersiz ID sayısı ve aşama medyanları refactor öncesiyle
  **aynı** (± ölçüm gürültüsü). Öncesi bu belgede kayıtlı.

### 10.2 — Ön işleme maliyeti

- `letterbox` küçültme yöntemi ölçülür: INTER_AREA (bugün), INTER_LINEAR,
  `pyrDown` zinciri.
- **Doğruluk önce, hız sonra:** her seçenek için pilot kliplerde pozlu kare
  oranı, benzersiz ID sayısı ve `eval/pilot_eval.py` TP/FP/FN tablosu
  alınır. Hızlı olan seçenek doğruluğu düşürüyorsa **alınmaz**.
- **Onay kriteri:** üç yöntem için hız + doğruluk tablosu; seçim gerekçesi
  `docs/DURUM.md`'de.

### 10.3 — Tek süreç, N kamera, toplu çıkarım

- `run.py --sources a.mp4,b.mp4,...` (veya `--cameras` ile API'den).
- Tur: her kameradan bir kare → tek `detector(images)` → sonuçlar sahibine.
- Kamera başına ayrı `Tracker`, `Smoother`, `FeatureEngine`, hakem, yayıncı.
- Rapor kamera başına satır + toplam.
- **Onay kriteri:** 4 pilot klip tek süreçte koşuyor; VRAM tepe kullanımı ve
  kamera başına FPS ölçülmüş; `scripts/run_pilot_cameras.py`'nin N süreçli
  ölçümüyle yan yana tabloda.

### 10.4 — Düğme tablosu

`yolo26s-pose` / `yolo26n-pose` × ReID açık/kapalı × `imgsz` 960/640 için
4 kamerada FPS **ve** doğruluk (pilot TP/FP/FN). Amaç en hızlıyı seçmek
değil, **hangi doğruluk bedeliyle 20 FPS'e çıkıldığını** göstermek.

- **Onay kriteri:** tablo tam; seçilen yapılandırma ve gerekçesi yazılı.

### 10.5 — 8 saat kesintisiz koşu (aşamanın onay kriteri)

- 4 kamera, `--loop`, tam hat (Kafka + Spark + tüketici + panel).
- İzlenen: FPS sapması, VRAM/RAM sızıntısı, düşen kare, yeniden bağlanma,
  Kafka teslim hatası, Spark checkpoint büyümesi, olay sayısı.
- **Onay kriteri:** 8 saat, süreç çökmeden; FPS ilk saat ile son saat
  arasında %20'den fazla düşmemiş; RAM artışı doğrusal değil.

### 10.6 — Tez çıktıları

- Ablation raporu (Aşama 9.5 tablosu) + gecikme dağılımı + v1/v2
  karşılaştırma tablosu (PLAN.md § 8) tek belgede.
- README: kurulum, çalıştırma, mimari şema.
- **Veri kümesi atıfları** (Aşama 9'dan devraldı): SPHAR ve alt kaynakları
  — CASIA (yazar izni), BIT-Interaction (ticari olmayan), UT-Interaction
  (MIT), UCF-ARG (yalnız araştırma) — ve UR Fall Detection (ticari olmayan
  akademik). Her birinin özgün makalesi kaynakçaya girer.
- **Onay kriteri:** tez tabloları üretilmiş, README bir başkasının sıfırdan
  kurabileceği kadar tam.

---

## 4. Bilinçli sınırlar

**IP kamera yok, kaynaklar dosya ve dizüstü kamerası.** 4 kameralı test
`--loop` ile dosyadan beslenir. RTSP yolu `VideoSource`'ta yazılı ve Aşama 2'de
denendi ama 8 saatlik koşu gerçek RTSP kesintisini içermez; bu sınır raporda
açıkça yazılacak.

**Süreç başına tek GPU.** Çoklu GPU, model paralelliği, TensorRT dönüşümü
kapsam dışı. 4 GB tek kart bu tezin donanımıdır.

**Aşama 9'un iki açık sorusu burada çözülmüyor, ölçülüyor:** FIGHT
duyarlılığı 0.07 ve modelin pilot alanda 12 sahte FALL üretmesi. İkisi de
veri sorunudur (kısa kavga klibi, alan farkı); 10.4'ün düğme tablosu
bunları düzeltmez, yalnızca hangi yapılandırmada ne olduğunu gösterir.

**8 saatlik koşu bir kez yapılır.** Tekrarlanabilirlik için `logs/` altına
periyodik ölçüm satırı yazılır; koşu tekrar edilmeden tablo üretilebilsin.
