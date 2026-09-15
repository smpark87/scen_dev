"""ngip 운영 DB 읽기 전용 접근 계층.

**모든 DB 접근은 이 모듈을 경유한다.** 다른 모듈에서 psycopg2 를 직접 부르지 않는다.

이중 방어:
  1) 계정 자체가 읽기 전용 (scen_ro — SELECT 권한만 보유)
  2) 연결 세션도 read-only 로 강제 (default_transaction_read_only)

운영 DB(ngip-prod)는 LIORA 와 20종 크론이 상시 사용 중이다. 쓰기가 한 번이라도
새어 들어가면 운영 데이터가 손상된다. 그래서 "조심한다"가 아니라 구조로 막는다.
"""
from __future__ import annotations

import contextlib
from typing import Any, Iterator, Sequence

import pandas as pd
import psycopg2

from config import env

_READ_ONLY_OPTS = "-c default_transaction_read_only=on -c statement_timeout=600000"


def _dsn() -> str:
    raw = env("SCEN_DATABASE_URL")
    # SQLAlchemy 형식이 들어와도 받아준다
    return raw.replace("postgresql+psycopg2://", "postgresql://")


@contextlib.contextmanager
def connect() -> Iterator[psycopg2.extensions.connection]:
    """읽기 전용 연결. with 블록을 벗어나면 항상 닫힌다."""
    conn = psycopg2.connect(_dsn(), options=_READ_ONLY_OPTS, connect_timeout=30)
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: Sequence[Any] | dict | None = None) -> pd.DataFrame:
    """SELECT 결과를 DataFrame 으로. 대용량은 query_chunks 를 쓴다."""
    with connect() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def query_iter(
    sql: str,
    params: Sequence[Any] | dict | None = None,
    chunksize: int = 5_000,
) -> Iterator[pd.DataFrame]:
    """서버사이드 커서로 나눠 읽는다. 임베딩(1536차원 × 6만행) 같은 대용량용.

    한 번에 다 올리면 메모리도 문제지만, 운영 DB 쪽 부하도 커진다.
    """
    with connect() as conn:
        with conn.cursor(name="scen_ro_cursor") as cur:
            cur.itersize = chunksize
            cur.execute(sql, params)
            cols: list[str] | None = None
            while True:
                rows = cur.fetchmany(chunksize)
                if not rows:
                    break
                # 서버사이드 커서는 첫 fetch 이후에야 description 이 채워진다
                if cols is None:
                    cols = [d[0] for d in cur.description]
                yield pd.DataFrame(rows, columns=cols)


def healthcheck() -> dict[str, Any]:
    """접속 계정과 읽기전용 여부를 확인한다. 스크립트 시작 시 1회 호출 권장."""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT current_user, current_setting('transaction_read_only')")
        user, ro = cur.fetchone()
        ok = (ro == "on")
        if not ok:
            raise RuntimeError(f"세션이 read-only 가 아니다 (user={user}) — 중단")
        return {"user": user, "read_only": ok}
