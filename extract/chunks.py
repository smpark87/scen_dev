"""D2 — 청크 임베딩 + 메타데이터를 로컬 parquet 스냅샷으로 추출.

왜 스냅샷인가 (07-demo-plan §1):
  1) 반복 실험이 본체다. 집계·Factor 방식을 수십 번 바꿔 돌린다.
     매번 RDS에서 373MB를 끌어오면 회당 수 분, 로컬은 수 초.
  2) 운영 DB 보호. ngip-prod 는 RAM 2GB 인데 LIORA 의 HNSW 인덱스가 466MB다.
     임베딩 컬럼을 반복 풀스캔하면 그 인덱스가 캐시에서 밀려 LIORA 가 느려진다.
  3) 재현성. 크론 20종이 매일 돌아 코퍼스가 계속 늘어난다.
     스냅샷을 얼리지 않으면 1주차와 3주차 결과를 비교할 수 없다.

산출:
  data/chunks_<snapshot>.parquet   청크별 임베딩(float16) + 문서 메타
  data/snapshot.json               스냅샷 시점·행수·해시 (재현성 기록)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from config import CORPUS_DATE_MAX, CORPUS_DATE_MIN, DATA, EMBED_DIM  # noqa: E402

# 임베딩은 text 로 받아 파싱한다(pgvector -> '[0.1,0.2,...]').
# 벡터 타입을 그대로 받으려면 register_vector 가 필요한데, 읽기 전용 데모에서는
# 의존성을 늘리지 않고 텍스트 파싱이 단순하고 안전하다.
SQL = """
SELECT
    c.id                        AS chunk_id,
    c.document_id,
    c.chunk_index,
    c.token_count,
    c.embedding::text           AS emb,
    d.source_type,
    d.source_name,
    d.title,
    d.published_at
FROM ai_document_chunks c
JOIN ai_documents d ON d.id = c.document_id
WHERE c.embedding IS NOT NULL
  AND d.published_at IS NOT NULL
  AND d.published_at >= %(dmin)s
  AND d.published_at <  %(dmax)s
ORDER BY c.id
"""


def _parse_vec(s: str) -> np.ndarray:
    return np.fromstring(s.strip()[1:-1], sep=",", dtype=np.float32)


def main() -> None:
    info = db.healthcheck()
    print(f"DB 접속: {info['user']} (read_only={info['read_only']})")

    snapshot = datetime.now(timezone.utc)
    params = {"dmin": CORPUS_DATE_MIN, "dmax": CORPUS_DATE_MAX}

    metas: list[pd.DataFrame] = []
    vecs: list[np.ndarray] = []
    n = 0
    for part in db.query_iter(SQL, params, chunksize=2_000):
        arr = np.vstack([_parse_vec(s) for s in part["emb"]])
        if arr.shape[1] != EMBED_DIM:
            raise ValueError(f"차원 불일치: {arr.shape[1]} != {EMBED_DIM}")
        vecs.append(arr.astype(np.float16))       # 저장 절반 (03/02 §10.4 정밀도 축소)
        metas.append(part.drop(columns=["emb"]))
        n += len(part)
        print(f"  ... {n:,} 청크", end="\r", flush=True)
    print()

    if not metas:
        raise SystemExit("추출된 청크가 없다 — 쿼리/기간 확인")

    meta = pd.concat(metas, ignore_index=True)
    emb = np.vstack(vecs)
    assert len(meta) == len(emb)

    # 날짜 정규화: 집계는 일 단위로 한다. tz 는 UTC 기준으로 통일.
    meta["published_at"] = pd.to_datetime(meta["published_at"], utc=True)
    meta["date"] = meta["published_at"].dt.date

    # 임베딩을 컬럼 하나(list)로 넣으면 parquet 이 비대해진다.
    # 별도 2D 배열을 그대로 저장할 수 있도록 컬럼 분해 대신 npy 병행 저장.
    stamp = snapshot.strftime("%Y%m%dT%H%M%SZ")
    meta_path = DATA / f"chunks_meta_{stamp}.parquet"
    emb_path = DATA / f"chunks_emb_{stamp}.npy"
    meta.to_parquet(meta_path, index=False)
    np.save(emb_path, emb)

    # 최신 스냅샷을 가리키는 고정 이름 (분석 코드가 이걸 읽는다)
    (DATA / "latest.json").write_text(
        json.dumps(
            {
                "snapshot_utc": snapshot.isoformat(),
                "rows": int(len(meta)),
                "dim": int(emb.shape[1]),
                "meta": meta_path.name,
                "emb": emb_path.name,
                "date_min": str(meta["date"].min()),
                "date_max": str(meta["date"].max()),
                "emb_dtype": str(emb.dtype),
                "size_mb": round(emb.nbytes / 1e6, 1),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"\n스냅샷 {stamp}")
    print(f"  청크        {len(meta):,}")
    print(f"  기간        {meta['date'].min()} ~ {meta['date'].max()}")
    print(f"  임베딩      {emb.shape} {emb.dtype}  ({emb.nbytes/1e6:.1f} MB)")
    print(f"  meta        {meta_path.name}")
    print(f"  emb         {emb_path.name}")
    print("\nsource_type 구성:")
    print(meta["source_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
