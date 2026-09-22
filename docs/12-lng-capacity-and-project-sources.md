---
title: OUTLOOK — 유럽 재기화와 글로벌 액화 프로젝트 데이터 설계
date: 2026-09-22
status: source assessment
---

# OUTLOOK — 유럽 재기화와 글로벌 액화 프로젝트 데이터 설계

## 1. 먼저 구분할 값

설비능력과 실제 물량을 한 계열로 다루지 않는다.

- **재기화 명목능력**: 터미널이 설계상 처리할 수 있는 연간 물량
- **재기화 당일 선언용량**: 운영사가 해당 가스데이에 선언한 send-out capacity
- **실제 send-out**: 해당 가스데이에 터미널에서 가스망으로 보낸 물량
- **LNG 탱크 재고**: 터미널 탱크의 일말 LNG 재고
- **액화 명목능력**: 수출 프로젝트·phase·train의 설계 MTPA
- **프로젝트 일정**: 발표 당시의 상태와 예상 가동시점, 실제 FID·착공·가동시점

이 구분이 있어야 유럽 수입 여력, 실제 이용률, 글로벌 신규 공급의 가동 시나리오를
서로 다른 변수로 사용할 수 있다.

## 2. 유럽 재기화

### 2.1 GIE LNG Database — 설비와 프로젝트 기준표

[GIE LNG Database](https://www.gie.eu/transparency/databases/lng-database/)는 공개 XLSX로
운영중·건설중·계획 터미널을 함께 제공한다. 2026-08-26판 원본을 직접 내려받아 확인했다.

| 항목 | 확인 결과 |
|---|---|
| 원천 단위 | 터미널의 existing/new facility/expansion 행 |
| 행·국가·터미널 | 77행, 25개국, 70개 `(국가, 터미널)` |
| 상태 | operational 44, planned 21, under construction 6, suspended 2, 기타 이전·폐쇄 4 |
| 핵심 값 | start-up year, FSRU/onshore 유형, 시간당 최대 send-out, 연간 bcm, LNG 저장용량, 탱크·선석·선박 크기 |
| 일정 정밀도 | 연도 단위. 77행 중 10행은 start-up year가 없음 |
| 식별자 | EIC와 안정적인 project id가 없고 좌표도 없음 |

같은 터미널에 existing·expansion 행이 함께 있으므로 터미널명만으로 덮어쓰지 않는다.
원본 상태에는 `relocated to Ravenna`처럼 일반 상태가 아닌 값도 있으므로 원문을 보존하고
정규화 상태를 별도 컬럼으로 만든다. 빈 가동연도는 추정해서 채우지 않는다.

직접 XLSX 주소를 고정하기보다 데이터베이스 안내 페이지에서 최신 XLSX 링크와 발행일을
찾아 내려받고, 원본 해시가 바뀐 경우에만 새 release snapshot을 적재하는 방식이 안전하다.
이 원천은 키가 필요 없어 NGIP job으로 바로 만들 수 있다.

### 2.2 GIE ALSI — 일별 운영실적

[GIE ALSI API 문서](https://www.gie.eu/transparency-platform/GIE_API_documentation_v007.pdf)는
API를 공개·무료로 제공하고, GIE/ALSI 출처 표기를 조건으로 재가공을 허용한다. 개인 API
키 발급을 위한 무료 등록은 필요하다.

ALSI는 2012-01-01 또는 각 터미널 가동일부터 일별 이력을 제공한다.

| 필드 | 의미 | 단위 |
|---|---|---|
| `inventory` | 일말 LNG 탱크 재고 | 천 m³ LNG |
| `sendOut` | 가스데이 실제 send-out | GWh/d |
| `dtmi` | 선언 최대 LNG 저장용량 | 천 m³ LNG |
| `dtrs` | 선언 기준 send-out capacity | GWh/d |

시설과 운영사는 EIC로 식별하고 품질상태(estimated/confirmed/no data)와 service
announcement를 같이 보존한다. EIC는 운영사 변경 등에 따라 달라질 수 있으므로 `PRIOR`
코드를 포함한 source-id 이력을 유지해야 한다. 값은 사후 정정될 수 있으므로 최신값만
upsert하지 않고 수집시점도 남긴다.

API는 페이지당 최대 300행, 분당 60호출 제한이다. 일별 신규분은 하루 한 번 수집하되
최근 구간을 다시 읽어 사후 정정을 반영하고, 정기적으로 전체 해시·건수를 대조한다.
ALSI 키는 코드나 저장소에 두지 않고 NGIP 배포 secret으로 주입한다.

GIE XLSX의 명칭과 ALSI의 EIC 사이에는 자동 공통키가 없으므로 한 번 검토한 crosswalk가
필요하다. GIE XLSX의 연간 명목능력과 ALSI의 일별 `dtrs`는 정의와 시점이 다르므로 어느
한쪽으로 다른 쪽을 덮어쓰지 않는다.

### 2.3 보조 원천

- [ENTSOG Transparency API](https://transparency.entsog.eu/api/archiveDirectories/8/api-manual/ENTSOG_TP_API_UserManual_v3.0.pdf)는
  공개 API로 Firm Technical·Firm Available·Physical Flow 등을 제공한다. LNG 터미널의
  가스망 진입점 검증과 ALSI 공백 대조에 사용하되, 터미널과 point-direction 매핑이 필요해
  1차 수집원으로 삼지 않는다.
- GIE IIP/REMIT의 계획·비계획 unavailable capacity는 터미널 outage와 실제 가용능력
  분석에 유용하다. ALSI API 문서상 unavailability는 ALSI API 범위 밖이므로 2단계에서
  별도 수집 계약을 확인한다.
- [GIE LNG Map](https://www.gie.eu/publications/maps/gie-lng-map/)은 운영·건설중·계획
  터미널과 send-out·연간·저장용량을 시각적으로 대조하는 자료로 사용한다.

## 3. 글로벌 액화능력과 프로젝트 일정

### 3.1 Global Energy Monitor GGIT — 기본 자산 로스터

[Global Gas Infrastructure Tracker](https://globalenergymonitor.org/projects/global-gas-infrastructure-tracker)는
글로벌 LNG 수입·수출 프로젝트를 자산/phase 단위로 관리한다. 2025-09 LNG terminal
release 기준으로 공식 페이지는 1,207개 프로젝트를 제시하고, 운영·건설·제안·보류·취소·
idle·mothballed·retired 상태를 구분한다. 위치, 소유자, 상태, 용량, 시작연도를 갖는
글로벌 기준 로스터로 가장 적합하다.

다만 전체 Excel/GeoJSON/GeoPackage/Shapefile은 다운로드 폼을 거친다. GEM의 공개
운영 저장소도 원본 데이터 파일을 Git에서 제외하고 있으며 headless Google Sheets
인증이 아직 대체되지 않았다고 기록한다. 따라서 현재 확인된 범위에서는 새 release를
고정 URL로 무인 수집하는 job을 만들 수 없다.

운영 방식은 다음과 같이 나눈다.

1. 담당자가 공식 폼에서 release 원본을 내려받아 통제된 NGIP S3 inbox에 올린다.
2. NGIP job은 파일명에 의존하지 않고 workbook 구조, release date, 행 수, 필수 컬럼,
   중복, 합계를 검증한다.
3. 검증된 원본과 정규화본을 S3에 보존하고 DB에는 release snapshot을 추가한다.
4. 다음 release와 비교해 상태·용량·예상 가동연도 변경을 event로 만든다.

공개 country/status summary sheet는 글로벌 총량 대조에는 쓸 수 있지만 프로젝트 일정과
phase를 잃으므로 원본 자산 파일을 대체하지 않는다. GEM에 자동 수집용 공식 URL/API를
문의해 확보하면 1단계 수동 반입만 제거한다.

### 3.2 연간 대조 자료

- [IGU World LNG Report](https://www.igu.org/igu-reports/2026-world-lng-report)는 국가·
  프로젝트별 운영능력, 신규 가동, FID와 건설중 총량의 연간 기준점으로 사용한다.
- [GIIGNL Annual Report](https://www.giignl.org/annual-report)는 운영 설비와 시장 총량을
  대조하는 자료로 사용한다. 공개 PDF와 회원 전용 상세 Excel의 접근 범위를 구분한다.

두 보고서는 PDF 중심의 연간 자료이므로 자산 snapshot의 자동 주원천으로 삼지 않는다.

## 4. 프로젝트 일정에는 비정형이 필요하다

구조화 로스터의 현재 상태와 start year만 저장하면 과거에 2027년으로 발표됐다가 2029년으로
밀린 사실과 지연 이유가 사라진다. 액화 공급전망에는 아래 사실 이력이 필요하다.

- 발표/FID/착공/commissioning/first LNG/commercial operation의 사건일
- 발표 당시 target start와 정밀도(day, month, quarter, half, year)
- 일정 변경 전후 값과 발표일
- 지연·중단·재개의 근거 문장과 원문 URL
- 회사발표, 규제기관, 정부, 프로젝트 금융, 보도자료의 출처 등급

GGIT/GIE의 정형 snapshot이 설비 우주와 기본 상태를 만들고, 회사·규제기관 발표와 기사에서
추출한 claim/event가 일정의 변화를 설명한다. 비정형은 정형 데이터 이후에 붙지만 프로젝트
일정에서는 선택 항목이 아니라 변경 이유와 as-of 재현을 위한 필수 계층이다.

## 5. DB 저장 원칙

현재 중앙 DB의 `lng_sites` 38행은 모두 미국이고, `lng_projects`와 `lng_trains`는
FERC·DOE·미국 액화 train을 중심으로 설계되어 있다. 글로벌 import terminal을 곧바로
섞지 않는다.

신규 저장층은 최소 세 종류가 필요하다.

1. **source release**: 원천, release date, 수집시각, 파일 해시, 원본 위치, 검증 결과
2. **asset snapshot**: release별 source asset/phase, import/export, 국가, 원문 상태,
   정규화 상태, 명목능력, 시작연도, 운영사와 좌표
3. **regas daily**: ALSI facility EIC, gas day, inventory, sendOut, dtmi, dtrs, 품질상태,
   수집시각

canonical site/project/train과 source asset의 crosswalk는 별도 보존한다. snapshot은 새
release가 와도 과거 행을 지우지 않는다. 그래야 특정 시점에 시장이 알고 있던 미래 공급량과
실제 결과를 비교할 수 있다.

## 6. 실행 순서

1. 키가 필요 없는 GIE LNG Database XLSX 수집·검증 job과 release snapshot을 먼저 만든다.
2. GIE/ALSI 계정을 발급받은 뒤 API key를 secret으로 연결해 일별 운영 이력을 백필한다.
3. GGIT 공식 release 원본을 한 번 확보해 asset snapshot parser와 변경 비교 job을 만든다.
4. 회사·규제기관 발표에서 일정 claim/event를 추출하는 비정형 계층을 붙인다.
5. IGU·GIIGNL 총량과 GIE/ENTSOG 값으로 release별 품질검사를 수행한다.

이 문서는 원천과 저장 원칙을 확정하기 위한 조사 결과다. 신규 DB migration, 운영 secret,
job 배포와 최초 운영 적재는 아직 수행하지 않았다.
