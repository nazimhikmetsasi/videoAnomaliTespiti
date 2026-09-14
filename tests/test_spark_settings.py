"""Spark'in esikleri API'den cekmesi: suresi dolmus jetonda yeniden giris.

Olculen ariza (docs/DURUM.md Asama 12.2): `.env`'e elle yapistirilan JWT
`JWT_EXPIRE_MINUTES` (720 dk) sonra oluyordu. Spark 401 aliyor, tek satir
uyari basip ortam varsayilanlarina dusuyordu -- yani panelden esik
degistirmek Spark suzgecini HIC etkilemiyordu ve hicbir sey gurultulu
bicimde basarisiz olmuyordu.

pyspark kurulu olmayabilir; bu test yalnizca HTTP katmanini olcer ve
spark_job.py'yi ice aktarmaz (ice aktarim SparkSession kurmaya calisir).

    venv\\Scripts\\python.exe -m pytest tests/test_spark_settings.py -q
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_module(monkeypatch, **env):
    """spark_job.py'yi pyspark OLMADAN yukler: pyspark isimleri sahte modulle
    karsilanir. Amac HTTP fonksiyonlarini olcmek, Spark'i degil."""
    for key in ("SETTINGS_API_URL", "SETTINGS_API_TOKEN",
                "SETTINGS_API_USER", "SETTINGS_API_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    if importlib.util.find_spec("pyspark") is None:
        fake = types.ModuleType("pyspark")
        sql = types.ModuleType("pyspark.sql")
        functions = types.ModuleType("pyspark.sql.functions")
        spark_types = types.ModuleType("pyspark.sql.types")
        sql.SparkSession = object
        for name in ("coalesce", "col", "concat_ws", "count", "create_map",
                     "element_at", "from_json", "lit", "max", "max_by", "min",
                     "session_window", "struct", "to_json"):
            setattr(functions, name, lambda *a, **k: None)
        for name in ("ArrayType", "DoubleType", "IntegerType", "MapType",
                     "StringType", "StructField", "StructType"):
            setattr(spark_types, name, lambda *a, **k: None)
        for name, mod in (("pyspark", fake), ("pyspark.sql", sql),
                          ("pyspark.sql.functions", functions),
                          ("pyspark.sql.types", spark_types)):
            monkeypatch.setitem(sys.modules, name, mod)

    sys.modules.pop("spark_job", None)
    spec = importlib.util.spec_from_file_location(
        "spark_job", ROOT / "stream" / "spark_job.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "spark_job", module)
    spec.loader.exec_module(module)
    return module


SETTINGS_BODY = {"spark_window_sec": 7, "spark_min_hits": 4,
                 "spark_min_sec": {"FALL": 1.5}}


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://api:8000/api/settings", code,
                                  "gecersiz jeton", {}, None)


def test_suresi_dolmus_jeton_yeniden_giris_tetikler(monkeypatch) -> None:
    mod = _load_module(monkeypatch, SETTINGS_API_URL="http://api:8000",
                       SETTINGS_API_TOKEN="bayat", SETTINGS_API_PASSWORD="s3cret")
    cagrilar: list[str] = []

    def fake_urlopen(req, timeout=0):
        url = req.full_url
        if url.endswith("/api/auth/login"):
            cagrilar.append("login")
            # Govde FORM-kodlu olmali, JSON degil (OAuth2PasswordRequestForm)
            assert b"username=admin" in req.data and b"password=s3cret" in req.data
            return _Resp({"access_token": "taze"})
        cagrilar.append(f"settings:{req.get_header('Authorization')}")
        if req.get_header("Authorization") == "Bearer bayat":
            raise _http_error(401)
        return _Resp(SETTINGS_BODY)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod.fetch_settings_from_api() == (7, 4, {"FALL": 1.5})
    assert cagrilar == ["settings:Bearer bayat", "login", "settings:Bearer taze"]


def test_giris_de_basarisizsa_varsayilana_duser(monkeypatch) -> None:
    mod = _load_module(monkeypatch, SETTINGS_API_URL="http://api:8000",
                       SETTINGS_API_TOKEN="bayat", SETTINGS_API_PASSWORD="yanlis")

    def fake_urlopen(req, timeout=0):
        if req.full_url.endswith("/api/auth/login"):
            raise _http_error(401)
        raise _http_error(401)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod.fetch_settings_from_api() is None, "cokmemeli, None donmeli"


def test_parola_yoksa_giris_denenmez(monkeypatch) -> None:
    """Eski davranis korunur: kimlik yoksa tek satir uyari + varsayilanlar."""
    mod = _load_module(monkeypatch, SETTINGS_API_URL="http://api:8000",
                       SETTINGS_API_TOKEN="bayat")
    cagrilar: list[str] = []

    def fake_urlopen(req, timeout=0):
        cagrilar.append(req.full_url)
        raise _http_error(401)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod.fetch_settings_from_api() is None
    assert not any("login" in url for url in cagrilar)


def test_401_disi_hata_giris_denemez(monkeypatch) -> None:
    """500 bir kimlik sorunu degildir; yeniden giris onu duzeltmez."""
    mod = _load_module(monkeypatch, SETTINGS_API_URL="http://api:8000",
                       SETTINGS_API_TOKEN="iyi", SETTINGS_API_PASSWORD="s3cret")
    cagrilar: list[str] = []

    def fake_urlopen(req, timeout=0):
        cagrilar.append(req.full_url)
        raise _http_error(500)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod.fetch_settings_from_api() is None
    assert not any("login" in url for url in cagrilar)


def test_jetonsuz_dogrudan_giris_ve_okuma(monkeypatch) -> None:
    """SPARK_SETTINGS_TOKEN artik zorunlu degil: bos jetonla 401 alinir,
    giris yapilir, esikler okunur."""
    mod = _load_module(monkeypatch, SETTINGS_API_URL="http://api:8000",
                       SETTINGS_API_PASSWORD="s3cret")

    def fake_urlopen(req, timeout=0):
        if req.full_url.endswith("/api/auth/login"):
            return _Resp({"access_token": "taze"})
        if req.get_header("Authorization") != "Bearer taze":
            raise _http_error(401)
        return _Resp(SETTINGS_BODY)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    assert mod.fetch_settings_from_api() == (7, 4, {"FALL": 1.5})


def test_api_url_yoksa_ozellik_kapali(monkeypatch) -> None:
    mod = _load_module(monkeypatch, SETTINGS_API_PASSWORD="s3cret")
    assert mod.fetch_settings_from_api() is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
