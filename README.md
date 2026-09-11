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
- **[docs/TEZ.md](docs/TEZ.md)** — bütün ölçüm tabloları, ablation sonuçları,
  tutmayan hedefler ve kaynakça

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
| Panel | Tailwind CDN + düz HTML/JS (derleme adımı yok), Canvas API |
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
| `--model models/yolo26n-pose.pt` | küçük model — **dikkat:** ölçümde FALL sınıfını tamamen kaybediyor (`docs/TEZ.md` § 3) |
| `--model models/yolov8s-pose.pt` | ablation karşılaştırması (v8, NMS'li) |
| `--reid-model auto` | varsayılan: dedektör bedava öznitelik veriyorsa onu, vermiyorsa `models/yolo26s-reid.onnx` |
| `--no-reid` | görünüm eşleşmesini tamamen kapat (ablation) |

Öz kontroller (GPU gerekmez):

```bash
venv/Scripts/python.exe tests/test_vision_core.py
```

## Tüm sistemi çalıştırma

Kaynaklar: **dizüstünün kendi kamerası ve mp4 dosyaları.** IP/güvenlik
kamerası gerekmez; RTSP yolu kodda var ama denenmedi.

1. Yığını kaldır (Docker Desktop açıkken):

```bash
docker compose up -d
```

2. Kameraları başlat — tek süreç, tek model, N kamera:

```bash
venv\Scripts\python.exe scripts\run_pilot_cameras.py --cameras webcam_01,zone_01,run_01,fall_01
```

3. Panele gir: **http://localhost:8000** — kullanıcı `admin`, şifre
   `.env` içindeki `ADMIN_PASSWORD`.

4. Durdur: kameralarda Ctrl+C, sonra `docker compose down`.

Kamera adları veritabanından gelir (`scripts/seed_pilot.py` tohumlar, panelden
de eklenebilir). Dört kameradan fazlası 4 GB VRAM'de ölçülmedi.

### Ekranlar

| Ekran | Ne yapar |
|---|---|
| Canlı İzleme | 1 / 2x2 / 3x3 ızgara, kutu-iskelet-bölge-ID katmanları, kırmızı alarm |
| Kameralar / Kamera Detay | kamera CRUD, kamera bazlı olay geçmişi |
| Olaylar / Olay Detay | filtreler (tip, kamera, tarih, **karar kaynağı**), kanıt klibi + karesi, Türkçe LLM raporu |
| Bölgeler | kare üstünde poligon çizimi, kameraya bağlı |
| Analitik | tip dağılımı, saat ısı haritası, kural/model/hibrit kırılımı |
| Ayarlar | eşikler panelden, **yeniden başlatma yok** (~1 sn'de uygulanır) |
| Sistem Sağlığı | kamera başına FPS, düşen kare, çıkarım süresi, GPU belleği |
| Kullanıcılar / Denetim Kaydı | rol yönetimi, değişiklik kaydı |

### Uzun koşu ölçümü

Koşu çalışırken yanda:

```bash
venv\Scripts\python.exe scripts\soak_test.py --interval 60 --hours 8
```

`logs/soak.csv` biriktirir; `--report logs/soak.csv` ilk saat / son saat
karşılaştırmasını basar (FPS sapması, RAM/VRAM sızıntısı, disk büyümesi).

## Veri kümeleri ve atıf

Eğitim verisi halka açık akademik kümelerden derlenmiştir ve depoya
girmez (`scripts/fetch_datasets.py` yeniden indirir). Kullanılan kaynaklar,
lisansları ve atıf künyeleri **[docs/TEZ.md](docs/TEZ.md) § 7**'de.

## Durum

Geliştirme aşamalı ilerliyor. Hangi aşamada olunduğu ve sonraki adım için
`docs/DURUM.md` dosyasına bakınız.
