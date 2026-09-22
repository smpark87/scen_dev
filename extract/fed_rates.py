"""NGIP 중앙 DB의 미국 연방기금금리를 읽는 OUTLOOK 어댑터.

수집·갱신·스케줄은 NGIP jobs.ingest_fed_rates가 소유한다.
"""
from __future__ import annotations

import json
from datetime import date

import db


METRICS = {
    "us_effr_monthly_avg", "us_effr_daily", "us_fed_target_lower",
    "us_fed_target_upper", "us_fed_target_mid",
}


def load_fed_rates(*, metrics=None, start=None, end=None):
    """EFFR와 정책 목표범위를 읽는다. FRED나 로컬 파일로 우회하지 않는다."""
    start = date(1954, 7, 1) if start is None else start
    end = date.today() if end is None else end
    if not isinstance(start, date) or not isinstance(end, date) or start > end:
        raise ValueError("Require date filters with start <= end")
    selected = sorted(METRICS if metrics is None else set(metrics))
    if not selected or not set(selected) <= METRICS:
        raise ValueError("Unknown Federal Reserve rate metric")
    return db.query("""
        SELECT metric, period, value, unit,
               CASE WHEN metric = 'us_effr_monthly_avg' THEN 'monthly' ELSE 'daily' END AS frequency,
               source, fetched_at AS collected_at,
               CASE WHEN value IS NULL THEN 'missing' ELSE 'reported' END AS status
        FROM market_indicators
        WHERE metric = ANY(%(metrics)s::text[])
          AND period BETWEEN %(start)s AND %(end)s
        ORDER BY metric, period
    """, {"metrics": selected, "start": start, "end": end})


def load_excel_policy_rate(*, start=None, end=None):
    """기존 WTI 엑셀의 `US Policy rate`와 같은 월평균 EFFR만 읽는다."""
    return load_fed_rates(metrics=["us_effr_monthly_avg"], start=start, end=end)


def main():
    connection = db.healthcheck()
    frame = load_fed_rates()
    print(json.dumps({**connection, "rows": len(frame),
                      "reported": int(frame["value"].notna().sum()),
                      "metrics": int(frame["metric"].nunique())}))


if __name__ == "__main__":
    main()
