"""Turkce ihbar metni: Gemini Flash-Lite + deterministik sablon yedegi
(ASAMA7_PLAN.md SS3).

v1 dersi (VideoAnomalySystem/backend/llm/reporter.py::_build_prompt): model,
ornek cumledeki "yasakli alana giris yapti" kalibini bolgeyle ilgisi olmayan
olaylara da uyguladi -- gercek bir yanlis ihbar uretti. Bu yuzden
action_phrase() TEK dogruluk kaynagidir; hem sablon hem LLM istemi onu
kullanir, model yalnizca uslubu duzenler, olay ifadesini degistiremez.

generate_report() ASLA istisna firlatmaz -- Gemini API cokse bile alarm
zinciri (SS0 onay kriteri) sablona duserek surer.
"""

from __future__ import annotations

import datetime
import time

import httpx

from api.config import GEMINI_API_KEY, GEMINI_MODEL, LLM_COOLDOWN_SEC, LLM_TIMEOUT_SEC

# SS3.1: 7 bilinen tip. Bilinmeyen tip dusurulmez -- consumer.py::SEVERITY'nin
# bilinmeyen tipe "medium" vermesiyle ayni gerekce, yeni bir kural eklendiginde
# bildirim zinciri sessizce kirilmamali.
_ACTION_PHRASES = {
    "FALL": "düşme hareketi sergiledi",
    "RUN": "hızlı koşma hareketi sergiledi",
    "ZONE_VIOLATION": "yasaklı alana giriş yaptı",
    "RUN_ZONE": "koşarak yasaklı alana giriş yaptı",
    "FIGHT": "karşılıklı saldırgan hareket sergiledi",
    "LOITERING": "alanda uzun süre oyalandı",
    "WRONG_DIRECTION": "izin verilen yönün tersine hareket etti",
}

_SENTENCE_END = ".!?…"

# testler MockTransport ile degistirir (SS8); None -- gercek agda varsayilan
# httpx tasiyicisi kullanilir.
_transport: httpx.BaseTransport | None = None

# SS3.5: kota sogutmasi modul duzeyinde TEK bir zaman damgasidir. Worker
# (api/notify.py) tek is parcaciginda calistigi icin kilide gerek yoktur --
# birden fazla is parcacigindan cagrilirsaydi gerekirdi.
_cooldown_until = 0.0


def action_phrase(anomaly_type: str) -> str:
    return _ACTION_PHRASES.get(anomaly_type, f"{anomaly_type} olayı tespit edildi")


def _sayi(value: object, basamak: int) -> str:
    """Sayiyi bicimler, cevrilemezse "bilinmiyor". isinstance(float) YETMEZ:
    NUMERIC sutunlari ham SQL'de Decimal doner ve tur denetimi bunu eleyip
    metne "bilinmiyor" yazardi (gercek olayda goruldu, olcum 2)."""
    try:
        return f"{float(value):.{basamak}f}"   # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "bilinmiyor"


def _format_zaman(started_at: object) -> str:
    if isinstance(started_at, datetime.datetime):
        return started_at.astimezone().strftime("%d.%m.%Y %H:%M:%S")
    return "bilinmiyor"


def template_report(ctx: dict) -> str:
    """Yedek yol -- HER ZAMAN calisir, istisna firlatmaz (SS3.3). Eksik alan
    yerine 'bilinmiyor' yazar."""
    camera = ctx.get("camera_name") or "bilinmiyor"
    action = action_phrase(ctx.get("anomaly_type") or "")
    track_count = ctx.get("track_count") or 1
    kisi = "bir kişi" if track_count <= 1 else f"{track_count} kişi"
    zaman = _format_zaman(ctx.get("started_at"))
    zone_name = ctx.get("zone_name")
    bolge = f" ({zone_name} bölgesi)" if zone_name else ""
    sure = _sayi(ctx.get("duration_sec"), 1)
    guven = _sayi(ctx.get("confidence"), 2)
    # "saatinde": kesme isaretli ek (…'te / …'de / …'da) saniye rakamina gore
    # degisir ve sabit yazilinca cumlenin dortte ucu yanlis cikar.
    return (f"{camera} kamerasında{bolge} {zaman} saatinde {kisi} {action}. "
            f"Olay {sure} saniye sürdü, güven skoru {guven}.")


def build_prompt(ctx: dict) -> str:
    """Gemini istemi (SS3.6). action_phrase() TEK dogruluk kaynagidir --
    model olay ifadesini degistiremez, yalnizca uslubu duzenler."""
    zone_name = ctx.get("zone_name")
    if zone_name:
        bolge_kurali = f'Kişi "{zone_name}" bölgesinin içindedir.'
    else:
        bolge_kurali = ('Olay bir bölge ihlali DEĞİLDİR — "yasaklı alan", '
                         '"bölge ihlali" gibi ifadeler KULLANMA.')
    duration_sec = ctx.get("duration_sec")
    sure = duration_sec if duration_sec is not None else "bilinmiyor"
    confidence = ctx.get("confidence")
    guven = confidence if confidence is not None else "bilinmiyor"
    return (
        "Sen bir güvenlik izleme sistemisin. Aşağıdaki olayı tek cümlelik, "
        "resmi bir Türkçe ihbar metnine çevir.\n"
        "KURALLAR:\n"
        '- "Eylem" alanındaki ifadeyi anlamını değiştirmeden kullan; yeni bir '
        "olay türü UYDURMA.\n"
        "- Sadece verilen alanları kullan, başka bilgi ekleme.\n"
        "- Tek cümle, en fazla 200 karakter, nokta ile bitir.\n"
        f"- {bolge_kurali}\n"
        f"Kamera: {ctx.get('camera_name') or 'bilinmiyor'}\n"
        f"Eylem: {action_phrase(ctx.get('anomaly_type') or '')}\n"
        f"Kişi sayısı: {ctx.get('track_count') or 1}\n"
        f"Süre: {sure} saniye\n"
        f"Güven: {guven}\n"
        f"Zaman: {_format_zaman(ctx.get('started_at'))}"
    )


def extract_text(data: dict) -> str:
    """candidates[0].content.parts icinden thought=true parcalar atilir,
    kalan text birlestirilir (SS3.4). Hepsi thought ise bos doner."""
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    texts = [p.get("text", "") for p in parts if not p.get("thought")]
    return "".join(texts).strip()


def usable(text: str, finish_reason: str | None = None) -> bool:
    """Kabul suzgeci (SS3.4) -- asagidakilerden biri bile tutmazsa sablona
    dusulur: bos metin, MAX_TOKENS, yarim cumle, 40'tan kisa veya 400'ten uzun."""
    if not text:
        return False
    if finish_reason == "MAX_TOKENS":
        return False
    if text[-1] not in _SENTENCE_END:
        return False
    if len(text) < 40 or len(text) > 400:
        return False
    return True


def _post(url: str, body: dict) -> httpx.Response:
    with httpx.Client(transport=_transport, timeout=LLM_TIMEOUT_SEC) as client:
        return client.post(url, json=body)


def generate_report(ctx: dict) -> tuple[str, str]:
    """(metin, mod) doner; mod: "llm" | "template". Asla istisna firlatmaz
    (SS3.7) -- LLM API cokse bile alarm zinciri sablona duserek surer."""
    template = template_report(ctx)
    if not GEMINI_API_KEY:
        return template, "template"

    global _cooldown_until
    now = time.monotonic()
    if now < _cooldown_until:
        return template, "template"

    generation_config: dict = {"temperature": 0.3, "maxOutputTokens": 300}
    if "lite" not in GEMINI_MODEL:
        # v1 dersi (SS3.4): dusunme jetonu tuketen modeller cumleyi
        # MAX_TOKENS ile yarida kesiyor.
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}
    body = {
        "contents": [{"parts": [{"text": build_prompt(ctx)}]}],
        "generationConfig": generation_config,
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")

    try:
        resp = _post(url, body)
    except httpx.HTTPError as exc:
        print(f"  gemini istegi basarisiz, sablona dusuluyor: {exc}")
        return template, "template"

    body_text = resp.text.lower()
    if resp.status_code == 429 or "quota" in body_text or "rate" in body_text:
        _cooldown_until = time.monotonic() + LLM_COOLDOWN_SEC
        print(f"  gemini kota/hiz siniri, {LLM_COOLDOWN_SEC:.0f} sn sogutmaya geciliyor")
        return template, "template"
    if resp.status_code != 200:
        print(f"  gemini HTTP {resp.status_code}, sablona dusuluyor")
        return template, "template"

    try:
        data = resp.json()
    except ValueError:
        return template, "template"

    candidates = data.get("candidates") or [{}]
    finish_reason = candidates[0].get("finishReason") if candidates else None
    text = extract_text(data)
    if not usable(text, finish_reason):
        return template, "template"
    return text, "llm"
