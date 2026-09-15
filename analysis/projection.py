"""D4 — 임베딩 공간 지도 (화면 ②).

증명하려는 것: **임베딩이 실제로 의미 구조를 담고 있는가.**
설명이 필요 없는 그림이라, 데모에서 "비정형이 수치가 된다"를 처음 체감시키는 자리다.

방법: 1536차원 → PCA 50차원 → UMAP 2차원.
  PCA 를 먼저 태우는 것은 표준 관행이다. UMAP 을 1536차원에 직접 돌리면
  느리고 거리 계산이 불안정하다.

색칠 두 가지:
  (a) source_type — 소스가 다르면 다른 영역에 모이는가 (구성 편향 확인)
  (b) 시기        — 시간이 지나며 의미 공간에서 이동하는가
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATA, DISCLAIMER, FIGS, WINDOW_JOINT  # noqa: E402

SEED = 20260803
PCA_DIM = 50
# 그림 용량·가독성 한계. 초과 시 층화 표본.
# 25,000 이면 HTML 이 4.7MB 가 되어 조립본이 11MB 를 넘고 뷰어에서 안 열린다.
# 산점도 가독성은 1만 점이면 충분하다 (2026-08-03 조정).
MAX_POINTS = 10_000


def main() -> None:
    info = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    meta = pd.read_parquet(DATA / info["meta"])
    meta["date"] = pd.to_datetime(meta["date"])
    emb = np.load(DATA / info["emb"])
    print(f"스냅샷 {info['snapshot_utc'][:19]} · {emb.shape}")

    # 결합 분석창으로 한정
    s, e = WINDOW_JOINT
    m = (meta.date >= pd.Timestamp(s)) & (meta.date <= pd.Timestamp(e))
    meta, emb = meta[m].reset_index(drop=True), emb[m.values]
    print(f"분석창 {s} ~ {e}: {len(meta):,} 청크")

    # 표본 축소 — 소스별 비율 유지
    if len(meta) > MAX_POINTS:
        frac = MAX_POINTS / len(meta)
        idx = (
            meta.groupby("source_type", group_keys=False)
            .apply(lambda g: g.sample(max(1, int(len(g) * frac)), random_state=SEED))
            .index
        )
        meta, emb = meta.loc[idx].reset_index(drop=True), emb[idx]
        print(f"층화 표본: {len(meta):,} 청크")

    X = emb.astype(np.float32)
    # 코사인 기준 공간이므로 L2 정규화 후 다룬다
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9

    from sklearn.decomposition import PCA
    print(f"PCA {X.shape[1]} → {PCA_DIM} ...")
    pca = PCA(n_components=PCA_DIM, random_state=SEED)
    Xp = pca.fit_transform(X)
    print(f"  설명 분산 누적 {pca.explained_variance_ratio_.sum():.1%}")
    print(f"  상위 5개 성분: {np.round(pca.explained_variance_ratio_[:5], 3)}")

    import umap
    print("UMAP 50 → 2 ... (수 분 소요)")
    xy = umap.UMAP(
        n_neighbors=25, min_dist=0.12, metric="cosine", random_state=SEED, verbose=False
    ).fit_transform(Xp)

    # 좌표는 소수 2자리로 자른다 — 전체 자릿수를 직렬화하면 용량이 배로 뛴다
    meta["x"], meta["y"] = np.round(xy[:, 0], 2), np.round(xy[:, 1], 2)
    meta["ym"] = meta.date.dt.to_period("M").astype(str)
    meta["t"] = (meta.date - meta.date.min()).dt.days

    fig = make_subplots(
        rows=1, cols=2, horizontal_spacing=0.06,
        subplot_titles=("소스별 — 문서 종류가 영역을 만드는가",
                        "시기별 — 시간에 따라 의미가 이동하는가"),
    )
    palette = px.colors.qualitative.Set2
    for i, (st, g) in enumerate(meta.groupby("source_type")):
        if len(g) < 30:
            continue
        fig.add_trace(
            go.Scattergl(
                x=g.x, y=g.y, mode="markers", name=st,
                marker=dict(size=2.5, color=palette[i % len(palette)], opacity=0.55),
                hovertext=g.title.str.slice(0, 55), hoverinfo="text+name",
            ),
            row=1, col=1,
        )
    fig.add_trace(
        go.Scattergl(
            x=meta.x, y=meta.y, mode="markers", showlegend=False,
            marker=dict(size=2.5, color=meta.t, colorscale="Turbo", opacity=0.6,
                        colorbar=dict(title="경과일", x=1.02, len=0.85)),
            hovertext=meta.date.dt.strftime("%Y-%m-%d") + " · " + meta.title.str.slice(0, 45),
            hoverinfo="text",
        ),
        row=1, col=2,
    )
    for c in (1, 2):
        fig.update_xaxes(visible=False, row=1, col=c)
        fig.update_yaxes(visible=False, row=1, col=c)
    fig.update_layout(
        height=620, template="plotly_white",
        title=dict(
            text=f"② 임베딩 공간 지도 &nbsp;<span style='font-size:12px;color:#c00'>[{DISCLAIMER}]</span>"
                 f"<br><span style='font-size:11px;color:#666'>"
                 f"{len(meta):,} 청크 · 1536차원 → PCA {PCA_DIM} → UMAP 2차원</span>",
            x=0.01,
        ),
        legend=dict(orientation="h", y=-0.05, font=dict(size=10)),
        margin=dict(t=110, b=50),
    )
    out = FIGS / "02_embedding_map.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"\n그림: {out}")

    np.save(DATA / "umap_xy.npy", xy)
    meta[["chunk_id", "x", "y"]].to_parquet(DATA / "umap_coords.parquet", index=False)


if __name__ == "__main__":
    main()
