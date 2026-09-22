"""NGIP 중앙 DB의 GIE LNG 터미널 발행본을 읽는 OUTLOOK 어댑터.

수집·원본 보존·스케줄은 NGIP jobs.ingest_gie_lng가 소유한다.
"""
from __future__ import annotations

import json

import db


SOURCE = "gie_lng_database"
STATUSES = {"operating", "proposed", "construction", "suspended",
            "retired", "relocated", "other"}


def load_gie_lng_assets(*, countries=None, statuses=None, startup_from=None,
                        startup_to=None, release_id=None):
    """선택한 발행본의 유럽 LNG 터미널 phase를 읽는다. 기본은 최신 발행본이다."""
    country_names = None if countries is None else sorted({
        str(country).strip() for country in countries if str(country).strip()
    })
    if countries is not None and (not country_names or any(
            len(country) > 80 for country in country_names)):
        raise ValueError("Expected non-empty GIE country names")
    status_names = None if statuses is None else sorted({
        str(status).strip().lower() for status in statuses if str(status).strip()
    })
    if statuses is not None and (not status_names or not set(status_names) <= STATUSES):
        raise ValueError("Unknown GIE LNG normalized status")
    for value in (startup_from, startup_to):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                  or not 1900 <= value <= 2100):
            raise ValueError("GIE LNG startup year must be 1900..2100")
    if startup_from is not None and startup_to is not None and startup_from > startup_to:
        raise ValueError("Require startup_from <= startup_to")
    if release_id is not None and (isinstance(release_id, bool)
                                   or not isinstance(release_id, int) or release_id <= 0):
        raise ValueError("GIE LNG release_id must be a positive integer")

    return db.query("""
        WITH chosen AS (
            SELECT id
            FROM lng_asset_releases
            WHERE source = %(source)s
              AND (%(release_id)s::integer IS NULL OR id = %(release_id)s)
            ORDER BY release_date DESC, collected_at DESC, id DESC
            LIMIT 1
        )
        SELECT r.id AS release_id, r.release_date, r.collected_at,
               r.source_page_url, r.download_url, r.raw_sha256, r.raw_uri,
               a.source_row, a.source_asset_id, a.direction, a.country, a.region,
               a.asset_name, a.phase_name, a.status_raw, a.status_normalized,
               a.startup_year, a.facility_type, a.operator_name,
               a.capacity_mtpa, a.capacity_bcm_pa, a.capacity_m3h,
               a.storage_m3_lng, a.metadata_json
        FROM chosen c
        JOIN lng_asset_releases r ON r.id = c.id
        JOIN lng_asset_snapshots a ON a.release_id = r.id
        WHERE (%(countries)s::text[] IS NULL OR a.country = ANY(%(countries)s::text[]))
          AND (%(statuses)s::text[] IS NULL OR a.status_normalized = ANY(%(statuses)s::text[]))
          AND (%(startup_from)s::integer IS NULL OR a.startup_year >= %(startup_from)s)
          AND (%(startup_to)s::integer IS NULL OR a.startup_year <= %(startup_to)s)
        ORDER BY a.country, a.asset_name, a.source_row
    """, {"source": SOURCE, "release_id": release_id, "countries": country_names,
           "statuses": status_names, "startup_from": startup_from,
           "startup_to": startup_to})


def main():
    connection = db.healthcheck()
    frame = load_gie_lng_assets()
    summary = {**connection, "rows": len(frame)}
    if not frame.empty:
        summary.update({"release_date": str(frame["release_date"].iloc[0]),
                        "countries": int(frame["country"].nunique()),
                        "assets": int(frame[["country", "asset_name"]].drop_duplicates().shape[0])})
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
