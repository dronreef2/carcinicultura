"""
Carregamento de dados do dashboard.

- Fonte API: consome o backend FastAPI real.
- Fonte simulada: usa gerador local para demo/offline.
"""

from __future__ import annotations

from typing import Any
import os

import numpy as np
import pandas as pd
import requests

from data_simulator import (
    generate_ponds,
    generate_sensor_data,
    generate_cycles,
    generate_biometrics,
    generate_harvests,
    generate_management_events,
    generate_alerts,
)

SENSOR_COLUMNS = [
    "temperature",
    "ph",
    "salinity",
    "dissolved_oxygen",
    "turbidity",
    "tds",
    "electrical_conductivity",
]


def _empty_events_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "pond_id", "event_type", "details"])


def _empty_cycles_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "id",
            "pond_id",
            "start_date",
            "end_date",
            "species",
            "stocking_density",
            "initial_biomass",
            "system_type",
            "status",
            "day",
        ]
    )


def _empty_biometrics_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "id",
            "cycle_id",
            "pond_id",
            "timestamp",
            "avg_weight_g",
            "sample_size",
            "survival_estimate",
        ]
    )


def _empty_harvests_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "id",
            "cycle_id",
            "pond_id",
            "timestamp",
            "harvest_weight_kg",
            "survival_rate",
            "avg_final_weight_g",
            "price_per_kg",
            "total_revenue",
            "productivity_kg_ha",
        ]
    )


def _build_simulated_data() -> dict[str, Any]:
    ponds = generate_ponds()

    sensor_data: dict[str, pd.DataFrame] = {}
    for pond_id in ponds[ponds["status"] == "active"]["id"]:
        sensor_data[pond_id] = generate_sensor_data(pond_id, hours=168)

    cycles = generate_cycles()
    biometrics = generate_biometrics(cycles)
    harvests = generate_harvests(cycles)
    events = generate_management_events(ponds, days=7)
    alerts = generate_alerts(sensor_data)

    return {
        "ponds": ponds,
        "sensor_data": sensor_data,
        "cycles": cycles,
        "biometrics": biometrics,
        "harvests": harvests,
        "events": events,
        "alerts": alerts,
    }


def _normalize_readings(readings: list[dict[str, Any]], pond_id: str) -> pd.DataFrame:
    if not readings:
        df = pd.DataFrame(columns=["timestamp", "pond_id", "device_id"] + SENSOR_COLUMNS)
        return df

    df = pd.DataFrame(readings)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.NaT

    if "pond_id" not in df.columns:
        df["pond_id"] = pond_id

    if "device_id" not in df.columns:
        df["device_id"] = "unknown"

    for col in SENSOR_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    df = df[["timestamp", "pond_id", "device_id"] + SENSOR_COLUMNS]
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _normalize_alerts(alerts_rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not alerts_rows:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "pond_id",
                "alert_type",
                "severity",
                "parameter",
                "value",
                "threshold",
                "message",
                "handled",
            ]
        )

    rows: list[dict[str, Any]] = []
    for row in alerts_rows:
        rows.append(
            {
                "timestamp": row.get("timestamp"),
                "pond_id": row.get("pond_id"),
                "alert_type": "temperature",
                "severity": row.get("severidade", "warning"),
                "parameter": "temperature",
                "value": row.get("temperatura"),
                "threshold": np.nan,
                "message": row.get("mensagem", ""),
                "handled": row.get("reconhecido", False),
            }
        )

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def _build_api_data(api_base_url: str, timeout_s: int = 8) -> dict[str, Any]:
    sess = requests.Session()

    health = sess.get(f"{api_base_url}/api/health", timeout=timeout_s)
    health.raise_for_status()

    ponds_resp = sess.get(f"{api_base_url}/api/ponds", timeout=timeout_s)
    ponds_resp.raise_for_status()
    ponds_json = ponds_resp.json()

    ponds = pd.DataFrame(ponds_json)
    if ponds.empty:
        ponds = pd.DataFrame(columns=["id", "name", "status", "area_m2", "depth_m", "system_type"])

    # Campos esperados pelas paginas do dashboard
    if "area_m2" not in ponds.columns:
        ponds["area_m2"] = 5000
    if "depth_m" not in ponds.columns:
        ponds["depth_m"] = 1.2
    if "system_type" not in ponds.columns:
        ponds["system_type"] = "monitoramento"

    ponds["status"] = ponds.get("status", "active").fillna("active")

    sensor_data: dict[str, pd.DataFrame] = {}
    all_alerts: list[dict[str, Any]] = []

    active_ponds = ponds[ponds["status"] == "active"]["id"].tolist()
    for pond_id in active_ponds:
        readings_resp = sess.get(
            f"{api_base_url}/api/ponds/{pond_id}/readings",
            params={"hours": 168, "limit": 3000},
            timeout=timeout_s,
        )
        readings_resp.raise_for_status()
        sensor_data[pond_id] = _normalize_readings(readings_resp.json(), pond_id)

        alerts_resp = sess.get(
            f"{api_base_url}/api/ponds/{pond_id}/alerts",
            params={"hours": 168, "limit": 200},
            timeout=timeout_s,
        )
        alerts_resp.raise_for_status()
        all_alerts.extend(alerts_resp.json())

    alerts = _normalize_alerts(all_alerts)

    return {
        "ponds": ponds,
        "sensor_data": sensor_data,
        "cycles": _empty_cycles_df(),
        "biometrics": _empty_biometrics_df(),
        "harvests": _empty_harvests_df(),
        "events": _empty_events_df(),
        "alerts": alerts,
    }


def load_dashboard_data(source_mode: str = "auto", api_base_url: str | None = None):
    """
    Retorna (data, data_info).

    data_info:
    - source: "api" ou "sim"
    - error: mensagem de erro no fallback automatico
    """
    mode = (source_mode or "auto").lower()
    api_url = (api_base_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")).rstrip("/")
    timeout_s = int(os.getenv("API_TIMEOUT_S", "8"))

    if mode == "sim":
        return _build_simulated_data(), {"source": "sim", "error": None}

    if mode == "api":
        data = _build_api_data(api_base_url=api_url, timeout_s=timeout_s)
        return data, {"source": "api", "error": None}

    try:
        data = _build_api_data(api_base_url=api_url, timeout_s=timeout_s)
        return data, {"source": "api", "error": None}
    except Exception as exc:
        fallback = _build_simulated_data()
        return fallback, {"source": "sim", "error": str(exc)}
