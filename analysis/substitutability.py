"""D9-b — 의미 축의 **대체가능성** 측정과 고유 성분만의 재분해.

문제 제기 (2026-08-03):
  채택한 축 9개 중 상당수가 정형 변수의 다른 표현일 뿐이다.
  · 한파 ↔ 폭염          → HDD/CDD 에 이미 있다
  · 생산·공급 전망        → 생산 계열에 이미 있다
  비정형만의 가치가 있을 만한 것은 정형에 대응 계열이 **없는** 축이다.
  · 지정학·호르무즈       → 대응 정형 계열 없음
  · EIA 재고 발표 "반응"  → 실제 재고는 정형에 있으나 **컨센서스와 해석**은 없다
  · 수요 전망 코멘터리     → 정형은 실현치만, 전망 서술은 없음

이것을 가정하지 않고 **잰다.** 각 의미 축을 정형 블록으로 회귀한다.

    R²(축 | 정형) 높음  →  이미 숫자에 있다 (대체가능)
    R²(축 | 정형) 낮음  →  숫자에 없는 것을 담고 있다 (고유)

그다음 고유 축만으로 다시 분해한다. 축을 9개 다 넣으면 대체가능 축들이
차원만 늘려 정규화를 희석시키고 공유 성분을 부풀린다 — 고유 기여가 있어도
묻힌다. 03 §5.1.2 "공선성은 대상에 따라 다르다"를 정형↔의미 경계에 적용한 것.

출력: data/substitutability.json · figures/07_substitutability.html
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analysis.decompose import TARGETS, boot_ci, load, oos_pred, score  # noqa: E402
from config import DATA, DISCLAIMER, FIGS  # noqa: E402

warnings.filterwarnings("ignore")
CUT = 0.25          # 이 이상이면 "정형이 이미 담고 있다"로 본다


def main() -> None:
    df, scols, mcols = load()
    anames = json.loads((DATA / "axis_names.json").read_text(encoding="utf-8"))
    cnames = json.loads((DATA / "cluster_names.json").read_text(encoding="utf-8"))
    adopted = anames["adopted"]
    print(f"결합 패널 {len(df)}일 · 정형 {len(scols)} · 의미 {len(mcols)}\n")

    # ── 1. 축마다 R²(축 | 정형) ─────────────────────────────────────
    print("── 각 의미 축이 정형으로 얼마나 재현되는가 (표본 외 R²) ──")
    rows = []
    for col, spec in adopted.items():
        c = f"m_{col}_m"
        if c not in df.columns:
            continue
        y = df[c]
        r2 = score(y.to_numpy(), oos_pred(df[scols], y, 5, "num"), "num")
        rows.append({"axis": col, "cluster": spec["cluster"],
                     "label": f"{spec['neg']} ↔ {spec['pos']}",
                     "cluster_name": cnames[str(spec["cluster"])]["name"],
                     "r2_given_S": float(r2)})
    R = pd.DataFrame(rows).sort_values("r2_given_S", ascending=False)
    for _, r in R.iterrows():
        tag = "대체가능" if r.r2_given_S >= CUT else "고유"
        print(f"  {r.r2_given_S:+.3f}  [{tag}]  {r.axis:9} {r.label[:48]}")

    proxy = R[R.r2_given_S >= CUT].axis.tolist()
    uniq = R[R.r2_given_S < CUT].axis.tolist()
    print(f"\n  대체가능 {len(proxy)} · 고유 {len(uniq)}")

    m_proxy = [f"m_{a}_m" for a in proxy if f"m_{a}_m" in df.columns]
    m_uniq = [f"m_{a}_m" for a in uniq if f"m_{a}_m" in df.columns]
    # 구성비·이견·문서량 서프라이즈는 특정 주제의 대체물이 아니라 '무엇을 얼마나
    # 말했나'라 고유 쪽에 둔다. 다만 별도로 표시한다.
    ctx = [c for c in mcols if c.startswith(("m_share_", "m_dispersion", "m_docs_"))]

    # ── 2. 고유 축만으로 재분해 ─────────────────────────────────────
    print("\n── 고유 성분만으로 재분해 (정형 vs 고유 의미) ──")
    out = []
    for col, name, kind, hor in TARGETS:
        y = df[col]
        if y.notna().sum() < 100:
            continue
        m = y.notna()
        sub, yv = df[m], y[m]
        gap = max(hor, 5)
        sets = {"S": scols, "Mu": m_uniq + ctx, "S+Mu": scols + m_uniq + ctx,
                "Mall": mcols}
        sc, ci = {}, {}
        for tag, cols in sets.items():
            p = oos_pred(sub[cols], yv, gap, kind)
            sc[tag] = score(yv.to_numpy(), p, kind)
            ci[tag] = boot_ci(yv.to_numpy(), p, kind)
        gain = sc["S+Mu"] - sc["S"]
        out.append({"target": col, "name": name, "kind": kind, "n": int(m.sum()),
                    **{f"r_{k}": float(v) for k, v in sc.items()},
                    **{f"lo_{k}": float(v[0]) for k, v in ci.items()},
                    **{f"hi_{k}": float(v[1]) for k, v in ci.items()},
                    "gain": float(gain)})
        unit = "R²" if kind == "num" else "AUC"
        print(f"{name:22} {unit}  S {sc['S']:+.3f}  고유의미 {sc['Mu']:+.3f}"
              f"  S+고유 {sc['S+Mu']:+.3f}   증분 {gain:+.3f}"
              f" [{ci['Mu'][0]:+.2f},{ci['Mu'][1]:+.2f}]")

    O = pd.DataFrame(out)

    # ── 3. 그림 ─────────────────────────────────────────────────────
    fig = make_subplots(rows=1, cols=2, column_widths=[0.44, 0.56],
                        horizontal_spacing=0.16,
                        subplot_titles=("의미 축이 정형으로 재현되는 정도",
                                        "고유 의미의 증분 (S+고유 − S)"))
    lab = [f"[{r.cluster}] {r.label[:34]}" for _, r in R.iloc[::-1].iterrows()]
    fig.add_trace(go.Bar(
        x=R.iloc[::-1].r2_given_S, y=lab, orientation="h",
        marker_color=["#B03A2E" if v >= CUT else "#1a7f4b"
                      for v in R.iloc[::-1].r2_given_S],
        showlegend=False,
        hovertemplate="R²(축|정형) %{x:.3f}<extra></extra>"), row=1, col=1)
    fig.add_vline(x=CUT, line_dash="dot", line_color="#666", row=1, col=1,
                  annotation_text="대체가능 기준", annotation_position="top")
    fig.update_xaxes(title_text="R²(축 | 정형) — 높을수록 이미 숫자에 있다",
                     row=1, col=1, title_font=dict(size=10))

    num = O[O.kind == "num"].iloc[::-1]
    fig.add_trace(go.Bar(
        x=num.gain, y=num.name, orientation="h",
        marker_color=["#1a7f4b" if v > 0 else "#999" for v in num.gain],
        showlegend=False,
        hovertemplate="증분 %{x:+.3f}<extra></extra>"), row=1, col=2)
    fig.add_vline(x=0, line_width=2, line_color="#333", row=1, col=2)
    fig.update_xaxes(title_text="표본 외 R² 증분", row=1, col=2,
                     title_font=dict(size=10))
    fig.update_yaxes(tickfont=dict(size=10), row=1, col=1)
    fig.update_yaxes(tickfont=dict(size=10), row=1, col=2)
    fig.update_layout(
        height=460, template="plotly_white",
        title=dict(text=f"③′ 비정형만의 가치가 있는 축은 무엇인가 &nbsp;"
                        f"<span style='font-size:12px;color:#c00'>[{DISCLAIMER}]</span>"
                        f"<br><span style='font-size:11px;color:#666'>"
                        f"왼쪽: 초록 = 정형에 없는 정보 · 빨강 = 숫자의 다른 표현 &nbsp;|&nbsp; "
                        f"오른쪽: 고유 축만 추가했을 때의 증분</span>", x=0.01),
        margin=dict(t=110, b=60, l=250))
    o = FIGS / "07_substitutability.html"
    fig.write_html(o, include_plotlyjs="cdn")
    print(f"\n그림: {o}")

    (DATA / "substitutability.json").write_text(
        json.dumps({"cut": CUT, "axes": R.to_dict("records"),
                    "proxy": proxy, "unique": uniq,
                    "decomp": out}, indent=2, ensure_ascii=False, default=float),
        encoding="utf-8")
    print("저장: substitutability.json")


if __name__ == "__main__":
    main()
