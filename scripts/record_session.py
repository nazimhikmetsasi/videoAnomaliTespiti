"""Saha kaydi araci (Asama 14A, docs/ASAMA14_PLAN.md SS2).

    python -m scripts.record_session --list
    python -m scripts.record_session --source 0 --scene dusme_kalkamama

Kareler kaynaktan okundugu gibi yazilir (yeniden olcekleme / CLAHE yok;
degerlendirme hatti kendisi uygular). Bitince etiket iskeleti yazilir.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
NO_FRAME_TIMEOUT = 5.0
COUNTDOWN_SEC = 3
FPS_PROBE_FRAMES = 15
VALID_OUTCOMES = ("down", "recovered", "unknown")

# anahtar -> (aciklama, tekrar, sure_sn, beklenen tipler, 13.4 sonucu)
_ROWS = [
    ("dusme_kalkamama",
     "Yurur, duser, en az 35 sn yerde kalir (hareketsiz ya da kalkmaya calisarak)",
     "3 (yana, kameraya dogru, kameradan uzaga)", 60, ["FALL"], "down"),
    ("dusme_hizli_kalkma",
     "Duser, 10 sn icinde kalkar, yuruyup gider",
     "3", 30, ["FALL"], "recovered"),
    ("dusme_yerde_oturma",
     "Duser, dogrulup yerde oturur, 35 sn kalir (bilinen sinir)",
     "2", 60, ["FALL"], "unknown"),
    ("sandalye_oturma",
     "Sandalyeye hizli oturur, 15 sn oturur (yanlis FALL sinamasi)",
     "3", 25, [], None),
    ("egilme",
     "Yerden bir sey alir / bagcik baglar (yanlis FALL sinamasi)",
     "3", 20, [], None),
    ("yere_birakma",
     "Cantayi yere birakip gider (yanlis FALL / LOITER sinamasi)",
     "2", 20, [], None),
    ("oyalanma",
     "Ayni yerde en az 40 sn durur, hafif salinir",
     "2", 55, ["LOITERING"], None),
    ("yon_ihlali",
     "Kadraji bir yonden oburuna yuruyerek gecer; sonra ters yonde",
     "3 + 3", 20, ["WRONG_DIRECTION"], None),
    ("kosu_yanal",
     "Kadraji keserek kosar",
     "2", 15, ["RUN"], None),
    ("kosu_derinlik",
     "Kameraya dogru / uzaga kosar",
     "2 + 2", 15, ["RUN"], None),
    ("karanlik",
     "Los isikta yurur ve duser (35 sn yerde)",
     "2", 60, ["FALL"], "down"),
    ("itisme",
     "Istege bagli, iki gonullu, hafif itisme",
     "2", 25, ["FIGHT"], None),
    ("normal",
     "Siradan hareket: yurume, oturma, telefon (yanlis pozitif tabani)",
     "1", 120, [], None),
    ("yuz",
     "Kameraya 6 m'den 1 m'ye yavasca yurur",
     "2", 30, [], None),
    ("rtsp",
     "Telefon IP kamera; 2 dk yayin, ortada Wi-Fi 10 sn kapatilir",
     "1", 150, [], None),
]

SCENES = {
    k: {"description": d, "repeats": r, "seconds": s,
        "events": list(ev), "outcome": oc}
    for k, d, r, s, ev, oc in _ROWS
}


def format_table() -> str:
    lines = [f"{'anahtar':<20} {'sure':>5}  {'tekrar':<36} {'olay':<16} 13.4",
             "-" * 92]
    for k, sc in SCENES.items():
        lines.append(f"{k:<20} {sc['seconds']:>4}s  {sc['repeats']:<36} "
                     f"{','.join(sc['events']) or '-':<16} {sc['outcome'] or '-'}")
        lines.append(f"    {sc['description']}")
    return "\n".join(lines)


def next_index(video_dir: Path, ann_dir: Path, scene: str) -> int:
    """Siradaki NN: video ya da iskelet varsa onun ustune yazmamak icin ikisine de bakar."""
    used = [0]
    for d, ext in ((video_dir, ".mp4"), (ann_dir, ".json")):
        for p in d.glob(f"{scene}_*{ext}") if d.is_dir() else []:
            tail = p.stem[len(scene) + 1:]
            if tail.isdigit():
                used.append(int(tail))
    return max(used) + 1


def build_skeleton(video_rel: str, scene: str, fps: float, duration: float) -> dict:
    sc = SCENES[scene]
    events = []
    for t in sc["events"]:
        ev = {"type": t, "start_sec": None, "end_sec": None}
        if t == "FALL" and sc["outcome"]:
            ev["outcome"] = sc["outcome"]
        events.append(ev)
    return {"video": video_rel, "scene": scene, "description": sc["description"],
            "fps": round(fps, 2), "duration_sec": round(duration, 1),
            "_not": "olay saniyelerini videoya bakarak doldurun",
            "events": events}


def write_skeleton(path: Path, skeleton: dict) -> bool:
    """Var olan iskeletin ustune yazmaz (elle doldurulmus etiket kaybolmasin)."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return True


def open_source(src: str):
    return cv2.VideoCapture(int(src) if src.isdigit() else src)


def record(cap, out_path: Path, seconds: float, countdown: int = COUNTDOWN_SEC,
           log=print) -> tuple[int, float]:
    """Kaynaktan (frames, fps) doner. cap: isOpened/read/get/release.

    Hata: RuntimeError (acilamadi / 5 sn kare yok). Ctrl+C dosyayi kapatip
    o ana kadar yazilanla biter.
    """
    if not cap.isOpened():
        raise RuntimeError("Kaynak acilamadi.")
    for i in range(countdown, 0, -1):
        log(f"Basliyor: {i}")
        time.sleep(1)

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    fps_ok = 1.0 <= src_fps <= 120.0  # RTSP bazen 0 / 90000 bildirir
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    pending: list = []
    frames = 0
    fps = src_fps if fps_ok else 0.0
    t_wait = t_first = time.monotonic()
    got_any = False
    last_print = -1

    def open_writer(frame, rate):
        h, w = frame.shape[:2]
        wr = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"),
                             rate, (w, h))
        if not wr.isOpened():
            raise RuntimeError(f"Dosya yazilamadi: {out_path}")
        return wr

    try:
        while True:
            now = time.monotonic()
            if got_any and now - t_first >= seconds:
                break
            ok, frame = cap.read()
            if not ok or frame is None:
                if not got_any and time.monotonic() - t_wait >= NO_FRAME_TIMEOUT:
                    raise RuntimeError(
                        f"{NO_FRAME_TIMEOUT:.0f} sn boyunca kare gelmedi.")
                if got_any:
                    log("Kaynak bitti / kare gelmiyor; kayit sonlandi.")
                    break
                time.sleep(0.05)
                continue
            if not got_any:
                got_any = True
                t_first = time.monotonic()
            remaining = int(seconds - (time.monotonic() - t_first))
            if remaining != last_print:
                last_print = remaining
                log(f"Kalan: {max(remaining, 0)} sn")
            if writer is None:
                if fps_ok:
                    fps = src_fps
                    writer = open_writer(frame, fps)
                else:
                    pending.append(frame)
                    if len(pending) < FPS_PROBE_FRAMES:
                        continue
                    # olculen FPS: ilk karelerin gelis hizi
                    fps = len(pending) / max(time.monotonic() - t_first, 1e-3)
                    writer = open_writer(pending[0], fps)
                    for f in pending:
                        writer.write(f)
                        frames += 1
                    pending = []
                    continue
            writer.write(frame)
            frames += 1
    except KeyboardInterrupt:
        log("Ctrl+C: kayit erken bitiriliyor.")
    finally:
        if writer is None and pending:  # cok kisa kayit: yine de yaz
            fps = len(pending) / max(time.monotonic() - t_first, 1e-3)
            writer = open_writer(pending[0], fps)
            for f in pending:
                writer.write(f)
                frames += 1
        if writer is not None:
            writer.release()
        cap.release()
    return frames, fps


def run(source: str, scene: str, seconds: float | None, out: Path,
        cap=None, countdown: int = COUNTDOWN_SEC, root: Path = ROOT,
        ann_dir: Path | None = None, log=print) -> tuple[Path, Path | None]:
    sc = SCENES[scene]
    seconds = float(seconds if seconds is not None else sc["seconds"])
    day = datetime.now().strftime("%Y%m%d")
    out = out if out.is_absolute() else root / out
    ann_dir = ann_dir or root / "eval" / "annotations" / "field"
    video_dir = out / day
    nn = next_index(video_dir, ann_dir, scene)
    video = video_dir / f"{scene}_{nn:02d}.mp4"
    cap = cap if cap is not None else open_source(source)
    frames, fps = record(cap, video, seconds, countdown, log)
    if frames == 0:
        raise RuntimeError("Hic kare yazilamadi.")
    try:
        rel = video.relative_to(root).as_posix()
    except ValueError:
        rel = video.as_posix()
    skel = build_skeleton(rel, scene, fps, frames / fps)
    ann = ann_dir / f"{scene}_{nn:02d}.json"
    wrote = write_skeleton(ann, skel)
    log(f"Kayit: {video} ({frames} kare, {fps:.1f} fps)")
    log(f"Iskelet: {ann}" if wrote else f"Iskelet zaten var, dokunulmadi: {ann}")
    return video, ann if wrote else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Saha kayit araci")
    ap.add_argument("--list", action="store_true", help="sahne tablosunu bas")
    ap.add_argument("--source", default="0", help="kamera indeksi ya da URL")
    ap.add_argument("--scene", help="sahne anahtari (--list ile bakin)")
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--out", type=Path, default=Path("data/field"))
    a = ap.parse_args(argv)
    if a.list:
        print(format_table())
        return 0
    if a.scene not in SCENES:
        print(f"Hata: --scene gerekli ve listede olmali. Bkz. --list",
              file=sys.stderr)
        return 2
    try:
        run(a.source, a.scene, a.seconds, a.out)
    except RuntimeError as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
