# Windows 개발 환경

이 문서의 명령은 `scen_dev` 폴더의 PowerShell에서 실행한다. 로컬 개발은 형제 `../shared/.venv`의 Python 3.13 환경을 NGIP·LAI Finance·평가모델과 공유한다. 운영 배포의 이미지와 의존성 명세는 이 저장소에서 독립적으로 유지한다.

## 설치

```powershell
if (-not (Test-Path ..\shared\.venv\Scripts\python.exe)) { python -m venv ..\shared\.venv }
..\shared\.venv\Scripts\python.exe -m pip install -r ..\shared\requirements.txt -c ..\shared\requirements.lock
..\shared\.venv\Scripts\python.exe -m pip check
git config --local core.hooksPath .githooks
```

공용 `../shared/requirements.txt`가 이 저장소의 `requirements-dev.txt`까지 참조한다. 패키지 변경 전에는 전체 공용 명세로 dry-run을 하고, 관련 프로젝트를 검사한 뒤 lock을 갱신한다. 한 프로젝트의 명세만으로 공용 환경을 sync하거나 기존 패키지를 제거하지 않는다. 이 저장소에는 별도 `.venv`를 만들지 않는다. 가상환경 폴더는 Git에 넣지 않는다.
새 PC에서는 형제 `shared/requirements.txt`와 `shared/requirements.lock`을 함께 준비한다. 이 파일들은 `scen_dev` 저장소에 들어 있지 않다.

## 작업 시작과 검증

로컬 OUTLOOK은 `.\run.ps1`로 실행한다. 실행 스크립트가 공용 Python과 프로젝트 작업 폴더를 지정한다.

```powershell
git status --short
..\shared\.venv\Scripts\python.exe -m pytest -q
..\shared\.venv\Scripts\python.exe scripts\ratchet.py --list
..\shared\.venv\Scripts\python.exe scripts\security_source_gate.py --all
```

커밋 직전에는 staged 파일 목록을 보고 Git 훅의 `security_source_gate.py --staged`와 래칫이 통과하는지 확인한다. 래칫은 Git이 추적하거나 staged로 추가한 파일을 본다. 새 파일은 `git add` 후 검사한다. CI는 Python 3.13에서 전체 테스트·컴파일·래칫·보안 소스 게이트·시크릿 스캔을 실행한다. `ratchet.toml`의 기준선은 위반을 숨기기 위해 자동으로 올리지 않는다.

## 본사 자가점검

```powershell
..\shared\.venv\Scripts\python.exe scripts\security_scan_preflight.py
```

사전 점검이 통과한 뒤 본사에서 배포한 도구를 별도로 실행한다. 도구의 설치 위치, 버전, 실제 검사 범위, 결과와 미해결 판정은 `SECURITY_SELFCHECK.md`에 적는다. 개발 게이트나 CI 통과를 본사 보안 승인으로 해석하지 않는다.

현재 PC의 본사 배포물은 형제 `../SourceCode_Selfcheck Tool/`에 있다. `사용설명서.html`에 따라 `SecureCodeCheck.exe`를 열고 **폴더 선택**으로 이 저장소를 지정한 뒤 **검사 실행**과 **HTML 리포트 저장**을 사용한다. 도구는 하위 폴더까지 검사하므로 실행 전에 사전 점검을 통과해야 한다. 리포트의 민감 정보를 확인하고 Git 밖에 보관한다.
