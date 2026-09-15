"""④′ 사건 코호트 연구 — 분석 단위를 날짜에서 **사건**으로 바꾼다.

왜 이 화면이 필요한가 (2026-08-03 논의):
  시나리오는 본질적으로 "X 가 일어나면 Y" 다. 조건부 사건 구조지 시계열이 아니다.
  일자 패널의 표본은 국면 5~6 개지만, 사건 단위로 세면 유형별 수십 건이 된다.
  2023-06 의 공급차질과 2025-11 의 공급차질은 **거의 독립된 두 관측**이다.

그리고 여기서만 임베딩이 대체 불가능하다:
  키워드 "Freeport" 로 찾으면 Freeport 만 나온다.
  임베딩으로 찾으면 "수출설비의 예기치 못한 가동 중단"이라는 **의미**가 같은 사건이
  전부 나온다 — 이름을 모르는 것까지. 정형 데이터로는 이 코호트를 만들 수 없다.

일화가 아니라 통계가 되기 위한 3조건:
  ① 사건 정의에 **결과(가격)를 넣지 않는다.** 문서 내용만으로 정의한다.
     (06 §④ 초안의 "잔차 큰 날 고르기"는 결과 기준 선별이라 폐기)
  ② t=0 정렬. 달력 시간을 버린다.
  ③ **귀무분포를 만든다.** 같은 크기·같은 월 구성의 무작위 코호트를 1,000번 뽑아
     동일 통계를 계산하고 실제 코호트의 위치를 본다.

출력:
  data/event_cohorts.parquet · data/event_study.json · figures/05_event_study.html
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

SEED = 20260803
TOP_N = 220          # 앵커에 가장 가까운 문서 수
MERGE_DAYS = 3       # 이 안에 붙은 사건은 하나로 본다
PRE, POST = 5, 10    # 반응창 (영업일)
N_PERM = 1000

SEEDS = {
    "공급차질·설비 가동중단": r"outage|unplanned|force majeure|shut ?down|halt|disrupt|curtail|가동 ?중단|정비|차질",
    "한파·혹한": r"cold blast|arctic|polar|freeze|freez|winter storm|한파|혹한|강추위",
    "지정학 충격": r"hormuz|iran|strike|attack|\bwar\b|sanction|호르무즈|이란|전쟁|제재",
    "LNG 장기계약·FID": r"\bSPA\b|offtake|\bFID\b|long-?term (?:supply|deal|agreement)|장기 ?계약|계약 ?체결",
    "저장 서프라이즈": r"storage (?:print|surprise|build|draw|report)|EIA (?:storage|print)|재고 ?(?:실적|발표)",
}


def load():
    meta = pd.read_parquet(DATA / "market_meta.parquet").reset_index(drop=True)
    meta["date"] = pd.to_datetime(meta["date"])
    X = np.load(DATA / "emb_centered.npy").astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    T = pd.read_parquet(DATA / "target_panel.parquet")
    S = pd.read_parquet(DATA / "structured_panel.parquet")
    return meta, X, T, S


def build_cohort(meta: pd.DataFrame, X: np.ndarray, pat: str,
                 lo: pd.Timestamp, hi: pd.Timestamp):
    """키워드로 씨앗을 잡고, **임베딩으로 넓힌다.**

    씨앗은 출발점일 뿐이다. 확장분에서 키워드에 걸리지 않은 문서가
    얼마나 나오는지가 임베딩의 기여분이다.
    """
    inwin = (meta.date >= lo) & (meta.date <= hi)
    seedm = inwin & meta.title.str.contains(pat, case=False, na=False, regex=True)
    if seedm.sum() < 10:
        return None
    anchor = X[seedm.to_numpy()].mean(axis=0)
    anchor /= np.linalg.norm(anchor) + 1e-9

    sim = X @ anchor
    cand = meta.loc[inwin].copy()
    cand["sim"] = sim[inwin.to_numpy()]
    cand["is_seed"] = seedm[inwin].to_numpy()
    # 문서 단위로 최고 유사도를 취해 긴 문서가 자리를 독식하지 않게 한다
    doc = (cand.sort_values("sim", ascending=False)
           .drop_duplicates("document_id")
           .head(TOP_N))
    return doc.sort_values("date")


def merge_events(dates: pd.Series, bdays: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """반응창 중첩을 줄이려고 근접 사건을 하나로 합친다."""
    d = sorted({bdays[bdays.searchsorted(x)] for x in dates
                if bdays.searchsorted(x) < len(bdays)})
    out: list[pd.Timestamp] = []
    for x in d:
        if not out or (x - out[-1]).days > MERGE_DAYS:
            out.append(x)
    return out


def response(lp: pd.Series, bdays: pd.DatetimeIndex,
             events: list[pd.Timestamp]) -> np.ndarray:
    """t=0 정렬 누적 수익률 행렬 (사건 × 시평)."""
    pos = {d: i for i, d in enumerate(bdays)}
    rows = []
    for e in events:
        i = pos.get(e)
        if i is None or i - PRE < 0 or i + POST >= len(bdays):
            continue
        seg = lp.iloc[i - PRE:i + POST + 1].to_numpy()
        if np.isnan(seg).any():
            continue
        rows.append(seg - seg[PRE])
    return np.array(rows)


def main() -> None:
    meta, X, T, S = load()
    lo, hi = (pd.Timestamp(x) for x in WINDOW_JOINT)

    px = T.index.to_series()  # placeholder
    hhf = pd.read_parquet(DATA / "structured_panel.parquet")["hh"]
    # 근월 선물을 쓴다 (08 §1) — target_panel 생성 때와 동일 계열
    import db  # noqa: E402
    q = """SELECT DISTINCT ON (p.trade_date) p.trade_date, p.settlement_price
           FROM hub_prices p JOIN hubs h ON h.id=p.hub_id
           WHERE h.name='Henry Hub' AND p.settlement_price IS NOT NULL
           ORDER BY p.trade_date, p.delivery_strip"""
    d = db.query(q)
    px = pd.Series(d.settlement_price.to_numpy(),
                   index=pd.to_datetime(d.trade_date)).sort_index()

    bdays = pd.DatetimeIndex(sorted(px.index[(px.index >= lo - pd.Timedelta(days=30)) &
                                             (px.index <= hi + pd.Timedelta(days=30))]))
    lp = np.log(px.reindex(bdays).ffill(limit=3))

    rng = np.random.default_rng(SEED)
    results, store = [], []
    print(f"분석창 {lo:%Y-%m-%d} ~ {hi:%Y-%m-%d} · 거래일 {len(bdays)}\n")

    for name, pat in SEEDS.items():
        doc = build_cohort(meta, X, pat, lo, hi)
        if doc is None:
            print(f"{name}: 씨앗 부족 — 건너뜀")
            continue
        events = merge_events(doc.date, bdays)
        R = response(lp, bdays, events)
        if len(R) < 15:
            print(f"{name}: 사건 {len(R)}건 — 부족")
            continue
        expand = int((~doc.is_seed).sum())

        # 통계량: t=0 → t+3 누적 수익률의 코호트 평균
        h3 = R[:, PRE + 3].mean()
        h5 = R[:, PRE + 5].mean()
        pre = R[:, 0].mean()          # t−5 → t=0 사전 표류

        # 귀무분포 — **월 구성을 맞춘** 무작위 코호트
        months = pd.DatetimeIndex(events).month
        pool = {m: bdays[(bdays.month == m)] for m in set(months)}
        null3 = np.empty(N_PERM)
        for b in range(N_PERM):
            fake = [pool[m][rng.integers(len(pool[m]))] for m in months]
            Rf = response(lp, bdays, sorted(set(fake)))
            null3[b] = Rf[:, PRE + 3].mean() if len(Rf) else np.nan
        null3 = null3[~np.isnan(null3)]
        pct = float((null3 < h3).mean())
        p2 = 2 * min(pct, 1 - pct)

        results.append({"name": name, "n_events": len(R), "n_docs": len(doc),
                        "n_expanded": expand, "pre5": float(pre),
                        "h3": float(h3), "h5": float(h5),
                        "null_mean": float(null3.mean()), "null_sd": float(null3.std()),
                        "pctile": pct, "p_two_sided": p2})
        store.append({"name": name, "R": R, "null": null3, "events": events})

        print(f"{name}")
        print(f"   사건 {len(R):3d}건 · 문서 {len(doc)} (키워드 밖 확장 {expand}건 = "
              f"{expand/len(doc):.0%})")
        print(f"   사전표류(t−5→0) {pre:+.2%}   t+3 {h3:+.2%}   t+5 {h5:+.2%}")
        print(f"   귀무 평균 {null3.mean():+.2%} sd {null3.std():.2%} → "
              f"백분위 {pct:.1%}  양측 p {p2:.3f}\n")

    # ── 그림 ────────────────────────────────────────────────────────
    ncol = 2
    nrow = int(np.ceil(len(store) / ncol))
    fig = make_subplots(rows=nrow, cols=ncol, vertical_spacing=0.13,
                        horizontal_spacing=0.09,
                        subplot_titles=[f"{s['name']} (n={len(s['R'])})" for s in store])
    xs = np.arange(-PRE, POST + 1)
    for i, s in enumerate(store):
        r, c = i // ncol + 1, i % ncol + 1
        R = s["R"]
        med = np.median(R, axis=0)
        q1, q3 = np.percentile(R, [25, 75], axis=0)
        fig.add_trace(go.Scatter(x=np.r_[xs, xs[::-1]], y=np.r_[q3, q1[::-1]],
                                 fill="toself", fillcolor="rgba(76,120,168,0.15)",
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"),
                      row=r, col=c)
        fig.add_trace(go.Scatter(x=xs, y=med, mode="lines+markers",
                                 line=dict(color="#4C78A8", width=2),
                                 marker=dict(size=4), showlegend=False,
                                 hovertemplate="t%{x:+d}  %{y:.2%}<extra></extra>"),
                      row=r, col=c)
        fig.add_vline(x=0, line_dash="dot", line_color="#c00", row=r, col=c)
        fig.add_hline(y=0, line_width=0.8, line_color="#999", row=r, col=c)
        fig.update_yaxes(tickformat=".1%", row=r, col=c)
        fig.update_xaxes(title_text="영업일 (t=0 사건일)", row=r, col=c,
                         title_font=dict(size=9))
    fig.update_layout(
        height=330 * nrow, template="plotly_white",
        title=dict(text=f"④′ 사건 코호트 반응 — 중앙값과 사분위 &nbsp;"
                        f"<span style='font-size:12px;color:#c00'>[{DISCLAIMER}]</span>"
                        f"<br><span style='font-size:11px;color:#666'>"
                        f"코호트는 키워드 씨앗을 임베딩으로 넓혀 구성 · 가격은 정의에 쓰지 않음 · "
                        f"HH 근월</span>", x=0.01),
        margin=dict(t=110, b=50))
    out = FIGS / "05_event_study.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"그림: {out}")

    (DATA / "event_study.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.concat([pd.DataFrame({"cohort": s["name"], "event_date": s["events"]})
               for s in store]).to_parquet(DATA / "event_cohorts.parquet", index=False)
    print("저장: event_study.json · event_cohorts.parquet")


if __name__ == "__main__":
    main()
