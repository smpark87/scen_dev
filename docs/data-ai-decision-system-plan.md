---
title: Data & AI-driven 의사결정 체계 구축(안)
subtitle: AI 기반 Scenario Planning 추진
document_date: 2026-07-28
source: internal
origin: "OneDrive://LAI Planning Team/General/12. LAI Strategy/2026/Data & AI-driven 의사결정 체계 추진안.docx"
category: strategy
confidence: draft
tags: [scenario planning, signpost, decision intelligence, portfolio optimization]
---

# Data & AI-driven 의사결정 체계 구축(안)

**AI 기반 Scenario Planning 추진**

---

## 1. 추진 목적

### AI 기반 Scenario Decision System 추진

LAI는 Operatorship 기반 가스전 확장, G2P 개발, HH연동 LNG 장기계약 등 주요 성장 과제의 추진 여부와 최적 진입시점을 판단할 체계가 필요하다. 이에 AI 기반 Scenario Planning과 시장전망을 통해 사업·투자 의사결정을 고도화하고, 분석 결과를 포트폴리오 Optimization까지 연계하고자 한다.

**[핵심 의사결정]**

| 성장 과제 | 핵심 판단 |
|---|---|
| Operatorship 기반 가스전 확장 | 어느 지역·자산에 언제, 어느 규모로 진입할 것인가 |
| G2P 개발 | 어떤 시장과 사업모델을 우선 추진하고, 언제 투자할 것인가 |
| HH 연동 LNG 장기계약 | 향후 수급과 가격 Scenario를 고려할 때 언제, 어느 물량을 확보할 것인가 |
| Portfolio Optimization | 확보한 가스·LNG·Power 자산과 계약을 어떻게 배분·운영·Hedge할 것인가 |

### 구축 방향

- 미래 Scenario별 사업·투자 타당성과 진입시점 판단
- 뉴스·정책·기업발표 등 정성정보까지 AI로 구조화
- 시장전망을 Go/No-Go 및 When-to-Go 판단에 직접 연결
- 동일 분석 결과를 물량배분·계약·Hedge Optimization에 확장

> 시장 변화와 주요 Signpost를 지속적으로 추적하여 성장 과제별 Go/No-Go와 최적 진입시점을 판단하고, 실행 이후에는 동일한 시장·Scenario 분석을 Portfolio Optimization에 활용하는 의사결정 체계 구축

---

## 2. 핵심 추진과제

### AI 기반 Scenario Planning 시스템 구축 범위

Domain Logic 및 Data·AI 두 축의 상호 검증을 통한 의사결정 체계 고도화

| 구축 단계 | Domain Logic 축 | Data·AI 축 | 두 축의 결합 결과 |
|---|---|---|---|
| 판단구조 정의 | 성장 과제별 의사결정 목표 수립, 핵심 Driver 및 영향경로 정의 | Domain에서 정의한 핵심 Driver와 영향경로를 기준으로 실제 데이터를 연결하고, 변수별 데이터 확보 가능 여부와 Gap 점검 | 분석에 필요한 Data, Event 및 모델 변수 확정 |
| Scenario·Signpost 설정 | 구조적 Scenario와 주요 Signpost, 판단 변경 가설 및 후보 임계수준 설정 | Scenario 및 Signpost 검증을 위한 Event·Semantic 모델링 및 Embedding 기반 과거 유사국면·시장반응 분석 | Scenario별 Signpost를 측정 가능한 Indicator로 전환하고, 예측력·선행시차·Trigger 임계수준을 정량화 |
| 시장전망 Dynamic Update | 신규 Event의 영향경로와 Scenario 전환 가능성 해석 | 정형변수와 Semantic Factor를 결합하여 가격·Spread·수급 전망 및 Scenario Probability 재산출 | Scenario 가능성과 시장전망 지속 업데이트 |
| 사업·투자 의사결정 모델링 | 성장 과제별 사업가치와 핵심 제약조건을 구체화하고, 진입시점, 규모, 사업구조별 판단기준 설계 | Scenario별 시장전망을 사업 경제성 Model에 연계하여 주요 변수 변화에 따른 가치 변동 분석 | 분석 결과를 Domain 판단기준에 적용하여 추진 여부·조건·규모 및 진입시점에 대한 의사결정안 도출 |
| Portfolio 영향 및 대응 분석 | 신규 의사결정이 기존 사업에 미치는 영향과 대응수단 정의 | 사업·계약별 물량·가격·Risk Exposure를 통합 모델링하고, Scenario별 Portfolio 변화와 대응조합 Simulation | 사업·투자 판단과 물량배분·계약·Hedge Action을 연계한 Portfolio 대응안 도출 |

Domain Logic은 AI가 탐지·분석해야 할 Data·Event·변수와 사업·투자 판단기준을 정의하고, Data·AI 분석은 실제 데이터와 과거 사례를 통해 Scenario·Signpost를 검증·정량화하고 대안별 영향을 분석한다. 두 축을 반복적으로 연계하여 시장전망을 지속 보정하고, 그 결과를 사업·투자 판단과 Portfolio 대응으로 연결한다.

---

## 3. 단계별 추진 Milestone

과거 실제 사업·투자 의사결정 사례를 기반으로 당시 판단과정과 결과를 재현·검증하고, 이를 통해 보정된 Logic과 모델을 신규 성장과제에 적용한 후 Portfolio 대응으로 단계적으로 확대한다.

| 구분 | Domain Logic 축 | Data·AI 축 | Milestone |
|---|---|---|---|
| **Phase1 (~1M)**<br>우선 적용과제 설계 | 주요 성장과제 중 우선 적용과제 선정<br>의사결정 목표, 핵심 Driver 및 영향경로 정의 | 핵심 Driver 기반 필요 Data·Event·모델 변수 확정<br>기존 플랫폼 활용범위 및 Data Gap 점검 | 의사결정·분석 Blueprint 확정<br>의사결정 목표 ↔ Data ↔ 분석모델 연결 |
| **Phase2 (2M~3M)**<br>Core Engine 구축 | Scenario 및 Signpost 가설과 판단 변경 기준 설계<br>사업가치·Risk 판단기준 구체화 | 통합 Data Model과 AI Event 분석체계 구축<br>Semantic Factor·유사국면 분석 및 시장전망 Prototype 개발 | Scenario·Signpost Engine MVP 완성<br>측정 가능한 Indicator와 전망 산출 |
| **Phase3 (4M~7M)**<br>의사결정 적용·검증 | 과거 실제 사업·투자 판단 사례를 선정하고, 당시 고려한 판단기준 및 주요 전제와 실제 의사결정 결과 재구성 | 의사결정 당시 확보 가능했던 Data 및 Event를 기준으로 Scenario·시장전망 및 사업가치 재산출<br>Signpost의 예측력·선행기간·Trigger 기준 검증 | 실제 의사결정 활용성 검증 (Back-Test)<br>실제 사업 판단에 대한 재현성·설명력 및 의사결정 활용성 검증 |
| **Phase4 (8M+)**<br>운영·확장 | 검증된 판단체계를 주요 성장과제로 확대<br>사업·투자 판단과 Portfolio 대응절차 표준화 | 상시 Event Monitoring과 Scenario Update 체계 구축<br>사업·계약별 Exposure 및 Portfolio 대응 Simulation 연계 | 주요 성장과제 적용 및 운영체계 정착<br>Portfolio 영향·대응 분석까지 연계 |

---

## 4. Discussion

### 주요 의사결정을 위한 Monitoring 항목 및 Signpost 예시

#### 4.1 Feedgas & Power Procurement / Hedge

| 모니터링 항목 | 주요 Signpost | Category |
|---|---|---|
| Gas·Power 수요 | CDD/HDD, 폭염·한파, Forecast Dispersion | Weather&Climate |
| Renewable 가용성 | 풍량, Cloud Cover, Solar·Wind Forecast Error | Weather&Climate |
| Gulf Coast 재해위험 | Hurricane 경로·강도, Storm Surge, Flooding | Weather&Climate |
| 발전·용수 제약 | 가뭄, Cooling Water Availability, 고온 Derating | Weather&Climate |
| Oil·Associated Gas 영향 | 미국–이란, Hormuz Risk, WTI·Brent | Geopolitical Events |
| US Gas Balance | HH Curve·Volatility, Storage, 생산량, LNG Feedgas, Mexico Export | Market State |
| Regional Gas Balance | HSC·OK·Waha Basis, Pipeline Flow | Market State |
| ERCOT Power Balance | Net Load, MORA, Reserve, Outage, Houston Power Price | Market State |
| Gas Infrastructure | Pipeline Capacity·Flow·Maintenance·Outage | Physical Constraints |
| Power Infrastructure | Houston/Freeport Congestion, Transmission Outage | Physical Constraints |
| FLNG Operation | Train Availability, Feedgas·Power Intensity, Outage | Physical Constraints |

#### 4.2 Equity Gas Development & Marketing

| 모니터링 항목 | 주요 Signpost | Category |
|---|---|---|
| Upstream 기상위험 | Freeze-off, 강수·결빙, 생산지역 기온 | Weather&Climate |
| Oil·Associated Gas 영향 | 미국–이란, Hormuz Risk, WTI·Brent | Geopolitical Events |
| US Gas Balance | HH Curve·Volatility, Storage, 생산량, LNG Feedgas, Mexico Export | Market State |
| Regional Gas Balance | HSC·OK·Waha Basis, Pipeline Flow | Market State |
| Upstream Operation | Well, Gathering·Processing Capacity, Curtailment | Physical Constraints |

#### 4.3 LNG Contracting — Execute/Hold, FOB/DES, Volume·Tenor·Index

| 모니터링 항목 | 주요 Signpost | Category |
|---|---|---|
| Global Gas/LNG Supply Shock | 러시아–우크라이나, 유럽 가스공급, Sanction | Geopolitical Events |
| Shipping Disruption | Red Sea·Suez·Panama, Vessel Availability·운임 | Geopolitical Events |
| 미국 정책·통상 | LNG 수출정책, 관세, Sanction, DOE/FERC 정책 | Geopolitical Events |
| Global LNG Contract Market | JKM·TTF, LNG–HH Netback, SPA Slope·Fee, FID/COD, 미계약 Capacity | Market State |
| Regional LNG Arbitrage | JKM–TTF Spread, Delivered Netback, 운임, 항해기간 | Market State |
| Shipping·Regas | Vessel·Port·Regas Capacity 및 Outage | Physical Constraints |

#### 4.4 Cargo·Shipping & Portfolio Optimization

| 모니터링 항목 | 주요 Signpost | Category |
|---|---|---|
| Gulf Coast 재해위험 | Hurricane 경로·강도, Storm Surge, Flooding | Weather&Climate |
| Global Gas/LNG Supply Shock | 러시아–우크라이나, 유럽 가스공급, Sanction | Geopolitical Events |
| Shipping Disruption | Red Sea·Suez·Panama, Vessel Availability·운임 | Geopolitical Events |
| 미국 정책·통상 | LNG 수출정책, 관세, Sanction, DOE/FERC 정책 | Geopolitical Events |
| Regional LNG Arbitrage | JKM–TTF Spread, Delivered Netback, 운임, 항해기간 | Market State |
| FLNG Operation | Train Availability, Feedgas·Power Intensity, Outage | Physical Constraints |
| Shipping·Regas | Vessel·Port·Regas Capacity 및 Outage | Physical Constraints |

---

## 변환 메모 (원본 대비 수정 이력)

원본 `.docx` → Markdown 변환 시 아래 오타만 수정했으며, 그 외 본문 내용은 원문 그대로 유지했다.

| # | 위치 | 원본 | 수정 |
|---|---|---|---|
| 1 | 3장 Milestone 표 | `Phase1 (4M~7M)` | `Phase3 (4M~7M)` |
| 2 | 3장 Milestone 표 | `Phase1 (8M+)` | `Phase4 (8M+)` |
| 3 | 4.2 / 4.3 / 4.4 표 머리글 3열 | `주요 Signpost` (2열과 중복) | `Category` (4.1 표 기준) |
| 4 | 3장 소제목 | `AI 기반 Scenario Planning 시스템 구축 범위` (2장 소제목과 중복 — 복사 흔적) | 삭제 (장 제목 `단계별 추진 Milestone`으로 충분) |
| 5 | 2장 표 · 3장 표 | `예측력·선행시차· Trigger`, `Semantic Factor· 유사국면` | 불필요한 공백 제거 |

**미수정 — 확인 필요 사항**

- 2장 표는 `선행시차`, 3장 Phase3는 `선행기간`으로 같은 개념을 다르게 표기하고 있다. 어느 쪽으로 통일할지 원문 작성자 확인 필요하여 원문 그대로 두었다.
