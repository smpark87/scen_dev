"""D5/D6 — 의미 독립변수의 일별 패널.

합의된 그림 (2026-08-03):
  날짜는 변수가 아니라 **정합 키**다. 정형 변수(생산·기온·유가) 옆에
  여기서 만든 열들이 나란히 서고, 회귀의 x 가 된다.

두 종류의 열:
  vol_<c>(t)     의미 c 를 말한 문서 수 — 얼마나 많이 얘기했나
  ax_<c>_<j>(t)  그 안에서 **어느 방향**이었나 — 부호 있는 연속량

  ax 가 없으면 폭염 기사와 한파 기사가 똑같이 '기상 1건'이 되어 버린다.
  채택된 축만 쓴다 (data/axis_names.json — 본문을 읽고 판정, 형식·언어 축은 폐기).

집계 규약:
  · 문서당 총 1표 (w = 1/문서 청크수). 870청크 EIS 가 기사 870건이 되지 않도록.
  · 축은 **합(net)** 을 주력으로 한다. 그날 없으면 0 이 되고 그 0 이 의미가 있다
    ("오늘은 그런 얘기가 없었다"). 평균은 문서가 1건인 날 분산이 튀어 보조로만 둔다.
  · 중심점 평균("그날의 의미")은 만들지 않는다 — 무관한 주제의 평균은 의미가 아니다.

출력:
  data/semantic_panel.parquet
  figures/03_semantic_panel.html
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATA, DISCLAIMER, FIGS, WINDOW_JOINT  # noqa: E402


def main() -> None:
    meta = pd.read_parquet(DATA / "market_meta.parquet")
    meta["date"] = pd.to_datetime(meta["date"])
    meta = meta.merge(pd.read_parquet(DATA / "clusters.parquet"), on="chunk_id")
    meta = meta.merge(pd.read_parquet(DATA / "axis_scores.parquet"), on="chunk_id", how="left")
    cnames = json.loads((DATA / "cluster_names.json").read_text(encoding="utf-8"))
    anames = json.loads((DATA / "axis_names.json").read_text(encoding="utf-8"))
    adopted = anames["adopted"]
    k = int(meta.cluster.max()) + 1
    print(f"{len(meta):,} 청크 · 덩어리 {k} · 채택 축 {len(adopted)}")

    out = pd.DataFrame(index=pd.Index(sorted(meta.date.unique()), name="date"))
    out["n_docs"] = meta.groupby("date").w.sum()

    # 이견(dispersion) — 그날 문서들이 얼마나 흩어져 있나. 03 §5.6 의 3성분 중 하나.
    # 주제가 갈리거나 시각이 갈리면 커진다. 볼륨·방향과 다른 정보다.
    Z = np.load(DATA / "pca50.npy").astype(np.float32)
    Zn = Z / (np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9)
    pos = meta.reset_index(drop=True)
    disp = {}
    for d, g in pos.groupby("date"):
        V = Zn[g.index.to_numpy()]
        if len(V) < 2:
            continue
        mu = V.mean(axis=0)
        mu /= np.linalg.norm(mu) + 1e-9
        disp[d] = float(1.0 - (V @ mu).mean())
    out["dispersion"] = pd.Series(disp)

    # ── 볼륨: 의미별 문서 수 ────────────────────────────────────────
    vol = (meta.groupby(["date", "cluster"]).w.sum().unstack(fill_value=0.0)
           .reindex(columns=range(k), fill_value=0.0))
    vol.columns = [f"vol_{c}" for c in vol.columns]

    # ── 축: 부호 있는 방향 (net = Σ w·z, mean = net / Σ w) ──────────
    cols_net, cols_mean = {}, {}
    for col, spec in adopted.items():
        c = spec["cluster"]
        m = meta.cluster == c
        sub = meta.loc[m, ["date", "w", col]].dropna(subset=[col])
        net = (sub.w * sub[col]).groupby(sub.date).sum()
        wsum = sub.groupby("date").w.sum()
        cols_net[col] = net
        cols_mean[col + "_m"] = net / wsum
    net_df = pd.DataFrame(cols_net).reindex(out.index).fillna(0.0)
    mean_df = pd.DataFrame(cols_mean).reindex(out.index)      # 결측은 결측으로 둔다

    panel = pd.concat([out, vol, net_df, mean_df], axis=1)
    panel[vol.columns] = panel[vol.columns].fillna(0.0)
    panel["n_docs"] = panel["n_docs"].fillna(0.0)
    panel.to_parquet(DATA / "semantic_panel.parquet")
    print(f"패널 {panel.shape[0]:,}일 × {panel.shape[1]}열 "
          f"({panel.index.min():%Y-%m-%d} ~ {panel.index.max():%Y-%m-%d})")

    # ── 그림: 채택 축 6개의 일별 방향 (결합창, 21일 이동평균) ────────
    s, e = WINDOW_JOINT
    p = panel[(panel.index >= pd.Timestamp(s)) & (panel.index <= pd.Timestamp(e))]
    p = p[p.index.dayofweek < 5]
    show = ["ax_2_0", "ax_2_1", "ax_2_2", "ax_14_0", "ax_15_2", "ax_1_2"]
    titles = []
    for a in show:
        sp = adopted[a]
        titles.append(f"[{sp['cluster']}] {cnames[str(sp['cluster'])]['name']}"
                      f" &nbsp;—&nbsp; <b>− {sp['neg']}</b> ↔ <b>+ {sp['pos']}</b>")
    fig = make_subplots(rows=len(show), cols=1, shared_xaxes=True,
                        vertical_spacing=0.035, subplot_titles=titles)
    for i, a in enumerate(show):
        y = p[a].rolling(21, min_periods=5).mean()
        fig.add_trace(go.Scatter(x=p.index, y=y, mode="lines", showlegend=False,
                                 line=dict(width=1.3, color="#4C78A8")),
                      row=i + 1, col=1)
        fig.add_hline(y=0, line_width=0.8, line_color="#999", row=i + 1, col=1)
    for i in range(len(show)):
        fig.layout.annotations[i].font.size = 11
    fig.update_layout(
        height=1080, template="plotly_white",
        title=dict(
            text=f"③ 의미 축의 일별 방향 (문서가중 순합 · 21일 이동평균)"
                 f" &nbsp;<span style='font-size:12px;color:#c00'>[{DISCLAIMER}]</span>"
                 f"<br><span style='font-size:11px;color:#666'>"
                 f"덩어리도 축도 데이터가 만들었고 이름만 붙였다 · 각 선이 회귀의 x 하나</span>",
            x=0.01),
        margin=dict(t=110, b=40))
    outp = FIGS / "03_semantic_panel.html"
    fig.write_html(outp, include_plotlyjs="cdn")
    print(f"그림: {outp}")

    # 요약 — 결합창 평일 기준
    print("\n── 채택 축 요약 (결합창 평일) ──")
    for a, sp in adopted.items():
        v = p[a]
        cov = (p[a + "_m"].notna()).mean()
        print(f"  {a:9} 존재일 {cov:4.0%}  sd {v.std():5.2f}   "
              f"− {sp['neg'][:16]:<18} + {sp['pos'][:16]}")


if __name__ == "__main__":
    main()
