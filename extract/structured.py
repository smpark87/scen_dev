"""D7 — 정형 변수 일별 패널 추출.

의미 패널(semantic_panel.parquet) 옆에 나란히 설 열들을 만든다.
날짜는 변수가 아니라 정합 키다 — 여기서 만든 열과 의미 열이 같은 날짜로 붙는다.

원칙 (03 §5.1, §5.2.1):
  · **수준이 아니라 스프레드와 서프라이즈에 정보가 있다.**
    Waha−HH 베이시스, 저장량의 5년평균 대비 편차 등.
  · 발표 주기가 다른 계열을 섞는다. 저장량은 주간(목 발표), 리그는 주간(금),
    생산·수요·feedgas 는 일간. **as-of 를 적용하지 않는 데모**이므로 여기서는
    단순 forward-fill 하되, 어떤 열이 저빈도인지 명시한다 (05_freq).
  · 공선성은 대상에 따라 달라지므로(03 §5.1.2) 여기서는 **자르지 않는다**.
    선택은 D9 회귀 단계에서 대상별로 한다.

출력:
  data/structured_panel.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from config import DATA  # noqa: E402

# market_indicators 에서 그대로 가져올 계열 (일간 또는 주간)
IND_DAILY = {
    "gas_production": "prod",
    "gas_demand": "demand",
    "lng_feedgas": "feedgas",
    "power_burn": "powerburn",
    "res_comm": "rescomm",
    "industrial": "indust",
    "gas_prod_appalachia": "prod_appalachia",
    "gas_prod_haynesville": "prod_haynesville",
    "gas_prod_permian": "prod_permian",
    "ercot_demand_peak": "ercot_peak",
    "ercot_gas_burn": "ercot_gasburn",
    "ercot_gen_wind": "ercot_wind",
    "ercot_gen_solar": "ercot_solar",
    "eur_usd": "eurusd",
}
IND_WEEKLY = {
    "gas_storage": "stor",
    "gas_storage_east": "stor_east",
    "gas_storage_midwest": "stor_midwest",
    "gas_storage_south_central": "stor_sc",
    "gas_storage_south_central_salt": "stor_sc_salt",
    "gas_rigs": "rigs_gas",
    "oil_rigs": "rigs_oil",
    "rig_haynesville": "rigs_haynesville",
    "rig_marcellus": "rigs_marcellus",
    "rig_permian": "rigs_permian",
    "crude_stocks": "crude_stocks",
    "crude_production": "crude_prod",
}
HUBS = {12: "hh", 67: "waha"}          # Henry Hub, Waha
OIL = {1: "brent", 2: "wti"}


def main() -> None:
    info = db.healthcheck()
    print(f"DB: {info['user']} (read_only={info['read_only']})")

    names = list(IND_DAILY) + list(IND_WEEKLY)
    ind = db.query(
        "SELECT metric, period, value FROM market_indicators "
        "WHERE metric = ANY(%s) AND period >= '2014-01-01' ORDER BY period",
        (names,),
    )
    ind = ind.pivot_table(index="period", columns="metric", values="value", aggfunc="last")
    ind.index = pd.to_datetime(ind.index)
    ind = ind.rename(columns={**IND_DAILY, **IND_WEEKLY})
    print(f"market_indicators: {ind.shape[0]:,}일 × {ind.shape[1]}계열")

    gd = db.query(
        "SELECT hub_id, price_date, price FROM gas_daily_prices "
        "WHERE hub_id = ANY(%s) ORDER BY price_date",
        (list(HUBS),),
    )
    gd = gd.pivot_table(index="price_date", columns="hub_id", values="price", aggfunc="last")
    gd.index = pd.to_datetime(gd.index)
    gd = gd.rename(columns=HUBS)
    print(f"gas_daily_prices: {gd.shape[0]:,}일 · {gd.index.min():%Y-%m-%d}~")

    op = db.query(
        "SELECT contract_id, trade_date, settlement_price FROM oil_prices "
        "WHERE contract_id = ANY(%s) AND delivery_strip IS NOT NULL ORDER BY trade_date",
        (list(OIL),),
    )
    op = op.pivot_table(index="trade_date", columns="contract_id",
                        values="settlement_price", aggfunc="first")
    op.index = pd.to_datetime(op.index)
    op = op.rename(columns=OIL)
    print(f"oil_prices: {op.shape[0]:,}일")

    # ── 일별 격자에 정렬 ────────────────────────────────────────────
    idx = pd.date_range("2015-01-01", "2026-08-03", freq="D")
    P = pd.concat([ind, gd, op], axis=1).reindex(idx)
    # 저빈도 계열은 발표 후 유지 (as-of 미적용 데모 — 08 §2 표기 대상)
    low = list(IND_WEEKLY.values())
    P[low] = P[low].ffill(limit=14)
    P[list(IND_DAILY.values())] = P[list(IND_DAILY.values())].ffill(limit=5)
    P[["hh", "waha", "brent", "wti"]] = P[["hh", "waha", "brent", "wti"]].ffill(limit=10)
    # ⚠️ oil_prices 는 **2026-01-28 ~ 2026-06-01 (124일) 수집 공백**이 있다.
    #    ICE 휴장이 아니라 ngip 수집 중단으로 보인다. 메우지 않고 결측으로 둔다 —
    #    ffill 로 4개월을 채우면 유가가 4개월간 고정된 가짜 계열이 된다.
    #    (ngip 운영 이슈로 별도 보고. 데모에서는 유가 관련 열의 결측률로 노출된다.)

    # ── 파생: 스프레드·서프라이즈·변화율 (03 §5.2.1) ─────────────────
    out = P.copy()
    # (P.prod 는 DataFrame.prod 메서드와 충돌한다 — 대괄호 접근으로 통일)
    out["basis_waha_hh"] = P["waha"] - P["hh"]               # 지역 병목
    out["spread_hh_brent"] = P["hh"] - P["brent"] / 17.2     # 유가 대비 가스 (열량 환산)
    out["balance"] = P["prod"] - P["demand"]                 # 순수급
    out["feedgas_share"] = P["feedgas"] / P["prod"]

    doy = out.index.dayofyear
    for c in ("stor", "stor_east", "stor_sc", "prod", "demand", "feedgas"):
        # 5년 계절 평균 대비 편차 — 수준이 아니라 "예년 대비"
        base = out[c].groupby(doy).transform(lambda s: s.rolling(5, min_periods=2).mean().shift(1))
        out[f"{c}_vs5y"] = out[c] - base
    out["stor_chg"] = out["stor"].diff()                     # 주간 순변화(주입/인출)

    # Waha 는 2023~ 퍼미안 공급과잉으로 **음수 결제**가 잦다 (결합창 평일 935일 중 294일,
    # 최저 −9.5). 로그수익률이 정의되지 않으므로 산술차분을 쓴다.
    # 이것은 데이터 결함이 아니라 실제 시장 현상이라 제거하면 안 된다.
    for c in ("hh", "brent", "wti"):
        out[f"{c}_ret1"] = np.log(out[c]).diff()
        out[f"{c}_ret5"] = np.log(out[c]).diff(5)
        out[f"{c}_vol20"] = out[f"{c}_ret1"].rolling(20, min_periods=10).std()
    out["waha_chg1"] = out["waha"].diff()
    out["waha_chg5"] = out["waha"].diff(5)
    out["waha_vol20"] = out["waha_chg1"].rolling(20, min_periods=10).std()
    for c in ("prod", "demand", "feedgas", "powerburn"):
        out[f"{c}_chg7"] = out[c] - out[c].shift(7)

    # 계절성 (달력은 변수가 아니라 키지만, 계절 자체는 정형 설명변수다)
    out["sin_doy"] = np.sin(2 * np.pi * doy / 365.25)
    out["cos_doy"] = np.cos(2 * np.pi * doy / 365.25)

    out.index.name = "date"
    out.to_parquet(DATA / "structured_panel.parquet")
    print(f"\n정형 패널: {out.shape[0]:,}일 × {out.shape[1]}열")

    j = out[(out.index >= "2023-01-01") & (out.index <= "2026-07-31")]
    j = j[j.index.dayofweek < 5]
    cov = j.notna().mean().sort_values()
    print(f"\n결합창 평일 {len(j)}일 · 결측 많은 열 (하위 8):")
    for c, v in cov.head(8).items():
        print(f"  {c:22} {v:5.0%}")
    print(f"결측 없는 열 {int((cov > 0.99).sum())}/{len(cov)}")


if __name__ == "__main__":
    main()
