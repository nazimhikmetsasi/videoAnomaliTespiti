"""Asama 7 oz kontrolu - agsiz, DB'siz, sadece assert + httpx.MockTransport.

Calistirma:
    venv\\Scripts\\python.exe tests/test_llm.py

action_phrase/template_report/build_prompt SAF fonksiyonlardir (api/llm.py,
ASAMA7_PLAN.md SS3.2) -- DB'ye dokunmaz, burada dogrudan cagrilir.
generate_report testleri modul-duzeyi api.llm._transport'i httpx.MockTransport
ile degistirir, gercek aga hicbir istek gitmez.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

import api.llm as llm  # noqa: E402
from api.llm import (  # noqa: E402
    action_phrase, build_prompt, extract_text, generate_report, template_report, usable,
)

_STARTED = datetime.datetime(2026, 9, 9, 14, 32, 5, tzinfo=datetime.timezone.utc)


def _ctx(**overrides) -> dict:
    base = dict(event_id=1, camera_name="Ana Giriş", anomaly_type="FALL",
                zone_name=None, confidence=0.87, duration_sec=1.8,
                started_at=_STARTED, track_count=1, severity="critical")
    base.update(overrides)
    return base


# --------------------------------------------------------------- action_phrase
def test_action_phrase_seven_known_types() -> None:
    assert action_phrase("FALL") == "düşme hareketi sergiledi"
    assert action_phrase("RUN") == "hızlı koşma hareketi sergiledi"
    assert action_phrase("ZONE_VIOLATION") == "yasaklı alana giriş yaptı"
    assert action_phrase("RUN_ZONE") == "koşarak yasaklı alana giriş yaptı"
    assert action_phrase("FIGHT") == "karşılıklı saldırgan hareket sergiledi"
    assert action_phrase("LOITERING") == "alanda uzun süre oyalandı"
    assert action_phrase("WRONG_DIRECTION") == "izin verilen yönün tersine hareket etti"


def test_action_phrase_unknown_type_fallback() -> None:
    assert action_phrase("SOMETHING_NEW") == "SOMETHING_NEW olayı tespit edildi"


# --------------------------------------------------------------- template_report
def test_template_run_without_zone_has_no_yasakli_word() -> None:
    # v1 hatasinin testi: RUN olayina "yasakli" kalibinin sizmadigi.
    text = template_report(_ctx(anomaly_type="RUN", zone_name=None))
    assert "yasaklı" not in text


def test_template_zone_violation_contains_zone_name() -> None:
    text = template_report(_ctx(anomaly_type="ZONE_VIOLATION", zone_name="Depo Girişi"))
    assert "Depo Girişi" in text


def test_template_multiple_people_uses_count() -> None:
    text = template_report(_ctx(track_count=2))
    assert "2 kişi" in text
    assert "bir kişi" not in text


def test_template_never_raises_on_missing_fields() -> None:
    text = template_report({})
    assert isinstance(text, str)
    assert "bilinmiyor" in text


# --------------------------------------------------------------- build_prompt
def test_build_prompt_contains_action_phrase() -> None:
    prompt = build_prompt(_ctx(anomaly_type="FALL"))
    assert action_phrase("FALL") in prompt


def test_build_prompt_no_zone_forbids_zone_wording() -> None:
    prompt = build_prompt(_ctx(zone_name=None))
    assert "DEĞİLDİR" in prompt


def test_build_prompt_with_zone_states_zone_rule() -> None:
    prompt = build_prompt(_ctx(zone_name="Depo Girişi"))
    assert "Depo Girişi" in prompt


# --------------------------------------------------------------- extract_text
def test_extract_text_drops_thought_parts() -> None:
    data = {"candidates": [{"content": {"parts": [
        {"text": "dusunuyorum...", "thought": True},
        {"text": "Sonuc cumlesi."},
    ]}}]}
    assert extract_text(data) == "Sonuc cumlesi."


def test_extract_text_all_thought_returns_empty() -> None:
    data = {"candidates": [{"content": {"parts": [{"text": "x", "thought": True}]}}]}
    assert extract_text(data) == ""


def test_extract_text_malformed_response_returns_empty() -> None:
    assert extract_text({}) == ""
    assert extract_text({"candidates": []}) == ""


# --------------------------------------------------------------- usable
def test_usable_rejects_empty_and_half_sentence() -> None:
    assert usable("") is False
    assert usable("Bu cumle noktasiz boyle bitiyor devam ediyor") is False


def test_usable_rejects_max_tokens_finish_reason() -> None:
    long_enough = "Bu cumle yeterince uzun ama MAX_TOKENS ile kesildi."
    assert usable(long_enough, finish_reason="MAX_TOKENS") is False


def test_usable_rejects_too_short_and_too_long() -> None:
    assert usable("Kisa.") is False
    assert usable(("A" * 401) + ".") is False


def test_usable_accepts_normal_sentence() -> None:
    text = "Ana Giriş kamerasında bir kişi düşme hareketi sergiledi, kontrol edilmeli."
    assert 40 <= len(text) <= 400
    assert usable(text) is True


# --------------------------------------------------------------- generate_report
def _patch(**kwargs):
    """api.llm modul degiskenlerini gecici degistirir, eski degerleri dondurur."""
    old = {name: getattr(llm, name) for name in kwargs}
    for name, value in kwargs.items():
        setattr(llm, name, value)
    return old


def _restore(old: dict) -> None:
    for name, value in old.items():
        setattr(llm, name, value)


def test_generate_report_empty_key_skips_http_and_returns_template() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    old = _patch(GEMINI_API_KEY="", _transport=httpx.MockTransport(handler), _cooldown_until=0.0)
    try:
        ctx = _ctx()
        text, mode = generate_report(ctx)
    finally:
        _restore(old)
    assert len(calls) == 0
    assert mode == "template"
    assert text == template_report(ctx)


def test_generate_report_429_sets_cooldown_second_call_skips_http() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "quota exceeded"}})

    old = _patch(GEMINI_API_KEY="test-key", _transport=httpx.MockTransport(handler), _cooldown_until=0.0)
    try:
        text1, mode1 = generate_report(_ctx())
        text2, mode2 = generate_report(_ctx())
    finally:
        _restore(old)
    assert mode1 == "template"
    assert mode2 == "template"
    assert len(calls) == 1   # ikinci cagri sogutma nedeniyle HTTP yapmadi


def test_generate_report_half_sentence_falls_back_to_template() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{
            "content": {"parts": [{"text": "Bu cumle noktasiz boyle bitiyor devam ediyor"}]},
            "finishReason": "STOP",
        }]})

    old = _patch(GEMINI_API_KEY="test-key", _transport=httpx.MockTransport(handler), _cooldown_until=0.0)
    try:
        text, mode = generate_report(_ctx())
    finally:
        _restore(old)
    assert mode == "template"


def test_generate_report_usable_llm_text_returned() -> None:
    llm_text = "Ana Giriş kamerasında bir kişi düşme hareketi sergiledi, ekip yönlendirildi."

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{
            "content": {"parts": [{"text": llm_text}]},
            "finishReason": "STOP",
        }]})

    old = _patch(GEMINI_API_KEY="test-key", _transport=httpx.MockTransport(handler), _cooldown_until=0.0)
    try:
        text, mode = generate_report(_ctx())
    finally:
        _restore(old)
    assert mode == "llm"
    assert text == llm_text


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


def test_template_report_decimal_sayilari_bicimler():
    """Gercek olayda goruldu (Asama 7 olcum 2): NUMERIC sutunlari ham SQL'de
    Decimal doner, tur denetimi bunu eleyip metne "bilinmiyor" yaziyordu."""
    metin = llm.template_report({
        "camera_name": "Ana Giris", "anomaly_type": "RUN", "track_count": 1,
        "confidence": Decimal("0.723"), "duration_sec": Decimal("11.1"),
        "started_at": None,
    })
    assert "0.72" in metin and "11.1" in metin
    assert "bilinmiyor" not in metin.replace("bilinmiyor saatinde", "")
