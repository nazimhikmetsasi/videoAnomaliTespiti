"""Kucuk test istemcisi: /ws/live ve /ws/meta akislarina baglanir, kare
sayar, uctan uca gecikmeyi olcer (ASAMA6_PLAN.md SS13, SS12 olcum 1-2).

Panelin YERINI TUTMAZ -- Asama 8'de gercek panel bunun yerine gecer.

Calistirma:
    venv\\Scripts\\python.exe scripts/ws_client.py --camera-id run_01 --token <jwt> --seconds 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import websockets


async def _count_frames(uri: str, seconds: float, counter: list[int]) -> None:
    try:
        async with websockets.connect(uri) as ws:
            deadline = time.monotonic() + seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                try:
                    await asyncio.wait_for(ws.recv(), timeout=remaining)
                    counter[0] += 1
                except asyncio.TimeoutError:
                    return
    except Exception as exc:  # noqa: BLE001
        print(f"  [live] baglanti hatasi: {exc}")


async def _measure_latency(uri: str, seconds: float, samples: list[float]) -> None:
    try:
        async with websockets.connect(uri) as ws:
            deadline = time.monotonic() + seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    return
                recv_at = time.time()
                try:
                    meta = json.loads(raw)
                except ValueError:
                    continue
                if "ts" in meta:
                    samples.append((recv_at - float(meta["ts"])) * 1000.0)
    except Exception as exc:  # noqa: BLE001
        print(f"  [meta] baglanti hatasi: {exc}")


async def _watch_alerts(uri: str, seconds: float, alerts: list[dict]) -> None:
    """SS12 olcum 4: kirmizi alarm /ws/alerts'ten (api, 8000) cikinca gelis
    ani kaydedilir. Gecikme, olayin BITISI ile alarmin gelisi arasindaki
    farktir -- Spark oturum boslugu + damga + mikro-toplu + tuketici bu
    araliktadir.

    EPOCH alani `end_time`, `end_ts` DEGIL: stream/spark_job.py `end_ts`'i
    adayin SAHNE zamanindan uretir (dosya kaynaginda 0'dan baslar), epoch'u
    ise `end_time` tasir (event_time'in double hali). `end_ts` kullanmak
    dosya kaynaginda epoch'un tamamini gecikme sanmaya yol acar."""
    try:
        async with websockets.connect(uri) as ws:
            deadline = time.monotonic() + seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    return
                recv_at = time.time()
                try:
                    body = json.loads(raw)
                except ValueError:
                    continue
                end_time = body.get("end_time")
                alerts.append({
                    "recv_at": recv_at,
                    "type": body.get("anomaly_type"),
                    "camera": body.get("camera_name") or body.get("camera_id"),
                    "lag_ms": (recv_at - float(end_time)) * 1000.0 if end_time else None,
                })
    except Exception as exc:  # noqa: BLE001
        print(f"  [alerts] baglanti hatasi: {exc}")


def _pct(samples: list[float], p: float) -> float:
    s = sorted(samples)
    return s[min(len(s) - 1, int(len(s) * p))] if s else 0.0


async def _run(args: argparse.Namespace) -> None:
    live_uri = f"{args.url}/ws/live/{args.camera_id}?token={args.token}"
    meta_uri = f"{args.url}/ws/meta/{args.camera_id}?token={args.token}"

    frame_count = [0]
    latency_samples: list[float] = []
    alerts: list[dict] = []

    tasks = [
        _count_frames(live_uri, args.seconds, frame_count),
        _measure_latency(meta_uri, args.seconds, latency_samples),
    ]
    if args.alerts_url:
        # /ws/alerts api'de (8000), live/meta vision'da (8001) -- panel de iki
        # ayri origin'e baglanir (ASAMA6_PLAN.md SS1).
        tasks.append(_watch_alerts(
            f"{args.alerts_url}/ws/alerts?token={args.token}", args.seconds, alerts))

    await asyncio.gather(*tasks)

    fps = frame_count[0] / args.seconds
    print(f"\n  kare sayisi ({args.seconds:.0f} sn)  : {frame_count[0]}")
    print(f"  FPS                      : {fps:.1f}")
    if latency_samples:
        print(f"  gecikme p50 (ms)         : {_pct(latency_samples, 0.50):.1f}")
        print(f"  gecikme p95 (ms)         : {_pct(latency_samples, 0.95):.1f}")
        print(f"  meta ornek sayisi        : {len(latency_samples)}")
    else:
        print("  gecikme                  : olculemedi (meta gelmedi)")

    if args.alerts_url:
        print(f"  kirmizi alarm sayisi     : {len(alerts)}")
        for a in alerts:
            lag = f"{a['lag_ms']/1000:.1f} sn" if a["lag_ms"] is not None else "end_time yok"
            print(f"    {a['type']} (kamera {a['camera']})  olay bitisinden beri: {lag}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Asama 6 WS test istemcisi")
    parser.add_argument("--url", default="ws://localhost:8001")
    parser.add_argument("--alerts-url", default="",
                        help="kirmizi alarm WS'i, orn. ws://localhost:8000 (bos = olculmez)")
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--token", default="", help="JWT (?token= ile gonderilir)")
    parser.add_argument("--seconds", type=float, default=10.0)
    return parser.parse_args()


def main() -> int:
    asyncio.run(_run(parse_args()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
