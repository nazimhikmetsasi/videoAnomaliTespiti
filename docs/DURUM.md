# Proje Durumu

Bu dosya her aşama sonunda güncellenir. Yeni oturum açıldığında önce
`docs/PLAN.md` sonra bu dosya okunur ve kaldığı yerden devam edilir.

**Son güncelleme:** 2026-08-24

---

## Şu an neredeyiz

**Aşama 0 — Ortam Hazırlığı tamamlandı.** GPU çıkarımı doğrulandı ve ölçüldü.
Sıradaki iş Aşama 1 (Docker altyapısı ve veritabanı şeması).

---

## Aşama durumu

| # | Aşama | Durum |
|---|---|---|
| — | Plan ve mimari (`docs/PLAN.md`) | Tamamlandı |
| 0 | Ortam hazırlığı | Tamamlandı |
| 1 | Altyapı (Docker, veritabanı şeması) | Sırada |
| 2 | Kaynak ve görü çekirdeği | Bekliyor |
| 3 | Öznitelik ve kural motoru | Bekliyor |
| 4 | Kafka ve Spark | Bekliyor |
| 5 | Veri katmanı ve API | Bekliyor |
| 6 | Canlı görüntü (WebSocket) | Bekliyor |
| 7 | LLM ve Telegram | Bekliyor |
| 8 | Panel (kullanıcı şablonu) | Bekliyor |
| 9 | TCN modeli ve yeni sınıflar | Bekliyor |
| 10 | Ölçek ve tez çıktıları | Bekliyor |

---

## Aşama 0 sonucu (2026-08-24)

Kurulan ortam:

- Git deposu (`main` dalı), `.gitignore`, `README.md`
- Python 3.11.9 venv (`venv/`)
- `torch 2.5.1+cu121`, `torchvision 0.20.1+cu121` — `cuda.is_available() == True`
- `ultralytics 8.4.127`, `opencv-python 5.0.0.93`, `numpy 2.4.6`
- `models/yolov8s-pose.pt`, `models/yolov8n-pose.pt`
- `scripts/check_gpu.py` — doğrulama ve ölçüm betiği

Ölçüm (RTX 3050 Laptop 4 GB, 960x540, FP16, ultralytics `bus.jpg`):

| model | kare başına | FPS | tepe VRAM | bulunan kişi |
|---|---|---|---|---|
| yolov8s-pose | 13.3 ms | 75.4 | 49 MiB | 3 |
| yolov8n-pose | 13.2 ms | 75.5 | 36 MiB | 4 |

**Yorum:** `s` ve `n` süreleri neredeyse aynı. Darboğaz GPU hesabı değil,
çağrı başına düşen sabit yük (ön işleme, NMS, Python). Bu, `s` modelinin
pratikte bedava geldiği anlamına gelir ve PLAN'daki `yolov8s-pose` kararını
doğrular. VRAM kullanımı 4 GB'ın yanında ihmal edilebilir.

**Ölçümün sınırı:** tek kare `predict()` çağrısıdır. Gerçek döngüde takip,
öznitelik çıkarımı ve yayın eklenince FPS düşecektir. Aşama 2'de gerçek
döngü ölçülecek.

Yan bulgu: ultralytics 8.4'te `half=True` kullanımdan kalkmış, yerine
`quantize=16` geldi.

---

## Bir sonraki adım

Aşama 1 — Altyapı:

1. `docker-compose.yml`: postgres, mongo, zookeeper, kafka, spark, api
2. `infra/postgres/init.sql`: tüm tablolar, indexler, admin tohum kaydı
3. `infra/mongo/init.js`: koleksiyonlar, indexler, TTL
4. `infra/kafka/topics.sh`: topic oluşturma
5. `.env.example`
6. WSL `docker-desktop` başlatılmalı (şu an durdurulmuş)

**Onay kriteri:** `docker compose up -d` tüm servisler healthy, tablolar ve
indexler yerinde.

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

---

## Açık sorular

- BoT-SORT ReID kalitesi ölçülmedi (Aşama 2'de ID değişim sayısı sayılacak)
- Gerçek döngüde (takip + öznitelik + yayın dahil) FPS ne olacak (Aşama 2)
- Frontend Tailwind şablonu henüz sağlanmadı (Aşama 8'e kadar gerekmiyor)

Kapanan soru: 4 GB VRAM'de `yolov8s-pose` sığıyor mu — evet, 49 MiB tepe
kullanım. Çoklu kamera için de rahat yer var.

---

## Test videoları

v1 projesinde hazır pilot videolar var, Aşama 2'de kullanılacak:
`C:\Users\pc\OneDrive\Masaüstü\projeler\VideoAnomalySystem\datasets\pilot\videos`
(`normal_01`, `run_01`, `fall_01`, `zone_01`, `mixed_01`, `police_run`)
