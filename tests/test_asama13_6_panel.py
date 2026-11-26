"""Asama 13.6 Paket F: panel (statik kaynak denetimi).

    venv\\Scripts\\python.exe -m pytest tests/test_asama13_6_panel.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "frontend" / "js"


def _src(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


def test_index_alarm_sound_and_mute() -> None:
    s = _src("index.js")
    assert "AudioContext" in s and "createOscillator" in s
    assert '"alarmMuted"' in s
    # every localStorage access sits inside a try block
    for m in re.finditer(r"localStorage\.", s):
        assert "try {" in s[max(0, m.start() - 80):m.start()]
    assert "Sesli alarm için sayfaya bir kez tıklayın" in s


def test_index_one_click_ack() -> None:
    s = _src("index.js")
    assert '"acknowledged"' in s and '"false_positive"' in s
    assert 'method: "PATCH"' in s and "/api/events" in s
    assert "Bu işlem için operatör yetkisi gerekiyor" in s
    assert "Olay henüz kaydedilmedi; Olaylar ekranından onaylayın" in s
    assert "Yanlış Alarm" in s


def test_index_fall_outcome() -> None:
    s = _src("index.js")
    assert "fall_outcome" in s and "Kalkamadı" in s and "Kalktı" in s


def test_sistem_sagligi_pulse() -> None:
    s = _src("sistem-sagligi.js")
    assert "stalled" in s and "candidates_window" in s
    assert "Aday var, olay yok" in s
    assert re.search(r"setInterval\(load,\s*15000\)", s)


def test_live_direction_arrow() -> None:
    assert "direction_vector" in _src("live.js")


def test_ayarlar_window_frames_hidden_but_sent() -> None:
    s = _src("ayarlar.js")
    assert 'windowSelect.parentElement.style.display = "none"' in s
    assert "window_frames: Number(windowSelect.value)" in s
