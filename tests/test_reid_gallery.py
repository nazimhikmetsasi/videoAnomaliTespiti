"""Asama 11.1 oz kontrolu: galeri eslestirme mantigi.

GPU ve ONNX gerektirmez -- kodlayici cagrilmaz, dogrudan sentetik gomme
vektorleriyle `match()` olculur. Olculen sey ReID agi degil GALERIdir:
esik davranisi, yeni kimlik acma, ayni kisiyi ikinci kez baglama, budama.

    venv\\Scripts\\python.exe -m pytest tests/test_reid_gallery.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision.reid_gallery import ReIDGallery, crop_bbox, sharpness  # noqa: E402


def _gallery(threshold: float = 0.75, **kw) -> ReIDGallery:
    """__init__ ONNX yukler; test kodlayiciya hic dokunmadigi icin atlanir."""
    gallery = ReIDGallery.__new__(ReIDGallery)
    gallery.threshold = threshold
    gallery.max_people = kw.get("max_people", 200)
    gallery.ttl_sec = kw.get("ttl_sec", 3600.0)
    gallery.people, gallery._next_id = [], 1
    gallery.calls, gallery.encode_ms, gallery.matched = 0, [], 0
    return gallery


def _vec(*values: float) -> np.ndarray:
    v = np.array(values, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_ilk_kisi_yeni_kimlik_acar() -> None:
    gallery = _gallery()
    person_id, score = gallery.match(_vec(1, 0, 0), now=100.0)
    assert person_id == 1 and score == 0.0
    assert len(gallery.people) == 1


def test_ayni_kisi_ikinci_olayda_ayni_kimligi_alir() -> None:
    """Tekrar giris: kadrajdan cikip donen kisi YENI ID almamali."""
    gallery = _gallery(threshold=0.75)
    first, _ = gallery.match(_vec(1, 0.05, 0), now=100.0)
    second, score = gallery.match(_vec(1, 0.10, 0), now=200.0)
    assert second == first
    assert score > 0.99
    assert gallery.matched == 1
    assert len(gallery.people) == 1        # galeride tek kisi


def test_farkli_kisi_yeni_kimlik_alir() -> None:
    gallery = _gallery(threshold=0.75)
    first, _ = gallery.match(_vec(1, 0, 0), now=100.0)
    second, score = gallery.match(_vec(0, 1, 0), now=100.0)
    assert second != first
    assert score == pytest.approx(0.0, abs=1e-6)
    assert len(gallery.people) == 2


def test_esik_karari_belirler() -> None:
    """Ayni cift, esik degisince farkli sonuc verir -- 11.3 taramasinin dayanagi."""
    a, b = _vec(1, 0, 0), _vec(1, 1, 0)      # kosinus ~0.707
    gevsek = _gallery(threshold=0.60)
    assert gevsek.match(a, now=0.0)[0] == gevsek.match(b, now=0.0)[0]
    siki = _gallery(threshold=0.80)
    assert siki.match(a, now=0.0)[0] != siki.match(b, now=0.0)[0]


def test_ttl_dolan_kimlik_dusurulur() -> None:
    gallery = _gallery(ttl_sec=60.0)
    first, _ = gallery.match(_vec(1, 0, 0), now=100.0)
    later, _ = gallery.match(_vec(1, 0, 0), now=100.0 + 61.0)
    assert later != first                    # eski kayit dustu, yeni kimlik
    assert len(gallery.people) == 1


def test_galeri_ust_siniri_asilmaz() -> None:
    gallery = _gallery(threshold=0.99, max_people=3)
    for i in range(6):
        v = np.zeros(6, dtype=np.float32)
        v[i] = 1.0
        gallery.match(v, now=100.0 + i)
    assert len(gallery.people) <= 3
    # En son gorulenler kalmali
    assert gallery.people[0].last_seen >= gallery.people[-1].last_seen


def test_kirpim_kare_disina_tasarsa_kirpilir() -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    assert crop_bbox(image, (-50, -50, 60, 80)).shape[:2] == (80, 60)
    assert crop_bbox(image, (0, 0, 10, 10)) is None      # MIN_CROP altinda
    assert crop_bbox(image, (190, 90, 260, 160)) is None  # tasan kisim kucuk


def test_keskinlik_bulanik_kareyi_ayirt_eder() -> None:
    rng = np.random.default_rng(0)
    keskin = (rng.random((64, 64, 3)) * 255).astype(np.uint8)
    import cv2
    bulanik = cv2.GaussianBlur(keskin, (9, 9), 5)
    assert sharpness(keskin) > sharpness(bulanik) * 2
