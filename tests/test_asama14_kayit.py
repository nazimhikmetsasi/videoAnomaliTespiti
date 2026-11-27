"""Asama 14A kayit araci testleri (kamera gerekmez)."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from eval.pilot_eval import load_annotation
from scripts import record_session as rs

KNOWN_TYPES = {"FALL", "RUN", "LOITERING", "WRONG_DIRECTION", "FIGHT"}


class FakeCap:
    def __init__(self, n=6, fps=10.0, opened=True):
        self.n, self.fps, self.opened, self.released = n, fps, opened, False

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return self.fps if prop == cv2.CAP_PROP_FPS else 0.0

    def read(self):
        if self.n <= 0:
            return False, None
        self.n -= 1
        return True, np.full((48, 64, 3), self.n * 20, np.uint8)

    def release(self):
        self.released = True


def test_scenes_sanity():
    assert len(rs.SCENES) == 15
    for key, sc in rs.SCENES.items():
        assert sc["seconds"] > 0, key
        assert set(sc["events"]) <= KNOWN_TYPES, key
        if sc["outcome"] is not None:
            assert sc["events"] == ["FALL"], key
            assert sc["outcome"] in rs.VALID_OUTCOMES, key
    assert rs.SCENES["dusme_kalkamama"]["outcome"] == "down"
    assert rs.SCENES["karanlik"]["outcome"] == "down"
    assert rs.SCENES["dusme_hizli_kalkma"]["outcome"] == "recovered"
    assert rs.SCENES["dusme_yerde_oturma"]["outcome"] == "unknown"
    assert rs.SCENES["normal"]["events"] == []


def test_list_prints_every_scene(capsys):
    assert rs.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert all(k in out for k in rs.SCENES)


def test_unknown_scene_rejected():
    assert rs.main(["--scene", "yok"]) == 2


def test_numbering(tmp_path):
    vd, ad = tmp_path / "v", tmp_path / "a"
    assert rs.next_index(vd, ad, "egilme") == 1
    vd.mkdir()
    (vd / "egilme_01.mp4").write_bytes(b"x")
    assert rs.next_index(vd, ad, "egilme") == 2
    ad.mkdir()
    (ad / "egilme_05.json").write_text("{}")  # iskelet de sayilir
    (ad / "normal_09.json").write_text("{}")  # baska sahne etkilemez
    assert rs.next_index(vd, ad, "egilme") == 6


def test_skeleton_format_and_loadable(tmp_path):
    sk = rs.build_skeleton("data/field/20261201/dusme_kalkamama_01.mp4",
                           "dusme_kalkamama", 30.0, 60.24)
    assert sk["events"] == [{"type": "FALL", "start_sec": None,
                             "end_sec": None, "outcome": "down"}]
    assert sk["duration_sec"] == 60.2 and "_not" in sk
    p = tmp_path / "s.json"
    assert rs.write_skeleton(p, sk)
    events, eval_end = load_annotation(p)  # null saniyeler eval_end yokken sorun cikarmaz
    assert eval_end is None and events[0]["start_sec"] is None
    fp = rs.build_skeleton("x.mp4", "normal", 25.0, 10.0)
    assert fp["events"] == []
    assert "outcome" not in rs.build_skeleton(
        "x.mp4", "kosu_yanal", 25.0, 1.0)["events"][0]


def test_existing_skeleton_preserved(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"elle": "dolduruldu"}', encoding="utf-8")
    assert rs.write_skeleton(p, {"yeni": 1}) is False
    assert json.loads(p.read_text(encoding="utf-8")) == {"elle": "dolduruldu"}


def test_record_fake_source(tmp_path):
    cap = FakeCap(n=6)
    ann_dir = tmp_path / "ann"
    video, ann = rs.run("0", "dusme_kalkamama", 30, tmp_path / "field",
                        cap=cap, countdown=0, root=tmp_path, ann_dir=ann_dir,
                        log=lambda *_: None)
    assert cap.released and video.name == "dusme_kalkamama_01.mp4"
    v = cv2.VideoCapture(str(video))
    assert int(v.get(cv2.CAP_PROP_FRAME_COUNT)) == 6
    assert v.get(cv2.CAP_PROP_FRAME_WIDTH) == 64
    v.release()
    data = json.loads(ann.read_text(encoding="utf-8"))
    assert data["video"].startswith("field/") and "\\" not in data["video"]
    assert data["fps"] == 10.0 and data["scene"] == "dusme_kalkamama"
    # ikinci kayit ustune yazmaz
    video2, _ = rs.run("0", "dusme_kalkamama", 30, tmp_path / "field",
                       cap=FakeCap(n=3), countdown=0, root=tmp_path,
                       ann_dir=ann_dir, log=lambda *_: None)
    assert video2.name == "dusme_kalkamama_02.mp4" and video.exists()


def test_record_unopened_source_errors(tmp_path):
    with pytest.raises(RuntimeError):
        rs.run("0", "normal", 5, tmp_path, cap=FakeCap(opened=False),
               countdown=0, root=tmp_path, ann_dir=tmp_path / "a",
               log=lambda *_: None)
