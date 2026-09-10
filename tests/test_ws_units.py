"""Asama 6 WebSocket oz kontrolu - broker'siz, agsiz, GPU gerektirmez.
Asyncio sunucusu HIC baslatilmaz -- yalniz saf/senkron parcalar test edilir.

Calistirma:
    venv\\Scripts\\python.exe tests/test_ws_units.py
"""

from __future__ import annotations

import datetime
import sys
import time
from pathlib import Path

import jwt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.camera import (  # noqa: E402
    JPEG_QUALITY_MAX, JPEG_QUALITY_MIN, build_meta, next_jpeg_quality,
)
from vision.rules.engine import Zone  # noqa: E402
from vision.stages.tracker import Track  # noqa: E402
from vision.ws_server import StreamServer  # noqa: E402

SECRET = "test-secret"


def _token(secret: str = SECRET, expired: bool = False) -> str:
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=-5 if expired else 5)
    return jwt.encode({"sub": "1", "exp": exp}, secret, algorithm="HS256")


def test_token_validation() -> None:
    server = StreamServer(jwt_secret=SECRET)
    assert server._valid_token(_token()) is True
    assert server._valid_token(_token(expired=True)) is False, "suresi gecmis jeton kabul edilmemeli"
    assert server._valid_token(_token(secret="baska-sir")) is False, "yanlis imza kabul edilmemeli"
    assert server._valid_token(None) is False
    assert server._valid_token("") is False


def test_latest_value_box_keeps_newest() -> None:
    server = StreamServer(jwt_secret=SECRET)
    server.publish_frame("cam1", b"kare-1")
    server.publish_frame("cam1", b"kare-2")
    server.publish_frame("cam1", b"kare-3")
    box = server._frames["cam1"]
    assert box.data == b"kare-3", "kutu en son yazilan kareyi tutmali"
    assert box.seq == 3

    server.publish_meta("cam1", {"a": 1})
    server.publish_meta("cam1", {"a": 2})
    assert server._meta["cam1"].data == '{"a": 2}', "meta str olmali (TEXT WS cercevesi)"


def test_adaptive_quality_bounds() -> None:
    q = 70
    q = next_jpeg_quality(q, encode_publish_ms=10.0)
    assert q == 65, "10 ms'lik kodlamada kalite dusmeli"
    q = next_jpeg_quality(q, encode_publish_ms=2.0)
    assert q == 70, "2 ms'de kalite yukselmeli"

    # Tabanin altina inmemeli.
    low = JPEG_QUALITY_MIN + 2
    assert next_jpeg_quality(low, 10.0) == JPEG_QUALITY_MIN
    assert next_jpeg_quality(JPEG_QUALITY_MIN, 10.0) == JPEG_QUALITY_MIN

    # Tavanin ustune cikmamali.
    high = JPEG_QUALITY_MAX - 2
    assert next_jpeg_quality(high, 2.0) == JPEG_QUALITY_MAX
    assert next_jpeg_quality(JPEG_QUALITY_MAX, 2.0) == JPEG_QUALITY_MAX

    # Aradaki bant (4-8 ms) kaliteyi degistirmemeli.
    assert next_jpeg_quality(70, 6.0) == 70


def test_meta_body_pose_and_zone_fields() -> None:
    track_no_pose = Track(track_id=1, bbox=np.array([10.0, 20.0, 30.0, 60.0]),
                          conf=0.8, keypoints=None)
    zone = Zone(name="bina girisi", zone_type="forbidden",
                polygon=np.array([[0.30, 0.26], [0.5, 0.5], [0.1, 0.9]], dtype=np.float32))

    meta = build_meta("cam1", 1042, time.time(), 960, 540, 24.8,
                      [track_no_pose], [zone], [], {"pre": 1.2, "infer": 21.4})

    assert meta["schema"] == 1
    assert meta["tracks"][0]["has_pose"] is False
    assert meta["tracks"][0]["kp"] is None, "pozsuz iz kp: null almali"
    assert meta["tracks"][0]["bbox"] == [10.0, 20.0, 30.0, 60.0]
    poly = meta["zones"][0]["polygon"]
    assert all(abs(a - b) < 1e-4 for a, b in zip(poly[0], [0.30, 0.26])), \
        "bolge poligonu normalize (0-1) kalmali, piksele cevrilmemeli"
    assert meta["width"] == 960 and meta["height"] == 540


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  [OK]   {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  [HATA] {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  [HATA] {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n  {len(tests) - failed}/{len(tests)} gecti")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
