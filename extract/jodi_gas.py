"""NGIP 중앙 DB의 JODI-Gas 국가별 월간 수급을 읽는 OUTLOOK 어댑터.

수집·갱신·스케줄은 NGIP jobs.ingest_jodi_gas가 소유한다.
"""
from __future__ import annotations

import json
from datetime import date

import db


FLOWS = {
    "INDPROD", "OSOURCES", "TOTIMPSB", "IMPLNG", "IMPPIP", "TOTEXPSB",
    "EXPLNG", "EXPPIP", "STOCKCH", "TOTDEMC", "STATDIFF", "TOTDEMO",
    "MAINTOT", "CLOSTLV",
}
UNITS = {"million_m3", "TJ", "thousand_tonnes"}


def load_jodi_gas(*, countries=None, flows=None, units=None, assessments=None,
                  start=date(2009, 1, 1), end=None):
    """국가 수급 실적과 JODI 품질등급을 읽는다. 원천 파일로 우회하지 않는다."""
    end = date.today() if end is None else end
    if not isinstance(start, date) or not isinstance(end, date) or start > end:
        raise ValueError("Require date filters with start <= end")
    country_codes = None if countries is None else sorted({str(code).upper() for code in countries})
    if country_codes is not None and (not country_codes or any(
            len(code) != 2 or not code.isascii() or not code.isalpha() for code in country_codes)):
        raise ValueError("Expected two-letter JODI country codes")
    flow_codes = None if flows is None else sorted({str(flow).upper() for flow in flows})
    if flow_codes is not None and (not flow_codes or not set(flow_codes) <= FLOWS):
        raise ValueError("Unknown JODI-Gas flow")
    unit_names = None if units is None else sorted(set(units))
    if unit_names is not None and (not unit_names or not set(unit_names) <= UNITS):
        raise ValueError("Unknown JODI-Gas unit")
    quality = None if assessments is None else sorted(set(assessments))
    if quality is not None and (not quality or not set(quality) <= {1, 2, 3}):
        raise ValueError("JODI assessment must be 1, 2, or 3")
    return db.query("""
        SELECT split_part(metric, '_', 5) AS country_code,
               upper(split_part(metric, '_', 4)) AS flow,
               period, 'monthly' AS frequency, value, unit,
               right(source, 1)::integer AS assessment_code,
               source, fetched_at AS collected_at
        FROM market_indicators
        WHERE starts_with(metric, 'jodi_gas_')
          AND period BETWEEN %(start)s AND %(end)s
          AND (%(countries)s::text[] IS NULL OR split_part(metric, '_', 5) = ANY(%(countries)s::text[]))
          AND (%(flows)s::text[] IS NULL OR upper(split_part(metric, '_', 4)) = ANY(%(flows)s::text[]))
          AND (%(units)s::text[] IS NULL OR unit = ANY(%(units)s::text[]))
          AND (%(assessments)s::integer[] IS NULL OR right(source, 1)::integer = ANY(%(assessments)s::integer[]))
        ORDER BY country_code, flow, unit, period
    """, {"countries": country_codes, "flows": flow_codes, "units": unit_names,
           "assessments": quality, "start": start, "end": end})


def main():
    connection = db.healthcheck()
    frame = load_jodi_gas()
    print(json.dumps({**connection, "rows": len(frame),
                      "countries": int(frame["country_code"].nunique()),
                      "flows": int(frame["flow"].nunique())}))


if __name__ == "__main__":
    main()
