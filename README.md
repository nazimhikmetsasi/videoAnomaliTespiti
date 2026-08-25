# Video Tabanlı Anomali Tespiti ve Davranış Analizi Platformu

Gözetim kameralarından gelen canlı video akışında normal dışı hareketleri
(düşme, koşma, yasaklı alan ihlali, kavga, şüpheli dolaşma) otonom olarak
saptayan; olayları web kontrol panelinde yöneten; operatöre Türkçe doğal dil
raporu sunan ve güvenlik personeline anlık bildirim ileten platform.

## Belgeler

- **[docs/PLAN.md](docs/PLAN.md)** — dondurulmuş mimari, veritabanı şeması,
  aşama planı, ölçülebilir hedefler
- **[docs/DURUM.md](docs/DURUM.md)** — güncel ilerleme, karar günlüğü,
  bir sonraki adım

## Mimari özeti

| Katman | Teknoloji |
|---|---|
| Görü ve çıkarım | Python 3.11, OpenCV, YOLO26s-pose (CUDA/FP16, NMS'siz), BoT-SORT + YOLO26 ReID, NumPy |
| Karar | Kural motoru + TCN sınıflandırıcı (hibrit) |
| Dağıtık akış | Apache Kafka (KRaft), Spark Structured Streaming |
| Depolama | PostgreSQL (SQLAlchemy), MongoDB (PyMongo) |
| Backend | FastAPI + Uvicorn, WebSocket |
| Raporlama | Google Gemini Flash + Türkçe şablon yedeği |
| Bildirim | Telegram Bot API |
| Panel | React, Tailwind CSS, Canvas API, Recharts |
| Dağıtım | Docker Compose |

`vision/` servisi GPU erişimi için host üzerinde native venv'de çalışır.
Diğer tüm servisler Docker'da yaşar.

## Kurulum

Ayrıntılar `docs/PLAN.md` bölüm 7, Aşama 0 ve Aşama 1'de.

```bash
py -3.11 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python scripts/fetch_models.py
python scripts/check_gpu.py
```

`fetch_models.py` ağırlıkları `models/` altına indirir (`.gitignore`'da).

Altyapı (Aşama 1) — Docker Desktop çalışır durumdayken:

```bash
cp .env.example .env      # şifreleri doldur
docker compose up -d
bash scripts/check_infra.sh
```

## Görü çekirdeğini çalıştırma (Aşama 2)

```bash
venv/Scripts/python.exe -m vision.run --source data/pilot/zone_01.mp4
```

```bash
venv/Scripts/python.exe -m vision.run --source 0 --show
```

Kaynak mp4 yolu, webcam indeksi (`0`) veya `rtsp://...` olabilir. `--save
cikti.mp4` işaretlenmiş videoyu yazar, `--gmc sparseOptFlow` hareketli kamera
için telafiyi açar. Çıktı gerçek döngü FPS'ini, aşama sürelerini ve ID
kararlılık göstergelerini raporlar.

Model ve görünüm eşleştirme seçenekleri:

| bayrak | ne yapar |
|---|---|
| `--model models/yolo26n-pose.pt` | çoklu kamera / düşük bütçe modeli |
| `--model models/yolov8s-pose.pt` | ablation karşılaştırması (v8, NMS'li) |
| `--reid-model auto` | varsayılan: dedektör bedava öznitelik veriyorsa onu, vermiyorsa `models/yolo26s-reid.onnx` |
| `--no-reid` | görünüm eşleşmesini tamamen kapat (ablation) |

Öz kontroller (GPU gerekmez):

```bash
venv/Scripts/python.exe tests/test_vision_core.py
```

## Durum

Geliştirme aşamalı ilerliyor. Hangi aşamada olunduğu ve sonraki adım için
`docs/DURUM.md` dosyasına bakınız.
