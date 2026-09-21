"""NGIP 중앙 DB의 World Bank GDP를 읽는 OUTLOOK 어댑터.

수집·갱신·스케줄은 NGIP jobs.ingest_worldbank_gdp가 소유한다.
"""
from __future__ import annotations
import json
from datetime import date
import db

METRICS = {"gdp_real", "gdp_nominal", "gdp_growth"}


def load_gdp(*, economies=None, metrics=None, start=1995, end=None):
    """국가/집계와 결측을 구분해 연간 GDP를 읽는다. 원천 API 호출은 없다."""
    end = date.today().year if end is None else end
    if not 1960 <= start <= end <= date.today().year:
        raise ValueError("Require 1960 <= start <= end <= current year")
    if metrics is not None and not set(metrics) <= METRICS:
        raise ValueError("Unknown GDP metric")
    codes = None if economies is None else [str(code).upper() for code in economies]
    if codes is not None and any(len(code) != 3 or not code.isascii() or not code.isalpha() for code in codes):
        raise ValueError("Expected three-letter World Bank economy codes")
    return db.query("""
        SELECT split_part(metric, '_', 5) AS economy_code,
               'gdp_' || split_part(metric, '_', 3) AS metric,
               split_part(metric, '_', 4) = 'a' AS is_aggregate,
               extract(year FROM period)::integer AS year,
               'annual' AS frequency, value, unit, source,
               right(source, 10) AS source_updated_on,
               fetched_at AS collected_at,
               CASE WHEN value IS NULL THEN 'missing' ELSE 'reported' END AS status
        FROM market_indicators
        WHERE starts_with(metric, 'wb_gdp_')
          AND period BETWEEN %(start)s AND %(end)s
          AND (%(codes)s::text[] IS NULL OR split_part(metric, '_', 5) = ANY(%(codes)s::text[]))
          AND (%(metrics)s::text[] IS NULL OR 'gdp_' || split_part(metric, '_', 3) = ANY(%(metrics)s::text[]))
        ORDER BY economy_code, metric, period
    """, {"start": date(start, 1, 1), "end": date(end, 12, 31), "codes": codes,
           "metrics": None if metrics is None else list(metrics)})


def main():
    connection = db.healthcheck()
    frame = load_gdp()
    print(json.dumps({**connection, "rows": len(frame),
                      "reported": int(frame["value"].notna().sum()),
                      "economies": int(frame["economy_code"].nunique())}))


if __name__ == "__main__":
    main()
