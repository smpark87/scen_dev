"""D12 — 방향 구별 실패 시연 (화면 ⑤).

06 §⑤ · 01 §4.1 · E6. 초안은 합성 문장쌍이었으나 **실제 코퍼스에서 더 강한
사례가 나왔다** — `[09] 기상 예보 노트`의 본문이 같은 템플릿에 단어 하나만 다르다.

    "The Lower 48 forecast has **warmed** by +5°F compared to the previous run"
    "The Lower 48 forecast has **cooled** by a total of 3°F compared to the prior run"

측정: 같은 방향끼리의 거리 vs 반대 방향끼리의 거리.
  구별한다면  → 반대끼리가 더 멀다
  구별 못한다면 → 두 거리가 같다

대조군으로 **서술형 기사**(`[02]` 선물 코멘터리)에서 동일 측정을 한다.
같은 임베딩·같은 척도인데 결과가 다르면, 문제는 임베딩 일반이 아니라
**문서 형식**임이 드러난다. 그것이 구조화 추출(03 §5.4 `direction`)의 근거다.

출력: data/direction_test.json · figures/06_direction.html
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from config import DATA, DISCLAIMER, FIGS, WINDOW_JOINT  # noqa: E402

SEED = 20260803

# 쉬운 것 → 어려운 것 순. 이 순서 자체가 화면의 메시지다.
# (덩어리, 표시명, 양(+)방향 패턴, 음(−)방향 패턴, 방향의 종류)
CASES = [
    (2, "① 어휘가 다른 방향<br>폭염 ↔ 한파 (서술형 기사)",
     r"\b(?:heat|hot|warm|mild)\w*\b|폭염|무더위|온화",
     r"\b(?:cold|chill|freez|frigid|arctic)\w*\b|한파|추위|강추위", "어휘 상이"),
    (9, "② 같은 템플릿 안 단어 차이<br>warmed ↔ cooled (예보 노트)",
     r"\bwarm(?:ed|er|ing)\b|shifted warmer|warming",
     r"\bcool(?:ed|er|ing)\b|shifted colder|colder", "템플릿 내 단어"),
    (2, "③ 비교로만 갈리는 방향<br>예상 하회 ↔ 상회 (재고 서프라이즈)",
     r"bullish|tight(?:er)?|below (?:consensus|expectation)|저조한|하회",
     r"bearish|loose(?:r)?|above (?:consensus|expectation)|상회|예상 ?상회", "비교·부정"),
]


def verdict(auc: float) -> str:
    if auc >= 0.85:
        return "구별한다"
    if auc >= 0.65:
        return "구별하나 비지도 축에선 밀린다"
    return "구별하지 못한다"


def pair_stats(V: np.ndarray, lab: np.ndarray) -> dict:
    """같은 방향 / 반대 방향 코사인 거리의 평균과 분리도."""
    A, B = V[lab == 1], V[lab == 0]
    if len(A) < 8 or len(B) < 8:
        return {}
    d = lambda P, Q: 1.0 - P @ Q.T  # noqa: E731
    within = np.r_[d(A, A)[np.triu_indices(len(A), 1)],
                   d(B, B)[np.triu_indices(len(B), 1)]]
    between = d(A, B).ravel()
    # 분리도 = 표준화된 평균 차. 0 이면 구별 못 함.
    pooled = np.sqrt((within.var() + between.var()) / 2)
    sep = float((between.mean() - within.mean()) / pooled) if pooled > 0 else np.nan

    # 분류 가능성 — 임베딩만으로 방향을 맞힐 수 있는가
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    auc = float(np.mean(cross_val_score(
        LogisticRegression(C=0.5, max_iter=2000),
        V, lab, cv=5, scoring="roc_auc")))
    return {"n_pos": int(len(A)), "n_neg": int(len(B)),
            "within": float(within.mean()), "between": float(between.mean()),
            "sep": sep, "auc": auc,
            "within_arr": within, "between_arr": between}


def main() -> None:
    meta = pd.read_parquet(DATA / "market_meta.parquet").reset_index(drop=True)
    meta["date"] = pd.to_datetime(meta["date"])
    meta = meta.merge(pd.read_parquet(DATA / "clusters.parquet"), on="chunk_id")
    X = np.load(DATA / "emb_centered.npy").astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    lo, hi = (pd.Timestamp(x) for x in WINDOW_JOINT)

    info = db.healthcheck()
    print(f"DB: {info['user']} (read_only={info['read_only']})\n")

    out, panels = [], []
    for cl, name, pos_pat, neg_pat, kind in CASES:
        sel = meta.index[(meta.cluster == cl) & (meta.date >= lo) & (meta.date <= hi)]
        if len(sel) < 40:
            print(f"{name}: 청크 {len(sel)} — 부족")
            continue
        ids = meta.loc[sel, "chunk_id"].astype(int).tolist()
        txt = db.query("SELECT id AS chunk_id, text FROM ai_document_chunks "
                       "WHERE id = ANY(%s)", (ids,))
        sub = meta.loc[sel].merge(txt, on="chunk_id")
        body = sub.text.fillna("")
        p = body.str.contains(pos_pat, case=False, regex=True)
        n = body.str.contains(neg_pat, case=False, regex=True)
        keep = p ^ n                      # 한쪽만 언급한 청크만 (양쪽 언급은 제외)
        sub, lab = sub[keep], p[keep].astype(int).to_numpy()
        # meta 의 행 순서가 X 의 행 순서다. chunk_id → 행 위치로 정확히 매핑한다.
        pos_map = pd.Series(np.arange(len(meta)), index=meta.chunk_id)
        V = X[pos_map.loc[sub.chunk_id].to_numpy()]
        st = pair_stats(V, lab)
        if not st:
            print(f"{name}: 한쪽 표본 부족 (+{int(lab.sum())} / −{int((1-lab).sum())})")
            continue
        st.update({"case": name, "kind": kind, "cluster": cl})
        panels.append(st)
        out.append({k: v for k, v in st.items() if not k.endswith("_arr")})
        print(f"{re.sub('<br>', ' / ', name)}")
        print(f"   표본  +{st['n_pos']}  −{st['n_neg']}")
        print(f"   같은 방향 거리 {st['within']:.4f}   반대 방향 거리 {st['between']:.4f}")
        print(f"   분리도 {st['sep']:+.3f}   방향 분류 AUC {st['auc']:.3f}"
              f"   → {verdict(st['auc'])}\n")

    # ── 그림 ────────────────────────────────────────────────────────
    fig = make_subplots(
        rows=1, cols=len(panels), horizontal_spacing=0.07,
        subplot_titles=[
            f"{p['case']}<br><sub>방향 분류 AUC <b>{p['auc']:.2f}</b> — "
            f"{'✓ ' if p['auc'] >= 0.85 else ('△ ' if p['auc'] >= 0.65 else '✗ ')}"
            f"{verdict(p['auc'])}</sub>" for p in panels])
    for i, p in enumerate(panels):
        # 원시 거리 배열(수만 개)을 그대로 넘기면 HTML 이 1MB 를 넘는다.
        # 여기서 구간화해 45개 막대로 보낸다 — 그림은 같고 용량만 준다.
        both = np.r_[p["within_arr"], p["between_arr"]]
        edges = np.linspace(both.min(), both.max(), 46)
        ctr = np.round((edges[:-1] + edges[1:]) / 2, 4)
        for arr, nm, c in ((p["within_arr"], "같은 방향끼리", "#4C78A8"),
                           (p["between_arr"], "반대 방향끼리", "#E4572E")):
            dens, _ = np.histogram(arr, bins=edges, density=True)
            fig.add_trace(go.Bar(x=ctr, y=np.round(dens, 3), name=nm,
                                 marker_color=c, opacity=0.55,
                                 showlegend=(i == 0), legendgroup=nm),
                          row=1, col=i + 1)
        fig.update_xaxes(title_text="코사인 거리", row=1, col=i + 1,
                         title_font=dict(size=10))
    fig.update_layout(
        barmode="overlay", height=430, template="plotly_white",
        title=dict(text=f"⑤ 임베딩은 어떤 방향을 구별하고 어떤 방향을 못 구별하는가"
                        f" &nbsp;<span style='font-size:12px;color:#c00'>[{DISCLAIMER}]</span>"
                        f"<br><span style='font-size:11px;color:#666'>"
                        f"두 분포가 겹칠수록 방향을 구별하지 못한다는 뜻 · "
                        f"같은 임베딩·같은 척도</span>", x=0.01),
        legend=dict(orientation="h", y=1.08, x=0.62),
        margin=dict(t=120, b=50))
    o = FIGS / "06_direction.html"
    fig.write_html(o, include_plotlyjs="cdn")
    print(f"그림: {o}")
    (DATA / "direction_test.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
