"""Asama 4 onay olcumu: aday -> Kafka -> Spark -> dogrulanmis olay -> puanlama.

`eval/pilot_eval.py`'i YENIDEN KULLANIR (`run_clip`, `to_second_set`, `score`,
`markdown_table`), kopyalamaz -- iki yerde iki farkli puanlama olmasin. Esik
mantigi da tek yerde: `stream/filters.py` (`session_passes`); `spark_job.py`
sutun ifadesiyle aynisini uygular (ASAMA4_PLAN.md SS5.3). Bu script Spark'a
hic dokunmaz, yalnizca Kafka uzerinden konusur -- Spark ayrica
`docker compose up -d spark` ile calisiyor olmalidir.

Table A'nin "oturum" sutunu, o an Spark ne esikle calisiyorsa onu yansitir.
Spark permissif calisirken (SPARK_MIN_HITS=0, SPARK_MIN_SEC_DEFAULT=0 VE
SPARK_MIN_SEC='{}' -- ucu de sifirlanmali, DEFAULT tek basina bilinen tipler
icin no-op'tur cunku onlar zaten SPARK_MIN_SEC haritasinda acikca var) TUM
oturumlar gelir; "dogrulanmis olay" sutunu bu oturumlara `session_passes`
VARSAYILAN esiklerle cevrimdisi uygulanarak hesaplanir.

anomaly-events konusuna her kosu YENI mesaj EKLER, eskiyi SILMEZ (Kafka
topic'i temizlenmez). `consume_events` bu yuzden yalnizca BU kosunun
event_time >= base_epoch olan mesajlarini kabul eder -- aksi halde onceki
kosularin ciktisi (farkli esiklerle uretilmis) yeni olculumle karisir.

Calistirma -- iki AYRI Spark konfigurasyonuyla iki AYRI cagri onerilir:
    # 1) varsayilan esikli Spark calisirken (docker compose up -d spark):
    venv\\Scripts\\python.exe -m eval.spark_eval --from-cache
    # 2) permissif Spark calisirken (SPARK_MIN_HITS=0, SPARK_MIN_SEC_DEFAULT=0,
    #    SPARK_MIN_SEC='{}'), ayri bir dosyaya, esik supurmesi icin:
    venv\\Scripts\\python.exe -m eval.spark_eval --from-cache --sweep --events-out eval/out/events_sweep.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

from confluent_kafka import Consumer

from eval.pilot_eval import markdown_table, run_clip, score, to_second_set
from stream.filters import MIN_SEC_DEFAULT_MAP, session_passes
from vision.publish import EOS_LEAD_SEC, CandidatePublisher, candidate_to_dict
from vision.rules.engine import Candidate
from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
from vision.stages.preprocess import FRAME_W

OUT_DIR = Path("eval/out")
EPOCH_FILE = OUT_DIR / ".epoch_base"
CAND_FILE = OUT_DIR / "candidates.jsonl"
# 0 aday ureten klip (mixed_01, police_run) candidates.jsonl'e HIC satir
# yazmaz -- klip listesini ayri tutmazsak --from-cache o klibi hic gormez,
# publish_all onun icin EOS bile basmaz (bulundu: SS9 olcum kosusunda 6
# yerine 4 EOS gelmesinin sebebi buydu).
CLIP_STEMS_FILE = OUT_DIR / ".clip_stems"
EVENTS_FILE = OUT_DIR / "events.jsonl"
DEFAULT_MIN_HITS = 2
CLIP_GAP_SEC = 1000.0    # klipler arasi epoch bosluk: olay zamanlari karismasin


def next_epoch_base() -> float:
    """Onceki kosunun en buyuk event_time'indan sonra baslar.

    Spark damgasi (watermark) kalicidir (checkpoint). Duvar saatinden
    baslarsak onceki `_EOS`'un ittigi damganin gerisinde kalinip yeni kosunun
    tamami 'gec veri' sayilir ve sessizce dusurulur (ASAMA4_PLAN.md SS9#2).
    """
    prev = float(EPOCH_FILE.read_text()) if EPOCH_FILE.exists() else 0.0
    return max(time.time(), prev + 1.0)


def generate_candidates(clips_dir: Path, zones_path: str) -> dict[str, list[Candidate]]:
    detector = PoseDetector(DEFAULT_WEIGHTS, device="cuda", conf=0.25, imgsz=FRAME_W)
    by_clip: dict[str, list[Candidate]] = {}
    for clip in sorted(clips_dir.glob("*.mp4")):
        print(f"  kosuluyor: {clip.name}")
        by_clip[clip.stem] = run_clip(clip, detector, zones_path)
    detector.close()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CLIP_STEMS_FILE.write_text("\n".join(sorted(by_clip)), encoding="utf-8")
    return by_clip


def load_cached_candidates() -> dict[str, list[Candidate]]:
    # 0 aday ureten klipler de bos listeyle yer alsin (bkz. CLIP_STEMS_FILE notu).
    by_clip: dict[str, list[Candidate]] = defaultdict(list)
    if CLIP_STEMS_FILE.exists():
        for stem in CLIP_STEMS_FILE.read_text(encoding="utf-8").splitlines():
            if stem.strip():
                by_clip[stem.strip()] = []
    for line in CAND_FILE.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        by_clip[row["camera_id"]].append(Candidate(
            anomaly_type=row["anomaly_type"], track_ids=row["track_ids"],
            score=row["score"], idx=row["idx"], ts=row["ts"],
            metrics=row["metrics"], thresholds_used=row["thresholds_used"],
            zone_name=row["zone_name"]))
    return dict(by_clip)


def publish_all(by_clip: dict[str, list[Candidate]], bootstrap: str,
                 base_epoch: float) -> tuple[dict, dict[str, float]]:
    """Her klibi ayri epoch dilimine basar, klipler arasi olay zamani karismaz.

    `finish_wall`: klip basina EOS'un basildigi DUVAR saati. Tablo D bunu
    kullanir -- `event_time` (sahne zamani) klipler arasi 1000 sn kaydirilmis
    oldugu icin dogrudan duvar saatiyle kiyaslanamaz (SS9#2).
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    max_event_time = base_epoch
    stats = {}
    finish_wall: dict[str, float] = {}
    with CAND_FILE.open("w", encoding="utf-8") as f:
        for i, (camera_id, cands) in enumerate(sorted(by_clip.items())):
            clip_epoch = base_epoch + i * CLIP_GAP_SEC
            pub = CandidatePublisher(bootstrap, camera_id, epoch_base=clip_epoch)
            pub(cands)
            pub.close(eos=True)
            finish_wall[camera_id] = time.time()
            stats[camera_id] = (pub.published, pub.queued, pub.failed, pub.last_error)
            for c in cands:
                f.write(json.dumps(candidate_to_dict(c, camera_id, clip_epoch)) + "\n")
            clip_max_ts = max((c.ts for c in cands), default=0.0)
            max_event_time = max(max_event_time, clip_epoch + clip_max_ts + EOS_LEAD_SEC)
    EPOCH_FILE.write_text(str(max_event_time + 1.0))
    return stats, finish_wall


def consume_events(bootstrap: str, idle_timeout: float, min_start_time: float,
                    events_out: Path) -> list[dict]:
    """anomaly-events'i okur, YALNIZCA bu kosuya ait olaylari tutar.

    Topic her kosuda mesaj biriktirir, hic silinmez (Kafka retention 24 sn
    degil saat). earliest + benzersiz group.id ile OKUNAN HER SEY onceki
    kosularin (farkli esik/farkli Spark yapilandirmasi) ciktisini da kapsar.
    `min_start_time` (bu kosunun base_epoch'u) altindaki oturumlar oncekinden
    kalmadir ve elenir -- aksi halde farkli olculumlerin sonuclari karisir.
    """
    consumer = Consumer({
        "bootstrap.servers": bootstrap,
        "group.id": f"spark-eval-{uuid.uuid4()}",
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe(["anomaly-events"])
    events: list[dict] = []
    stale = 0
    last_msg = time.monotonic()
    while time.monotonic() - last_msg < idle_timeout:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        row = json.loads(msg.value())
        last_msg = time.monotonic()
        if row.get("start_time", 0.0) < min_start_time:
            stale += 1
            continue
        row["_recv_wall"] = time.time()
        events.append(row)
    consumer.close()
    if stale:
        print(f"  ({stale} eski kosudan kalma olay elendi -- topic temizlenmiyor)")
    events_out.parent.mkdir(parents=True, exist_ok=True)
    events_out.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return events


def events_to_seconds(events: list[dict]) -> set[tuple[str, int]]:
    """Dogrulanmis (varsayilan esigi gecen) oturumlari (tip, saniye) kumesine acar.

    Asama 3 tablosu da bu birimle uretildi (SS9 adim 5); birim ayni olmazsa
    oncesi/sonrasi karsilastirmasi anlamsizdir.
    """
    out: set[tuple[str, int]] = set()
    for e in events:
        if e["anomaly_type"] == "_EOS":
            continue
        if not session_passes(e["hits"], e["duration_sec"], e["anomaly_type"],
                               DEFAULT_MIN_HITS, MIN_SEC_DEFAULT_MAP):
            continue
        for sec in range(int(e["start_ts"]), int(e["end_ts"]) + 1):
            out.add((e["anomaly_type"], sec))
    return out


def table_a(raw_counts: dict[str, dict[str, int]], events_by_clip: dict[str, list[dict]]) -> str:
    lines = ["| klip | tip | ham aday | oturum | dogrulanmis olay |",
             "|---|---|---|---|---|"]
    for clip in sorted(set(raw_counts) | set(events_by_clip)):
        types = sorted(set(raw_counts.get(clip, {})) |
                        {e["anomaly_type"] for e in events_by_clip.get(clip, [])})
        for t in types:
            raw = raw_counts.get(clip, {}).get(t, 0)
            evs = [e for e in events_by_clip.get(clip, []) if e["anomaly_type"] == t]
            confirmed = sum(1 for e in evs if session_passes(
                e["hits"], e["duration_sec"], t, DEFAULT_MIN_HITS, MIN_SEC_DEFAULT_MAP))
            lines.append(f"| {clip} | {t} | {raw} | {len(evs)} | {confirmed} |")
    return "\n".join(lines)


def table_b(events_by_clip: dict[str, list[dict]]) -> str:
    lines = ["| klip | tip | hits | duration_sec | sonuc |", "|---|---|---|---|---|"]
    for clip in sorted(events_by_clip):
        for e in events_by_clip[clip]:
            passed = session_passes(e["hits"], e["duration_sec"], e["anomaly_type"],
                                     DEFAULT_MIN_HITS, MIN_SEC_DEFAULT_MAP)
            lines.append(f"| {clip} | {e['anomaly_type']} | {e['hits']} | "
                        f"{e['duration_sec']:.2f} | {'gecti' if passed else 'elendi'} |")
    return "\n".join(lines)


def table_d(events: list[dict], finish_wall: dict[str, float]) -> str:
    deltas = [(e["_recv_wall"] - finish_wall[e["camera_id"]]) * 1000.0
              for e in events if e["anomaly_type"] != "_EOS" and e["camera_id"] in finish_wall]
    if not deltas:
        return "  olcum yok (dogrulanmis olay gelmedi)"
    deltas.sort()
    median = deltas[len(deltas) // 2]
    p95 = deltas[min(len(deltas) - 1, int(len(deltas) * 0.95))]
    return f"  medyan {median:.0f} ms, p95 {p95:.0f} ms  (n={len(deltas)})"


def sweep_table(events: list[dict], ann_dir: Path) -> str:
    """`--sweep`: events.jsonl uzerinde min_hits x min_sec cevrimdisi taranir.

    Spark permissif calismis olmali (SPARK_MIN_HITS=0, SPARK_MIN_SEC_DEFAULT=0)
    -- aksi halde eleklenmis oturumlar zaten events.jsonl'de yoktur.
    """
    hits_opts = [1, 2, 3, 5]
    sec_opts = [0.0, 0.5, 1.0, 1.5, 2.0]
    lines = ["| min_hits | min_sec | precision | recall | F1 |", "|---|---|---|---|---|"]
    events_by_clip: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        if e["anomaly_type"] != "_EOS":
            events_by_clip[e["camera_id"]].append(e)

    for mh in hits_opts:
        for ms in sec_opts:
            tp: dict[str, int] = defaultdict(int)
            fp: dict[str, int] = defaultdict(int)
            fn: dict[str, int] = defaultdict(int)
            flat_map = {k: ms for k in MIN_SEC_DEFAULT_MAP}
            for clip, evs in events_by_clip.items():
                ann_path = ann_dir / f"{clip}.json"
                if not ann_path.exists():
                    continue
                cand_set: set[tuple[str, int]] = set()
                for e in evs:
                    if session_passes(e["hits"], e["duration_sec"], e["anomaly_type"],
                                       mh, flat_map, ms):
                        for sec in range(int(e["start_ts"]), int(e["end_ts"]) + 1):
                            cand_set.add((e["anomaly_type"], sec))
                ann = json.loads(ann_path.read_text(encoding="utf-8"))
                ann_events, eval_end = ann["events"], ann.get("eval_end_sec")
                if eval_end is not None:
                    ann_events = [x for x in ann_events if x["start_sec"] < eval_end]
                    cand_set = {c for c in cand_set if c[1] < eval_end}
                score(cand_set, ann_events, 1.0, tp, fp, fn)
            a, b, c = sum(tp.values()), sum(fp.values()), sum(fn.values())
            prec = a / (a + b) if (a + b) else 0.0
            rec = a / (a + c) if (a + c) else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
            lines.append(f"| {mh} | {ms} | {prec:.2f} | {rec:.2f} | {f1:.2f} |")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Asama 4 Spark onay olcumu")
    parser.add_argument("--clips", default="data/pilot")
    parser.add_argument("--annotations", default="eval/annotations")
    parser.add_argument("--zones", default="eval/zones.json")
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--from-cache", action="store_true",
                        help="GPU atla, eval/out/candidates.jsonl'den oku")
    parser.add_argument("--idle-timeout", type=float, default=45.0)
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--events-out", default=str(EVENTS_FILE),
                        help="permissif esik supurmesi varsayilan olcumu ezmesin diye "
                             "farkli bir dosyaya yonlendirilebilir")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clips_dir, ann_dir = Path(args.clips), Path(args.annotations)

    if args.from_cache:
        if not CAND_FILE.exists():
            print(f"  HATA: {CAND_FILE} yok, once --from-cache'siz calistirin")
            return 1
        by_clip = load_cached_candidates()
    else:
        by_clip = generate_candidates(clips_dir, args.zones)

    raw_counts: dict[str, dict[str, int]] = {clip: {} for clip in by_clip}
    for clip, cands in by_clip.items():
        for c in cands:
            raw_counts[clip][c.anomaly_type] = raw_counts[clip].get(c.anomaly_type, 0) + 1

    base_epoch = next_epoch_base()
    pub_stats, finish_wall = publish_all(by_clip, args.bootstrap, base_epoch)
    for clip, (published, queued, failed, last_error) in pub_stats.items():
        if failed:
            print(f"  UYARI: {clip} yayininda {failed} basarisiz mesaj: {last_error}")
    events_out = Path(args.events_out)
    events = consume_events(args.bootstrap, args.idle_timeout, base_epoch, events_out)
    print(f"  {len(events)} olay alindi ({events_out})")

    events_by_clip: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        if e["anomaly_type"] != "_EOS":
            events_by_clip[e["camera_id"]].append(e)

    print("\n" + "=" * 62)
    print("TABLO A - ham aday -> oturum -> dogrulanmis olay")
    print("=" * 62)
    print(table_a(raw_counts, events_by_clip))

    print("\n" + "=" * 62)
    print("TABLO B - oturum dokumu")
    print("=" * 62)
    print(table_b(events_by_clip))

    tp_before, fp_before, fn_before = defaultdict(int), defaultdict(int), defaultdict(int)
    tp_after, fp_after, fn_after = defaultdict(int), defaultdict(int), defaultdict(int)
    for clip, cands in by_clip.items():
        ann_path = ann_dir / f"{clip}.json"
        if not ann_path.exists():
            continue
        ann = json.loads(ann_path.read_text(encoding="utf-8"))
        ann_events, eval_end = ann["events"], ann.get("eval_end_sec")

        before_set = to_second_set(cands)
        after_set = events_to_seconds(events_by_clip.get(clip, []))
        ev_ref = ann_events
        if eval_end is not None:
            ev_ref = [e for e in ann_events if e["start_sec"] < eval_end]
            before_set = {c for c in before_set if c[1] < eval_end}
            after_set = {c for c in after_set if c[1] < eval_end}
        score(before_set, ev_ref, 1.0, tp_before, fp_before, fn_before)
        score(after_set, ev_ref, 1.0, tp_after, fp_after, fn_after)

    print("\n" + "=" * 62)
    print("TABLO C - precision/recall: Spark oncesi / sonrasi")
    print("=" * 62)
    print("\n  oncesi (ham aday, Asama 3 puanlamasi):")
    print(markdown_table(tp_before, fp_before, fn_before))
    print("\n  sonrasi (Spark oturum + varsayilan esik):")
    print(markdown_table(tp_after, fp_after, fn_after))

    print("\n" + "=" * 62)
    print("TABLO D - uctan uca gecikme (event_time -> anomaly-events alimi)")
    print("=" * 62)
    print(table_d(events, finish_wall))

    if args.sweep:
        print("\n" + "=" * 62)
        print("ESIK SUPURMESI (--sweep)")
        print("=" * 62)
        print(sweep_table(events, ann_dir))

    return 0


if __name__ == "__main__":
    sys.exit(main())
