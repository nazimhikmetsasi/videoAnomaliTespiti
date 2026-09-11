"""Asama 11.3: ReID kosinus esigi taramasi ve "en iyi kare" olcumu.

Gercek referans UYDURULMAZ, veri kumesinin kendisinden gelir: CASIA
klipleri dosya adinda kisi kimligi tasir (`casia_angleview_p01_faint_a1`).
Ayni `pXX` farkli klipte = ayni kisi (olumlu cift), farkli `pXX` = farkli
kisi (olumsuz cift).

Uc sey olculur:

1. **Tekrar giris (asil kullanim)** — ayni klibin BASI ile SONU. Kisi
   kadrajdan cikip birkac saniye sonra geri girmis gibi: ayni kamera, ayni
   kiyafet, farkli an. Sistemin gercekte cozmesi istenen problem budur.
2. **Farkli klip / farkli eylem (zor kosul)** — ayni `pXX` farkli klipte.
   Burada kisi kimi zaman yatiyor, kimi zaman kosuyor; gorunum modeli bunu
   ayni kisiye baglamakta zorlanir.
3. **En iyi kare secimi** — olay aninda en keskin kareyi secmek, ilk kareyi
   almaya gore eslestirmeyi gercekten iyilestiriyor mu.

Kodlayicinin saglamligi ayrica dogrulandi: AYNI klipte ardisik karelerde
kosinus ortalamasi 0.66-0.79. Yani asagidaki dusuk skorlar kodlayici
hatasi degil, kosulun zorlugudur.

BILINEN SINIR: CASIA tek oturumda tek kamerayla cekilmis; ayni kisi
kliplerde buyuk olasilikla ayni kiyafette. Bu ReID'yi oldugundan KOLAY
gosterir. Farkli kamera / farkli gun kosulu olculmemistir.

    venv/Scripts/python.exe -m eval.reid_eval
    venv/Scripts/python.exe -m eval.reid_eval --per-person 8 --frames 12
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from vision.reid_gallery import ReIDGallery, crop_bbox, sharpness
from vision.stages.pose_detector import DEFAULT_WEIGHTS, PoseDetector
from vision.stages.preprocess import Preprocessor

PERSON_RE = re.compile(r"casia_[a-z]+_(p\d+)_")
THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


def clip_person(path: Path) -> str | None:
    match = PERSON_RE.search(path.name)
    return match.group(1) if match else None


def collect_clips(root: Path, per_person: int) -> dict[str, list[Path]]:
    """kisi -> klip listesi (en az 2 klibi olan kisiler)."""
    by_person: dict[str, list[Path]] = defaultdict(list)
    for clip in sorted(root.glob("*/casia_*.mp4")):
        person = clip_person(clip)
        if person:
            by_person[person].append(clip)
    return {p: c[:per_person] for p, c in sorted(by_person.items()) if len(c) >= 2}


def clip_vectors(path: Path, detector: PoseDetector, gallery: ReIDGallery,
                 preprocess: Preprocessor, frames: int) -> dict[str, np.ndarray]:
    """Klipten dort gomme dondurur (kisi bulunabildigi kadar):

    `en_iyi` / `ilk`  — klibin tamamindan, en keskin kare ve ilk kare
    `bas` / `son`     — klibin ILK ve SON yarisindan en keskin kare
                        (tekrar giris senaryosunun karsiligi)
    """
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or frames
    step = max(total // max(frames, 1), 1)
    best = (0.0, None, None)          # (keskinlik, kare, bbox)
    halves = {"bas": (0.0, None, None), "son": (0.0, None, None)}
    first = None
    index = 0
    while True:
        ok, raw = cap.read()
        if not ok:
            break
        if index % step:
            index += 1
            continue
        half = "bas" if index < total / 2 else "son"
        index += 1
        image = preprocess(raw)
        result = detector([image])[0]
        if result.boxes is None or not len(result.boxes):
            continue
        boxes = result.boxes.xyxy.cpu().numpy()
        # En buyuk kutu: kalabaliksa bile ana ozne odur (CASIA klipleri tek kisilik).
        bbox = boxes[int(np.argmax(boxes[:, 3] - boxes[:, 1]))]
        crop = crop_bbox(image, bbox)
        if crop is None:
            continue
        if first is None:
            first = (image, bbox)
        score = sharpness(crop)
        if score > best[0]:
            best = (score, image, bbox)
        if score > halves[half][0]:
            halves[half] = (score, image, bbox)
    cap.release()

    out: dict[str, np.ndarray] = {}
    picks = {"ilk": first, "en_iyi": best[1:] if best[1] is not None else None,
             "bas": halves["bas"][1:] if halves["bas"][1] is not None else None,
             "son": halves["son"][1:] if halves["son"][1] is not None else None}
    for name, pick in picks.items():
        if pick is None:
            continue
        vec = gallery.embed(pick[0], [pick[1]])
        if vec is not None:
            out[name] = vec[0]
    return out


def sweep(pairs: list[tuple[float, bool]]) -> list[tuple[float, float, float, float]]:
    """(esik, precision, recall, F1) — 'ayni kisi' karari icin."""
    rows = []
    for threshold in THRESHOLDS:
        tp = sum(1 for score, same in pairs if score >= threshold and same)
        fp = sum(1 for score, same in pairs if score >= threshold and not same)
        fn = sum(1 for score, same in pairs if score < threshold and same)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append((threshold, precision, recall, f1))
    return rows


def print_sweep(label: str, pairs: list[tuple[float, bool]]) -> None:
    same = [s for s, ok in pairs if ok]
    diff = [s for s, ok in pairs if not ok]
    print(f"\n### {label}\n")
    print(f"  olumlu cift {len(same)}  (kosinus ort {np.mean(same):.3f})   "
          f"olumsuz cift {len(diff)}  (ort {np.mean(diff):.3f})")
    print(f"\n| esik | precision | recall | F1 |")
    print("|---|---|---|---|")
    best = max(sweep(pairs), key=lambda r: r[3])
    for threshold, precision, recall, f1 in sweep(pairs):
        star = "  **<-- en iyi**" if threshold == best[0] else ""
        print(f"| {threshold:.2f} | {precision:.2f} | {recall:.2f} | {f1:.2f} |{star}")


def main() -> int:
    parser = argparse.ArgumentParser(description="ReID esik taramasi")
    parser.add_argument("--clips", default="data/train")
    parser.add_argument("--per-person", type=int, default=6, help="kisi basina klip")
    parser.add_argument("--frames", type=int, default=10, help="klip basina ornek kare")
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS)
    args = parser.parse_args()

    by_person = collect_clips(Path(args.clips), args.per_person)
    if len(by_person) < 2:
        print(f"  HATA: {args.clips} altinda en az 2 klipli CASIA kisisi yok")
        return 1

    detector = PoseDetector(args.weights, reid_feats=False)
    gallery = ReIDGallery(device=detector.device)
    preprocess = Preprocessor(clahe=False)

    vectors: dict[str, list[tuple[str, np.ndarray]]] = defaultdict(list)
    reentry: list[tuple[float, bool]] = []
    halves: list[tuple[str, np.ndarray, np.ndarray]] = []
    for person, clips in by_person.items():
        for clip in clips:
            found = clip_vectors(clip, detector, gallery, preprocess, args.frames)
            for mode, vector in found.items():
                vectors[mode].append((person, vector))
            if "bas" in found and "son" in found:
                halves.append((person, found["bas"], found["son"]))

    # Tekrar giris: AYNI klibin basi ve sonu = ayni kisi (olumlu).
    # Olumsuz ciftler farkli KISILERIN yarilarindan kurulur.
    for i, (person_i, bas_i, son_i) in enumerate(halves):
        reentry.append((float(bas_i @ son_i), True))
        for person_j, bas_j, _ in halves[i + 1:]:
            if person_j != person_i:
                reentry.append((float(son_i @ bas_j), False))

    print(f"\n  {len(by_person)} kisi, "
          f"{sum(len(c) for c in by_person.values())} klip, "
          f"kodlayici cagrisi {gallery.calls}, "
          f"gomme suresi medyan {np.median(gallery.encode_ms):.1f} ms")

    if reentry:
        print_sweep(f"TEKRAR GIRIS — ayni klibin basi/sonu, {len(halves)} klip", reentry)

    for mode, label in (("en_iyi", "Farkli klip/eylem, en iyi kare (Laplacian)"),
                        ("ilk", "Farkli klip/eylem, ilk kare (secim yok)")):
        items = vectors[mode]
        pairs = [(float(a[1] @ b[1]), a[0] == b[0])
                 for a, b in itertools.combinations(items, 2)]
        if pairs:
            print_sweep(f"{label} — {len(items)} klip vektoru", pairs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
