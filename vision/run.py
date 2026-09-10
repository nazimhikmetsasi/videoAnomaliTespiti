"""Goru surucusu: N kamera, TEK model, tek toplu cikarim cagrisi.

Kamera basina durumun tamami `vision/camera.py`'deki `CameraPipeline`'dadir;
bu dosya yalnizca surer ve raporlar. N=1 ile N=4 ayni koddan gecer.

Gercek dongude olculur (Asama 0'daki tek kare `predict()` olcumu degil):
kare basina asama sureleri, gercek FPS ve ID kararlilik gostergeleri.

Calistirma:
    venv\\Scripts\\python.exe -m vision.run --source data/test.mp4
    venv\\Scripts\\python.exe -m vision.run --source 0 --show
    venv\\Scripts\\python.exe -m vision.run --source data/pilot/zone_01.mp4 --rules --zones eval/zones.json
    venv\\Scripts\\python.exe -m vision.run --source a.mp4,b.mp4,c.mp4,d.mp4 --rules --loop

Coklu kamerada `--source` virgulle ayrilir; kamera kimligi dosya adindan
turer. Toplu cikarimin tek sahibi bu dongudur -- her kamera kendi modelini
cagirsaydi batch hic olusmazdi (olculen kazanc: kare basina 14.45 -> 10.45 ms).

ID degisimi olcumu: etiketli gercek referans olmadan tam sayilamaz. Burada
pratik gosterge, isinma sonrasi (varsayilan 30 kare) yaratilan YENI ID
sayisidir. Kadro degismeyen bir sahnede bu sayi dogrudan ID degisimidir.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

import cv2

from vision.camera import (  # noqa: F401  (load_zones disaridan da kullaniliyor)
    LIVE_WAIT_SEC, WARMUP_FRAMES, CameraPipeline, draw, load_zones,
)
from vision.rules.engine import Candidate
from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
from vision.stages.preprocess import FRAME_H, FRAME_W
from vision.stages.tracker import DEFAULT_REID, OVERRIDES
from vision.ws_server import StreamServer

# Coklu kamerada tek kaynagin sessizligi turu bloklamamali: karesi hazir
# olmayan kamera (tipik olarak webcam) atlanir, digerleri beklemez. Tek
# kamerada eski davranis (2 sn) korunur.
MULTI_READ_TIMEOUT = 0.0
IDLE_SLEEP = 0.005      # hicbir kaynak kare vermediyse bos donguyu yakma


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Asama 2 goru dongusu")
    parser.add_argument("--source", required=True,
                        help="mp4 yolu, webcam indeksi (0) veya rtsp:// adresi; "
                             "virgulle ayrilmis birden fazla kaynak")
    parser.add_argument("--model", default=DEFAULT_WEIGHTS)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=FRAME_W)
    parser.add_argument("--max-frames", type=int, default=0, help="0 = sinirsiz")
    parser.add_argument("--loop", action="store_true",
                        help="dosya kaynagi bitince basa sar (idx sifirlanmaz)")
    parser.add_argument("--no-clahe", action="store_true")
    parser.add_argument("--gmc", default=OVERRIDES["gmc_method"],
                        help="kamera hareketi telafisi: sparseOptFlow / none")
    parser.add_argument("--no-reid", action="store_true",
                        help="gorunum eslestirmesini kapat (ID degisimi karsilastirmasi)")
    parser.add_argument("--reid-model", default="auto",
                        help=f"'auto' = dedektor oznitelikleri, yol = ayri ag "
                             f"(varsayilan {DEFAULT_REID})")
    parser.add_argument("--show", action="store_true", help="pencerede goster, q ile cik")
    parser.add_argument("--save", default="", help="isaretlenmis videoyu bu yola yaz")
    parser.add_argument("--rules", action="store_true",
                        help="oznitelik + kural motorunu calistir")
    parser.add_argument("--no-tcn", action="store_true",
                        help="TCN hakemini kapat, yalniz kural (Asama 9 ablation)")
    parser.add_argument("--tcn-min-conf", type=float, default=0.60,
                        help="model guveni bunun altindaysa karar kurala duser")
    parser.add_argument("--zones", default="",
                        help="bolge tanimi json'u (eval/zones.json)")
    parser.add_argument("--kafka", nargs="?", const="localhost:9092", default="",
                        help="aday olaylari Kafka'ya bas (varsayilan localhost:9092)")
    parser.add_argument("--camera-id", default="",
                        help="bos = kaynak dosya adi / webcam indeksi; coklu "
                             "kaynakta virgulle ayrilmis ve AYNI sirada")
    parser.add_argument("--settings-url", default="",
                        help="esikleri periyodik cekilecek API tabani")
    parser.add_argument("--settings-interval", type=float, default=5.0)
    parser.add_argument("--settings-token", default="", help="bos = jetonsuz istek")
    parser.add_argument("--ws", action="store_true",
                        help="canli kare + meta WebSocket sunucusunu ac")
    parser.add_argument("--ws-port", type=int, default=8001)
    parser.add_argument("--jpeg-quality", type=int, default=70,
                        help="baslangic JPEG kalitesi (SS4.2 denetleyicisi ayarlar)")
    parser.add_argument("--evidence", action="store_true",
                        help="olay basina klip + kare yaz, API'ye bildir")
    parser.add_argument("--storage-dir", default="storage", help="klip ve kare kok dizini")
    parser.add_argument("--heartbeat-sec", type=float, default=5.0, help="0 = kapali (SS7)")
    return parser.parse_args(argv)


def choose_reid(requested: str, disabled: bool, native_feats: bool) -> tuple[str, str]:
    """(tracker'a verilecek model, rapor notu). YOLO26 end2end oldugu icin
    dedektorun bedava govde oznitelikleri gelmez; o durumda ayri ReID agi."""
    if disabled:
        return "auto", "kapali (--no-reid)"
    if requested != "auto":
        return requested, f"ayri ag: {requested}"
    if native_feats:
        return "auto", "dedektor oznitelikleri (bedava)"
    return DEFAULT_REID, (f"ayri ag: {DEFAULT_REID} "
                          "(dedektor end2end, bedava oznitelik yok)")


def print_report(pipe: CameraPipeline, args, prefix: str = "") -> None:
    """Tek kameranin raporu. Coklu kamerada `prefix` kamera adini tasir."""
    active_frames = sum(1 for c in pipe.per_frame_counts if c)
    max_persons = max(pipe.per_frame_counts) if pipe.per_frame_counts else 0
    mean_persons = pipe.track_total / active_frames if active_frames else 0.0
    unique_ids = len(pipe.tracker.seen_ids)

    print("\n" + "=" * 62)
    print(f"ASAMA 2 - GERCEK DONGU RAPORU{prefix}")
    print("=" * 62)
    print(f"  kare sayisi          : {pipe.frames}  ({pipe.elapsed:.1f} sn)")
    print(f"  gercek FPS           : {pipe.frames / pipe.elapsed:.1f}")
    print(f"  dusen kare (kaynak)  : {pipe.dropped}")
    print(f"  yeniden baglanma     : {pipe.reconnects}")
    if pipe.outages:
        print(f"  kaynak kesintisi     : {pipe.outages} kez "
              f"{LIVE_WAIT_SEC:.0f} sn+ sessizlik")
    print(f"  CLAHE uygulandi      : {pipe.preprocess.clahe_applied} / {pipe.frames}")
    print(f"\n  {'asama':<20} {'medyan ms':>10} {'p95 ms':>10}")
    stage_rows = [("on isleme", pipe.pre_ms), ("cikarim", pipe.infer_ms),
                  ("takip", pipe.track_ms)]
    if args.rules:
        stage_rows += [("duzleme", pipe.smooth_ms), ("oznitelik+kural", pipe.rules_ms)]
    if pipe.publisher is not None and pipe.publish_ms:
        stage_rows.append(("kafka publish", pipe.publish_ms))
    if getattr(pipe.rule_engine, "model_ms", None):
        # TCN suresi "kural" satirinin ICINDEdir; ayrica gosterilir ki
        # hakemin bedeli ablationda gorunsun.
        stage_rows.append(("  ^ TCN cikarimi", pipe.rule_engine.model_ms))
    if pipe.stream_server is not None and pipe.ws_ms:
        stage_rows.append(("ws kodlama+yayin", pipe.ws_ms))
    stage_rows.append(("dongu toplam", pipe.loop_ms))
    for name, samples in stage_rows:
        p95 = sorted(samples)[min(len(samples) - 1, int(len(samples) * 0.95))]
        print(f"  {name:<20} {statistics.median(samples):>10.1f} {p95:>10.1f}")

    print(f"\n  benzersiz ID         : {unique_ids}")
    print(f"  es zamanli en cok    : {max_persons} kisi")
    print(f"  kare basina ortalama : {mean_persons:.2f} kisi")
    if max_persons:
        print(f"  ID / es zamanli      : {unique_ids / max_persons:.2f}"
              "   (1.00 = hic ID degisimi yok)")
    print(f"  isinma sonrasi yeni ID: {pipe.late_new_ids}  (ilk {WARMUP_FRAMES} kare haric)")
    print(f"  pozsuz iz            : {pipe.pose_missing} / {pipe.track_total}")

    if args.rules:
        print("\n  aday olay ozeti (--rules):")
        if pipe.all_candidates:
            by_type: dict[str, list[Candidate]] = {}
            for cand in pipe.all_candidates:
                by_type.setdefault(cand.anomaly_type, []).append(cand)
            for anomaly_type in sorted(by_type):
                cands = by_type[anomaly_type]
                track_ids = {tid for c in cands for tid in c.track_ids}
                first_ts = min(c.ts for c in cands)
                print(f"    {anomaly_type:<16} aday {len(cands):>5}  "
                      f"iz {len(track_ids):>3}  ilk tetik {first_ts:>6.1f} sn")
        else:
            print("    aday yok")

    if pipe.publisher is not None:
        print(f"\n  kafka yayin           : yayinlanan {pipe.publisher.published}  "
              f"kuyruga alinan {pipe.publisher.queued}  basarisiz {pipe.publisher.failed}")
        if pipe.publisher.last_error:
            print(f"  kafka son hata        : {pipe.publisher.last_error}")
    if pipe.settings_client is not None:
        print(f"\n  esik sicak yukleme    : {pipe.settings_client.applied} kez uygulandi, "
              f"{pipe.settings_client.failures} hata")
        if pipe.settings_client.last_error:
            print(f"  esik son hata         : {pipe.settings_client.last_error}")
    if pipe.stream_server is not None:
        print(f"\n  WebSocket             : acildi={pipe.stream_server.opened}  "
              f"son gorulen istemci sayisi={pipe.stream_server.live_clients}  "
              f"bitis kalitesi={pipe.jpeg_quality}")
    if pipe.evidence_writer is not None:
        ev = pipe.evidence_writer
        print(f"\n  kanit                 : klip {ev.written_clips}  "
              f"kare {ev.written_frames}  "
              f"POST basarili {ev.posted}  basarisiz {ev.post_failed}  "
              f"mongo hata {ev.mongo_failed}  kuyruktan dusen {ev.dropped}")
        if ev.last_error:
            print(f"  kanit son hata        : {ev.last_error}")
    if pipe.health_client is not None:
        print(f"\n  kalp atisi            : gonderilen {pipe.health_client.sent}  "
              f"hata {pipe.health_client.failures}")
        if pipe.health_client.last_error:
            print(f"  kalp atisi son hata   : {pipe.health_client.last_error}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sources = [s.strip() for s in str(args.source).split(",") if s.strip()]
    multi = len(sources) > 1
    if multi and (args.show or args.save):
        print("  --show/--save yalniz tek kaynakta calisir")
        return 2

    detector = PoseDetector(args.model, device=args.device, conf=args.conf,
                            imgsz=args.imgsz, reid_feats=not args.no_reid)
    reid_model, reid_note = choose_reid(args.reid_model, args.no_reid,
                                        detector.has_reid_feats)
    print(f"  ReID: {reid_note}")

    stream_server: StreamServer | None = None
    if args.ws:
        # JWT_SECRET ortamdan okunur -- yoksa StreamServer.start() sunucuyu
        # ACMAZ ve tek satir uyari basar (ASAMA6_PLAN.md SS3). Varsayilan
        # DEGER verilmez: api/config.py'nin "dev-secret-change-me" yedegi
        # burada BILEREK tekrarlanmiyor -- kimliksiz yayin kabul edilemez.
        # TEK sunucu, TEK port: kameralar ayri surec olmadigi icin 8.6'nin
        # port-basina-kamera cozumu artik gerekmiyor, `ws_port` sagliga
        # yazilmaya devam eder (hepsi ayni portu bildirir).
        stream_server = StreamServer(port=args.ws_port, jwt_secret=os.getenv("JWT_SECRET"))
        stream_server.start()

    # Kamera adlari kaynaklarla ayni sirada verilir; sayi tutmuyorsa ad
    # kaynaktan turer (tek kamerali eski davranis).
    names = [c.strip() for c in str(args.camera_id).split(",") if c.strip()]
    if len(names) != len(sources):
        names = [args.camera_id if not multi else ""] * len(sources)
    pipes = [CameraPipeline(src, args, reid_model=reid_model,
                            stream_server=stream_server, camera_id=name)
             for src, name in zip(sources, names)]
    for pipe in pipes:
        pipe.start()
    if stream_server is not None:
        for pipe in pipes:
            print(f"  WebSocket: ws://localhost:{args.ws_port}/ws/live|meta/{pipe.camera_id}"
                  + ("" if stream_server.opened else " (ACILAMADI)"))

    timeout = MULTI_READ_TIMEOUT if multi else 2.0
    writer = None
    stop = False
    while not stop and not all(p.finished for p in pipes):
        batch: list[tuple[CameraPipeline, object, object]] = []
        for pipe in pipes:
            if pipe.finished:
                continue
            frame = pipe.read(timeout=timeout)
            if frame is None:
                continue
            batch.append((pipe, frame, pipe.prepare(frame)))
        if not batch:
            time.sleep(IDLE_SLEEP)
            continue

        t0 = time.perf_counter()
        results = detector([image for _, _, image in batch])
        # Toplu cagrinin suresi kameralara esit bolunur: kare basina maliyet
        # budur, tek kameraya tum batch'i yazmak raporu yalanlardi.
        infer_ms = (time.perf_counter() - t0) * 1000 / len(batch)
        for (pipe, frame, image), result in zip(batch, results):
            pipe.consume(frame, image, result, infer_ms)

            if args.show or args.save:
                annotated = draw(image, pipe.last_tracks, pipe.last_labels)
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
                        stop = True
        if args.max_frames and all(p.frames >= args.max_frames for p in pipes):
            stop = True

    for pipe in pipes:
        pipe.close()
    if stream_server is not None:
        stream_server.stop()
    if writer is not None:
        writer.release()
    if args.show:
        cv2.destroyAllWindows()
    detector.close()

    if all(p.frames == 0 for p in pipes):
        print(f"  HATA: hic kare okunamadi. {pipes[0].last_error or ''}")
        return 1

    for pipe in pipes:
        if pipe.frames == 0:
            print(f"\n  {pipe.camera_id or pipe.source_arg}: hic kare okunamadi. "
                  f"{pipe.last_error or ''}")
            continue
        print_report(pipe, args, f" - {pipe.camera_id or pipe.source_arg}" if multi else "")
    if multi:
        total = sum(p.frames / p.elapsed for p in pipes if p.frames)
        print(f"\n  TOPLAM: {len(pipes)} kamera, {total:.1f} FPS "
              f"(kamera basina ortalama {total / len(pipes):.1f})")
    if args.save:
        print(f"\n  video yazildi        : {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
