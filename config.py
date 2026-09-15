"""scen_dev 공통 설정.

경로·분석창·상수만 둔다. DB 접속은 db.py, 자격증명은 .env.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"          # 중간 산출 (parquet) — git 미추적
FIGS = ROOT / "figures"       # 그림
OUT = ROOT / "out"            # 최종 HTML
for _d in (DATA, FIGS, OUT):
    _d.mkdir(exist_ok=True)


# ── 분석창 (07-demo-plan §0.3, 2026-08-03 확정) ───────────────────
#
# 결합 분석은 2023-01~ 만 한다.
#   article 소스가 2023년부터만 존재해 그 이전은 평일당 문서 1.8건뿐이다.
#   무료 EIA 소스(STEO·NG Weekly·Today in Energy)를 실제로 열어 확인한 결과
#   밀도를 메울 수 없었다 — STEO 는 이미 완비(백필 불필요), NG Weekly 는
#   우리가 이미 보유한 정형 숫자의 서술이고 2026-01 발행 중단.
#
# 정형·Regime 은 더 길게 본다. 기간 근거가 "국면 수"(03 §2)여서 텍스트와 무관하다.
#   하한은 gas_daily_prices 시작일(2020-01).
#
# 남는 한계는 밀도가 아니라 **국면 다양성**이다 — 2023~2026 은 저가·공급과잉
# 국면 위주라 위기 국면(2021 Uri, 2022 우크라이나)의 의미 관계는 학습할 수 없다.
# 이것이 상용 뉴스 아카이브 조달의 실제 근거다.
WINDOW_JOINT = (date(2023, 1, 1), date(2026, 7, 31))    # 정형 + 의미 결합
WINDOW_STRUCT = (date(2020, 1, 1), date(2026, 7, 31))   # 정형·Regime 단독

# 하위호환 별칭 (기존 스크립트용)
WINDOW_MAIN = WINDOW_JOINT
WINDOW_STABLE = WINDOW_JOINT

# 거래일만 사용한다. 주말은 문서도 가격도 없어 결측이 아니라 비영업일이다.
#   (진단: 전체 0건인 날 29.2% → 평일만 보면 4.8%)
BUSINESS_DAYS_ONLY = True

# published_at 이상치 방어 — 이 밖은 코퍼스 오염으로 보고 배제.
# (s3_markdown 에 2056년 등이 존재)
CORPUS_DATE_MIN = date(1995, 1, 1)
CORPUS_DATE_MAX = date(2026, 12, 31)

EMBED_DIM = 1536
EMBED_MODEL = "text-embedding-3-small"

# 데모 산출물 전역 표기 — 06-demo.md §2
DISCLAIMER = "설명용 · 예측력 검증 아님 · as-of 미적용"


def env(key: str, default: str | None = None) -> str:
    """.env → 환경변수 순으로 조회. 값은 절대 로그에 남기지 않는다."""
    if not hasattr(env, "_cache"):
        cache: dict[str, str] = {}
        dotenv = ROOT / ".env"
        if dotenv.exists():
            for line in dotenv.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cache[k.strip()] = v.strip().strip('"').strip("'")
        env._cache = cache  # type: ignore[attr-defined]
    val = env._cache.get(key) or os.environ.get(key) or default  # type: ignore[attr-defined]
    if val is None:
        raise KeyError(f"{key} 없음 — scen_dev/.env 확인")
    return val
