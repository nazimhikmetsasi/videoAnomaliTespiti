"""Asama 2 giris noktasi: kaynak -> on isleme -> pose -> takip.

Gercek dongude olculur (Asama 0'daki tek kare `predict()` olcumu degil):
kare basina asama sureleri, gercek FPS ve ID kararlilik gostergeleri.

Calistirma:
    venv\\Scripts\\python.exe -m vision.run --source data/test.mp4
    venv\\Scripts\\python.exe -m vision.run --source 0 --show
    venv\\Scripts\\python.exe -m vision.run --source rtsp://... --save out.mp4
    venv\\Scripts\\python.exe -m vision.run --source data/pilot/zone_01.mp4 --rules --zones eval/zones.json
    venv\\Scripts\\python.exe -m vision.run --source data/pilot/run_01.mp4 --rules --kafka

ID degisimi olcumu: etiketli gercek referans olmadan tam sayilamaz. Burada
pratik gosterge, isinma sonrasi (varsayilan 30 kare) yaratilan YENI ID
sayisidir. Kadro degismeyen bir sahnede bu sayi dogrudan ID degisimidir.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from vision.evidence import EvidenceWriter, default_mongo_url
from vision.health_client import HealthClient
from vision.publish import CandidatePublisher
from vision.rules.engine import Candidate, RuleEngine, Zone
from vision.settings_client import SettingsClient
from vision.source import VideoSource
from vision.stages.features import FeatureEngine
from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
from vision.stages.preprocess import FRAME_H, FRAME_W, Preprocessor
from vision.stages.smoother import Smoother
from vision.stages.tracker import DEFAULT_REID, OVERRIDES, Track, Tracker
from vision.ws_server import StreamServer

# ASAMA6_PLAN.md SS4.2: kodlama+yayin toplami butceyi tehdit ediyorsa kalite
# duser, bosluk varsa yukselir. ponytail: sabit adim (5) ve sabit esikler
# (4/8 ms) kaba bir denetleyicidir; istemci basina bant genisligi olcumu
# gerekirse buraya girer.
JPEG_QUALITY_MIN = 40
JPEG_QUALITY_MAX = 85
JPEG_QUALITY_STEP = 5

WARMUP_FRAMES = 30
# Webcam acilisi bu makinede ~5 sn suruyor, RTSP yeniden baglanmasi daha da
# uzun. Canli kaynakta tek bir zaman asimi akisin bittigi anlamina gelmez;
# bu sure boyunca hic kare gelmezse pes edilir.
LIVE_WAIT_SEC = 30.0
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Asama 2 goru cekirdegi")
    parser.add_argument("--source", required=True,
                        help="mp4 yolu, webcam indeksi (0) veya rtsp://...")
    parser.add_argument("--model", default=DEFAULT_WEIGHTS)
    parser.add_argument("--device", default="cuda")
    # YOLO26 end2end kafasi ayni tespite YOLOv8'den daha dusuk skor verir:
    # police_run klibinde v8@0.35 = 193 izli kare, yolo26@0.35 = 132,
    # yolo26@0.25 = 191. Esik modelle birlikte kalibre edildi.
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=FRAME_W)
    parser.add_argument("--max-frames", type=int, default=0, help="0 = sinirsiz")
    parser.add_argument("--loop", action="store_true",
                        help="dosya kaynagi bitince basa sarar (canlida yok sayilir); "
                             "--max-frames verilmisse yine ona uyar")
    parser.add_argument("--no-clahe", action="store_true")
    parser.add_argument("--gmc", default=OVERRIDES["gmc_method"],
                        help="kamera hareketi telafisi: none|sparseOptFlow|orb|sift|ecc")
    parser.add_argument("--no-reid", action="store_true",
                        help="gorunum eslesmesini tamamen kapat (ablation)")
    parser.add_argument("--reid-model", default="auto",
                        help=f"auto = dedektor bedava oznitelik veriyorsa onu "
                             f"kullan, vermiyorsa {DEFAULT_REID}; ya da acik yol")
    parser.add_argument("--show", action="store_true", help="pencerede goster, q ile cik")
    parser.add_argument("--save", default="", help="isaretlenmis videoyu bu yola yaz")
    parser.add_argument("--rules", action="store_true",
                        help="duzleme+oznitelik+kural zincirini calistir (Asama 3)")
    parser.add_argument("--no-tcn", action="store_true",
                        help="TCN hakemini kapat, yalniz kural (Asama 9 ablation)")
    parser.add_argument("--tcn-min-conf", type=float, default=0.60,
                        help="model guveni bunun altindaysa karar kurala duser")
    parser.add_argument("--zones", default="",
                        help="bolge JSON yolu (SS7 formati); verilmezse bos bolge listesi")
    parser.add_argument("--kafka", nargs="?",
                        const=os.getenv("KAFKA_BOOTSTRAP_HOST", "localhost:9092"),
                        default="", help="aday olaylari Kafka'ya bas (varsayilan bootstrap: env)")
    parser.add_argument("--camera-id", default="", help="bos = kaynak dosya adi / webcam indeksi")
    parser.add_argument("--settings-url", default="",
                        help="esik API taban URL'i, orn. http://localhost:8000 (bos = sicak yukleme kapali)")
    parser.add_argument("--settings-interval", type=float, default=5.0)
    parser.add_argument("--settings-token", default="", help="bos = jetonsuz istek")
    parser.add_argument("--ws", action="store_true",
                        help="WebSocket sunucusunu ac (varsayilan kapali)")
    parser.add_argument("--ws-port", type=int, default=8001)
    parser.add_argument("--jpeg-quality", type=int, default=70,
                        help="baslangic kalitesi (adaptif, SS4.2)")
    parser.add_argument("--evidence", action="store_true",
                        help="kanit uretimini ac (SS5)")
    parser.add_argument("--storage-dir", default="storage", help="klip ve kare kok dizini")
    parser.add_argument("--heartbeat-sec", type=float, default=5.0, help="0 = kapali (SS7)")
    return parser.parse_args(argv)


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


def choose_reid(requested: str, disabled: bool, native_feats: bool) -> tuple[str, str]:
    """ReID yolunu sec ve rapora yazilacak tek satirlik aciklamayi dondur.

    `auto`: dedektor bedava govde oznitelikleri veriyorsa (end2end olmayan
    model) onlar kullanilir; vermiyorsa (YOLO26) ayri ReID agina dusulur.
    """
    if disabled:
        return "auto", "kapali (--no-reid), takip yalnizca hareket tabanli"
    if requested != "auto":
        return requested, f"ayri ag: {requested} (elle secildi)"
    if native_feats:
        return "auto", "dedektorun kendi oznitelikleri (bedava, ek cikarim yok)"
    return DEFAULT_REID, f"ayri ag: {DEFAULT_REID} (dedektor end2end, bedava oznitelik yok)"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    preprocess = Preprocessor(clahe=not args.no_clahe)
    detector = PoseDetector(args.model, device=args.device, conf=args.conf,
                            imgsz=args.imgsz, reid_feats=not args.no_reid)
    reid_model, reid_note = choose_reid(args.reid_model, args.no_reid,
                                        detector.has_reid_feats)
    tracker = Tracker(device=args.device, gmc_method=args.gmc,
                      with_reid=not args.no_reid, model=reid_model)
    print(f"  ReID: {reid_note}")

    smoother = Smoother() if args.rules else None
    feature_engine = FeatureEngine() if args.rules else None
    rule_engine = None
    all_candidates: list[Candidate] = []
    if args.rules:
        zones = load_zones(args.zones, Path(str(args.source)).stem) if args.zones else []
        rule_engine = RuleEngine(zones=zones)
        if not args.no_tcn:
            # Model yoksa (henuz egitilmedi / agirlik indirilmedi) hat aynen
            # kural motoruyla calisir -- Asama 9 oncesi davranis korunur.
            try:
                from models.tcn import TCNClassifier
                from vision.rules.arbiter import HybridArbiter
                rule_engine = HybridArbiter(rule_engine, TCNClassifier(args.device),
                                            min_conf=args.tcn_min_conf)
                print(f"  TCN hakemi acik (tcn_min_conf={args.tcn_min_conf})")
            except (FileNotFoundError, OSError, KeyError) as exc:
                print(f"  TCN agirligi yok, yalniz kural: {exc}")

    writer = None
    pre_ms, infer_ms, track_ms, smooth_ms, rules_ms, loop_ms, publish_ms = [], [], [], [], [], [], []
    ws_ms = []
    per_frame_counts = []
    late_new_ids = pose_missing = track_total = frames = 0
    started = time.perf_counter()
    idle_since: float | None = None
    publisher: CandidatePublisher | None = None
    settings_client: SettingsClient | None = None
    stream_server: StreamServer | None = None
    evidence_writer: EvidenceWriter | None = None
    health_client: HealthClient | None = None
    jpeg_quality = args.jpeg_quality

    with VideoSource(args.source, loop=args.loop) as source:
        print(f"  kaynak: {args.source} ({source.source_type}), model: {args.model}")
        camera_id = ""
        if args.kafka or args.settings_url or args.ws or args.evidence:
            camera_id = args.camera_id or (
                f"cam-{args.source}" if source.source_type == "webcam"
                else Path(str(args.source)).stem)
        # Canli kaynakta cand.ts zaten epoch'tur (epoch_base=0.0); dosya
        # kaynaginda sahne zamani duvar saatinden farkli akabilir (SS2).
        # publish.py'daki candidate_to_dict ile AYNI anlasma: events.started_at
        # (Spark/consumer) bu epoch_base + cand.ts'ten gelir; evidence.py'nin
        # POST /api/evidence govdesi eslesebilmek icin ayni degeri kullanir
        # (ASAMA6_PLAN.md SS8.2). args.rules olmadan cand.ts hic uretilmez.
        epoch_base = (0.0 if source.is_live else time.time()) if args.rules else 0.0
        if args.kafka and args.rules:
            publisher = CandidatePublisher(args.kafka, camera_id, epoch_base=epoch_base)
            print(f"  Kafka: {args.kafka} -> {publisher.topic} (camera_id={camera_id})")
        if args.settings_url and args.rules:
            settings_client = SettingsClient(
                args.settings_url, camera_id, rule_engine,
                interval=args.settings_interval, token=args.settings_token or None)
            settings_client.start()
            print(f"  esik sicak yukleme: {args.settings_url} "
                  f"(camera_id={camera_id}, interval={args.settings_interval}s)")
        if args.ws:
            # JWT_SECRET ortamdan okunur -- yoksa StreamServer.start() sunucuyu
            # ACMAZ ve tek satir uyari basar (ASAMA6_PLAN.md SS3). Varsayilan
            # DEGER verilmez: api/config.py'nin "dev-secret-change-me" yedegi
            # burada BILEREK tekrarlanmiyor -- kimliksiz yayin kabul edilemez.
            stream_server = StreamServer(port=args.ws_port, jwt_secret=os.getenv("JWT_SECRET"))
            stream_server.start()
            print(f"  WebSocket: ws://localhost:{args.ws_port}/ws/live|meta/{camera_id}"
                  + ("" if stream_server.opened else " (ACILAMADI)"))
        if args.evidence and args.rules:
            evidence_writer = EvidenceWriter(
                source, storage_dir=args.storage_dir,
                api_base_url=args.settings_url, token=args.settings_token or "",
                mongo_url=default_mongo_url(), epoch_base=epoch_base)
            evidence_writer.start()
            print(f"  kanit uretimi: acik (storage_dir={args.storage_dir})")
        if args.heartbeat_sec > 0 and args.settings_url and camera_id:
            # ws_port yalniz StreamServer GERCEKTEN acildiysa yazilir (JWT_SECRET
            # yoksa acilmaz, bkz. yukarida) -- panel olmayan bir porta korlemesine
            # baglanmaya calismasin (ASAMA8_PLAN.md 8.6 SS3).
            health_client = HealthClient(
                args.settings_url, camera_id, source,
                interval=args.heartbeat_sec, token=args.settings_token or None,
                mongo_url=default_mongo_url(),
                ws_port=args.ws_port if (stream_server is not None and stream_server.opened) else None)
            health_client.start()
            print(f"  kalp atisi: {args.settings_url} (interval={args.heartbeat_sec}s)")
        while True:
            frame = source.read()
            if frame is None:
                if source.eof.is_set():      # yalnizca dosya kaynagi bunu kurar
                    break
                idle_since = idle_since or time.monotonic()
                if time.monotonic() - idle_since > LIVE_WAIT_SEC:
                    print(f"  kaynak {LIVE_WAIT_SEC:.0f} sn kare vermedi: "
                          f"{source.last_error or 'sebep bilinmiyor'}")
                    break
                continue
            idle_since = None
            if frames == 0:
                # Sayac ilk karede baslar: webcam/RTSP acilis suresi (bu
                # makinede ~5 sn) FPS'i yanlis dusuk gostermesin.
                started = time.perf_counter()

            loop_start = time.perf_counter()

            t0 = time.perf_counter()
            image = preprocess(frame.image)
            t1 = time.perf_counter()
            result = detector([image])[0]
            t2 = time.perf_counter()
            known = set(tracker.seen_ids)
            tracks = tracker.update(result, image)
            t3 = time.perf_counter()

            pre_ms.append((t1 - t0) * 1000)
            infer_ms.append((t2 - t1) * 1000)
            track_ms.append((t3 - t2) * 1000)

            active_labels: dict[int, str] = {}
            candidates: list[Candidate] = []
            if args.rules:
                # Video zamani: dosya kaynaginda kare indeksi/FPS, canlida duvar
                # saati. Smoother ve FeatureEngine'in tek zaman kaynagi budur.
                ts = frame.idx / source.fps if not source.is_live else frame.ts
                t4 = time.perf_counter()
                tracks = smoother(tracks, ts)
                t5 = time.perf_counter()
                windows = feature_engine(tracks, frame.idx, ts, image.shape[:2])
                candidates = rule_engine(windows)
                t6 = time.perf_counter()
                smooth_ms.append((t5 - t4) * 1000)
                rules_ms.append((t6 - t5) * 1000)
                all_candidates.extend(candidates)
                if publisher is not None:
                    tp0 = time.perf_counter()
                    publisher(candidates)
                    publish_ms.append((time.perf_counter() - tp0) * 1000)
                for cand in candidates:
                    for tid in cand.track_ids:
                        active_labels[tid] = cand.anomaly_type

            if evidence_writer is not None:
                # I/O yok -- epizot takibi hafif, ana dongude guvenle cagrilir.
                # `ts` sahne zamani (candidate.ts ile ayni saat), `frame.ts`
                # duvar saati (halka tampon eslesmesi icin, bkz. evidence.py).
                evidence_writer.on_frame(camera_id, frame.idx, ts, frame.ts, tracks, candidates)

            if stream_server is not None:
                # SS3/SS12 olcum 3: dinleyen yoksa NE meta kurulur NE JPEG
                # kodlanir. Iki akis AYRI sayilir -- yalniz meta dinleyen bir
                # istemci kare kodlamasini baslatmamali.
                tw0 = time.perf_counter()
                if stream_server.meta_clients > 0:
                    stage_ms = {"pre": pre_ms[-1], "infer": infer_ms[-1], "track": track_ms[-1]}
                    if args.rules:
                        stage_ms["rules"] = rules_ms[-1]
                    recent_loop = loop_ms[-30:]
                    fps_now = 1000.0 / (sum(recent_loop) / len(recent_loop)) if recent_loop else 0.0
                    meta = build_meta(camera_id, frame.idx, frame.ts, FRAME_W, FRAME_H, fps_now,
                                       tracks, rule_engine.zones if rule_engine else [],
                                       candidates, stage_ms)
                    stream_server.publish_meta(camera_id, meta)
                if stream_server.live_clients > 0:
                    # SS4.2 denetleyicisine YALNIZ kodlama+yayin suresi girer;
                    # tw0'dan olcmek meta kurulumunu da iceri katar ve kaliteyi
                    # yanlis yere dusururdu.
                    te0 = time.perf_counter()
                    ok, buf = cv2.imencode(".jpg", image,
                                           [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                    if ok:
                        stream_server.publish_frame(camera_id, buf.tobytes())
                    jpeg_quality = next_jpeg_quality(
                        jpeg_quality, (time.perf_counter() - te0) * 1000)
                # Kosulsuz olculur: sifir istemcideki maliyet de raporda
                # gorunmeli, yoksa SS12 olcum 3 kendi kor noktasini olcerdi.
                ws_ms.append((time.perf_counter() - tw0) * 1000)

            if health_client is not None:
                health_client.note(frames / (time.perf_counter() - started + 1e-9), infer_ms[-1])

            frames += 1
            per_frame_counts.append(len(tracks))
            track_total += len(tracks)
            pose_missing += sum(1 for t in tracks if t.keypoints is None)
            if frames > WARMUP_FRAMES:
                late_new_ids += len(tracker.seen_ids - known)

            if args.show or args.save:
                annotated = draw(image, tracks, active_labels)
                if args.save:
                    if writer is None:
                        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
                        writer = cv2.VideoWriter(args.save,
                                                 cv2.VideoWriter_fourcc(*"mp4v"),
                                                 25.0, (FRAME_W, FRAME_H))
                    writer.write(annotated)
                if args.show:
                    cv2.imshow("vision", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

            loop_ms.append((time.perf_counter() - loop_start) * 1000)
            if args.max_frames and frames >= args.max_frames:
                break

        elapsed = time.perf_counter() - started
        last_error = source.last_error
        dropped, reconnects = source.frames_dropped, source.reconnects

        if evidence_writer is not None:
            # Dosya EOF: kalan acik epizotlar `gap_sec`'lik sessizligi hic
            # gormeden zorla kapatilir (bkz. evidence.py flush() docstring).
            evidence_writer.flush(camera_id)

    if publisher is not None:
        publisher.close(eos=True)
    if settings_client is not None:
        settings_client.stop()
    if health_client is not None:
        health_client.stop()
    if evidence_writer is not None:
        evidence_writer.stop()
    if stream_server is not None:
        stream_server.stop()

    if writer is not None:
        writer.release()
    if args.show:
        cv2.destroyAllWindows()
    detector.close()

    if frames == 0:
        print(f"  HATA: hic kare okunamadi. {last_error or ''}")
        return 1

    active_frames = sum(1 for c in per_frame_counts if c)
    max_persons = max(per_frame_counts)
    mean_persons = track_total / active_frames if active_frames else 0.0
    unique_ids = len(tracker.seen_ids)

    print("\n" + "=" * 62)
    print("ASAMA 2 - GERCEK DONGU RAPORU")
    print("=" * 62)
    print(f"  kare sayisi          : {frames}  ({elapsed:.1f} sn)")
    print(f"  gercek FPS           : {frames / elapsed:.1f}")
    print(f"  dusen kare (kaynak)  : {dropped}")
    print(f"  yeniden baglanma     : {reconnects}")
    print(f"  CLAHE uygulandi      : {preprocess.clahe_applied} / {frames}")
    print(f"\n  {'asama':<20} {'medyan ms':>10} {'p95 ms':>10}")
    stage_rows = [("on isleme", pre_ms), ("cikarim", infer_ms), ("takip", track_ms)]
    if args.rules:
        stage_rows += [("duzleme", smooth_ms), ("oznitelik+kural", rules_ms)]
    if publisher is not None and publish_ms:
        stage_rows.append(("kafka publish", publish_ms))
    if getattr(rule_engine, "model_ms", None):
        # TCN suresi "kural" satirinin ICINDEdir; ayrica gosterilir ki
        # hakemin bedeli ablationda gorunsun.
        stage_rows.append(("  ^ TCN cikarimi", rule_engine.model_ms))
    if stream_server is not None and ws_ms:
        stage_rows.append(("ws kodlama+yayin", ws_ms))
    stage_rows.append(("dongu toplam", loop_ms))
    for name, samples in stage_rows:
        p95 = sorted(samples)[min(len(samples) - 1, int(len(samples) * 0.95))]
        print(f"  {name:<20} {statistics.median(samples):>10.1f} {p95:>10.1f}")

    print(f"\n  benzersiz ID         : {unique_ids}")
    print(f"  es zamanli en cok    : {max_persons} kisi")
    print(f"  kare basina ortalama : {mean_persons:.2f} kisi")
    if max_persons:
        print(f"  ID / es zamanli      : {unique_ids / max_persons:.2f}"
              "   (1.00 = hic ID degisimi yok)")
    print(f"  isinma sonrasi yeni ID: {late_new_ids}  (ilk {WARMUP_FRAMES} kare haric)")
    print(f"  pozsuz iz            : {pose_missing} / {track_total}")

    if args.rules:
        print("\n  aday olay ozeti (--rules):")
        if all_candidates:
            by_type: dict[str, list[Candidate]] = {}
            for cand in all_candidates:
                by_type.setdefault(cand.anomaly_type, []).append(cand)
            for anomaly_type in sorted(by_type):
                cands = by_type[anomaly_type]
                track_ids = {tid for c in cands for tid in c.track_ids}
                first_ts = min(c.ts for c in cands)
                print(f"    {anomaly_type:<16} aday {len(cands):>5}  "
                      f"iz {len(track_ids):>3}  ilk tetik {first_ts:>6.1f} sn")
        else:
            print("    aday yok")

    if publisher is not None:
        print(f"\n  kafka yayin           : yayinlanan {publisher.published}  "
              f"kuyruga alinan {publisher.queued}  basarisiz {publisher.failed}")
        if publisher.last_error:
            print(f"  kafka son hata        : {publisher.last_error}")

    if settings_client is not None:
        print(f"\n  esik sicak yukleme    : {settings_client.applied} kez uygulandi, "
              f"{settings_client.failures} hata")
        if settings_client.last_error:
            print(f"  esik son hata         : {settings_client.last_error}")

    if stream_server is not None:
        print(f"\n  WebSocket             : acildi={stream_server.opened}  "
              f"son gorulen istemci sayisi={stream_server.live_clients}  "
              f"bitis kalitesi={jpeg_quality}")

    if evidence_writer is not None:
        print(f"\n  kanit                 : klip {evidence_writer.written_clips}  "
              f"kare {evidence_writer.written_frames}  "
              f"POST basarili {evidence_writer.posted}  basarisiz {evidence_writer.post_failed}  "
              f"mongo hata {evidence_writer.mongo_failed}  kuyruktan dusen {evidence_writer.dropped}")
        if evidence_writer.last_error:
            print(f"  kanit son hata        : {evidence_writer.last_error}")

    if health_client is not None:
        print(f"\n  kalp atisi            : gonderilen {health_client.sent}  "
              f"hata {health_client.failures}")
        if health_client.last_error:
            print(f"  kalp atisi son hata   : {health_client.last_error}")

    if args.save:
        print(f"\n  video yazildi        : {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
