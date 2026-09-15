"""D6 보조 — 축 양 끝 청크의 **본문**을 가져온다.

제목만으로는 축 판정이 안 되는 덩어리가 있다. 기상 예보 노트는 제목이
"Weather", "Lower 48 Forecast" 뿐이라 폭염인지 한파인지 제목에 없다.
임베딩은 본문으로 만들어졌으니 축은 멀쩡한데 **사람이 읽을 근거**가 없는 것.

축마다 양 끝 N개 청크의 본문을 끌어와 로컬에 저장한다.
읽기 전용·1회성이며, 데모 화면(축 해석)에도 그대로 쓴다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from config import DATA  # noqa: E402
from analysis.factors import N_AXES, wpca  # noqa: E402

TOP = 8


def main() -> None:
    meta = pd.read_parquet(DATA / "market_meta.parquet").reset_index(drop=True)
    meta["date"] = pd.to_datetime(meta["date"])
    meta = meta.merge(pd.read_parquet(DATA / "clusters.parquet"), on="chunk_id")
    X = np.load(DATA / "emb_centered.npy").astype(np.float32)
    k = int(meta.cluster.max()) + 1

    picks: list[dict] = []
    for c in range(k):
        idx = meta.index[meta.cluster == c].to_numpy()
        if len(idx) < 250:
            continue
        sub = meta.loc[idx]
        Xi = X[idx].copy()
        cells = (sub.source_type + "|" + sub.lang).to_numpy()
        for cv in np.unique(cells):
            m = cells == cv
            if m.sum() >= 25:
                Xi[m] -= Xi[m].mean(axis=0)
        Z, _V, _evr, _mu = wpca(Xi, sub.w.to_numpy(dtype=np.float64), N_AXES)
        for ax in range(N_AXES):
            o = np.argsort(Z[:, ax])
            for tag, order in (("neg", o[:TOP]), ("pos", o[::-1][:TOP])):
                for rank, i in enumerate(order):
                    picks.append({
                        "cluster": c, "axis": ax, "end": tag, "rank": rank,
                        "chunk_id": int(sub.iloc[i].chunk_id),
                        "score": float(Z[i, ax]),
                    })
    p = pd.DataFrame(picks)
    ids = sorted(p.chunk_id.unique().tolist())
    print(f"축 {p.groupby(['cluster','axis']).ngroups}개 · 청크 {len(ids):,}건 본문 요청")

    info = db.healthcheck()
    print(f"DB: {info['user']} (read_only={info['read_only']})")
    txt = db.query(
        "SELECT id AS chunk_id, text FROM ai_document_chunks WHERE id = ANY(%s)",
        (ids,),
    )
    print(f"수신 {len(txt):,}건")
    out = p.merge(txt, on="chunk_id").merge(
        meta[["chunk_id", "title", "date", "source_type", "lang"]], on="chunk_id"
    )
    out.to_parquet(DATA / "axis_extremes.parquet", index=False)
    print(f"저장: axis_extremes.parquet ({len(out):,}행)")


if __name__ == "__main__":
    main()
