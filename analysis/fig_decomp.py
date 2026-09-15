"""화면 ④ — 대칭 설명력 분해 결과 그림.

정직하게 그린다. 0 선을 굵게 두고 신뢰구간을 반드시 함께 그린다 —
점추정만 그리면 신뢰구간이 0 을 포함하는 결과가 발견처럼 보인다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATA, DISCLAIMER, FIGS  # noqa: E402

C_S, C_M, C_SM = "#4C78A8", "#E4572E", "#8C8C8C"


def main() -> None:
    R = pd.read_parquet(DATA / "decomp.parquet")
    num = R[R.kind == "num"].iloc[::-1]
    bin_ = R[R.kind == "bin"].iloc[::-1]

    fig = make_subplots(
        rows=1, cols=2, column_widths=[0.62, 0.38], horizontal_spacing=0.14,
        subplot_titles=("연속 대상 — 표본 외 R²", "이진 대상 — AUC"),
    )
    for i, (d, base, col) in enumerate([(num, 0.0, 1), (bin_, 0.5, 2)]):
        for tag, c, off in (("S", C_S, +0.18), ("M", C_M, -0.18)):
            y = np.arange(len(d)) + off
            fig.add_trace(
                go.Scatter(
                    x=d[tag], y=y, mode="markers", name=("정형 S" if tag == "S" else "의미 M"),
                    marker=dict(size=9, color=c, symbol="diamond"),
                    error_x=dict(type="data", symmetric=False,
                                 array=(d[f"{tag}_hi"] - d[tag]).clip(lower=0),
                                 arrayminus=(d[tag] - d[f"{tag}_lo"]).clip(lower=0),
                                 color=c, thickness=1.4, width=4),
                    showlegend=(col == 1), legendgroup=tag,
                    hovertemplate="%{customdata}<br>%{x:.3f}<extra></extra>",
                    customdata=d.name,
                ),
                row=1, col=col,
            )
        fig.add_vline(x=base, line_width=2, line_color="#333", row=1, col=col)
        fig.update_yaxes(tickmode="array", tickvals=np.arange(len(d)),
                         ticktext=d.name, row=1, col=col, tickfont=dict(size=11))
    fig.update_xaxes(title_text="표본 외 R² (0 = 평균만큼도 못 맞힘)", row=1, col=1)
    fig.update_xaxes(title_text="AUC (0.5 = 무작위)", row=1, col=2)

    fig.update_layout(
        height=520, template="plotly_white",
        title=dict(
            text=f"④ 대칭 설명력 분해 &nbsp;<span style='font-size:12px;color:#c00'>"
                 f"[{DISCLAIMER}]</span><br><span style='font-size:11px;color:#666'>"
                 f"889 거래일 · 정형 59열 vs 의미 31열 · 시계열 분할(최소 학습 2년, purge) · "
                 f"이동블록 부트스트랩 90% 구간</span>", x=0.01),
        legend=dict(orientation="h", y=1.06, x=0.7),
        margin=dict(t=110, b=60, l=150),
    )
    out = FIGS / "04_decomposition.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"그림: {out}")

    # 판정 요약
    print("\n── 판정 (신뢰구간이 기준선을 배제하는가) ──")
    for _, r in R.iterrows():
        base = 0.0 if r.kind == "num" else 0.5
        for tag in ("S", "M"):
            lo, hi = r[f"{tag}_lo"], r[f"{tag}_hi"]
            v = r[tag]
            if np.isnan(lo):
                continue
            mark = "○ 유의" if lo > base else ("· 무의미" if hi > base else "× 음수")
            if lo > base:
                print(f"  {mark}  {r['name']:20} {tag}  {v:+.3f} [{lo:+.3f},{hi:+.3f}]")


if __name__ == "__main__":
    main()
