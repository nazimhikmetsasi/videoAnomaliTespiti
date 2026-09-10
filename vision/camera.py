"""Kamera basina hat durumu: kaynak -> on isleme -> takip -> kural -> yayin.

Asama 10.1'de `vision/run.py`'nin `main()` govdesinden CIKARILDI. Amac coklu
kamera: `run.py` artik surucudur, N adet `CameraPipeline` kurar, hepsinden
birer kare toplar, TEK `detector(images)` cagrisi yapar ve sonuclari sahibine
dagitir. N=1 ayni koddan gecer -- tek kameralik davranis ayri bir yol
degildir, dolayisiyla sessizce ayrisamaz.

Ikinci bir `run_multi.py` yazilmadi: yazilsaydi canli yayin, kanit, kalp
atisi, JPEG kalite denetleyicisi ve rapor mantigi iki kopyada yasardi --
v1'in 435 satirlik `pipeline.py`'sinin tekrari (PLAN.md zayif nokta 12).

Cikarim BU SINIFTA yapilmaz. Toplu cagrinin tek sahibi surucudur; her
kamera kendi modelini cagirsaydi batch hic olusmazdi.
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path

import cv2
import numpy as np

from vision.evidence import EvidenceWriter, default_mongo_url
from vision.health_client import HealthClient
from vision.publish import CandidatePublisher
from vision.rules.engine import Candidate, RuleEngine, Zone
from vision.settings_client import SettingsClient
from vision.source import Frame, VideoSource
from vision.stages.features import FeatureEngine
from vision.stages.preprocess import FRAME_H, FRAME_W, Preprocessor
from vision.stages.smoother import Smoother
from vision.stages.tracker import Track, Tracker
from vision.ws_server import StreamServer

# ASAMA6_PLAN.md SS4.2: kodlama+yayin toplami butceyi tehdit ediyorsa kalite
# duser, bosluk varsa yukselir. ponytail: sabit adim (5) ve sabit esikler
# (4/8 ms) kaba bir denetleyicidir; istemci basina bant genisligi olcumu
# gerekirse buraya girer.
JPEG_QUALITY_MIN = 40
JPEG_QUALITY_MAX = 85
JPEG_QUALITY_STEP = 5

WARMUP_FRAMES = 30
KP_CONF = 0.5
# COCO 17 nokta iskelet baglantilari.
SKELETON = [
    (15, 13), (13, 11), (16, 14), (14, 12), (11, 12), (5, 11), (6, 12),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (1, 2), (0, 1), (0, 2),
    (1, 3), (2, 4), (3, 5), (4, 6),
]


def color_for(track_id: int) -> tuple[int, int, int]:
    """ID'ye gore sabit renk - ayni kisi hep ayni renkte gorunur."""
    rng = np.random.default_rng(track_id * 9781)
    return tuple(int(c) for c in rng.integers(64, 256, 3))


def draw(image: np.ndarray, tracks: list[Track],
         labels: dict[int, str] | None = None) -> np.ndarray:
    """Yalnizca hata ayiklama icindir.

    Uretimde overlay istemcide cizilir (PLAN.md zayif nokta 11). Bu fonksiyon
    ayni zamanda metadata yeterliligini kanitlar: cizim icin Track disinda
    hicbir sey kullanilmiyor.

    `labels`: track_id -> aktif aday tipi (--rules ile doldurulur, Asama 3).
    """
    out = image.copy()
    for track in tracks:
        color = color_for(track.track_id)
        x1, y1, x2, y2 = track.bbox.astype(int)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, f"ID {track.track_id} {track.conf:.2f}", (x1, max(14, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        if labels and track.track_id in labels:
            cv2.putText(out, labels[track.track_id], (x1, y2 + 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if track.keypoints is None:
            cv2.putText(out, "poz yok", (x1, y2 + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            continue

        kp = track.keypoints
        for a, b in SKELETON:
            if kp[a, 2] > KP_CONF and kp[b, 2] > KP_CONF:
                cv2.line(out, (int(kp[a, 0]), int(kp[a, 1])),
                         (int(kp[b, 0]), int(kp[b, 1])), color, 2)
        for x, y, conf in kp:
            if conf > KP_CONF:
                cv2.circle(out, (int(x), int(y)), 3, color, -1)
    return out


def next_jpeg_quality(quality: int, encode_publish_ms: float) -> int:
    """SS4.2 kurali: kodlama+yayin suresi butceyi asarsa kalite duser, bosluk
    varsa yukselir. Taban/tavan disina cikmaz."""
    if encode_publish_ms > 8.0:
        return max(JPEG_QUALITY_MIN, quality - JPEG_QUALITY_STEP)
    if encode_publish_ms < 4.0:
        return min(JPEG_QUALITY_MAX, quality + JPEG_QUALITY_STEP)
    return quality


def build_meta(camera_id: str, frame_idx: int, ts: float, width: int, height: int,
                fps: float, tracks: list[Track], zones: list[Zone],
                pre_alarms: list[Candidate], stage_ms: dict[str, float]) -> dict:
    """`/ws/meta` govdesi (SS4.1). Overlay istemcide cizilir (PLAN.md zayif
    nokta 11): bbox islenen kare uzayinda PIKSEL, zones 0-1 NORMALIZE kalir.
    Pozsuz iz `kp: null` alir -- "pozsuz iz takipte gosterilir ama anomali
    uretmez" kuralinin panele yansimasi."""
    return {
        "schema": 1,
        "camera_id": camera_id,
        "frame_idx": frame_idx,
        "ts": ts,
        "width": width, "height": height,
        "fps": round(fps, 1),
        "tracks": [
            {
                "id": t.track_id,
                "bbox": [float(v) for v in t.bbox],
                "conf": float(t.conf),
                "kp": t.keypoints.tolist() if t.keypoints is not None else None,
                "has_pose": t.keypoints is not None,
            }
            for t in tracks
        ],
        "zones": [
            {"name": z.name, "type": z.zone_type, "polygon": z.polygon.tolist()}
            for z in zones
        ],
        "pre_alarms": [
            {"type": c.anomaly_type, "track_ids": c.track_ids, "score": float(c.score)}
            for c in pre_alarms
        ],
        "stage_ms": stage_ms,
    }




class CameraPipeline:
    """Tek kameranin tum durumu. Cikarim disarida, toplu yapilir."""

    def __init__(self, source: str, args, *, reid_model: str,
                 stream_server: StreamServer | None = None,
                 camera_id: str = "", zones_stem: str = "") -> None:
        self.args, self.source_arg = args, source
        self.stream_server = stream_server
        self.preprocess = Preprocessor(clahe=not args.no_clahe)
        self.tracker = Tracker(device=args.device, gmc_method=args.gmc,
                               with_reid=not args.no_reid, model=reid_model)
        self.smoother = Smoother() if args.rules else None
        self.feature_engine = FeatureEngine() if args.rules else None
        self.rule_engine = None
        self.zones_stem = zones_stem or Path(str(source)).stem
        self._camera_id_override = camera_id

        self.source = VideoSource(source, loop=args.loop)
        self.publisher: CandidatePublisher | None = None
        self.settings_client: SettingsClient | None = None
        self.evidence_writer: EvidenceWriter | None = None
        self.health_client: HealthClient | None = None

        self.all_candidates: list[Candidate] = []
        self.pre_ms: list[float] = []
        self.infer_ms: list[float] = []
        self.track_ms: list[float] = []
        self.smooth_ms: list[float] = []
        self.rules_ms: list[float] = []
        self.publish_ms: list[float] = []
        self.ws_ms: list[float] = []
        self.loop_ms: list[float] = []
        self.per_frame_counts: list[int] = []
        self.late_new_ids = self.pose_missing = self.track_total = self.frames = 0
        self.jpeg_quality = args.jpeg_quality
        self.started = time.perf_counter()
        self.elapsed = 0.0
        self.idle_since: float | None = None
        self.finished = False
        self.outages = 0            # canli kaynagin kac kez sessiz kaldigi
        self.camera_id = ""
        self.epoch_base = 0.0
        self._loop_start = 0.0
        self._known_ids: set[int] = set()

    # ------------------------------------------------------------------ kurulum
    def start(self) -> None:
        """Kaynagi ve yardimci istemcileri ayaga kaldirir."""
        args = self.args
        self.source.start()
        self.camera_id = self._camera_id_override
        if not self.camera_id and (args.kafka or args.settings_url or args.ws or args.evidence):
            self.camera_id = (f"cam-{self.source_arg}"
                              if self.source.source_type == "webcam" else self.zones_stem)
        # Canli kaynakta cand.ts zaten epoch'tur (epoch_base=0.0); dosya
        # kaynaginda sahne zamani duvar saatinden farkli akabilir (SS2).
        # publish.py'daki candidate_to_dict ile AYNI anlasma: events.started_at
        # (Spark/consumer) bu epoch_base + cand.ts'ten gelir; evidence.py'nin
        # POST /api/evidence govdesi eslesebilmek icin ayni degeri kullanir.
        self.epoch_base = (0.0 if self.source.is_live else time.time()) if args.rules else 0.0
        print(f"  kaynak: {self.source_arg} ({self.source.source_type}), model: {args.model}")

        if args.rules:
            zones = load_zones(args.zones, self.zones_stem) if args.zones else []
            self.rule_engine = build_engine(args, zones)
        if args.kafka and args.rules:
            self.publisher = CandidatePublisher(args.kafka, self.camera_id,
                                                epoch_base=self.epoch_base)
            print(f"  Kafka: {args.kafka} -> {self.publisher.topic} "
                  f"(camera_id={self.camera_id})")
        if args.settings_url and args.rules:
            self.settings_client = SettingsClient(
                args.settings_url, self.camera_id, self.rule_engine,
                interval=args.settings_interval, token=args.settings_token or None)
            self.settings_client.start()
            print(f"  esik sicak yukleme: {args.settings_url} "
                  f"(camera_id={self.camera_id}, interval={args.settings_interval}s)")
        if args.evidence and args.rules:
            self.evidence_writer = EvidenceWriter(
                self.source, storage_dir=args.storage_dir,
                api_base_url=args.settings_url, token=args.settings_token or "",
                mongo_url=default_mongo_url(), epoch_base=self.epoch_base)
            self.evidence_writer.start()
            print(f"  kanit uretimi: acik (storage_dir={args.storage_dir})")
        if args.heartbeat_sec > 0 and args.settings_url and self.camera_id:
            # ws_port yalniz StreamServer GERCEKTEN acildiysa yazilir (JWT_SECRET
            # yoksa acilmaz) -- panel olmayan bir porta korlemesine baglanmasin.
            opened = self.stream_server is not None and self.stream_server.opened
            self.health_client = HealthClient(
                args.settings_url, self.camera_id, self.source,
                interval=args.heartbeat_sec, token=args.settings_token or None,
                mongo_url=default_mongo_url(),
                ws_port=args.ws_port if opened else None)
            self.health_client.start()
            print(f"  kalp atisi: {args.settings_url} (interval={args.heartbeat_sec}s)")

    # -------------------------------------------------------------------- dongu
    def read(self, timeout: float = 2.0) -> Frame | None:
        """Kare yoksa None. Kaynak bittiginde/oldugunde `finished` isaretlenir."""
        frame = self.source.read(timeout=timeout)
        if frame is None:
            if self.source.eof.is_set():          # yalnizca dosya kaynagi kurar
                self._finish()
            else:
                self.idle_since = self.idle_since or time.monotonic()
                if time.monotonic() - self.idle_since > LIVE_WAIT_SEC:
                    # Canli kaynak KALICI olarak bitmis sayilmaz. Onceden
                    # sayilirdi ve bir daha hic okunmuyordu: webcam acilista
                    # 30 sn'yi asinca kamera sessizce olu kaldi, kuyrugu dolu
                    # oldugu icin dusen kare durmadan arti (olculdu: 955).
                    # VideoSource'un ustel geri cekilmeli yeniden baglanmasi
                    # ancak okumaya devam edilirse ise yarar. Dosya kaynagi
                    # gercekten biter (eof), canli kaynak bitmez.
                    self.outages += 1
                    print(f"  {self.camera_id or self.source_arg}: kaynak "
                          f"{LIVE_WAIT_SEC:.0f} sn kare vermedi "
                          f"({self.source.last_error or 'sebep bilinmiyor'}), "
                          f"beklemeye devam ({self.outages}. kesinti)")
                    self.idle_since = time.monotonic()
            return None
        self.idle_since = None
        if self.frames == 0:
            # Sayac ilk karede baslar: webcam/RTSP acilis suresi (bu makinede
            # ~5 sn) FPS'i yanlis dusuk gostermesin.
            self.started = time.perf_counter()
        self._loop_start = time.perf_counter()
        return frame

    def _finish(self) -> None:
        """Kaynak bitti. Sure BURADA durur: coklu kamerada kisa klibi biten
        kamera, digerleri kosarken gecen sureyi kendi FPS'ine yazmamali."""
        self.finished = True
        self.elapsed = time.perf_counter() - self.started

    def prepare(self, frame: Frame) -> np.ndarray:
        t0 = time.perf_counter()
        image = self.preprocess(frame.image)
        self.pre_ms.append((time.perf_counter() - t0) * 1000)
        return image

    def consume(self, frame: Frame, image: np.ndarray, result, infer_ms: float) -> None:
        """Cikarim sonucundan sonrasi: takip, kural, yayin, kanit, olcum."""
        args = self.args
        self.infer_ms.append(infer_ms)
        t2 = time.perf_counter()
        self._known_ids = set(self.tracker.seen_ids)
        tracks = self.tracker.update(result, image)
        self.track_ms.append((time.perf_counter() - t2) * 1000)

        active_labels: dict[int, str] = {}
        candidates: list[Candidate] = []
        ts = frame.ts if self.source.is_live else frame.idx / self.source.fps
        if args.rules:
            t4 = time.perf_counter()
            tracks = self.smoother(tracks, ts)
            t5 = time.perf_counter()
            windows = self.feature_engine(tracks, frame.idx, ts, image.shape[:2])
            candidates = self.rule_engine(windows)
            t6 = time.perf_counter()
            self.smooth_ms.append((t5 - t4) * 1000)
            self.rules_ms.append((t6 - t5) * 1000)
            self.all_candidates.extend(candidates)
            if self.publisher is not None:
                tp0 = time.perf_counter()
                self.publisher(candidates)
                self.publish_ms.append((time.perf_counter() - tp0) * 1000)
            for cand in candidates:
                for tid in cand.track_ids:
                    active_labels[tid] = cand.anomaly_type

        if self.evidence_writer is not None:
            # I/O yok -- epizot takibi hafif, ana dongude guvenle cagrilir.
            self.evidence_writer.on_frame(self.camera_id, frame.idx, ts, frame.ts,
                                          tracks, candidates)
        if self.stream_server is not None:
            self._publish_ws(frame, image, tracks, candidates)

        if self.health_client is not None:
            self.health_client.note(
                self.frames / (time.perf_counter() - self.started + 1e-9), infer_ms)

        self.frames += 1
        self.per_frame_counts.append(len(tracks))
        self.track_total += len(tracks)
        self.pose_missing += sum(1 for t in tracks if t.keypoints is None)
        if self.frames > WARMUP_FRAMES:
            self.late_new_ids += len(self.tracker.seen_ids - self._known_ids)
        self.last_tracks, self.last_labels = tracks, active_labels
        self.loop_ms.append((time.perf_counter() - self._loop_start) * 1000)

    def _publish_ws(self, frame: Frame, image: np.ndarray, tracks: list[Track],
                    candidates: list[Candidate]) -> None:
        # SS3/SS12 olcum 3: dinleyen yoksa NE meta kurulur NE JPEG kodlanir.
        # Iki akis AYRI sayilir -- yalniz meta dinleyen bir istemci kare
        # kodlamasini baslatmamali.
        tw0 = time.perf_counter()
        if self.stream_server.meta_clients > 0:
            stage_ms = {"pre": self.pre_ms[-1], "infer": self.infer_ms[-1],
                        "track": self.track_ms[-1]}
            if self.args.rules:
                stage_ms["rules"] = self.rules_ms[-1]
            recent = self.loop_ms[-30:]
            fps_now = 1000.0 / (sum(recent) / len(recent)) if recent else 0.0
            self.stream_server.publish_meta(self.camera_id, build_meta(
                self.camera_id, frame.idx, frame.ts, FRAME_W, FRAME_H, fps_now,
                tracks, self.rule_engine.zones if self.rule_engine else [],
                candidates, stage_ms))
        if self.stream_server.live_clients > 0:
            # SS4.2 denetleyicisine YALNIZ kodlama+yayin suresi girer; tw0'dan
            # olcmek meta kurulumunu da iceri katar ve kaliteyi yanlis yere
            # dusururdu.
            te0 = time.perf_counter()
            ok, buf = cv2.imencode(".jpg", image,
                                   [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            if ok:
                self.stream_server.publish_frame(self.camera_id, buf.tobytes())
            self.jpeg_quality = next_jpeg_quality(
                self.jpeg_quality, (time.perf_counter() - te0) * 1000)
        # Kosulsuz olculur: sifir istemcideki maliyet de raporda gorunmeli.
        self.ws_ms.append((time.perf_counter() - tw0) * 1000)

    # -------------------------------------------------------------------- kapan
    def close(self) -> None:
        if not self.finished:
            self.elapsed = time.perf_counter() - self.started
        self.last_error = self.source.last_error
        self.dropped, self.reconnects = self.source.frames_dropped, self.source.reconnects
        if self.evidence_writer is not None:
            # Dosya EOF: kalan acik epizotlar `gap_sec`'lik sessizligi hic
            # gormeden zorla kapatilir (bkz. evidence.py flush() docstring).
            self.evidence_writer.flush(self.camera_id)
        self.source.stop()
        if self.publisher is not None:
            self.publisher.close(eos=True)
        if self.settings_client is not None:
            self.settings_client.stop()
        if self.health_client is not None:
            self.health_client.stop()
        if self.evidence_writer is not None:
            self.evidence_writer.stop()


# Asagidakiler run.py'den cagrilir; dongusel import olmasin diye burada.
LIVE_WAIT_SEC = 30.0


def load_zones(path: str, clip_stem: str) -> list[Zone]:
    """Bolge JSON'u yukler (Asama 3 SS7 formati): {klip_adi: [bolge, ...], "_...": not}.

    "_" ile baslayan anahtarlar not/yorumdur; `clip_stem` anahtar olarak
    aranmadigi icin kendiliginden atlanir. Klip icin bolge yoksa (cogu pilot
    klip icin durum budur) sessizce bos liste doner.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    zones = []
    for entry in data.get(clip_stem, []):
        zones.append(Zone(
            name=entry["name"],
            zone_type=entry["zone_type"],
            polygon=np.array(entry["polygon"], dtype=np.float32),
            active_from=datetime.time.fromisoformat(entry["active_from"])
                if entry.get("active_from") else None,
            active_to=datetime.time.fromisoformat(entry["active_to"])
                if entry.get("active_to") else None,
        ))
    return zones


def build_engine(args, zones: list[Zone]):
    """Kural motoru; TCN agirligi varsa HybridArbiter ile sarilir."""
    engine = RuleEngine(zones=zones)
    if args.no_tcn:
        return engine
    # Model yoksa (henuz egitilmedi / agirlik indirilmedi) hat aynen kural
    # motoruyla calisir -- Asama 9 oncesi davranis korunur.
    try:
        from models.tcn import TCNClassifier
        from vision.rules.arbiter import HybridArbiter
        wrapped = HybridArbiter(engine, TCNClassifier(args.device),
                                min_conf=args.tcn_min_conf)
        print(f"  TCN hakemi acik (tcn_min_conf={args.tcn_min_conf})")
        return wrapped
    except (FileNotFoundError, OSError, KeyError) as exc:
        print(f"  TCN agirligi yok, yalniz kural: {exc}")
        return engine
