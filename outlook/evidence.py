"""읽기 전용 관측 어댑터. 예측/인과 추정과 기술 통계를 분리한다."""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

import db
from outlook.catalog import AXES, CATALOG_VERSION, METRICS

# 날짜/지표를 바인딩하고 DB 계층의 읽기 전용 연결을 유지한다.
OBSERVATIONS_SQL = """
SELECT metric, period, value, unit, source, fetched_at
FROM market_indicators
WHERE metric = ANY(%(metrics)s)
  AND period >= %(start)s AND period <= %(cutoff)s
  AND fetched_at < %(available_before)s
ORDER BY metric, period, fetched_at
"""


def read_observations(cutoff: date) -> list[dict]:
    with db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '15000ms'")
            cursor.execute(OBSERVATIONS_SQL, {
                "metrics": list(METRICS),
                "start": cutoff - timedelta(days=800),
                "cutoff": cutoff,
                "available_before": cutoff + timedelta(days=1),
            })
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _monthly(metric: str, observations: list[dict], cutoff: date) -> tuple[list[dict], int]:
    _, source, unit, frequency = METRICS[metric]
    unique = {}
    rejected = 0
    for row in observations:
        if row.get("metric") != metric:
            continue
        if row.get("source") != source:
            continue
        try:
            period = _date(row["period"])
            collected = _date(row["fetched_at"])
            value = float(row["value"])
        except (ValueError, TypeError, KeyError):
            rejected += 1
            continue
        if row.get("unit") != unit or not math.isfinite(value):
            rejected += 1
            continue
        if period > cutoff or collected > cutoff or period < cutoff - timedelta(days=800):
            continue
        # 완료 월만 비교하며, 동일 관측일은 수집시각이 가장 늦은 버전을 쓴다.
        month = period.replace(day=1)
        if month >= cutoff.replace(day=1):
            continue
        previous = unique.get(period)
        stamp = str(row["fetched_at"])
        if previous is None or stamp > previous["collected"]:
            unique[period] = {"date": period, "value": value, "collected": stamp}

    grouped = defaultdict(list)
    for period, row in unique.items():
        grouped[period.replace(day=1)].append(row)
    points = []
    for month, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: row["date"])
        days = calendar.monthrange(month.year, month.month)[1]
        if frequency == "daily":
            minimum, edge = math.ceil(days * 0.9), 3
        elif frequency == "business_daily":
            minimum, edge = 18, 5
        elif frequency == "weekly":
            minimum, edge = 3, 7
        else:
            minimum, edge = 1, days
        if (len(rows) < minimum or rows[0]["date"].day > edge + 1
                or rows[-1]["date"].day < days - edge):
            rejected += len(rows)
            continue
        value = (rows[-1]["value"] if frequency in {"weekly", "monthly"}
                 else sum(row["value"] for row in rows) / len(rows))
        points.append({
            "month": month.isoformat(), "value": round(value, 4),
            "observations": len(rows), "last_observation": rows[-1]["date"].isoformat(),
            "collected_at": max(row["collected"] for row in rows),
        })
    return points, rejected


def _chart(points: list[dict]) -> dict:
    if not points:
        return {"segments": [], "min": None, "max": None}
    low, high = min(p["value"] for p in points), max(p["value"] for p in points)
    months = [date.fromisoformat(p["month"]) for p in points]
    ordinals = [month.year * 12 + month.month for month in months]
    span = max(ordinals[-1] - ordinals[0], 1)
    segments, segment = [], []
    previous = None
    for point, ordinal in zip(points, ordinals, strict=True):
        if previous is not None and ordinal != previous + 1:
            segments.append(" ".join(segment))
            segment = []
        x = 8 + 284 * (ordinal - ordinals[0]) / span
        y = 42 if high == low else 70 - 56 * (point["value"] - low) / (high - low)
        segment.append(f"{x:.1f},{y:.1f}")
        previous = ordinal
    segments.append(" ".join(segment))
    return {"segments": segments, "min": low, "max": high}


def build_evidence(cutoff: date, observations: list[dict], error: bool = False) -> dict:
    metrics = {}
    expected_month = (cutoff.replace(day=1) - timedelta(days=1)).replace(day=1)
    for metric, (label, source, unit, frequency) in METRICS.items():
        points, rejected = _monthly(metric, observations, cutoff)
        latest = points[-1] if points else None
        reference = None
        if latest:
            prior = date.fromisoformat(latest["month"]).replace(year=int(latest["month"][:4]) - 1)
            reference = next((p for p in points if p["month"] == prior.isoformat()), None)
        change = latest["value"] - reference["value"] if reference else None
        metrics[metric] = {
            "id": metric, "label": label, "source": source, "unit": unit,
            "aggregation": "Month-end observation" if frequency == "weekly" else (
                "Monthly observation" if frequency == "monthly" else "Monthly mean"),
            "points": points[-24:], "chart": _chart(points[-24:]), "latest": latest,
            "reference": reference, "change": round(change, 4) if change is not None else None,
            "stale": bool(latest and latest["month"] < expected_month.isoformat()),
            "excluded": rejected,
        }
    return {
        "schema_version": 1, "catalog_version": CATALOG_VERSION,
        "market": "US gas / Henry Hub", "as_of": cutoff.isoformat(),
        "built_at": datetime.now(UTC).isoformat(),
        "basis": "Collection-time filter on current database rows; historical vintages are not reconstructed.",
        "status": "unavailable" if error else ("ready" if any(m["latest"] for m in metrics.values()) else "empty"),
        "axes": AXES, "metrics": metrics,
        "available_count": sum(bool(m["latest"]) for m in metrics.values()),
    }
