"""D5-a — 분석 모집단 정의 + 소스 편향 제거.

2026-08-03 합의된 원칙:

  1) 같은 벡터 DB 라도 용도가 다르면 모집단이 다르다.
     LIORA(사내 검색)에는 계약서·이사회 자료가 핵심 자산이지만,
     scen 의 Semantic Factor 는 "시장이 무슨 얘기를 하는가"의 통계이므로
     **시장 외 문서를 모집단에서 제외**한다. 품질 판단이 아니라 용도 구분.

  2) 제외는 질의(유사도 검색)가 아니라 **규칙**으로 한다.
     결과(가격)를 보고 고르면 선택 편향이다. 문서 성격만 본다.

  3) AI 생성물(LIORA 산출 분석·대화 기억)은 무조건 제외 — 순환 방지 (02 §10).

  4) 남은 시장 문서에 **(소스 × 언어) 셀 내 중심화** → 문체·형식·언어 편향 제거.
     소스만으로 중심화하면 `article` 안의 국문/영문 차이가 남는다. 전체 eta² 로는
     0.7% 라 작아 보이지만, 국문 코멘터리가 몰린 덩어리 안에서는 국소적으로
     제1축을 차지한다 (2026-08-03 측정: [6] 선물시장 PC1 = 언어).

  5) 문서 가중 w = 1/(그 문서의 청크 수) 를 함께 저장한다.
     STEO 전문은 문서당 33청크라 청크 기준으로는 코퍼스의 17.6% 를 차지하고,
     가중 없이 PCA 를 돌리면 축이 시장 의미가 아니라 **STEO 발행연도**로 간다.
     제외하지 않고 가중으로 눌러 189개 문서 = 1.5% 몫만 갖게 한다.

출력:
  data/market_meta.parquet   시장 모집단 청크 메타 (+doc_class, lang, w)
  data/emb_centered.npy      중심화·정규화된 임베딩 (float16, market 순서 동일)
  data/prep_summary.json     분류 집계·eta² 전후
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import CORPUS_DATE_MAX, CORPUS_DATE_MIN, DATA  # noqa: E402

# ── 분류 규칙 (문서 성격 기준 — 제목 반복 횟수 아님) ────────────────
AI_GENERATED = {
    "gas_market_analysis", "lng_market_analysis", "gas_commentary",
    "conversation_memory",
}
# s3_markdown 은 사내 S3 업로드 코퍼스(ai-corpus/) 자체다.
# 제목 키워드로 갈라 보았으나 "market" 판정 잔여분도 전부 사내 보고서·보드 자료였다
# (2026-08-03 검증). 소스 단위로 일괄 internal 처리한다.
INTERNAL_SOURCES = {"background_context", "s3_markdown"}
MARKET_SOURCES = {
    "article", "public_report", "steo_outlook", "tariff_filing",
    "weather_discussion", "ferc_docket",
}


def classify(row: pd.Series) -> str:
    st = row.source_type
    if st in AI_GENERATED:
        return "ai_generated"
    if st in INTERNAL_SOURCES:
        return "internal"
    if st in MARKET_SOURCES:
        return "market"
    return "other"


def hangul_share(s: str) -> float:
    s = str(s)
    if not s:
        return 0.0
    h = sum(1 for ch in s if "가" <= ch <= "힣")
    return h / max(1, len(s.replace(" ", "")))


def eta2(X: np.ndarray, labels: pd.Series) -> float:
    """전체 분산 중 그룹 평균이 설명하는 몫 (전 차원 합산)."""
    mu = X.mean(axis=0)
    ss_tot = float(((X - mu) ** 2).sum())
    ss_betw = 0.0
    for _, idx in labels.groupby(labels).groups.items():
        g = X[labels.index.get_indexer(idx)]
        ss_betw += len(g) * float(((g.mean(axis=0) - mu) ** 2).sum())
    return ss_betw / ss_tot


def main() -> None:
    info = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    meta = pd.read_parquet(DATA / info["meta"])
    meta["date"] = pd.to_datetime(meta["date"])
    emb = np.load(DATA / info["emb"])
    assert len(meta) == len(emb)
    print(f"스냅샷 {len(meta):,} 청크")

    # 날짜 위생 (published_at 이상치 방어)
    ok = (meta.date >= pd.Timestamp(CORPUS_DATE_MIN)) & (
        meta.date <= pd.Timestamp(CORPUS_DATE_MAX)
    )
    print(f"날짜 이상치 제외: {(~ok).sum():,}")
    meta, emb = meta[ok].reset_index(drop=True), emb[ok.values]

    # ── 1. 문서 성격 분류 (문서 단위로 판정 → 청크에 전파) ──────────
    doc = meta.groupby("document_id").first()[["source_type", "title"]].reset_index()
    doc["doc_class"] = doc.apply(classify, axis=1)
    meta = meta.merge(doc[["document_id", "doc_class"]], on="document_id", how="left")

    print("\n── 분류 결과 (청크 기준) ──")
    tab = meta.groupby(["doc_class", "source_type"]).size().unstack(fill_value=0)
    print(tab.T.to_string())
    print("\n청크:", meta.doc_class.value_counts().to_dict())
    print("문서:", doc.doc_class.value_counts().to_dict())

    # ── 2. 시장 모집단 확정 ─────────────────────────────────────────
    mkt = meta.doc_class == "market"
    m_meta = meta[mkt].reset_index(drop=True)
    X = emb[mkt.values].astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    m_meta["lang"] = np.where(m_meta.title.map(hangul_share) > 0.15, "ko", "en")
    m_meta["cell"] = m_meta.source_type + "|" + m_meta.lang
    # 문서 가중 — 문서당 총 1표
    m_meta["w"] = 1.0 / m_meta.groupby("document_id")["chunk_id"].transform("count")
    print(f"\n시장 모집단: {len(m_meta):,} 청크 / {m_meta.document_id.nunique():,} 문서")
    print("언어:", m_meta.lang.value_counts().to_dict())

    print("\n── 청크 몫 vs 문서 몫 (가중이 필요한 이유) ──")
    sh = pd.DataFrame({
        "청크%": m_meta.source_type.value_counts(normalize=True) * 100,
        "문서%": m_meta.groupby("source_type").w.sum() / m_meta.w.sum() * 100,
    }).sort_values("청크%", ascending=False).round(1)
    print(sh.to_string())

    # ── 3. eta² 전후 측정 ───────────────────────────────────────────
    yr = m_meta.date.dt.year.astype(str)
    before = {
        "source": eta2(X, m_meta.source_type),
        "lang": eta2(X, m_meta.lang),
        "year": eta2(X, yr),
    }
    # (소스 × 언어) 셀 내 중심화. 셀이 너무 작으면 소스 단위로 후퇴.
    MIN_CELL = 30
    Xc = X.copy()
    small = 0
    for cell, idx in m_meta.groupby("cell").groups.items():
        ii = m_meta.index.get_indexer(idx)
        if len(ii) < MIN_CELL:
            small += len(ii)
            continue
        Xc[ii] -= Xc[ii].mean(axis=0)
    for st, idx in m_meta[m_meta.groupby("cell").cell.transform("size") < MIN_CELL].groupby(
        "source_type"
    ).groups.items():
        ii = m_meta.index.get_indexer(idx)
        Xc[ii] -= Xc[ii].mean(axis=0)
    if small:
        print(f"\n작은 셀 {small:,} 청크는 소스 단위로 중심화")
    Xc /= np.linalg.norm(Xc, axis=1, keepdims=True) + 1e-9
    after = {
        "source": eta2(Xc, m_meta.source_type),
        "lang": eta2(Xc, m_meta.lang),
        "year": eta2(Xc, yr),
    }
    print("\n── eta² (전 차원 합산) ──")
    print(f"{'':8} {'중심화 전':>10} {'후':>8}")
    for k in before:
        print(f"{k:8} {before[k]:>9.1%} {after[k]:>8.1%}")

    # ── 4. 저장 ─────────────────────────────────────────────────────
    m_meta.to_parquet(DATA / "market_meta.parquet", index=False)
    np.save(DATA / "emb_centered.npy", Xc.astype(np.float16))
    (DATA / "prep_summary.json").write_text(
        json.dumps(
            {
                "chunks_by_class": meta.doc_class.value_counts().to_dict(),
                "docs_by_class": doc.doc_class.value_counts().to_dict(),
                "market_chunks": int(len(m_meta)),
                "market_docs": int(m_meta.document_id.nunique()),
                "lang": m_meta.lang.value_counts().to_dict(),
                "eta2_before": before,
                "eta2_after": after,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("\n저장: market_meta.parquet · emb_centered.npy · prep_summary.json")


if __name__ == "__main__":
    main()
