"""D8 — 종속변수(대상) 정의와 진단.

06 §4.0.2 (나) 의 7개 대상을 **연산 가능한 정의**로 확정한다.
W2 말에 동결한다 — 회귀를 돌려보고 대상을 고르면 그건 결과를 보고 표본을
고르는 것이다 (charter §7, "채택은 느리게").

기준 가격 두 가지:
  hhf   Henry Hub 선물 근월 (hub_prices, 2010~)  ← **주 기준**
        시장의 전망이 담긴 가격. 날씨 소음이 현물보다 적다.
  hh    Henry Hub 현물     (gas_daily_prices, 2020~)
        물리적 수급의 즉시 반영. 꼬리·변동성 대상에서 함께 본다.

⚠️ 중첩 창: T1·T3·T4·T5 는 t→t+5, t+10 을 쓰므로 인접일 관측이 겹친다.
   유효 표본은 일수/구간길이 수준이며, 추론에서 블록 부트스트랩이 필요하다.
   여기서는 정의와 기술통계만 낸다.

출력:
  data/target_panel.parquet
  data/target_summary.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from config import DATA, WINDOW_JOINT  # noqa: E402

H_SHORT, H_MID = 5, 10


def fetch_front_month() -> pd.Series:
    """HH 선물 근월. 거래일마다 delivery_strip 이 가장 이른 것."""
    q = """
    SELECT DISTINCT ON (p.trade_date)
           p.trade_date, p.settlement_price
    FROM hub_prices p JOIN hubs h ON h.id = p.hub_id
    WHERE h.name = 'Henry Hub' AND p.settlement_price IS NOT NULL
    ORDER BY p.trade_date, p.delivery_strip
    """
    d = db.query(q)
    s = pd.Series(d.settlement_price.to_numpy(),
                  index=pd.to_datetime(d.trade_date), name="hhf").sort_index()
    return s


def build(px: pd.Series, tag: str) -> pd.DataFrame:
    lp = np.log(px)
    r1 = lp.diff()
    out = pd.DataFrame(index=px.index)

    # T2 일간 변동 — 정형이 지배할 것으로 보는 대조군
    out[f"{tag}_T2_ret1"] = lp.shift(-1) - lp

    # T1 방향 지속성 — **주 대상** (06 §4.0.2 (나))
    #   과거 5일 방향으로 앞으로 5일이 얼마나 더 가는가. 양수면 지속.
    r_past = lp - lp.shift(H_SHORT)
    r_fwd = lp.shift(-H_SHORT) - lp
    out[f"{tag}_T1_persist"] = np.sign(r_past) * r_fwd
    out[f"{tag}_T1_persist_bin"] = (np.sign(r_past) == np.sign(r_fwd)).astype(float)
    out.loc[r_past.isna() | r_fwd.isna(), f"{tag}_T1_persist_bin"] = np.nan

    # T1 유효 표본 — 과거 움직임이 거의 0 이면 sign() 이 잡음이다.
    #   |r_past| 가 중앙값 이상인 날만 "방향이 있었다"로 본다.
    out[f"{tag}_T1_valid"] = (r_past.abs() >= r_past.abs().median()).astype(float)

    # T3 강도 변화 — 같은 방향이나 약해지는가
    #   0 근처 분모로 꼬리가 폭발하므로 바닥을 일간 변동성의 10% 로 둔다.
    floor = r1.rolling(60, min_periods=30).std() * 0.1
    out[f"{tag}_T3_intensity"] = np.log(
        (r_fwd.abs() + floor) / (r_past.abs() + floor)
    ).clip(-4, 4)

    # T4 변동성 변화 — 불확실성은 텍스트에 먼저 온다는 가설의 시험대
    v_past = r1.rolling(20, min_periods=12).std()
    v_fwd = r1.shift(-H_MID).rolling(H_MID, min_periods=6).std()
    out[f"{tag}_T4_volchg"] = np.log((v_fwd + 1e-6) / (v_past + 1e-6))

    # T5 체제 이탈 — 전환의 대용. 60일 변동성 대비 10일 이동의 크기.
    #   2σ 로 잡으면 결합창에서 발생률 0.8%(7건) 라 모형화가 불가능하다.
    #   1.25σ 로 완화하고, 연속형(z)도 함께 남겨 임계값 선택에 의존하지 않게 한다.
    s60 = r1.rolling(60, min_periods=40).std()
    r_mid = lp.shift(-H_MID) - lp
    z_mid = r_mid / (s60 * np.sqrt(H_MID))
    out[f"{tag}_T5_breakz"] = z_mid.abs()
    out[f"{tag}_T5_break"] = (z_mid.abs() > 1.25).astype(float)
    out.loc[z_mid.isna(), f"{tag}_T5_break"] = np.nan

    # T7 꼬리 — 다음날 극단 변동 (분석창 내 95 분위)
    s, e = WINDOW_JOINT
    w = out.loc[str(s):str(e), f"{tag}_T2_ret1"].abs()
    thr = float(w.quantile(0.95))
    out[f"{tag}_T7_tail"] = (out[f"{tag}_T2_ret1"].abs() > thr).astype(float)
    out.loc[out[f"{tag}_T2_ret1"].isna(), f"{tag}_T7_tail"] = np.nan
    out.attrs[f"{tag}_tail_thr"] = thr
    return out


def build_basis(basis: pd.Series) -> pd.DataFrame:
    """Waha−HH 베이시스 대상. 지역 질문(03 §5.1.2)의 예고편.

    베이시스는 음수가 정상이라 로그를 쓰지 않고 산술차분한다.
    "질문이 바뀌면 쓸모 있는 변수도 바뀐다" — HH 에는 63개 허브가 중복이지만
    지역 질문에는 그 허브들이 본질이다. 그 대비를 데모에서 직접 보이려는 대상.
    """
    out = pd.DataFrame(index=basis.index)
    b_past = basis - basis.shift(H_SHORT)
    b_fwd = basis.shift(-H_SHORT) - basis
    out["wb_T1_persist"] = np.sign(b_past) * b_fwd
    out["wb_T1_persist_bin"] = (np.sign(b_past) == np.sign(b_fwd)).astype(float)
    out.loc[b_past.isna() | b_fwd.isna(), "wb_T1_persist_bin"] = np.nan
    out["wb_T1_valid"] = (b_past.abs() >= b_past.abs().median()).astype(float)
    out["wb_T2_chg1"] = basis.shift(-1) - basis
    # 베이시스 붕괴 — 퍼미안 병목의 실물 신호. 5일 뒤 베이시스가 60일 하위 10% 아래로
    thr = basis.rolling(60, min_periods=40).quantile(0.10)
    out["wb_T5_blowout"] = (basis.shift(-H_SHORT) < thr).astype(float)
    out.loc[basis.shift(-H_SHORT).isna() | thr.isna(), "wb_T5_blowout"] = np.nan
    return out


def main() -> None:
    info = db.healthcheck()
    print(f"DB: {info['user']} (read_only={info['read_only']})")
    S = pd.read_parquet(DATA / "structured_panel.parquet")

    hhf = fetch_front_month()
    print(f"HH 근월: {len(hhf):,}일 {hhf.index.min():%Y-%m-%d}~{hhf.index.max():%Y-%m-%d}")
    idx = S.index
    px_f = hhf.reindex(idx).ffill(limit=5)
    px_s = S["hh"]

    T = pd.concat([build(px_f, "hhf"), build(px_s, "hh"),
                   build_basis(S["basis_waha_hh"])], axis=1)

    # T6 저장량 nowcast — 발표 전 구간의 유일한 정보원 가설 (06 §4.0.2)
    #   목요일 발표되는 주간 순변화. 발표 **이전** 시점에서 맞히는 것이 대상.
    #   본문에 "Analysts Expect 106 Bcf build" 가 실제로 들어 있어(코퍼스 확인)
    #   의미 변수가 힘을 쓸 수 있는 자리다.
    stor = S["stor"]
    pub = stor.diff()
    pub = pub[pub.notna() & (pub != 0)]                 # 실제 갱신된 날 = 발표 반영일
    nxt = pub.reindex(idx).bfill(limit=9)
    T["T6_stor_next"] = nxt
    # **발표 직전 3영업일에만 관측을 둔다.** 매일 같은 값을 반복하면 자기상관 0.97 로
    # 유효 표본이 주 단위인데 일 단위인 척하게 된다.
    days_to = pd.Series(np.nan, index=idx)
    for d in pub.index:
        w = idx[(idx < d) & (idx >= d - pd.Timedelta(days=5))]
        days_to.loc[w] = (d - w).days
    T["T6_eve"] = (days_to.notna() & (days_to <= 3)).astype(float)
    T.loc[T.T6_eve == 0, "T6_stor_next"] = np.nan

    # 국면 분할 축 (06 §4.0.2 (다)) — t 시점에 알 수 있는 것만.
    # 분위는 **분석창 안에서** 끊는다. 전체 기간으로 끊으면 2023~ 이 고변동에 몰린다.
    s0, e0 = WINDOW_JOINT
    r1 = np.log(px_f).diff()
    v20 = r1.rolling(20, min_periods=12).std()
    win = (idx >= pd.Timestamp(s0)) & (idx <= pd.Timestamp(e0))
    qv = v20[win].quantile([1 / 3, 2 / 3]).to_numpy()
    T["regime_vol"] = pd.cut(v20, [-np.inf, *qv, np.inf],
                             labels=["저변동", "중변동", "고변동"])
    z20 = (np.log(px_f) - np.log(px_f).shift(20)) / (v20 * np.sqrt(20))
    qz = z20[win].quantile([1 / 3, 2 / 3]).to_numpy()
    T["regime_trend"] = pd.cut(z20, [-np.inf, *qz, np.inf],
                               labels=["하락추세", "횡보", "상승추세"])

    T.index.name = "date"
    T.to_parquet(DATA / "target_panel.parquet")

    # ── 진단 ────────────────────────────────────────────────────────
    s, e = WINDOW_JOINT
    j = T[(T.index >= pd.Timestamp(s)) & (T.index <= pd.Timestamp(e))]
    j = j[j.index.dayofweek < 5]
    print(f"\n결합창 평일 {len(j)}일\n")
    rows = []
    spec = [
        ("hhf_T1_persist", "T1 방향 지속성 (근월)", "연속"),
        ("hhf_T1_persist_bin", "   같은 방향 비율", "이진"),
        ("hhf_T2_ret1", "T2 익일 수익률", "연속"),
        ("hhf_T3_intensity", "T3 강도 변화", "연속"),
        ("hhf_T4_volchg", "T4 변동성 변화", "연속"),
        ("hhf_T5_break", "T5 체제 이탈 (1.25σ)", "이진"),
        ("hhf_T5_breakz", "   이동 크기 |z|", "연속"),
        ("T6_stor_next", "T6 차기 저장 변화(Bcf)", "연속"),
        ("hhf_T7_tail", "T7 꼬리 (상위 5%)", "이진"),
        ("hh_T1_persist", "  [현물] T1", "연속"),
        ("hh_T7_tail", "  [현물] T7", "이진"),
        ("wb_T1_persist", "W1 베이시스 지속성", "연속"),
        ("wb_T1_persist_bin", "   같은 방향 비율", "이진"),
        ("wb_T2_chg1", "W2 베이시스 익일변화", "연속"),
        ("wb_T5_blowout", "W3 베이시스 붕괴", "이진"),
    ]
    for c, nm, kind in spec:
        v = j[c].dropna()
        if kind == "이진":
            print(f"{nm:26} n={len(v):4d}  발생률 {v.mean():5.1%}")
            rows.append({"target": c, "n": len(v), "rate": round(float(v.mean()), 4)})
        else:
            ac = v.autocorr(1) if len(v) > 10 else np.nan
            print(f"{nm:26} n={len(v):4d}  평균 {v.mean():+8.4f}  sd {v.std():7.4f}"
                  f"  자기상관 {ac:+.2f}")
            rows.append({"target": c, "n": len(v), "mean": round(float(v.mean()), 5),
                         "sd": round(float(v.std()), 5), "ac1": round(float(ac), 3)})

    print("\n── 국면 분할 (t 시점 관측 가능) ──")
    print("  변동성:", j.regime_vol.value_counts().reindex(["저변동","중변동","고변동"]).to_dict())
    print("  추세  :", j.regime_trend.value_counts().reindex(["하락추세","횡보","상승추세"]).to_dict())

    print("\n── T1 방향 지속성: 국면별 같은 방향 비율 (동전 = 50%) ──")
    jv = j[j.hhf_T1_valid == 1]
    print(f"  (과거 5일 움직임이 중앙값 이상인 날만 · n={len(jv)})")
    for rc in ("regime_vol", "regime_trend"):
        g = jv.groupby(rc, observed=True)["hhf_T1_persist_bin"].agg(["mean", "count"])
        print(f"  [{rc}]  " + "  ".join(
            f"{k}: {v['mean']:.0%}(n={int(v['count'])})" for k, v in g.iterrows()))

    (DATA / "target_summary.json").write_text(
        json.dumps({"window": [str(s), str(e)], "n_days": len(j), "targets": rows},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n저장: target_panel.parquet ({T.shape[0]:,}×{T.shape[1]}) · target_summary.json")


if __name__ == "__main__":
    main()
