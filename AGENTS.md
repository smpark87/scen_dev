## 보안 규정 회귀 게이트

- 본사 자가점검 도구를 실행하기 전에 `python scripts/security_scan_preflight.py`로
  `debug/` 잔여물과 저장소 내부의 중첩 Git 작업 트리를 확인한다. 실패하면 실제
  소유 작업과 사용처를 확인해 정리한 뒤 검사하며, 제외 설정으로 숨기지 않는다.
- 커밋 전 `python scripts/security_source_gate.py --staged`를 실행한다. 로컬 훅은
  `git config --local core.hooksPath .githooks`로 연결하며 CI는 전체 작성 소스와
  변경분을 다시 검사한다.
- 빈 오류 처리와 동적 SQL 같은 확실한 위반은 수정한다. 맥락상 안전한 새 위험 API는
  `scripts/security_reviewed.json`에 정확한 코드와 한국어 근거를 남긴다. 이 등록은
  본사 도구의 오탐 판정이나 예외 승인을 대신하지 않는다.
- 자격증명, 토큰, 개인 정보, 운영 데이터와 `.env`는 Git에 커밋하지 않는다.
- DB 접근은 `db.py`를 경유하고 운영 연결의 읽기 전용 강제를 해제하지 않는다.
- 이 게이트는 본사 자가점검 도구의 정규식을 복제한 것이 아니다. 본사 도구는 정기적으로
  별도 실행하고, 새 판정이 나오면 게이트와 검토 근거를 갱신한다.
