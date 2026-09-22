---
title: OUTLOOK 공개 데이터 수집 작업
document_date: 2026-09-22
status: GDP 중앙 적재 완료, 금리·JODI-Gas job 공식 원천 dry-run 완료(배포 대기)
---

# OUTLOOK 공개 데이터 수집 작업

**수집·검증·적재·스케줄은 NGIP, 조회·분석·전망은 OUTLOOK이 담당한다.**
DB는 기존 NGIP 중앙 DB 하나를 사용한다. scen_dev는 `db.py`의 읽기 전용 계정과
세션을 유지한다. 공개 데이터이며 반복 실행 가능한 공식 API·파일부터 연결한다.

## 1. World Bank GDP

운영 코드와 배포 정의는 NGIP 저장소의 `jobs/ingest_worldbank_gdp.py`,
`core/worldbank_gdp.py`, `infra/cloudformation/jobs.yaml`에 있다.
NGIP 운영 설명은 해당 저장소의 `docs/WORLDBANK_GDP.md`를 따른다.
scen_dev의 `extract/worldbank_gdp.py`는 **DB 조회 어댑터**이며 수집 job이 아니다.

| 계열 | World Bank WDI 코드 | 단위 |
|---|---|---|
| 실질 GDP | NY.GDP.MKTP.KD | 2015년 기준 US$ |
| 명목 GDP | NY.GDP.MKTP.CD | 당해 US$ |
| GDP 성장률 | NY.GDP.MKTP.KD.ZG | 연간 % |

### OUTLOOK에서 읽기

```python
from extract.worldbank_gdp import load_gdp

gdp = load_gdp(economies=["KOR", "CHN", "JPN", "USA", "EMU", "WLD"],
               metrics=["gdp_real", "gdp_growth"], start=1995)
```

연도·단위·국가 코드·국가/집계 구분·원천 결측 상태·출처·수집시점을 함께 반환한다.
`python -m extract.worldbank_gdp`는 읽기 전용 연결과 중앙 DB의 GDP 건수를 확인한다.
NGIP가 아직 적재하지 않았다면 빈 결과다. 원천 API나 로컬 파일로 자동 우회하지 않는다.

### 데이터 계약

- 중앙 표는 `market_indicators`, 지표 키는 `wb_gdp_{real|nominal|growth}_{c|a}_{경제코드}`다.
  `c`는 국가, `a`는 지역·소득 집계다. 예: `wb_gdp_real_c_KOR`, `wb_gdp_real_a_EMU`.
- 연간 관측의 `period`는 해당 연도 1월 1일이다. 발표일로 해석하지 않는다.
- `value IS NULL`은 원천 결측이다. 0과 음수 성장률은 정상 값이다.
- `source`는 World Bank WDI와 데이터셋 갱신일, `fetched_at`은 수집 시작시점(UTC)이다.
  원본·공식 국가 메타데이터·요청 URL·SHA256·정규화 파일은 NGIP S3에 실행별 보존한다.
- 검증과 원본 업로드가 모두 성공해야 요청 기간의 GDP 지표만 한 트랜잭션으로 교체한다.
  실패 시 기존 DB 값은 유지되고, 늦게 완료된 옛 수집본이 최신 값을 덮어쓰지 못한다.
- 매회 전체 요청 기간을 다시 수집하여 과거 수치 개정을 반영한다.
- 국가와 집계를 함께 합산하지 않는다. EAS는 한·중·일 합계가 아니다.
  한·중·일 합계는 세 나라의 같은 연도·단위 값이 모두 있을 때 계산하고 성장률은 합산하지 않는다.
- GDP 원값은 US$다. 엑셀의 billion US$와 비교하려면 10억으로 나눈다.
- WDI는 최신 개정 계열이며 과거 최초 발표본이 아니다. `source_updated_on`도
  개별 관측치의 최초 발표일이 아니다. 이 job은 미래 전망을 제공하지 않는다.

### 운영 상태 (2026-09-21)

- NGIP `ngip-jobs` 스택에 GDP 전용 작업·실행 역할·주간 스케줄·실패 알림을 배포했다.
  기존 공통 job 이미지와 리소스를 수정하지 않고 GDP 전용 리소스를 추가했다.
- 스케줄은 매주 월요일 13:00 UTC이며 ENABLED 상태다.
- ECS 수동 실행은 AWS `RunTask`의 `ServerException: Internal Error`로 작업 생성 전에 실패했다.
  **스케줄 등록 완료와 서버 실행 성공을 구분한다.** ECS 실제 실행 검증은 남아 있다.
- 같은 NGIP job을 현재 개발 환경에서 실행해 S3 원본 보존과 중앙 DB 최초 적재를 완료했다.
  scen_dev의 수집기로 우회한 것이 아니며 이후 조회는 중앙 DB만 사용한다.
- `scen_ro` 계정의 읽기 전용 세션에서 24,645행·유효 23,470개·결측 1,175개를 대조했다.
  핵심 6개 경제권의 실질 GDP 31년, 필터·국가/집계 구분도 확인했다.

### 검증 기록과 기존 로컬 파일

2026-09-21 API 및 배포 이미지의 쓰기 없는 실수집에서 265개 국가·지역,
1995~2025년 24,645행(유효 23,470·결측 1,175), WDI 갱신일 2026-07-13을 확인했다.
NGIP 수집·트랜잭션·업로드 실패·동시 실행 검사는 14개, OUTLOOK 조회 검사는 2개 통과했다.

초기 검증에서 만든 `data/open/worldbank_gdp/` 파일은 기존 실험 기록으로만 남는다.
운영 조회나 정기 갱신에서 사용하지 않는다. DB와 로컬 파일을 병행 관리하지 않는다.

공식 근거:

- [World Bank API 쿼리·페이지 처리](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures)
- [실질 GDP 정의 및 CC BY 4.0](https://data.worldbank.org/indicator/NY.GDP.MKTP.KD)
- [명목 GDP](https://data.worldbank.org/indicator/NY.GDP.MKTP.CD)
- [GDP 성장률](https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG)

## 2. Federal Reserve 금리

기존 WTI 엑셀 `Macro!B50:B178`의 `US Policy rate` 129개 값(2014-01~2024-09)을
FRED `FEDFUNDS`와 전부 대조했다. 이름과 달리 FOMC 목표금리가 아니라 월평균 EFFR이다.
OUTLOOK은 원 모델 재현 계열과 정책 해석 계열을 다음처럼 분리한다.

| metric | 원천 | 의미 |
|---|---|---|
| `us_effr_monthly_avg` | `FEDFUNDS` | 엑셀과 같은 월평균 EFFR |
| `us_effr_daily` | `DFF` | 일별 EFFR |
| `us_fed_target_lower` | `DFEDTARL` | 2008-12-16 이후 목표범위 하단 |
| `us_fed_target_upper` | `DFEDTARU` | 2008-12-16 이후 목표범위 상단 |
| `us_fed_target_mid` | `DFEDTAR`, 이후 상·하단 평균 | 장기 연속 정책금리 대표값 |

모든 값은 `percent_pa`이며 `5.33`은 `5.33%`다. `us_fed_target_mid`는
2008-12-15까지 단일 목표값, 다음 날부터 목표범위 중간값이다.

NGIP의 `jobs/ingest_fed_rates.py`가 공개 FRED CSV 전체 이력을 검증하고 원본·해시를
S3에 보존한 뒤 다섯 metric만 원자적으로 교체하도록 구현했다. EventBridge 정의는 평일
15:00 UTC다. 공식 원천 dry-run에서 1954-07-01~2026-09-21, 56,288행, 다섯 metric의
검증을 통과했고 S3·DB 쓰기는 0건이었다. 단위·기간·중복·최신성·상하단 정합성 및
업로드/DB 실패 원자성을 자동 검사한다.

scen_dev의 `extract/fed_rates.py`는 중앙 DB만 읽는다.

```python
from datetime import date
from extract.fed_rates import load_excel_policy_rate, load_fed_rates

excel_input = load_excel_policy_rate(start=date(2014, 1, 1))
policy = load_fed_rates(metrics=["us_fed_target_lower", "us_fed_target_upper",
                                 "us_fed_target_mid"])
```

금리 job의 배포, 스케줄 활성화, 중앙 DB 최초 적재는 사용자 지시에 따라 수행하지 않았다.
승인 전까지 DB 조회는 빈 결과를 반환하며 FRED나 로컬 파일로 자동 우회하지 않는다.

공식 근거:

- [FRED FEDFUNDS](https://fred.stlouisfed.org/series/FEDFUNDS)
- [FRED DFF](https://fred.stlouisfed.org/series/DFF)
- [FRED 목표금리 하단](https://fred.stlouisfed.org/series/DFEDTARL)
- [FRED 목표금리 상단](https://fred.stlouisfed.org/series/DFEDTARU)
- [New York Fed EFFR 설명](https://www.newyorkfed.org/markets/reference-rates/effr)

## 3. JODI-Gas 국가별 월간 수급

JODI-Gas 무료 공개 CSV를 NGIP job으로 연결했다. publisher API에서 매번 현재
publication id와 활성 ZIP 이름을 확인하므로 URL의 숫자나 파일명을 고정하지 않는다.

공식 전체 파일 dry-run 결과는 다음과 같다.

- publication 27, 94개국, 315,758행
- 2009-01~2026-07
- 국가·flow·unit 조합 2,044계열
- `(국가, 월, flow, unit)` 중복 0건, 빈 값 행 0건
- 품질등급 1·2·3을 원천 그대로 보존

제공 flow는 생산, 총/LNG/파이프라인 수출입, 재고 증감·월말 재고, 관측/계산 수요,
발전·열 수요다. M3·TJ와 LNG KTONS를 각각 저장하며 0을 결측으로 바꾸지 않는다.
국가가 보고하지 않은 관측은 행 자체가 없으므로 지역 합계에서 임의로 0으로 채우지 않는다.

NGIP는 원본 ZIP·publisher 응답·정규화 자료·coverage·해시를 S3에 보존한 뒤
`jodi_gas_{m3|tj|kt}_{flow}_{ISO2}` metric만 중앙 DB에서 원자 교체하도록 구현했다.
315,758행을 메모리에 한꺼번에 올리지 않고 CSV 생성과 DB INSERT를 스트리밍한다.
평일 데이터가 아니라 월간 공개이므로 스케줄 정의는 매주 월요일 14:30 UTC다.

OUTLOOK은 `extract/jodi_gas.py`로 중앙 DB만 읽는다.

```python
from datetime import date
from extract.jodi_gas import load_jodi_gas

asia_lng = load_jodi_gas(
    countries=["CN", "JP", "KR", "TW"], flows=["IMPLNG"],
    units=["million_m3"], assessments=[1, 2], start=date(2010, 1, 1))
```

JODI의 국가 수출입은 양자 교역이 아니며 설비용량·전망도 아니다. `TOTDEMO` 관측 수요와
`TOTDEMC` 계산 수요를 구분하고, 품질등급 2·3 및 국가별 누락월을 모델 입력에서 명시한다.

배포·스케줄 활성화·운영 S3/DB 최초 적재는 사용자 지시에 따라 수행하지 않았다.

공식 근거:

- [JODI-Gas 다운로드](https://www.jodidata.org/gas/database/data-downloads.aspx)
- [JODI-Gas flow·단위 정의](https://www.jodidata.org/gas/support/user-guide/data-available-in-the-jodi-gas-world-database.aspx)
- [JODI-Gas 이용·인용 안내](https://www.jodidata.org/gas/support/user-guide.aspx)

## 4. 다음 공개 데이터 후보

| 순서 | 공백 | 후보·선결 확인 | 상태 |
|---|---|---|---|
| 4 | 유럽 Regas capacity·운영 지표 | GIE 설비 파일과 ALSI. 키 필요 여부·파일 이력·설비와 흐름의 정의 확인 | job 미구현 |

위 순서는 쉬운 자동 수집부터 진행하기 위한 제안이다. GIE의 키 발급 절차 등이 필요하면
무인 수집 가능한 다른 항목부터 진행한다. 원본 다운로드와 검증을 실제 실행하기 전에는
공백이 해소됐다고 표시하지 않는다.
