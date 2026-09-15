"""D6 — 주제 덩어리 + 덩어리 내 **부호 있는 의미 축** 추출.

계획서 D6 원문: "Factor 추출(PCA 계열) + **각 축 극단 문서 제목 추출**".
초판에서 군집만 하고 축을 안 뽑아 "주제가 몇 번 언급됐나"만 남았다 —
폭염 기사와 한파 기사가 똑같이 '기상 1건'이 되어 가격 함의가 반대인데 구분이
사라졌다. 여기서 그 부분을 복구한다.

두 층위:
  1) 주제 덩어리 (k-means)  — 무슨 얘기인가
  2) 덩어리 내 축 (PCA)     — 그 안에서 **어느 방향**인가  ← 부호 있는 연속량

모든 PCA·군집은 **문서 가중**을 쓴다. 안 쓰면 축이 시장 의미가 아니라
문서 길이 편향으로 간다 (청크 몫: ferc 41% steo 18% vs 문서 몫: 16% 1.5%).

축은 자동 채택하지 않는다. 양 끝 문서를 사람이 읽고
  · 시장 의미 축이면 채택하고 이름을 붙인다
  · 형식·언어·발행연도 축이면 **폐기**한다
`data/axis_names.json` 에 채택분만 기록되며, 없으면 그 덩어리는 볼륨만 쓴다.

사용:
  python analysis/factors.py cluster 20     # 가중 PCA + 가중 군집
  python analysis/factors.py axes           # 덩어리별 축 후보 + 극단 문서 출력
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
N_AXES = 3          # 덩어리마다 후보 축 수
MIN_CHUNKS = 250    # 이보다 작은 덩어리는 축을 뽑지 않는다


def wpca(X: np.ndarray, w: np.ndarray, n: int):
    """문서 가중 PCA. 반환 (점수, 성분, 설명분산비, 가중평균)."""
    from sklearn.utils.extmath import randomized_svd
    wn = (w / w.sum()).astype(np.float64)
    mu = (wn[:, None] * X).sum(0).astype(np.float32)
    Xc = X - mu
    A = (np.sqrt(wn)[:, None] * Xc).astype(np.float32)
    _U, S, Vt = randomized_svd(A, n_components=n, random_state=SEED)
    tot = float((A ** 2).sum())
    return Xc @ Vt.T, Vt, (S ** 2) / tot, mu


def load():
    meta = pd.read_parquet(DATA / "market_meta.parquet")
    meta["date"] = pd.to_datetime(meta["date"])
    X = np.load(DATA / "emb_centered.npy").astype(np.float32)
    return meta.reset_index(drop=True), X, meta.w.to_numpy(dtype=np.float64)


def do_cluster(k: int) -> None:
    from sklearn.cluster import KMeans
    meta, X, w = load()
    print(f"{len(meta):,} 청크 · 문서가중 합 {w.sum():,.0f}")
    Z, _V, evr, _mu = wpca(X, w, PCA_DIM)
    print(f"가중 PCA 1536 → {PCA_DIM} · 설명분산 {evr.sum():.1%}")
    np.save(DATA / "pca50.npy", Z.astype(np.float16))

    km = KMeans(n_clusters=k, n_init=10, random_state=SEED)
    lab = km.fit_predict(Z, sample_weight=w)
    meta["cluster"] = lab
    meta["dist"] = np.linalg.norm(Z - km.cluster_centers_[lab], axis=1)

    print(f"\n════ k={k} · 덩어리별 대표 (중심 근접, 문서 중복 제거) ════")
    for c in range(k):
        g = meta[meta.cluster == c].sort_values("dist")
        src = g.groupby("source_type").w.sum().sort_values(ascending=False)
        src = src / src.sum()
        s = " ".join(f"{a}:{b:.0%}" for a, b in src.head(3).items())
        print(f"\n[{c:02d}] 청크 {len(g):,} · 문서 {g.document_id.nunique():,} "
              f"· 가중 {g.w.sum():,.0f} · {g.date.min():%Y-%m}~{g.date.max():%Y-%m}")
        print(f"     {s}")
        for t in g.title.drop_duplicates().head(10):
            print(f"     · {str(t)[:80]}")

    meta[["chunk_id", "cluster", "dist"]].to_parquet(DATA / "clusters.parquet", index=False)
    np.save(DATA / "cluster_centroids.npy", km.cluster_centers_)
    print("\n저장: clusters.parquet · cluster_centroids.npy · pca50.npy")


def do_axes() -> None:
    meta, X, w = load()
    cl = pd.read_parquet(DATA / "clusters.parquet")
    meta = meta.merge(cl, on="chunk_id")
    k = int(meta.cluster.max()) + 1
    names_p = DATA / "cluster_names.json"
    names = json.loads(names_p.read_text(encoding="utf-8")) if names_p.exists() else {}

    store: dict[str, np.ndarray] = {}
    rows = []
    scores: list[pd.DataFrame] = []
    for c in range(k):
        idx = meta.index[meta.cluster == c].to_numpy()
        if len(idx) < MIN_CHUNKS:
            print(f"\n[{c:02d}] 청크 {len(idx)} — 너무 작아 축 생략")
            continue
        sub = meta.loc[idx]
        # 덩어리 **안에서** 다시 (소스 × 언어) 중심화.
        #   전역 중심화는 전체 평균만 맞춘다. 주제를 고정하면 조건부 평균이 다시
        #   갈라져서 (국문 코멘터리 vs 영문 기사, 뉴스 vs EIA 리포트) 제1축을
        #   먹는다 — 2026-08-03 측정으로 확인. 여기서 걷어내야 내용 축이 나온다.
        Xi = X[idx].copy()
        cells = (sub.source_type + "|" + sub.lang).to_numpy()
        for cv in np.unique(cells):
            m = cells == cv
            if m.sum() >= 25:
                Xi[m] -= Xi[m].mean(axis=0)
        Z, V, evr, mu = wpca(Xi, sub.w.to_numpy(dtype=np.float64), N_AXES)
        store[f"comp_{c}"] = V.astype(np.float32)
        store[f"mu_{c}"] = mu.astype(np.float32)
        # 축 점수를 청크별로 저장 — 패널에서 그대로 집계한다.
        # 단위를 맞추려고 문서가중 표준편차로 나눈다 (덩어리마다 분산이 달라
        # 그대로 두면 회귀에서 큰 덩어리 축이 스케일만으로 유리해진다).
        wv = sub.w.to_numpy(dtype=np.float64)
        sd = np.sqrt((wv[:, None] * Z ** 2).sum(0) / wv.sum())
        sc = pd.DataFrame(Z / np.where(sd > 0, sd, 1.0),
                          columns=[f"ax_{c}_{j}" for j in range(N_AXES)])
        sc.insert(0, "chunk_id", sub.chunk_id.to_numpy())
        scores.append(sc)
        nm = names.get(str(c), {}).get("name", "?")
        print(f"\n{'='*80}\n[{c:02d}] {nm} · 청크 {len(idx):,} · 문서 {sub.document_id.nunique():,}")
        print(f"     축 설명분산 " + " ".join(f"PC{i+1} {v:.1%}" for i, v in enumerate(evr)))
        for ax in range(N_AXES):
            o = np.argsort(Z[:, ax])
            print(f"\n  ── PC{ax+1} ──")
            for tag, order in (("−", o), ("+", order_rev := o[::-1])):
                seen: set[str] = set()
                out = []
                for i in order:
                    t = str(sub.iloc[i].title)[:70]
                    if t in seen:
                        continue
                    seen.add(t)
                    out.append(t)
                    if len(out) >= 6:
                        break
                print(f"   [{tag}]")
                for t in out:
                    print(f"      {t}")
            rows.append({"cluster": c, "axis": ax, "evr": round(float(evr[ax]), 4)})

    np.savez(DATA / "axis_components.npz", **store)
    (DATA / "axis_candidates.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    sdf = scores[0]
    for s in scores[1:]:
        sdf = sdf.merge(s, on="chunk_id", how="outer")
    sdf.to_parquet(DATA / "axis_scores.parquet", index=False)
    print(f"\n저장: axis_components.npz ({len(store)//2} 덩어리) · axis_candidates.json"
          f" · axis_scores.parquet ({sdf.shape[0]:,}×{sdf.shape[1]-1})")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "axes"
    if mode == "cluster":
        do_cluster(int(sys.argv[2]) if len(sys.argv) > 2 else 20)
    elif mode == "axes":
        do_axes()
    else:
        raise SystemExit("cluster <k> | axes")


if __name__ == "__main__":
    main()
