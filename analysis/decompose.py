"""D9/D10 — 대칭 설명력 분해 (화면 ④).

06 §4.0.2 (가). 어느 쪽도 먼저 넣지 않는다.

    정형만  → R²_S
    의미만  → R²_M      ← "뉴스만 가지고 이만큼 설명한다"
    둘 다   → R²_SM

    고유 정형 = R²_SM − R²_M      "숫자만 아는 것"
    고유 의미 = R²_SM − R²_S      "뉴스만 아는 것"
    공유      = R²_S + R²_M − R²_SM

**표본 외 R²** 를 쓴다. 표본 내로 재면 변수가 많은 쪽이 무조건 이겨서
"의미가 더 설명한다"가 발견인지 차원 수의 부산물인지 구분할 수 없다.

누수 차단:
  · 시계열 분할 + **gap(purge)**. 대상이 t→t+5, t+10 을 쓰므로 학습·평가 구간이
    창 중첩으로 붙으면 정답이 새어 들어간다.
  · 표준화·결측대치는 **학습 구간에서만** 적합한다 (Pipeline).
  · 능선회귀 알파는 학습 구간 내부 CV 로만 고른다.

⚠️ 이 산출물로 예측력을 주장하지 않는다 (as-of 미적용). 설명 구조의 형태만 본다.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATA, WINDOW_JOINT  # noqa: E402

warnings.filterwarnings("ignore")
SEED = 20260803
N_SPLIT = 5
# 알파 상한이 낮으면 **신호가 없을 때 0 으로 수축하지 못해** R² 가 음수로 나온다.
# 표준화된 30~60열, 학습 700행 규모에서는 1e4 로 부족하다. 상한을 크게 잡는다.
ALPHAS = np.logspace(-1, 7, 17)

# (열이름, 표시명, 종류, 창길이) — 창길이는 purge gap 산정용
TARGETS = [
    ("hhf_T1_persist",   "T1 방향 지속성",       "num", 5),
    ("hhf_T2_ret1",      "T2 익일 수익률",       "num", 1),
    ("hhf_T3_intensity", "T3 강도 변화",         "num", 5),
    ("hhf_T4_volchg",    "T4 변동성 변화",       "num", 10),
    ("hhf_T5_breakz",    "T5 체제이탈 |z|",      "num", 10),
    ("T6_stor_next",     "T6 저장 nowcast",      "num", 5),
    ("hhf_T7_tail",      "T7 꼬리",              "bin", 1),
    ("wb_T1_persist",    "W1 베이시스 지속성",    "num", 5),
    ("wb_T2_chg1",       "W2 베이시스 익일변화",  "num", 1),
    ("wb_T5_blowout",    "W3 베이시스 붕괴",      "bin", 5),
]


ROLL = 250      # 후행 정규화 창 (약 1년)


def _roll_z(d: pd.DataFrame) -> pd.DataFrame:
    """후행 창 대비 표준화 = '최근 기준으로 얼마나 이례적인가'.

    **필수 처리다.** 원 계열을 그대로 넣으면 안 된다 —
      정형 17열이 강한 시간 추세를 갖고 (리그 −0.96, 퍼미안 생산 +0.96,
      생산 +0.84, feedgas +0.81), 문서량은 분석창 안에서 4.8 → 24.4 로 5배 늘었다.
      시계열 분할은 앞구간으로 배워 뒷구간을 맞히므로, 이런 계열은 평가 구간 값이
      **학습 범위 밖**이다. 능선회귀가 외삽하며 예측이 폭발한다
      (첫 실행에서 R² −8 ~ −234 가 나온 원인).
    후행 창만 쓰므로 미래를 보지 않는다. 03 §5.2.1 "수준이 아니라 서프라이즈".
    """
    mu = d.rolling(ROLL, min_periods=60).mean()
    sd = d.rolling(ROLL, min_periods=60).std()
    return ((d - mu) / sd.replace(0, np.nan)).clip(-5, 5)


def load() -> tuple[pd.DataFrame, list[str], list[str]]:
    S = pd.read_parquet(DATA / "structured_panel.parquet")
    M = pd.read_parquet(DATA / "semantic_panel.parquet")
    T = pd.read_parquet(DATA / "target_panel.parquet")

    # ── 정형: 계절항만 남기고 전부 후행 표준화 ──────────────────────
    snum = [c for c in S.columns if pd.api.types.is_numeric_dtype(S[c])]
    seas = ["sin_doy", "cos_doy"]
    Sx = pd.concat([_roll_z(S[[c for c in snum if c not in seas]]), S[seas]], axis=1)
    Sx.columns = [f"s_{c}" for c in Sx.columns]

    # ── 의미: 구성비 + 서프라이즈로 바꾼 뒤 표준화 ──────────────────
    k = len([c for c in M.columns if c.startswith("vol_")])
    nd = M["n_docs"].replace(0, np.nan)
    share = M[[f"vol_{c}" for c in range(k)]].div(nd, axis=0)      # 구성비 (규모 무관)
    share.columns = [f"share_{c}" for c in range(k)]
    # 축은 **문서당 평균**(ax_*_m)만 쓴다. 순합(net)은 문서 수에 비례해
    # 코퍼스 성장 자체를 신호로 오인한다.
    axm = M[[c for c in M.columns if c.endswith("_m")]].fillna(0.0)
    docs = np.log((M["n_docs"] + 0.5) / (M["n_docs"].rolling(60, min_periods=20).mean() + 0.5))
    Mraw = pd.concat([share, axm, M[["dispersion"]], docs.rename("docs_surp")], axis=1)
    Mx = _roll_z(Mraw)
    Mx.columns = [f"m_{c}" for c in Mx.columns]

    df = Sx.join(Mx, how="outer").join(T, how="left")
    s, e = WINDOW_JOINT
    df = df[(df.index >= pd.Timestamp(s)) & (df.index <= pd.Timestamp(e))]
    df = df[df.index.dayofweek < 5]

    scols = [c for c in Sx.columns if df[c].std(skipna=True) > 0]
    mcols = [c for c in Mx.columns if df[c].std(skipna=True) > 0]
    df[mcols] = df[mcols].fillna(0.0)      # 축이 그날 없음 = "그런 얘기가 없었다"
    return df, scols, mcols


def oos_pred(X: pd.DataFrame, y: pd.Series, gap: int, kind: str) -> np.ndarray:
    """표본 외 예측값. 시계열 분할 + purge."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegressionCV, RidgeCV
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    # 첫 학습 구간이 **최소 2년**은 되게 한다.
    #   기본 5분할이면 첫 학습이 7개월이라 계절을 한 바퀴도 못 본다. 저장량처럼
    #   계절이 지배하는 대상에서 그 모형이 뒷구간에 외삽하면 R² 가 −3 까지 간다.
    n = len(y)
    min_tr = max(int(n * 0.55), 260)
    ts = max((n - min_tr) // 3, 40)
    pred = np.full(n, np.nan)
    tss = TimeSeriesSplit(n_splits=3, test_size=ts, gap=gap)
    for tr, te in tss.split(X):
        if kind == "bin" and len(np.unique(y.iloc[tr])) < 2:
            continue
        # 알파·C 선택도 학습 구간 **안에서 시계열 분할**로 한다.
        # 무작위 K-분할을 쓰면 학습 구간 내부에서 미래를 보고 정규화 세기를 고른다.
        inner = TimeSeriesSplit(n_splits=3, gap=gap,
                                test_size=max(len(tr) // 6, 30))
        est = (RidgeCV(alphas=ALPHAS, cv=inner) if kind == "num"
               else LogisticRegressionCV(Cs=6, cv=inner, max_iter=2000,
                                         random_state=SEED))
        pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), est)
        pipe.fit(X.iloc[tr], y.iloc[tr])
        pred[te] = (pipe.predict(X.iloc[te]) if kind == "num"
                    else pipe.predict_proba(X.iloc[te])[:, 1])
    return pred


def boot_ci(y: np.ndarray, p: np.ndarray, kind: str,
            block: int = 20, n_rep: int = 400) -> tuple[float, float]:
    """이동블록 부트스트랩 90% 구간.

    대상이 t→t+5, t+10 을 쓰므로 인접일이 겹친다. 일 단위 재추출은 표본을
    부풀린다. 20일 블록으로 뽑아 중첩 구조를 보존한다 (08 §4).
    """
    m = ~(np.isnan(y) | np.isnan(p))
    y, p = y[m], p[m]
    n = len(y)
    if n < 60:
        return (np.nan, np.nan)
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / block))
    vals = []
    for _ in range(n_rep):
        st = rng.integers(0, max(n - block, 1), size=nb)
        idx = np.concatenate([np.arange(s, min(s + block, n)) for s in st])[:n]
        s = score(y[idx], p[idx], kind)
        if not np.isnan(s):
            vals.append(s)
    if len(vals) < 50:
        return (np.nan, np.nan)
    return (float(np.quantile(vals, 0.05)), float(np.quantile(vals, 0.95)))


def score(y: np.ndarray, p: np.ndarray, kind: str) -> float:
    m = ~(np.isnan(y) | np.isnan(p))
    if m.sum() < 30:
        return np.nan
    y, p = y[m], p[m]
    if kind == "num":
        return 1.0 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    from sklearn.metrics import roc_auc_score
    return roc_auc_score(y, p) if len(np.unique(y)) > 1 else np.nan


def selftest(df: pd.DataFrame, scols: list[str], mcols: list[str]) -> None:
    """하네스 검증 — 정답을 아는 대상 3종으로 채점기를 시험한다.

    "신호가 없다"와 "파이프라인이 신호를 못 잡는다"는 다르다.
    이 검사를 통과하지 못하면 아래 어떤 null 결과도 믿을 수 없다.
    """
    rng = np.random.default_rng(SEED)
    n = len(df)
    cases = []

    # (1) 순수 잡음 — R² 는 0 근처여야 한다. 크게 음수면 정규화가 부족한 것이다.
    cases.append(("순수 잡음 (기대 ≈0)", pd.Series(rng.normal(size=n), index=df.index)))
    # (2) 정형 3열의 선형결합 + 잡음 — S 가 높고 M 은 낮아야 한다.
    base = df[["s_stor_vs5y", "s_balance", "s_hh_vol20"]].fillna(0.0)
    cases.append(("정형 3열 합성 (S 높아야)",
                  (base.iloc[:, 0] * 0.7 + base.iloc[:, 1] * 0.5 - base.iloc[:, 2] * 0.4
                   + rng.normal(scale=0.5, size=n))))
    # (3) 의미 3열의 선형결합 + 잡음 — M 이 높아야 한다.
    bm = df[["m_ax_2_0_m", "m_share_2", "m_dispersion"]].fillna(0.0)
    cases.append(("의미 3열 합성 (M 높아야)",
                  (bm.iloc[:, 0] * 0.7 - bm.iloc[:, 1] * 0.5 + bm.iloc[:, 2] * 0.4
                   + rng.normal(scale=0.5, size=n))))

    print("── 하네스 자체 검증 ──")
    ok = True
    for nm, y in cases:
        r = {t: score(y.to_numpy(), oos_pred(df[c], y, 5, "num"), "num")
             for t, c in (("S", scols), ("M", mcols))}
        print(f"  {nm:26} S {r['S']:+.3f}   M {r['M']:+.3f}")
        if nm.startswith("순수") and (r["S"] < -0.1 or r["M"] < -0.1):
            ok = False
        if nm.startswith("정형") and r["S"] < 0.3:
            ok = False
        if nm.startswith("의미") and r["M"] < 0.3:
            ok = False
    print("  → 하네스 " + ("정상\n" if ok else "⚠️ 이상 — 아래 결과 신뢰 불가\n"))


def main() -> None:
    df, scols, mcols = load()
    if "--selftest" in sys.argv or True:
        print(f"결합 패널 {len(df)}일 · 정형 {len(scols)}열 · 의미 {len(mcols)}열\n")
        selftest(df, scols, mcols)
    print(f"결합 패널 {len(df)}일 · 정형 {len(scols)}열 · 의미 {len(mcols)}열")
    print(f"  {df.index.min():%Y-%m-%d} ~ {df.index.max():%Y-%m-%d}\n")

    rows, preds = [], {}
    for col, name, kind, hor in TARGETS:
        y = df[col]
        if y.notna().sum() < 100:
            print(f"{name:22} 표본 부족 — 건너뜀")
            continue
        m = y.notna()
        sub, yv = df[m], y[m]
        gap = max(hor, 5)
        out = {}
        for tag, cols in (("S", scols), ("M", mcols), ("SM", scols + mcols)):
            p = oos_pred(sub[cols], yv, gap, kind)
            out[tag] = score(yv.to_numpy(), p, kind)
            preds[(col, tag)] = pd.Series(p, index=sub.index)
        r = {"target": col, "name": name, "kind": kind, "n": int(m.sum()),
             "S": out["S"], "M": out["M"], "SM": out["SM"]}
        for tag in ("S", "M", "SM"):
            lo, hi = boot_ci(yv.to_numpy(), preds[(col, tag)].to_numpy(), kind)
            r[f"{tag}_lo"], r[f"{tag}_hi"] = lo, hi
        if kind == "num":
            r["uniq_S"] = out["SM"] - out["M"]
            r["uniq_M"] = out["SM"] - out["S"]
            r["shared"] = out["S"] + out["M"] - out["SM"]
        rows.append(r)
        unit = "R²" if kind == "num" else "AUC"
        print(f"{name:22} n={r['n']:4d} {unit}"
              f"  S {out['S']:+.3f}[{r['S_lo']:+.2f},{r['S_hi']:+.2f}]"
              f"  M {out['M']:+.3f}[{r['M_lo']:+.2f},{r['M_hi']:+.2f}]"
              f"  SM {out['SM']:+.3f}")

    R = pd.DataFrame(rows)
    R.to_parquet(DATA / "decomp.parquet", index=False)

    # ── 국면별 재평가 — 같은 예측값을 국면 부분집합에서 채점 ─────────
    print("\n── 국면별 (동일 예측값, 부분집합 채점) ──")
    reg_rows = []
    for col, name, kind, _h in TARGETS:
        if (col, "S") not in preds:
            continue
        for rc in ("regime_vol", "regime_trend"):
            for lev in df[rc].cat.categories:
                sel = df[rc] == lev
                idx = preds[(col, "S")].index.intersection(df.index[sel])
                if len(idx) < 60:
                    continue
                yv = df.loc[idx, col].to_numpy()
                sc = {t: score(yv, preds[(col, t)].loc[idx].to_numpy(), kind)
                      for t in ("S", "M", "SM")}
                reg_rows.append({"target": col, "name": name, "kind": kind,
                                 "split": rc, "level": str(lev), "n": len(idx), **sc})
    RG = pd.DataFrame(reg_rows)
    RG.to_parquet(DATA / "decomp_regime.parquet", index=False)

    key = ["hhf_T1_persist", "T6_stor_next", "wb_T1_persist"]
    for col in key:
        g = RG[(RG.target == col) & (RG.split == "regime_vol")]
        if g.empty:
            continue
        nm = g.name.iloc[0]
        print(f"  {nm}")
        for _, r in g.iterrows():
            print(f"     {r.level:6} n={int(r.n):4d}   S {r.S:+.3f}  M {r.M:+.3f}  SM {r.SM:+.3f}")

    (DATA / "decomp_summary.json").write_text(
        json.dumps({"rows": rows, "n_days": len(df),
                    "n_struct": len(scols), "n_semantic": len(mcols)},
                   indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print(f"\n저장: decomp.parquet · decomp_regime.parquet · decomp_summary.json")


if __name__ == "__main__":
    main()
