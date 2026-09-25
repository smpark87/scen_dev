# scen_dev — LIORA OUTLOOK 개발 저장소

제품 방향은 [docs/09-outlook-direction.md](docs/09-outlook-direction.md), 협업·보안·배포 규칙은 [AGENTS.md](AGENTS.md)를 따른다. 과거 헌장과 현재 방향이 다르면 09 문서를 우선한다.

| 문서 | 용도 |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Windows 개발 환경, 테스트, Git 훅, 본사 자가점검 절차 |
| [WORKLOG.md](WORKLOG.md) | 진행 중인 일·열린 결정·현재 상태 |
| [docs/WORKLOG_ARCHIVE.md](docs/WORKLOG_ARCHIVE.md) | 완료 작업의 이유와 검증 |
| [docs/SECURITY_SELFCHECK.md](docs/SECURITY_SELFCHECK.md) | 본사 자가점검 실행·판정 기록 |

로컬 개발은 형제 `../shared/.venv`의 공용 Python을 사용한다. 실행:

```powershell
.\run.ps1
```

로컬 OUTLOOK은 `http://127.0.0.1:8765/perspectives`에서 열린다. 기본 검증 명령:

```powershell
..\shared\.venv\Scripts\python.exe -m pytest -q
..\shared\.venv\Scripts\python.exe scripts\ratchet.py
..\shared\.venv\Scripts\python.exe scripts\security_source_gate.py --all
```

`ratchet.toml`은 품질 기준선이다. CI와 Git 훅에도 연결되어 있다. 운영 배포는 별도 명시적 승인 뒤에만 실행한다.
