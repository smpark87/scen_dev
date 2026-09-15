"""D3 — 문서 밀도 진단 (화면 ①).

07-demo-plan §0.1 에서 확인한 밀도·구성 변화를 스냅샷 기준으로 정밀 측정한다.
이 진단 결과가 D5(집계 방식) 결정의 근거가 된다.

특히 보는 것:
  1) 일자별 청크 수 — 적으면 집계 Factor 의 분산이 커진다 (신호로 오인됨)
  2) source_type 구성 변화 — 구성이 바뀌면 Factor 의 의미도 바뀐다
  3) 문서당 청크 수 — 긴 문서가 일자 집계를 지배하는지
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (DATA, DISCLAIMER, FIGS, WINDOW_JOINT,  # noqa: E402
                    WINDOW_STRUCT)


def load_meta() -> pd.DataFrame:
    info = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    meta = pd.read_parquet(DATA / info["meta"])
    meta["date"] = pd.to_datetime(meta["date"])
    return meta


def main() -> None:
    meta = load_meta()
    print(f"스냅샷 청크 {len(meta):,} · {meta['date'].min().date()} ~ {meta['date'].max().date()}\n")

    # ── 1. 문서당 청크 수 — 집계 편향의 원인 ──────────────────────
    per_doc = (
        meta.groupby("source_type")
        .agg(docs=("document_id", "nunique"), chunks=("chunk_id", "count"))
        .assign(chunks_per_doc=lambda d: (d.chunks / d.docs).round(1))
        .sort_values("chunks", ascending=False)
    )
    print("── source_type 별 문서·청크 (문서당 청크 수가 집계 가중을 좌우) ──")
    print(per_doc.to_string())

    total_docs, total_chunks = per_doc.docs.sum(), per_doc.chunks.sum()
    print(f"\n전체 문서당 평균 청크: {total_chunks/total_docs:.1f}")

    # ── 2. 분석창별 밀도 ──────────────────────────────────────────
    print("\n── 분석창별 일평균 밀도 ──")
    rows = []
    for label, (s, e) in [("정형 2020-01~", WINDOW_STRUCT), ("결합 2023-01~", WINDOW_JOINT)]:
        w = meta[(meta.date >= pd.Timestamp(s)) & (meta.date <= pd.Timestamp(e))]
        days = (pd.Timestamp(e) - pd.Timestamp(s)).days + 1
        covered = w.date.nunique()
        rows.append(
            {
                "창": label,
                "청크": len(w),
                "문서": w.document_id.nunique(),
                "일평균 청크": round(len(w) / days, 1),
                "문서 있는 날": covered,
                "커버리지%": round(100 * covered / days, 1),
            }
        )
    print(pd.DataFrame(rows).to_string(index=False))

    # ── 3. 거래일 기준 밀도 — 주말은 결측이 아니라 비영업일 ─────────
    s, e = date(2020, 1, 1), WINDOW_STRUCT[1]   # 진단은 넓게 본다
    w = meta[(meta.date >= pd.Timestamp(s)) & (meta.date <= pd.Timestamp(e))]
    full = pd.date_range(s, e, freq="D")
    daily = w.groupby("date").size().reindex(full, fill_value=0)
    bday = daily[daily.index.dayofweek < 5]
    docday = (
        w.groupby(["date", "document_id"]).size().groupby("date").size()
        .reindex(full, fill_value=0)
    )
    docbday = docday[docday.index.dayofweek < 5]

    print("\n── 결측의 정체: 주말 ──")
    print(f"  전체 기준  0건인 날 {100*(daily==0).mean():>5.1f}%")
    print(f"  거래일만   0건인 날 {100*(bday==0).mean():>5.1f}%   ← 주말이 원인이었다")

    print("\n── 연도별 거래일 중앙값 (청크 / 문서) — 21배 격차 ──")
    for y in range(2020, 2027):
        m = bday.index.year == y
        if m.sum():
            print(f"  {y}   청크 {bday[m].median():>5.0f}   문서 {docbday[m].median():>4.0f}")
    print("  → article 소스가 2023년부터만 존재. 결합 분석창을 2023-01~ 로 확정.")

    # ── 4. 월별 집계 + 구성 ───────────────────────────────────────
    meta["month"] = meta.date.dt.to_period("M").dt.to_timestamp()
    monthly = meta.groupby("month").size()
    comp = (
        meta.pivot_table(index="month", columns="source_type", values="chunk_id", aggfunc="count")
        .fillna(0)
    )
    top = per_doc.head(6).index.tolist()
    comp_top = comp.reindex(columns=top, fill_value=0)
    comp_share = comp_top.div(comp_top.sum(axis=1).replace(0, np.nan), axis=0) * 100

    # ── 5. 그림 ───────────────────────────────────────────────────
    win = (monthly.index >= pd.Timestamp(2020, 1, 1)) & (
        monthly.index <= pd.Timestamp(WINDOW_STRUCT[1])
    )
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
        subplot_titles=(
            "월별 청크 수 — 밀도 변화",
            "source_type 구성비 (%) — 구성 변화",
            "거래일 청크 수 — 2023부터 밀도 급증 (article 유입)",
        ),
    )
    fig.add_trace(
        go.Bar(x=monthly.index[win], y=monthly[win], name="청크", marker_color="#4C78A8"),
        row=1, col=1,
    )
    for c in comp_share.columns:
        m = comp_share.index >= pd.Timestamp(2020, 1, 1)
        fig.add_trace(
            go.Scatter(
                x=comp_share.index[m], y=comp_share[c][m], name=c,
                stackgroup="one", mode="none", hovertemplate="%{y:.0f}%",
            ),
            row=2, col=1,
        )
    fig.add_trace(
        go.Scatter(x=bday.index, y=bday.values, name="거래일 청크",
                   line=dict(color="#72B7B2", width=0.8), showlegend=False),
        row=3, col=1,
    )
    fig.add_hline(y=5, line_dash="dot", line_color="crimson", row=3, col=1,
                  annotation_text="5건", annotation_position="right")
    fig.update_layout(
        height=880, template="plotly_white", barmode="stack",
        title=dict(
            text=f"① 문서 밀도 진단 &nbsp;<span style='font-size:12px;color:#c00'>[{DISCLAIMER}]</span>",
            x=0.01,
        ),
        legend=dict(orientation="h", y=-0.06, font=dict(size=10)),
        margin=dict(t=90, b=60),
    )
    out = FIGS / "01_density.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"\n그림: {out}")

    # 요약 저장 (이후 화면 조립에서 재사용)
    (DATA / "density_summary.json").write_text(
        json.dumps(
            {
                "per_doc": per_doc.reset_index().to_dict("records"),
                "windows": rows,
                "zero_days_all_pct": round(float((daily == 0).mean() * 100), 1),
                "zero_days_bday_pct": round(float((bday == 0).mean() * 100), 1),
                "yearly_median_chunks": {int(y): float(bday[bday.index.year == y].median()) for y in range(2020, 2027)},
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
