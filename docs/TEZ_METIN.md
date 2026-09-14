# Tez Metni — Değiştirilecek Bölümler

Bu belge, `tez final raporu son hal.docx` içinde **doğrudan yerine
konacak** hazır metindir. İki iş var:

1. **§4.1'in değişmesi.** Mevcut metin dört regresyon istatistiği
   (MAE 0.1245, MSE 0.0467, RMSE 0.2161, R² 0.9412) "elde edilen bulgular"
   diye sunuyor. Bu sayılar üretilemez ve üretilmemiştir; yerlerine ölçülmüş
   sınıflandırma metrikleri geçiyor.
2. **Yeni bir alt bölüm.** "Yöntem Değişiklikleri ve Gerekçeleri" — tez
   metninde seçilen teknolojilerle kurulan sistemin farklarını ölçümle
   açıklar.

Bütün sayılar `docs/TEZ.md`'den gelir ve orada hangi koşulda ölçüldükleri
yazılıdır.

---

## Neden §4.1 değişmek zorunda

Mevcut metin şunu söylüyor:

> Ortalama Mutlak Hata (MAE): 0.1245. Bu değer, modelin tahmin ettiği eklem
> koordinatları ile gerçek koordinat matrisleri arasındaki mutlak sapmanın
> oldukça düşük olduğunu göstermektedir.

Üç ayrı sorun var:

**Birincisi, ölçülemez.** MAE/MSE/RMSE hesaplamak için kare bazında
**gerçek referans eklem koordinatı** gerekir. Elimizdeki hiçbir veri
kümesinde bu yok: pilot klipler saniye bazlı *olay* etiketlidir, URFD kare
bazlı *sınıf* etiketlidir. İkisi de keypoint koordinatı vermez.

**İkincisi, R² yanlış metrik ailesinden.** Belirlilik katsayısı bir
regresyon modelinin açıkladığı varyans oranıdır. Bu sistemde regresyon
modeli yoktur; TCN bir **sınıflandırıcıdır** ve dört sınıf üzerinde softmax
üretir. "Davranış değişimlerini %94.12 oranında açıklamak" cümlesinin
karşılığı olan bir hesap yoktur.

**Üçüncüsü, rapor bu sayıların ölçüm olmadığını kendi içinde söylüyor.**
§4.4 aynı raporda "gelecek dönem fiziksel olarak kodlanacak" diyor; §4.1'in
girişi de bulguların "simülasyona dayalı ön bulgular" olduğunu belirtiyor.
Dolayısıyla dört sayı literatür/simülasyon tahminidir. Sorun sayıların
kendisi değil, **ölçülmüş gibi sunulmalarıdır.**

Jüri "bu MAE'yi hangi referans koordinat kümesine karşı hesapladınız"
diye sorarsa savunulabilir cevap yoktur. Bu yüzden değiştirilmelidir —
üstelik yerine konacak sayılar daha güçlüdür, çünkü gerçekten ölçülmüştür.

---

## YERİNE KONACAK METİN — § 4.1

> **4.1. Uygulanan Sistemin Ölçülen Başarım Bulguları**
>
> "Profesyonel Yazılım Geliştirme I" döneminde bu bölümde raporlanan
> değerler, sistem henüz kodlanmadığı için literatür taramasına ve
> simülasyona dayalı ön kestirimlerdi. Bu dönemde sistem uçtan uca
> gerçeklendiğinden, söz konusu kestirimler yerini uygulamadan doğrudan
> alınan ölçümlere bırakmıştır.
>
> Ön kestirimlerde kullanılan regresyon hata metrikleri (MAE, MSE, RMSE ve
> belirlilik katsayısı R²) gerçeklenen sistem için **uygun metrik ailesi
> değildir** ve bilinçli olarak terk edilmiştir. Bunun iki nedeni vardır.
> Birincisi, bu metrikler kare bazında gerçek referans eklem koordinatı
> gerektirir; çalışmada kullanılan veri kümelerinin hiçbiri keypoint
> koordinatı etiketi içermez (pilot klipler saniye bazlı olay etiketli, UR
> Fall Detection kümesi kare bazlı sınıf etiketlidir). İkincisi, R² bir
> regresyon modelinin açıkladığı varyans oranıdır; gerçeklenen sistemde
> regresyon modeli bulunmamakta, zamansal evrişimli sinir ağı dört sınıf
> üzerinde **sınıflandırma** yapmaktadır. Bu nedenle başarım, sınıflandırma
> problemine uygun olan kesinlik (precision), duyarlılık (recall) ve F1
> ölçütleriyle raporlanmıştır.
>
> **Ölçüm ortamı.** Bütün ölçümler NVIDIA RTX 3050 Laptop (4 GB) ekran
> kartı, Windows 11 ve Python 3.11 ortamında alınmıştır. Görü süreci ana
> makinede yerel olarak, PostgreSQL, MongoDB, Apache Kafka, Apache Spark ve
> FastAPI servisleri Docker konteynerlerinde çalıştırılmıştır. Çalışmada IP
> tabanlı güvenlik kamerası donanımı kullanılmamış; tüm ölçümler dizüstü
> bilgisayarın tümleşik kamerası ve altı pilot video klibi üzerinden
> alınmıştır. RTSP akış desteği kod düzeyinde mevcut olmakla birlikte
> donanım bulunmadığından sınanmamıştır ve bu, sonuçların açıkça belirtilen
> bir sınırıdır.
>
> **4.1.1. Davranış sınıflandırma başarımı**
>
> Zamansal evrişimli sinir ağı (TCN), iz başına 50 karelik pencerelerle
> beslenmiş; her kare 53 kanalla temsil edilmiştir (17 eklem noktasının
> sınır kutusuna göre normalize edilmiş x/y koordinatları, 17 güven değeri
> ve ağırlık merkezi hızı). Model 66 116 parametreye sahiptir ve eğitim ile
> doğrulama ayrımı **klip bazında** yapılmıştır; aynı klibin pencereleri
> her iki kümeye birden düşmemiştir.
>
> | Sınıf | Kesinlik | Duyarlılık | F1 | Doğrulama penceresi |
> |---|---|---|---|---|
> | NORMAL | 0,802 | 0,722 | 0,760 | 540 |
> | FALL | 0,524 | 0,620 | 0,568 | 71 |
> | RUN | 0,704 | 0,974 | 0,817 | 39 |
> | FIGHT | 0,615 | 0,686 | 0,649 | 226 |
> | **Makro F1** | | | **0,698** | |
>
> Pencere başına çıkarım süresi 1,20 milisaniyedir.
>
> Etiket kalitesinin başarıma etkisi doğrudan ölçülmüştür. UR Fall
> Detection kümesindeki düşme kliplerinin yaklaşık %40'ı düşme öncesi normal
> yürüyüşten oluşmakta, buna rağmen klip düzeyinde tamamı FALL etiketi
> almaktadır. Kümenin kendi **kare bazlı** etiketleri kullanıldığında FALL
> sınıfının kesinliği 0,300'den 0,524'e, makro F1 ise 0,672'den 0,698'e
> yükselmiştir. Bu bulgu, veri kümesi kalitesinin model mimarisi kadar
> belirleyici olduğunu göstermektedir.
>
> **4.1.2. Karar katmanı: kural, model ve hibrit karşılaştırması**
>
> Sistemin karar katmanı üç ayrı kipte ölçülmüştür: yalnızca eşik tabanlı
> kural motoru, yalnızca TCN sınıflandırıcı ve ikisini birleştiren hibrit
> hakem. Ölçüm, eğitimde hiç kullanılmamış tutma (holdout) klipleri
> üzerinde yapılmıştır.
>
> | Kip | DP | YP | DN | Kesinlik | Duyarlılık | F1 |
> |---|---|---|---|---|---|---|
> | Kural | 13 | 6 | 31 | 0,68 | 0,30 | 0,41 |
> | Model | 25 | 6 | 19 | **0,81** | 0,57 | **0,67** |
> | Hibrit | **28** | 12 | **16** | 0,70 | **0,64** | **0,67** |
>
> Tip bazında F1 değerleri:
>
> | Anomali tipi | Kural | Model | Hibrit |
> |---|---|---|---|
> | Düşme (FALL) | 0,53 | 0,67 | **0,78** |
> | Koşma (RUN) | 0,50 | **0,55** | 0,48 |
> | Kavga (FIGHT) | 0,12 | **0,75** | **0,75** |
>
> Kural motoru tek başına yüksek kesinlik üretmekte ancak duyarlılığı düşük
> kalmaktadır (0,30); eşik tabanlı bir yaklaşımın yakalayabildiği durumlar
> sınırlıdır. Öğrenilmiş model duyarlılığı 0,57'ye çıkarmış, hibrit hakem
> ise 0,64 ile en yüksek değeri vermiştir. F1 açısından model ve hibrit
> eşittir (0,67); aradaki fark, hibrit kipin yanlış negatifleri azaltıp
> yanlış pozitifleri artırmasıdır. Güvenlik gözetimi bağlamında kaçırılan
> bir olayın maliyeti gereksiz bir uyarınınkinden yüksek olduğundan, hibrit
> kip varsayılan olarak seçilmiştir.
>
> Kavga tespitindeki sıçrama, ölçümle saptanan bir tasarım hatasının
> düzeltilmesinden kaynaklanmaktadır. Kural motorunun "karşılıklı uzuv
> hızı" ölçütü, kavga eylemini normal hareketten ayırt edememektedir;
> denenen her eşik değerinde normal davranış sınıfının oranı daha yüksek
> çıkmıştır. Hakem katmanı modelin kavga kararını bu çalışmayan kuralın
> onayına bağladığından, model kavgayı hiç üretememiştir. Yakınlık koşulu
> uzuv hızından ayrıştırılarak modelin, iz yakın bir insan çiftinin parçası
> olduğunda tek başına kavga kararı üretebilmesi sağlanmış ve duyarlılık
> **0,07'den 0,80'e** yükselmiştir.
>
> **4.1.3. Alan farkı ve sınırlar**
>
> Tutma kliplerinde 0,81 kesinlik üreten model, üretim alanını temsil eden
> 1080p ve 4K çözünürlüklü pilot kliplerde 12 yanlış düşme kararı
> üretmektedir. Eğitim verisinin ağırlıklı olarak 320x240 çözünürlüklü
> gözetim kayıtlarından oluşması, yüksek çözünürlüklü görüntülerde alan
> kayması (domain shift) yaratmaktadır. Bu sonuç olduğu gibi raporlanmakta
> ve tek ortalama altında gizlenmemektedir; iki kümenin ayrı tablolarda
> verilmesinin nedeni budur.
>
> Ek olarak, oyalanma (LOITERING) sınıfının duyarlılığı **ölçülememiştir**:
> erişilebilen hiçbir açık veri kümesinde bu sınıfa ait olumlu örnek
> bulunmamaktadır. Sınıf tanımlı ve kod düzeyinde çalışır durumdadır, yanlış
> pozitif üretmemektedir; ancak duyarlılığı bilinmediğinden bu çalışmada
> başarım iddiasında bulunulmamaktadır.
>
> **4.1.4. Gerçek zamanlılık ve kaynak kullanımı**
>
> Sistemin gerçek zamanlı kısıtları karşılayıp karşılamadığı, aşama bazında
> ölçülmüştür (3840x2160 çözünürlüklü klip, 200 kare, tüm katmanlar etkin):
>
> | Aşama | Medyan (ms) | %95'lik dilim (ms) |
> |---|---|---|
> | Ön işleme | 19,0 | 24,1 |
> | Çıkarım | 17,0 | 22,5 |
> | Takip (BoT-SORT + ReID) | 8,4 | 10,0 |
> | Düzleme (One-Euro) | 0,0 | 0,1 |
> | Öznitelik + kural | 0,2 | 2,3 |
> | *— bunun içinde TCN çıkarımı* | *1,6* | *2,5* |
> | **Döngü toplamı** | **44,9** | **56,5** |
>
> Öğrenilmiş karar katmanının maliyeti, toplam döngü süresinin yalnızca
> %3,6'sıdır. Toplu çıkarım (batch inference) kullanımı kare başına çıkarım
> süresini 14,45 ms'den 10,45 ms'ye düşürmüştür (4'lü grup).
>
> Dört kameranın tek süreçte eşzamanlı işlenmesiyle panel canlı görüntü
> hızı 26,3 FPS ölçülmüştür. Karşılaştırma amacıyla, aynı işlevi iki ayrı
> model geçişiyle gerçekleyen önceki sürüm 0,67 FPS'te kalmaktadır.
>
> **4.1.5. Uzun süreli çalışma kararlılığı**
>
> Sistem dört kamerayla sekiz saat kesintisiz çalıştırılmış, 60 saniyede bir
> olmak üzere 459 ölçüm alınmıştır.
>
> | Ölçüt | İlk saat | Son saat | Değişim |
> |---|---|---|---|
> | Toplam FPS | 33,2 | 33,4 | +%0,6 |
> | Çıkarım süresi | 13,9 ms | 14,0 ms | +%0,5 |
> | Bellek kullanımı (RSS) | 5804 MB | 6005 MB | +%3,5 |
> | GPU belleği | 791 MB | 898 MB | +%13,6 |
>
> İşleme hızında ve çıkarım süresinde sekiz saat boyunca sapma
> gözlenmemiştir; %1'in altındaki değişim ölçüm gürültüsü düzeyindedir. GPU
> belleğindeki %13,6'lık artış saatlik kırılımda incelendiğinde bellek
> sızıntısı olmadığı görülmektedir: değer üçüncü saatte 898 MB'de
> sabitlenmekte ve kalan beş saat boyunca değişmemektedir; artış CUDA bellek
> ön belleğinin ısınmasından kaynaklanmaktadır. Ana bellekte saatte yaklaşık
> 25 MB'lik salınımlı bir sürüklenme gözlenmiştir. Sekiz saatlik pencerede
> sızıntı **görülmemiştir**; daha uzun süreli ölçüm yapılmadığından kesin
> bir sızıntısızlık iddiasında bulunulmamaktadır.
>
> Uzun koşunun ortaya çıkardığı tek işletimsel engel, kanıt kliplerinin
> saatte 1,3 GB (günde yaklaşık 31 GB) disk tüketmesi olmuştur. Bu sorun,
> klip yaşı, kare yaşı ve toplam boyut tavanını birlikte uygulayan bir
> saklama politikasıyla giderilmiştir.

---

## EKLENECEK YENİ ALT BÖLÜM — § 4.5

> **4.5. Yöntem Değişiklikleri ve Gerekçeleri**
>
> Önceki dönem raporunda belirlenen teknoloji seçimlerinin bir bölümü,
> gerçekleme sürecinde alınan ölçümler doğrultusunda değiştirilmiştir. Bu
> değişiklikler plandan sapma değil, planın **ölçümle sınanmasının** sonucudur;
> her biri aşağıda gerekçesi ve gerekçeyi doğrulayan ölçümle birlikte
> verilmiştir.
>
> **4.5.1. İskelet çıkarımı: MediaPipe Pose yerine tek geçişli poz modeli**
>
> Planlanan mimaride nesne tespiti (YOLO) ve iskelet çıkarımı (MediaPipe
> Pose) iki ayrı model olarak kurgulanmıştı. Bu tasarım her kare için iki
> ayrı ileri besleme geçişi gerektirir. Aynı yaklaşımla gerçeklenen önceki
> sürümde panel canlı görüntü hızı **0,67 FPS**'te kalmıştır; bu değer
> gerçek zamanlı gözetim için kullanılamaz.
>
> Poz tahmini yapabilen tek bir model kullanıldığında sınır kutusu ve eklem
> noktaları **aynı geçişte** üretilmektedir. Ölçülen fark belirleyicidir:
> dört kamera tek süreçte 26,3 FPS ile işlenebilmektedir. Eklem sayısı
> 33'ten COCO standardındaki 17'ye inmiştir; ancak çalışmada kullanılan
> özniteliklerin tamamı (gövde eğimi, omurga açısı, diz açısı, uzuv hızı,
> ağırlık merkezi hızı) 17 noktadan hesaplanabilmektedir. Kaybedilen
> noktalar ağırlıklı olarak el ve yüz ayrıntılarıdır ve hedef anomali
> sınıflarında kullanılmamaktadır.
>
> **4.5.2. Nesne takibi: DeepSORT yerine BoT-SORT**
>
> Planda DeepSORT, Kalman filtresine derin öznitelik eşleştirmesi eklediği
> için seçilmişti. Gerçeklemede BoT-SORT kullanılmıştır; bu algoritma aynı
> derin öznitelik eşleştirmesini içermekte, ek olarak **kamera hareketi
> telafisi** (global motion compensation) uygulamaktadır. Seçim, planlanan
> yaklaşımın terk edilmesi değil, aynı yaklaşımın daha güncel bir
> gerçeklemesidir.
>
> **4.5.3. Panel: React yerine derleme adımsız HTML**
>
> Planda React tabanlı bir arayüz öngörülmüştü. Gerçeklemede, kurum
> tarafından sağlanan hazır HTML şablonu esas alınmış ve panel derleme adımı
> gerektirmeyen düz HTML ile Tailwind CSS üzerine kurulmuştur. Gerekçe
> işlevsel değil, maliyet temellidir: hazır şablonun on bir ekranını React
> bileşenlerine dönüştürmek, sistemin ölçülen başarımına hiçbir katkı
> sağlamayacak bir yeniden yazım anlamına gelmekteydi. Panelin gerçek zamanlı
> güncellemesi WebSocket üzerinden sağlanmakta olup bu yetenek arayüz
> kütüphanesinden bağımsızdır.
>
> **4.5.4. Kafka'nın taşıdığı veri: ham kare yerine olay meta verisi**
>
> Planda Kafka üzerinden Base64 kodlanmış ham video karelerinin taşınması
> öngörülmüştü. Gerçeklemede Kafka yalnızca **aday olay meta verisini**
> taşımaktadır: kamera kimliği, iz kimlikleri, anomali tipi, skor, zaman
> damgası ve eşik değerleri. Ham kare taşımak, mesaj başına megabaytlar
> düzeyinde veri üretir ve ağ bant genişliğini, Kafka disk alanını ve
> tüketici işlem gücünü hiçbir analitik karşılığı olmadan tüketir. Görüntü
> verisi, olay anında yerel halka tampondan mp4 klip olarak yazılmakta ve
> dosya yolu olay kaydına iliştirilmektedir; böylece kanıt korunurken akış
> hattı hafif kalmaktadır.
>
> **4.5.5. Zamansal model: TCN tercihi**
>
> Zaman serisi davranış sınıflandırması için yinelemeli ağlar (LSTM/GRU)
> yaygın bir seçimdir. Bu çalışmada genişletilmiş nedensel evrişim (dilated
> causal convolution) tabanlı bir TCN kullanılmıştır. Gerekçe gerçek zamanlı
> kısıttır: TCN'in bir pencereyi değerlendirmesi 1,20 ms sürmekte, bu da
> toplam işleme döngüsünün %3,6'sına karşılık gelmektedir. Model 66 116
> parametre ile 4 GB'lık ekran kartı belleğinde nesne tespiti modeliyle
> birlikte sorunsuz çalışmaktadır.
>
> **4.5.6. Kimlik eşleştirme: ölçülerek terk edilen modül**
>
> Kadrajdan çıkıp geri giren kişinin yeni bir takip kimliği alması, takip
> algoritmalarının bilinen bir sınırıdır. Bu sorunu çözmek üzere, olay
> tetiklendiğinde kişinin görsel imzasını çıkaran ve bir galeride kosinüs
> benzerliğiyle arayan bir yeniden tanımlama (ReID) modülü geliştirilmiş ve
> değerlendirilmiştir.
>
> Değerlendirme olumsuz sonuç vermiştir: tekrar giriş senaryosunda elde
> edilen en iyi F1 değeri 0,15'tir. Bu düzeyde bir eşleştirme, kişileri
> doğru bağlamak yerine yanlış bağlayacağı için modül **bilinçli olarak
> üretim hattına dahil edilmemiştir.** Kod ve birim testleri, daha yüksek
> çözünürlüklü kaynakla yeniden denenmek üzere depoda korunmaktadır.
> Çalışmayan bir bileşeni sisteme dahil edip başarım iddiasında bulunmak
> yerine, ölçüm sonucunun olduğu gibi raporlanması tercih edilmiştir.
>
> **4.5.7. Vektör veritabanı: ayrı servis yerine matris araması**
>
> Görsel imza aramasının bir vektör veritabanı (Qdrant) üzerinde yapılması
> düşünülmüştür. Çalışmanın ölçeğinde galeri birkaç yüz vektörden
> oluşmaktadır; bu boyutta arama tek bir matris çarpımıyla yapılabilmekte,
> ayrı bir veritabanı servisi mevcut dört konteynerin üzerine beşincisini
> eklemekte ve ölçülen sonucu değiştirmemektedir. Vektör veritabanına geçiş,
> galeri büyüklüğü artarsa izlenecek yükseltme yolu olarak belgelenmiştir.

---

## Güncellenmesi gereken diğer noktalar

Bunlar kısa düzeltmelerdir, ayrı metin gerektirmez:

| Yer | Mevcut | Olması gereken |
|---|---|---|
| Tablo 3.1 / 4.1 | MediaPipe Pose, 33 eklem | Tek geçişli poz modeli, COCO-17 |
| Tablo 4.1 | DeepSORT | BoT-SORT (kamera hareketi telafili) |
| Tablo 3.2 | `video-stream` topic'i, ham kare | `anomaly-candidates`, olay meta verisi |
| Metin geneli | YOLOv8 | Kullanılan sürüm |
| Kare boyutu | 640x480 | 960x540 (letterbox) |
| EK D.1 veri sözlüğü | `detected_person_id`, `confidence_score`, `ai_generated_report`, `timestamp` | `track_ids`, `confidence`, `llm_report_tr`, `started_at` / `ended_at` |
| §4.3 | "RTSP paket kayıpları ... aşılmıştır" | RTSP donanımı bulunmadığından sınanmamıştır |
| Hedef: yanlış alarm < %10 | Tutmuş gibi | Ham aday düzeyinde tutmamıştır; süzgeç sonrası oran ölçülmemiştir |

**EK D.1 için not:** sütun adlarını tezdeki adlara çekmek de bir
seçenektir ve veritabanı şeması küçük olduğu için maliyeti düşüktür.
Hangisinin tercih edileceği biçimsel bir karardır.
