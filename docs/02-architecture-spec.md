---
title: scen_dev 아키텍처 설계
subtitle: 헌장 §8 + 모델 정의(01)를 전제로 한 시스템 구조
document_date: 2026-07-30
status: v0.2 draft — 01 v2.0(Regime/Scenario 분리·연결 단위 심사) 반영
source: internal
category: architecture
tags: [architecture, contract tables, as-of, jobs, LIORA]
---

# scen_dev 아키텍처 설계

> 전제: 헌장(`00`) §8의 원칙 — 별도 개발, 계약 테이블 접합, ngip_dev 무수정,
> `as_of` 강제 — 과 모델 정의(`01`)의 상태공간·bitemporal 구조.
> 이 문서는 계속 변경될 수 있으나, **헌장과 충돌하는 방향으로는 변경하지 않는다.**
> **2026-09-25 로컬 환경 정정:** 아래 도식의 "별도 venv"는 운영 배포 경계를 가리킨다. 로컬 개발은 `../shared/.venv`를 사용하며 설치·검증 절차는 `SETUP.md`를 따른다.

---

## 1. 전체 구성

```
═══ scen_dev (별도 repo · venv · 이미지) ═══════════════════════════════

[수집]  소스별 인제스터 (일/주/월/불규칙)
            ↓
[저장]  scen_raw · scen_series · scen_curve · scen_forecast
        scen_docs · scen_event
            ↑ 읽기 전용 (판별 있는 것만)
            └── ngip_dev 기존 테이블
                hub_prices, gas_daily_prices, steo_outlooks,
                weather_discussions, ai_documents …
            ↓
[엔진 — 빠름 / 일별]                     → [산출]
        상태 갱신                            scen_state
        Regime 갱신                          scen_regime
        Transition 평가                      scen_transition
        Signpost 평가                        scen_signpost
        likelihood 갱신                      scen_scenario_state
        전망(Outlook Ⅰ/Ⅱ) · 서사 · 채점      scen_outlook · scen_narrative · scen_score

[엔진 — 느림 / 주·월 + 게이트]           → [산출]
        후보 생성 (candidate만)              scen_scenario
        Domain 심사 게이트                   scen_link · scen_evidence
                                             scen_signpost_def

═══════════════════════════════════════════════════════════════════════
            ↓  산출 계층 = 계약 (같은 RDS) · 읽기 전용
═══ ngip_dev (기존 웹) ═════════════════════════════════════════════════

        LIORA Estimation 워크스페이스 (ins-est: 캔버스 + assistant 레일)
        core/ask.py 신규 툴  ·  routes: /api/scen/* (얇은 read-only)
```

원칙의 재확인 (헌장 §8):
- ngip_dev는 scen_dev 코드를 **import하지 않는다**. 접합면은 테이블이다
- 리서치 의존성(통계·ML)은 scen_dev 이미지에만 들어간다
- 계산은 전부 배치. 요청 경로에서는 저장된 산출만 읽는다
- ngip_dev 운영 코드·필터는 수정하지 않는다. scen_dev용 수집이 필요하면
  별도 프로파일·별도 잡으로 둔다 (예: FERC Notice 포함 프로파일)

## 2. 저장 계층 (입력측)

데이터 명세서 §7의 규약을 그대로 쓴다. 전 테이블 공통: **bitemporal**.

| 테이블군 | 키 구조 | 내용 |
|---|---|---|
| `scen_raw` | (source, fetched_at, blob) | 수집 원본. 불변, 재파싱 가능하게 원형 보존 |
| `scen_series` | (series_id, effective_period, **observed_at**) | 정형 시계열. 개정 = 새 행 (upsert 금지) |
| `scen_curve` | (symbol, trade_date, delivery_strip) | 커브 면. 이미 bitemporal 구조 |
| `scen_forecast` | (source, **issued_at**, target_date, variable) | 예보·전망. 판별 그 자체 |
| `scen_docs` | (doc_id, **published_at**, **ingested_at**) | 텍스트 + **원본 임베딩** + 모델명·버전. 출처·역할 메타데이터 포함 (§5). 변환 좌표는 여기 저장하지 않는다 — §10.4 |
| `scen_event` | (event_id, occurred_at, **first_reported_at**) | 구조화 이벤트 |

- ngip_dev 기존 테이블 중 판별 구조가 있는 것(`hub_prices`, `steo_outlooks`,
  `gas_daily_prices` 등)은 읽기 전용으로 직접 쓴다. 복사하지 않는다
- 판별이 없는 것(`market_indicators`)은 모델 입력으로 쓰지 않는다.
  같은 지표를 `scen_series`에 vintage로 다시 쌓는다 (오늘부터 + 복원 가능분)
- 프록시→공식통계 짝 구조(01 §3.2)는 `scen_series`의 시리즈 메타데이터로 관리

## 3. 산출 계층 = 계약 테이블

**이 스키마가 ngip_dev와의 API다.** 변경은 additive를 원칙으로 하고,
breaking change는 버전 컬럼/뷰로 처리한다. 첫 구현 전에 스키마 리뷰를 거친다.

### 3.0 설계 원칙 두 가지

**① 개념 층마다 테이블을 나눈다.** Regime(현재 구조)·Transition(전환)·Scenario(미래 경로)를
한 테이블에 담으면 확률의 의미가 섞인다 (01 §7.1). 산출 스키마가 개념 분리를 강제한다.

**② 생명주기가 다른 것을 한 테이블에 담지 않는다.** 01 §7.2의 *"채택은 느리게,
갱신은 빠르게"* 가 스키마에 그대로 반영된다:

```
느린 것(정의·채택)   scen_scenario · scen_link · scen_evidence · scen_signpost_def
                     → 검증 게이트를 거쳐 주·월 단위로 변경. 이력 보존
빠른 것(상태·확률)   scen_state · scen_regime · scen_transition
                     scen_scenario_state · scen_signpost · scen_outlook
                     → 일별 append. (as_of_date, run_id) 키
```

### 3.1 상태·구조 계층 (일별)

| 테이블 | 키 구조 초안 |
|---|---|
| `scen_state` | (as_of_date, run_id, component[구조/계절/단기], dim, value, ci) |
| `scen_regime` | (as_of_date, run_id, regime_id, **membership_prob**, stability, status[active/emerging/fading], born_at) |
| `scen_transition` | (as_of_date, run_id, from_regime, to_regime, **horizon**, **transition_prob**) |

- `transition_prob`는 `horizon` 없이 저장 금지 (01 §7.1 — 시계 없는 전환확률은 무의미)
- `scen_regime.status`의 `emerging`은 01 §2.3 순차 진단을 통과 중인 후보 상태

### 3.2 Scenario 계층 — 정의(느림) / 상태(빠름) 분리

| 테이블 | 성격 | 키 구조 초안 |
|---|---|---|
| `scen_scenario` | **느림** | (scenario_id, title, status[candidate/core/wildcard/on_hold/excluded], importance, adopted_at, retired_at, reviewer, review_date) |
| `scen_scenario_state` | **빠름** | (as_of_date, run_id, scenario_id, **likelihood**, likelihood_type[point/range/grade/unscored], **confidence**) |

- 채택·퇴장은 `scen_scenario`에서 게이트를 거쳐 일어나고, 매일의 가능성 변동은
  `scen_scenario_state`에 쌓인다. **게이트를 매일 돌리지 않아도 확률은 매일 살아 있다**
- `likelihood_type`이 `unscored`/`grade`/`range`를 허용한다 — 근거가 부족하면 숫자를
  강제하지 않는다 (01 §7.3). `confidence`는 필수

### 3.3 연결·근거 계층 — 01 §6.3의 구현 **[신규]**

심사 단위가 Scenario가 아니라 연결이므로, 연결이 일급 레코드여야 한다.
**이 두 테이블이 "AI 서사는 증거가 아니다"를 데이터 구조로 강제하는 지점이다.**

| 테이블 | 키 구조 초안 |
|---|---|
| `scen_link` | (link_id, scenario_id, from_node, to_node, **grade**[S1/S2/S3/S4/**A**], serial_position, **inserted_by**[domain/ai/data], inserted_at, insertion_reason, superseded_by) |
| `scen_evidence` | (evidence_id, link_id, **stance**[support/**oppose**], source_ref, provenance, strength, added_at) |

- **`inserted_by`가 핵심이다.** AI가 사슬을 성립시키려 추가한 중간항이 여기서 보인다
  (01 §6.3.3 규칙①). 삽입이 무료가 아니라는 원칙이 컬럼 하나로 집행된다
- `grade = A`(가정)는 금지가 아니라 기록이다. 직렬 A의 개수·위치는 `serial_position`
  으로 계산되어 Scenario 강도에 반영된다 (규칙②③)
- **`stance`에 `oppose`가 없으면 확증편향의 자동화다** (01 §6.4). 지지 근거만 쌓는
  구조를 스키마 수준에서 막는다
- 연결·근거는 이력을 보존한다(`superseded_by`) — 등급이 바뀐 경위를 추적할 수 있어야
  재심이 가능하다

### 3.4 신호 계층

| 테이블 | 성격 | 키 구조 초안 |
|---|---|---|
| `scen_signpost_def` | **느림** | (signpost_id, target_type[scenario/regime/transition], target_id, **condition_expr**, condition_type[level/velocity/persistence/alignment/composite/event], active_from, retired_at) |
| `scen_signpost` | **빠름** | (as_of_date, run_id, signpost_id, value, **contribution**, lead_time_est, **trigger_distance**, direction, alignment_group) |

- Trigger는 단일 cutoff가 아니라 **조건식**이므로 정의를 별도 테이블에 둔다
  (01 §8.3). `condition_type`이 수준·속도·지속·정렬·조합·사건을 포괄
- `alignment_group`은 "여러 약한 신호가 같은 방향으로 정렬" 을 표현한다 — 조합·정렬이
  일급 개념이라는 원칙의 구현
- Signpost는 부상·퇴장하므로 정의에도 `active_from`/`retired_at`이 필요하다

### 3.5 산출·평가 계층

| 테이블 | 키 구조 초안 |
|---|---|
| `scen_outlook` | (as_of_date, run_id, **conditioned_on**[regime_id / scenario_id / 'marginal' / 'mixture'], target, horizon, quantiles, moments) |
| `scen_narrative` | (as_of_date, run_id, **subject_type**[regime/scenario], subject_id, text, evidence_refs, **verification_status**) |
| `scen_score` | (date, metric, target, horizon, value, benchmark_ref) |
| `scen_run` | (run_id, model_version, **embedding_version**, data_boundary, started, ended) |

- `scen_outlook`의 `conditioned_on`이 **Outlook Ⅰ/Ⅱ를 같은 테이블로 수용한다**
  (헌장 §3.2). MVP 단계에서는 `marginal`·`regime_id`로만 채워지고, Scenario 층이
  서면 `scenario_id`·`mixture` 행이 추가된다 — 스키마 변경 없이 확장된다
- **`scen_narrative`는 Scenario의 본체가 아니다.** Regime 또는 Scenario에 종속된 설명
  산출물이며, `evidence_refs`와 `verification_status`가 **필수**다. 근거 참조 없는
  서사는 저장하지 않는다
- `scen_score`에는 두 계열을 함께 담는다: **증분 예측력**(컨센서스·공식전망·단순모델
  대비)과 **절대 calibration**(분포·전환확률의 신뢰도). 상대평가만으로는 불충분하다
- surprise 수준(01 §2.3)은 일급 지표로 상시 공개

### 3.6 공통 규칙

- 모든 산출 행은 `run_id`를 갖는다 — 어느 모델 버전·임베딩 버전·데이터 경계에서 나온
  값인지 항상 추적 가능
- 서사·이벤트 추출에 쓰인 LLM 모델·프롬프트 버전도 `scen_run`에 기록한다 (서사 재현성)

### 3.7 벡터 인덱스 정책 **[원칙]** — 인프라 규모를 좌우하는 결정

> **ANN 인덱스는 필요한 계층에만 건다.** 이 한 줄이 RAM 요구를 수백 GB 바꾼다.

실측 근거 (ngip 운영 DB, 2026-07-31): `ai_document_chunks` 60,636 청크에서
**HNSW 인덱스만 466 MB — 청크당 7.9 KB.** 전체 청크당 20.7 KB의 38%다.

| 계층 | 규모 | ANN 인덱스 | 이유 |
|---|---|---|---|
| **청크 벡터** | 수천만 | **걸지 않는다** | scen의 주 연산은 날짜 구간 집계·순차 스캔이지 최근접 검색이 아니다 |
| **일자 집계 벡터** | 26년 × 365 ≈ 9,500 | **HNSW** | 유사국면 검색("지금이 과거 언제와 닮았나")의 실제 대상 |
| 엔티티 집계 벡터 | 수만 | HNSW | 엔티티 단위 유사 검색 |

3천만 청크에 HNSW를 걸면 인덱스만 **237 GB**다. 일자 집계에만 걸면 **75 MB**다.
**유사국면 검색은 개별 청크가 아니라 시점 단위 질문이므로, 후자로 충분하다.**

부수 규칙:
- 임베딩은 `halfvec`(float16) 저장을 기본으로 한다 — 벡터 크기 절반, 품질 손실 미미.
  단 §10.4(원본 보존)는 유지 — 정밀도 축소는 저장 형식 선택이지 변환이 아니다
- **청크 원문은 S3에 두고 DB에는 벡터·메타데이터만** 둔다. scen의 집계 연산은 원문을
  읽지 않으며, 원문은 추출(1회)과 표시에만 필요하다
- 위 셋을 적용하면 청크당 20.7 KB → **약 7 KB**로 내려간다

## 4. `as_of` 강제 — 구현 위치

원칙(헌장 §8.3): 기본값 없음, 편의 경로 금지. 구현은 **접근 계층 한 곳**에서:

```
scen_dev/core/asof.py   모든 읽기 함수가 이 모듈을 경유
                        read_series(series, as_of)  → observed_at <= as_of 만
                        read_docs(query, as_of)     → published_at <= as_of 만
                        read_curve(symbol, as_of)   → trade_date <= as_of 만
```

- 엔진 코드가 DB에 직접 쿼리하는 것을 금지한다 (코드 리뷰 규칙). 접근 계층을
  거치면 as-of 누락이 구조적으로 불가능해진다
- 라이브 운영은 `as_of = now`인 특수 케이스일 뿐이다. 백테스트와 같은 경로를 탄다
  — 경로가 하나면 누수도 하나만 막으면 된다

## 5. 문서 메타데이터 — 출처·역할 축

헌장 §7.5의 일반형. 특정 실험용 격리 플래그가 아니라 **모든 문서의 상시 메타데이터**다.

```yaml
provenance: market | official | internal_analysis | internal_decision
```

- `internal_decision`(심의·품의·사후 리뷰)은 모델 추론 경로에서 항상 제외된다.
  시간 컷오프와 무관하다 — 라이브에서도 순환논리 방지를 위해 필요하다
- 채점·대조 용도의 접근은 별도 코드 경로로만 한다
- ngip_dev `ai_documents`를 읽을 때도 이 분류를 적용한다 (`metadata_json` 기반,
  ngip 스키마 변경 없이)

## 6. 잡 편성

ngip_dev의 기존 패턴(EventBridge/Fargate cron, `jobs/` 모듈)을 그대로 따른다.

**잡 편성도 "채택은 느리게, 갱신은 빠르게"를 따른다.**

**빠른 체인 (일별, 자동)**

| 잡 | 내용 |
|---|---|
| 수집 인제스터들 | 소스별(일/주/월) 외부 소스 → scen_raw → 정규화 → scen_series/docs/event |
| `state_update` | 신규 관측으로 상태 갱신 (필터링) + **nowcast 산출** |
| `regime_refresh` | Regime 소속확률·안정성 갱신 |
| `transition_eval` | 전환 확률·후보 방향 갱신 (시계별) |
| `signpost_eval` | Signpost 조건식 평가 → 충족도·trigger 거리·정렬 |
| `scenario_likelihood` | **Signpost 충족도 + Regime 소속확률 + Transition 확률 → likelihood 갱신** (01 §7.2) |
| `outlook` | Scenario별 조건부 분포 + 혼합분포 |
| `narrate` | Regime·Scenario 서사 갱신 (근거 참조 필수) |
| `scoring` | 실현치 대비 채점 + calibration + surprise 집계 |

일별 체인은 `scen_scenario`(채택 목록)를 **읽기만 한다.** 새 Scenario를 만들지 않는다 —
그래서 매일 돌아도 §6.4의 소설화 위험이 없다.

**느린 체인 (주·월, 게이트 있음)**

| 잡 | 주기 | 내용 |
|---|---|---|
| `reestimate` | 주~월 | 파라미터 재추정. **Regime 생성·소멸 판정** (01 §2.3 순차 진단 적용) |
| `scenario_propose` | 주~월 또는 이벤트 트리거 | Regime·Transition·Signpost 상태 + 사건 유형 조합에서 **후보 대량 생성**, 연결 분해·등급 초안·근거 회수(지지+반증) |
| `scenario_review` | 주~월 | **Domain 심사 게이트.** 연결 등급 확정, 채택/보류/제외, Wildcard 분류 → `scen_scenario`·`scen_link` 갱신 |
| `regression_backtests` | 재추정 후 자동 | 고정 과거 구간 재실행 → 이전 결과와 비교 (헌장 §7.3) |

- `scenario_propose`는 **기계가 후보를 만들고 근거를 모으는 단계**이며, 그 자체로는
  아무것도 채택하지 않는다. 산출은 전부 `status=candidate`
- `scenario_review`가 유일한 채택 경로다. 사람이 심사자로 개입하는 지점이며,
  **후보를 만드는 공정이 아니다** (01 §6.2 가드레일)
- surprise 급등은 `scenario_propose`의 **이벤트 트리거**가 될 수 있다 — 모델이
  "내 틀 밖의 일"을 감지하면 후보 탐색을 앞당긴다

**운영 규칙**

- 일별 체인 실패 시 전날 산출이 그대로 남는다 (UI는 항상 마지막 성공 run을 읽음)
- 백테스트는 별도 프로젝트가 아니라 `reestimate`에 붙는 회귀 테스트 스위트다

## 7. 코드베이스 구조

```
scen_dev/
  docs/            00-charter / 01-model-definition / 02-architecture / data-acquisition-spec
  core/            asof.py(접근 계층) · schema.py(전 테이블 DDL) · config.py
  ingest/          소스별 인제스터 (ngip_dev와 독립, 필요시 로직 참조·복제는 허용, import 금지)
  engine/          state/ (필터·분해) · scenario/ (모드·전환) · signpost/ · outlook/ · narrate/
  scoring/         채점 지표 · 컨센서스 대비
  backtests/       회귀 테스트 구간 정의 + 러너
  jobs/            §6의 잡 엔트리포인트
  scripts/         1회성 (백필, 스키마 생성)
  tests/
```

- Python 단일 venv. 웹 프레임워크 없음 (UI는 ngip_dev 쪽)
- DB는 기존 RDS의 동일 데이터베이스에 `scen_` 접두 테이블 (스키마 분리는 배포 복잡도
  대비 이득이 없어 접두어 방식 채택 — ngip 선례와 동일)

## 8. ngip_dev 쪽 접합 (유일하게 ngip를 수정하는 지점)

최소 침습으로 한정한다:

1. **LIORA 툴** — `core/ask.py` TOOLS에 추가. 전부 계약 테이블 read-only.
   개념 층이 분리됐으므로 툴도 층을 따른다:

   | 툴 | 반환 | 도입 |
   |---|---|---|
   | `get_market_state` | 현재 상태 + **nowcast** ("공식치 이전의 현재 추정") | 1차 |
   | `get_regime_status` | 활성 Regime·소속확률·안정성·전환 가능성 | 1차 |
   | `get_scenarios` | 채택된 Scenario·likelihood·**confidence**·서사 | 1차 |
   | `get_signpost_status` | Signpost 보드 (충족도·trigger 거리·정렬 그룹) | 2차 |
   | `get_market_outlook` | Scenario별 조건부 분포 + 혼합분포·상대가치 | 2차 |
   | **`get_scenario_evidence`** | **연결 그래프·등급·지지/반증 근거** | 2차 |

   `get_scenario_evidence`가 중요하다. **"AI 서사는 증거가 아니다"(01 §6.4)가 UI에서
   실현되려면, 사용자가 서사 뒤의 연결과 등급을 열어볼 수 있어야 한다.** 서사만 보이고
   근거를 못 보는 화면은 정확히 소설 생성기의 인터페이스다.

2. **Estimation 워크스페이스 활성화** — `ins-est`의 고스트 프리뷰(Delivered price /
   Transport / Netback)를 교체. 캔버스 구성 요소:
   - 현재 Regime 카드 (소속확률·안정성·서사)
   - Scenario 목록 (likelihood + **confidence 표시**, `unscored` 포함)
   - **연결 그래프 뷰** — 등급 색상, `A`(가정) 강조, AI 삽입 표식
   - Signpost 보드 (정렬 그룹 시각화)
   - 전망 분포 차트, surprise 게이지

   `A` 등급과 AI 삽입을 **시각적으로 눈에 띄게** 처리한다. 숨기면 스키마로 막아둔
   것을 UI가 도로 푸는 셈이다. 우측 레일은 기존 구조 그대로 LIORA가 담당.

3. **`/api/scen/*` read 라우트** — 캔버스가 직접 그릴 데이터용 (LIORA 경유 없이)

UI 상세(카드 구성·차트)는 엔진 산출물이 실물로 나온 뒤 확정한다.

## 9. 구축 순서 (아키텍처 관점)

| 단계 | 내용 | 이유 |
|---|---|---|
| 1 | `schema.py` + `asof.py` + scen_raw/series/docs 생성 | 모든 것의 토대. **vintage 축적은 하루라도 빨리 시작해야 하는 자산** |
| 2 | 수집 인제스터: 무료·기보유 소스부터 (STEO 백필, EIA vintage, FERC 프로파일, NOAA) | 데이터 명세 트랙 2 |
| 3 | **E1~E6** 실증 (01 §10) — 노트북/스크립트 수준 | 상태·Regime 설계 확정 전 가설 검증. **E6는 아카이브 수집과 독립** (문장쌍 + 기존 코퍼스 샘플로 즉시 가능) — 수집과 병렬 |
| 4 | 엔진 MVP (상태·Regime): state_update + regime_refresh + **outlook Ⅰ** + scoring | 상시 채점 루프를 최대한 일찍 돌림 (헌장 §7.1). **Outlook Ⅰ이 없으면 채점할 대상이 없다** — 헌장 §3.1~3.2 |
| 5 | 계약 테이블 채우기 + LIORA 1차 툴 (`get_market_state`·`get_regime_status`·`get_market_outlook`) | 끝-끝 관통을 얇게 먼저. **전망까지 관통해야 관통이다** |
| 6 | **E7~E10** 실증 | Scenario 층 착수 전 검증 — 연결 등급의 신뢰성·반증 회수·층 분리·Signpost 안정성 |
| 7 | Scenario 층: propose / review 게이트 / link·evidence / likelihood 갱신 | E7~E8 통과가 선행조건 |
| 8 | **Outlook Ⅱ**(Scenario 조건부 + 혼합분포) + 조건부 calibration 채점 | Scenario 층이 서야 가능 |
| 9 | Signpost 고도화, Estimation 캔버스, E11 | 관통된 파이프 위에서 반복 |

> **Outlook은 단계 4에 반드시 들어간다.** 헌장 §3.2의 Ⅰ/Ⅱ 구분에 따라, 상태·Regime만
> 있어도 산출 가능한 **Marginal / Regime-conditional 분포(Ⅰ)** 를 MVP에서 내놓고
> 즉시 채점을 시작한다. Scenario 조건부(Ⅱ)는 Scenario 층이 선 뒤 단계 8에서 붙는다.
> v0.2까지 Outlook이 마지막 단계에 있어 `scoring`이 채점할 대상 없이 도는 모순이 있었다.

**원칙: 끝-끝을 얇게 먼저 관통하고, 각 층을 깊게 하는 것은 그다음이다.**

### 9.1 게이트 — 무엇이 무엇을 막는가

게이트는 **되돌리기 비싼 커밋** 앞에만 둔다. 배관 구축은 막지 않는다.

| 게이트 | 막는 것 | 막지 않는 것 |
|---|---|---|
| **E6 판정** | Factor·상태 모델의 **프로덕션 파라미터 확정** (임베딩이 바뀌면 재추정) | 파이프라인·스키마·수집·배관 구축. 임베딩 모듈을 버전화·교체 가능하게 설계하면 병렬 진행 가능 |
| **E7·E8 통과** | **Scenario 층 착수** — 연결 등급을 신뢰할 수 없으면 채택 체계가 성립 안 함 | 상태·Regime 층 전체 |

> v0.1의 "E6 판정 전 엔진 MVP 착수 금지"는 과한 게이트였다. §10.4(원본 임베딩 보존 +
> 어댑터)를 채택한 이상 재도출 비용이 낮으므로, 게이트는 *배관 착수*가 아니라
> *운영 파라미터 확정* 앞으로 이동한다.

## 10. ngip RAG와의 격리 — 임베딩 공유의 역방향 위험 차단

임베딩 **모델**은 공유하되, 다음 세 가지 결합은 금지한다 (2026-07-30 결정).

### 10.1 코퍼스 분리 — 모델 공유 ≠ 코퍼스 공유

"한 테이블 + 필터(태그)"가 아니라 **물리적 별도 테이블**로 분리한다.
근거는 사용자가 달라서가 아니다 — 그것만이라면 쿼리 필터로 충분하다. 진짜 근거 셋:

1. **필터는 관례, 분리는 구조.** 한 테이블 방식은 ngip의 모든 검색 경로가 빠짐없이
   필터를 걸어야 성립하는데, ngip 검색 코드는 무수정이 원칙이고 현재 기본 동작은
   전체 검색이다. 별도 테이블이면 지킬 규칙 자체가 없다 — 잊어버릴 필터가 없다
2. **HNSW 성능 간섭.** pgvector HNSW는 필터드 ANN 검색에 약하다(top-k 선탐색 후
   필터 적용). 같은 인덱스에 scen 수백만 청크가 들어오면 LIORA 검색이 태그와
   무관하게 느려지고 부정확해진다 — 운영 품질의 실질 저하
3. **책의 단위와 카드가 다르다.** 공유하는 것은 분류 좌표계(임베딩 모델)뿐이다.
   ngip는 검색용 청크 + 검색 facet, scen은 집계용 단위 + bitemporal·provenance·판별
   메타데이터 — 같은 스키마에 섞을 수 없는 레코드 구조다

수칙:
- scen 텍스트는 `scen_docs` 전용 (ngip 테이블에 쓰지 않음)
- S3는 `ai-corpus/` **밖의** 별도 프리픽스 — ngip 인제스터가 줍지 않는 곳
- ngip 쪽 문서를 scen이 읽는 것은 허용 (읽기 전용, §2)
- **문서 중복은 분리의 수용된 비용이다** (최근 FERC 등 양쪽에 존재 가능). 저장 비용은
  무시 가능하며, 겹치는 문서는 scen이 ngip 행을 읽기 전용 재활용해도 된다. 중복
  제거를 위해 테이블을 합치는 것은 위 세 근거를 무너뜨리는 비싼 해법이므로 금지

### 10.2 버전 독립 — 업그레이드 커플링 금지

두 시스템의 이해가 정반대다: RAG는 더 좋은 모델이 나오면 **올리고 싶고**(재임베딩하면
끝), Factor 시계열은 **못 박고 싶다**(교체 = 전량 재임베딩 + Factor·통계모델 재추정).

- 임베딩 버전은 각자 독립 소유. 어느 쪽도 상대의 업그레이드를 강제하거나 막지 않는다
- 교차 코퍼스 유사국면 검색 등 상호운용은 **버전이 일치하는 동안만 쓰는 기회적
  이점**이며, 계약이 아니다. 버전이 갈라지면 그 기능만 포기한다

### 10.3 역류 차단 — scen 산출물은 RAG에 인덱싱하지 않는다

`scen_narrative` 등 기계 생성 산출물이 ai-corpus로 흘러들면 LIORA가 기계가 쓴
시나리오 해석을 출처처럼 인용한다 — 순환논리의 RAG판. `provenance` 축(§5)으로
scen 산출물을 RAG 인덱싱 대상에서 상시 제외한다.

### 10.4 원본 임베딩 보존 — 좌표 변환은 파생 계층

**저장하는 것은 항상 임베딩 API가 돌려준 원본 벡터다.** 그 위의 어떤 변환도
파생물로 취급하며, `scen_docs`에 변환 결과를 덮어쓰지 않는다.

이유는 E6 실패 시의 대응 경로에 있다. 방향 민감도가 부족할 때 선택지는 넷인데,
재임베딩 비용이 극단적으로 갈린다:

| | 방법 | 전량 재임베딩 |
|---|---|---|
| A | 다른 기성 임베딩 모델로 교체 | 필요 |
| **B-light** | **원본 벡터 위에 변환층(어댑터) 학습** — "시장 함의가 반대면 멀어지도록" | **불필요** |
| B-heavy | 오픈웨이트 모델 직접 fine-tune (자체 호스팅 수반) | 필요 |
| C/D | 구조화 이벤트 추출·LLM 축 채점이 방향을 담당 (이미 설계에 있음) | 불필요 |

- **A는 답이 아닐 가능성이 높다.** 범용 임베딩은 대부분 같은 목적함수("의미가 비슷하면
  가깝게")로 학습되며, 그 기준에서 "저장량 많이 쌓임/적게 쌓임"은 실제로 비슷한 문장이다.
  E6 실패는 3-small의 결함이 아니라 범용 임베딩 부류 전체의 특성일 공산이 크다
- **B-light가 기본 대응 경로다.** 원본 벡터를 보존하면 변환층을 몇 번이고 재학습해도
  아카이브를 다시 만들지 않는다 — 실험 사이클이 주 단위에서 시간 단위로 줄어든다
- OpenAI 임베딩은 fine-tuning이 불가하므로 **B-heavy는 자동으로 오픈웨이트 이전 +
  자체 호스팅을 수반한다.** B-light는 그 무게를 피하는 경로다
- 교체를 실제로 검토하게 되면 그 시점의 지형을 다시 확인한다. 카테고리: OpenAI
  (3-large), 전문 벤더(Voyage — 금융 특화판 존재, Cohere), 오픈웨이트(BGE·E5·GTE·
  Nomic·Jina — fine-tune 가능한 유일한 부류), Google Gemini 계열

## 11. 미결정 사항

| # | 항목 | 결정 시점 |
|---|---|---|
| 1 | 종속변수 목록 (01 §9 — 도메인 판단) | 엔진 MVP 전. **Domain Logic 축과 협의 필요** |
| ~~2~~ | ~~임베딩 모델~~ | **확정 (2026-07-30): 시작은 ngip와 동일 (text-embedding-3-small, 1536) — 단, "동일"은 오늘의 편의이지 계약이 아니다 (§10).** 조건: ① 모든 임베딩 행에 모델명·버전 기록 ② 임베딩 단독으로 Factor를 만들지 않음 — 방향·스탠스는 구조화 이벤트 추출(`scen_event`)이 담당 (01 §8 E6) |
| 3 | 계약 테이블 스키마 확정 리뷰 | 단계 5 전 (Scenario 계층은 단계 7 전) |
| 8 | `scenario_propose`의 후보 생성 알고리즘 | E7 결과에 종속. 조합적 생성의 범위·가지치기 규칙 |
| 9 | Domain 심사 게이트의 운영 형태 | 단계 7 전. 누가·얼마나 자주·어떤 UI로 연결 등급을 확정하는가 — 이것이 병목이 되면 §6.2 가드레일이 무력화된다 |
| ~~4~~ | ~~클라우드 배포 형태~~ | **결론 변경 (2026-07-31, 실측 근거).** 구 판단은 "동일 RDS로 시작, 부하 겹치면 분리"였으나 실측 결과 **분리 시점이 훨씬 이르고 트리거도 다르다.** 현 운영 DB는 **db.t4g.small / 2 GB RAM / 20 GB**이며 이미 HNSW 인덱스(466 MB)가 shared_buffers(413 MB)를 초과한다. 현 디스크는 **약 91만 청크에서 소진**된다(현재의 15배 — FERC 전량 백필 + 아카이브 몇 개면 도달). → **1~2단계는 현 인스턴스, 아카이브 수집 단계부터 scen 전용 인스턴스로 분리.** 트리거는 RAM이 아니라 **스토리지·IOPS**. 상세 사양은 `04-infrastructure-requirements.md` |
| 5 | Estimation 캔버스 상세 | 엔진 산출물 실물 후 |
| 6 | 서사 생성(③층) LLM 선택·비용 구조 | 엔진 MVP 시. 배치에서 LLM API 호출 — 모델·프롬프트 버전을 `scen_run`에 기록해 서사 재현성 확보. 이벤트 추출(`scen_event`)용 LLM도 동일 취급 |
| 7 | 모니터링·알림 | 엔진 MVP 시. 잡 실패·데이터 지연(소스가 안 오는 날)·surprise 급등 알림 — ngip `rag_healthcheck` 패턴 준용 |
