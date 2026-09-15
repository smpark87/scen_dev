"""D6 — 의미 덩어리 추출.

합의된 그림 (2026-08-03):
  벡터 DB 에 좌표는 있지만 "의미 목록"은 없다. 청크가 공간 어디에 뭉치는지
  찾아 각 덩어리를 독립변수 하나로 만든다. 몇 개가 나올지는 데이터가 정한다.

설계 결정:
  - 군집은 **청크 단위** (표본 35,313 — 900일이 아니라). 단,
    문서당 총 가중치 1 (sample_weight = 1/문서 청크수) — 870청크짜리
    FERC EIS 한 건이 기사 870건만큼의 발언권을 갖지 않도록.
  - 중심화된 임베딩 사용 (prep.py) — 안 하면 덩어리가 의미가 아니라
    소스 문체로 잡힌다 (측정 근거: source eta² 20.5%).
  - k 는 실루엣 스캔으로 고르되 해석 가능성을 함께 본다.

사용:
  python analysis/meanings.py scan          # k 스캔만
  python analysis/meanings.py fit 24        # k=24 확정 적합 + 대표문서 출력
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATA  # noqa: E402

SEED = 20260803
PCA_DIM = 50


def load() -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    meta = pd.read_parquet(DATA / "market_meta.parquet")
    meta["date"] = pd.to_datetime(meta["date"])
    X = np.load(DATA / "emb_centered.npy").astype(np.float32)
    # 문서당 총 가중치 1
    per_doc = meta.groupby("document_id")["chunk_id"].transform("count")
    w = (1.0 / per_doc).to_numpy()
    return meta, X, w


def pca50(X: np.ndarray) -> tuple[np.ndarray, object]:
    from sklearn.decomposition import PCA
    p = PCA(n_components=PCA_DIM, random_state=SEED)
    Xp = p.fit_transform(X)
    print(f"PCA {X.shape[1]} → {PCA_DIM} · 설명분산 {p.explained_variance_ratio_.sum():.1%}")
    return Xp.astype(np.float32), p


def scan(Xp: np.ndarray, w: np.ndarray) -> None:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    rng = np.random.default_rng(SEED)
    sub = rng.choice(len(Xp), size=min(8000, len(Xp)), replace=False)
    print(f"\n k    실루엣(표본 {len(sub):,})  최소덩어리  중앙덩어리")
    for k in (8, 12, 16, 20, 24, 30, 40, 50):
        km = KMeans(n_clusters=k, n_init=4, random_state=SEED)
        lab = km.fit_predict(Xp, sample_weight=w)
        sil = silhouette_score(Xp[sub], lab[sub], metric="cosine")
        sizes = np.bincount(lab, minlength=k)
        print(f"{k:>3}   {sil:>8.3f}          {sizes.min():>6,}    {int(np.median(sizes)):>6,}")


def fit(meta: pd.DataFrame, Xp: np.ndarray, w: np.ndarray, k: int) -> None:
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, n_init=10, random_state=SEED)
    lab = km.fit_predict(Xp, sample_weight=w)
    meta = meta.copy()
    meta["cluster"] = lab

    # 중심 근접도 (해석·패널 양쪽에서 씀)
    d = np.linalg.norm(Xp - km.cluster_centers_[lab], axis=1)
    meta["dist"] = d

    print(f"\n════ k={k} 덩어리별 대표 (중심에 가까운 순, 제목 중복 제거) ════")
    rows = []
    for c in range(k):
        g = meta[meta.cluster == c].sort_values("dist")
        n_doc = g.document_id.nunique()
        srcs = g.source_type.value_counts(normalize=True).head(3)
        src_s = " ".join(f"{s}:{v:.0%}" for s, v in srcs.items())
        span = f"{g.date.min():%Y-%m} ~ {g.date.max():%Y-%m}"
        wsum = w[g.index].sum()
        print(f"\n[{c:02d}] 청크 {len(g):,} · 문서 {n_doc:,} · 가중 {wsum:,.0f} · {span}")
        print(f"     소스: {src_s}")
        for t in g.title.drop_duplicates().head(12):
            print(f"     · {str(t)[:82]}")
        rows.append({"cluster": c, "chunks": len(g), "docs": n_doc,
                     "weight": round(float(wsum), 1), "top_sources": src_s,
                     "span": span})

    meta[["chunk_id", "cluster", "dist"]].to_parquet(DATA / "clusters.parquet", index=False)
    np.save(DATA / "cluster_centroids.npy", km.cluster_centers_)
    (DATA / "clusters_summary.json").write_text(
        json.dumps({"k": k, "clusters": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n저장: clusters.parquet · cluster_centroids.npy · clusters_summary.json")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    meta, X, w = load()
    print(f"시장 모집단 {len(meta):,} 청크 · 유효 가중 {w.sum():,.0f} (≈문서수)")
    Xp, _p = pca50(X)
    np.save(DATA / "pca50.npy", Xp.astype(np.float16))
    if mode == "scan":
        scan(Xp, w)
    elif mode == "fit":
        fit(meta, Xp, w, int(sys.argv[2]))
    else:
        raise SystemExit("scan | fit <k>")


if __name__ == "__main__":
    main()
