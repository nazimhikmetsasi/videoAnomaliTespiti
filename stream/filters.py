"""Oturum kabul esigi: Spark'siz da test edilebilen SAF fonksiyon.

`spark_job.py` ayni mantigi sutun ifadesiyle (create_map + element_at) uygular
-- streaming DAG'inde performans icin UDF yerine native Spark ifadeleri
kullanilir (ASAMA4_PLAN.md SS5.3). Bu modul o mantigin TEK referans kopyasidir
ve pyspark'a bagimli DEGILDIR: `eval/spark_eval.py` esik supurmesinde (--sweep)
ve `tests/test_publish.py` broker'siz oz kontrolde aynen bunu cagirir. Boylece
iki yerde iki farkli esik mantigi olusmaz.
"""

from __future__ import annotations

# ASAMA4_PLAN.md SS5.3: FALL bir darbedir (min_sec=0, hits>=2 tek koruma),
# RUN/ZONE/LOITERING bir durumdur (kare hizindan bagimsiz sure sarti).
MIN_SEC_DEFAULT_MAP: dict[str, float] = {
    "FALL": 0.0,
    "RUN": 1.0,
    "ZONE_VIOLATION": 1.0,
    "LOITERING": 2.0,
    "FIGHT": 0.5,
}


def session_passes(hits: int, duration_sec: float, anomaly_type: str,
                    min_hits: int, min_sec: dict[str, float] | None = None,
                    min_sec_default: float = 1.0) -> bool:
    """SS5.3 filtresi: hits >= min_hits VE duration_sec >= tipe gore min_sec."""
    table = MIN_SEC_DEFAULT_MAP if min_sec is None else min_sec
    threshold = table.get(anomaly_type, min_sec_default)
    return hits >= min_hits and duration_sec >= threshold
