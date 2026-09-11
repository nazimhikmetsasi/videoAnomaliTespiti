# Aşama 11 — Olay Tetiklemeli ReID ve Tekrar Giriş Kimliği

İki ayrı şeyi çözer, ikisi de **ölçülmüş** bir eksikten doğuyor:

1. **Kaynak.** ReID ağı bugün her karede çalışıyor. Kapatınca 4 kamerada
   kamera başına 11.7 → 15.2 FPS (Aşama 10.4). Yani maliyeti gerçek ve üst
   sınırı biliniyor.
2. **Kimlik.** `docs/DURUM.md`'de Aşama 2'den beri açık: *"kadrajdan çıkıp
   geri giren kişi yeni ID alıyor."* Takip ID'si oturum içindedir; olaylar
   arasında kişiyi bağlayan bir kimlik yok.

Çözüm aynı fikirle ikisini birden karşılıyor: **ReID her karede değil,
yalnızca bir aday olay tetiklendiğinde çalışsın**, ve ürettiği vektör bir
galeride tutulup sonraki olaylarla eşleştirilsin.

---

## 1. Tasarım

### Durum makinesi

```
kişi kadrajda → BoT-SORT track_id atar (ReID YOK, IoU + Kalman)
       │
       └─ aday olay (FALL / RUN / ZONE / FIGHT / LOITERING) tetiklendi
              │
              ├─ en iyi kare seç  (halka tampondan, en keskin kırpım)
              ├─ ReID vektörü çıkar (tek çağrı)
              ├─ galeride kosinüs araması
              │     eşleşti  → var olan person_id
              │     eşleşmedi → yeni person_id, galeriye ekle
              └─ person_id adayın metriklerine yazılır
```

### Kararlar ve gerekçeleri

**Qdrant eklenmiyor.** Galeri bu ölçekte birkaç yüz vektördür; NumPy tek
matris çarpımıyla kosinüs araması yapar. Ayrı bir vektör veritabanı
servisi dört konteynerin üstüne beşincisini koyar ve ölçülen sonucu
değiştirmez. Tezde "Qdrant'a geçiş yolu" olarak anılır.

**En iyi kare halka tamponundan gelir.** `VideoSource.snapshot()` zaten var
(kanıt klibi için yazılmıştı) ve izin bbox geçmişi `FrameFeatures.bbox`'ta
duruyor (Aşama 9'da eklendi). Yani kare başına ek maliyet **sıfır**:
kırpım ve keskinlik hesabı yalnız olay anında yapılır. Keskinlik ölçüsü
Laplacian varyansı.

**`person_id` yeni sütun DEĞİL, `metrics` içinde taşınır.** `init.sql`
yalnızca ilk kurulumda çalışıyor; sütun eklemek elle migration ister ve
1040 olaylık veritabanını riske atar. `metrics` zaten Kafka → Spark →
tüketici → MongoDB `telemetry` boyunca akan bir sözlük. Ölçüm bunu
gerektirdiğini gösterirse sütun sonra eklenir.

**Takipteki ReID kapatılmıyor, seçime bırakılıyor.** Varsayılan bugünkü
davranış kalır; olay tetiklemeli galeri `--reid-gallery` ile açılır ve
kaynak tablosu iki modu yan yana ölçer.

---

## 2. Değerlendirme — gerçek referans nereden geliyor

CASIA klipleri dosya adında **kişi kimliği** taşıyor:
`casia_angleview_p01_faint_a1.mp4`. Elimizde p01 için 40, p02 için 26,
p03 için 31 klip var (toplam 24 kişi).

Bu, uydurulmuş değil kümenin kendi kimliğidir:

- **Olumlu çift:** aynı `pXX`, farklı klip → aynı kişi, eşleşmeli
- **Olumsuz çift:** farklı `pXX` → eşleşmemeli

**Bilinen sınır:** CASIA tek oturumda tek kamerayla çekilmiş; aynı kişi
kliplerde büyük olasılıkla aynı kıyafette. Bu, ReID'yi olduğundan kolay
gösterir. Sayı bu uyarıyla birlikte raporlanır; farklı kamera/kıyafet
koşulu ölçülmemiştir.

---

## 3. Alt aşamalar

### 11.1 — `ReIDGallery`

- `vision/reid_gallery.py`: bağımsız ONNX kodlayıcı (`build_encoder`),
  kosinüs araması, `person_id` atama, galeri budama (TTL / en fazla N).
- Birim testi: sentetik vektörlerle eşik davranışı, yeni kimlik açma,
  aynı kişiyi ikinci kez bağlama.
- **Onay kriteri:** testler yeşil; gömme vektörü boyutu ve tek çağrı süresi
  ölçülmüş.

### 11.2 — Olay tetiklemeli akış — **YAPILMADI (bilinçli)**

11.3'ün ölçümü galeriyi hatta bağlamanın yanlış olacağını gösterdi: tekrar
giriş senaryosunda en iyi F1 0.15. Çalışmayan bir kimlik ataması üretime
sokulmaz. Ölçüm `docs/DURUM.md` § Aşama 11'de, galeri kodu ve testleri
ileride daha yüksek çözünürlüklü kaynakla tekrar denenmek üzere duruyor.

<sub>Özgün plan aşağıdaki gibiydi:</sub>

- `CameraPipeline.consume`: aday üretildiğinde en iyi kareyi halka
  tampondan seç, vektör çıkar, galeriye sor, `person_id`'yi `metrics`'e yaz.
- `--reid-gallery` bayrağı; kapalıyken davranış birebir bugünküdür.
- **Onay kriteri:** aynı klip iki modda koşuyor; olay başına ek süre
  ölçülmüş (kare başına değil — olay başına).

### 11.3 — Kosinüs eşik taraması

- `eval/reid_eval.py`: CASIA kliplerinden kişi başına vektör çıkarır,
  0.50–0.90 aralığında eşiği tarar, her eşik için precision / recall / F1
  ve **kimlik değişim sayısı** üretir.
- **Onay kriteri:** eşik–precision/recall tablosu; seçilen eşik ve gerekçesi.

### 11.4 — FIGHT kök nedeni (kapsam değişti)

Özgün plan burada kaynak karşılaştırması yapacaktı; ReID hatta
bağlanmadığı için o ölçümün konusu kalmadı (kaynak farkı zaten Aşama
10.4'te ölçülü: 11.7 → 15.2 FPS). Yerine FIGHT duyarlılığı 0.07'nin kök
nedeni ölçüldü ve düzeltildi — ayrıntı `docs/DURUM.md`.

<sub>Özgün plan aşağıdaki gibiydi:</sub>

- 4 kamera, üç mod: (a) her karede ReID, (b) ReID kapalı, (c) olay
  tetiklemeli galeri.
- Ölçülen: kamera başına FPS, takip aşaması ms, GPU belleği, olay başına
  ReID süresi.
- **Onay kriteri (aşamanın onay kriteri):** üç modun hız + kimlik
  doğruluğu tablosu tek yerde.

---

## 4. Bilinçli sınırlar

**Yüz tanıma yok.** Bu aşama *kişiyi isimle tanımaz*, yalnız "bu, daha önce
olay üreten kişiyle aynı kişi mi" sorusunu yanıtlar. İsimli kimlik
(`TEZ_KAPSAM.txt` Faz 2) ayrı bir model, ayrı veri kümesi ve ayrı bir
KVKK tartışması demektir; tezde kapsam dışı ilan edilecek.

**Galeri kalıcı değil.** Süreç kapanınca düşer. Kalıcılık MongoDB'ye tek
koleksiyonla eklenebilir ama ölçülecek şeyi değiştirmez; gerekirse Aşama
12'de.

**Çoklu kamera arası eşleştirme ölçülmez.** Galeri süreç genelindedir,
yani teknik olarak kameralar arası çalışır; ama elimizde aynı kişiyi iki
kameradan gösteren kayıt yok. Ölçülmeyen şey iddia edilmez.
