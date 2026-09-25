"""소스 품질이 이전 기준보다 나빠지지 않도록 검사한다.

Git이 추적하거나 staged로 추가한 파일을 검사한다.
검사는 의존성 없이 실행되며, 본사 보안 점검을 대신하지 않는다.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import tokenize
import tomllib
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "ratchet.toml"
SOURCE_DIRS = {"analysis", "extract", "outlook", "scripts"}
SOURCE_FILES = {"assemble.py", "config.py", "db.py"}


def repo_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    )
    return sorted({ROOT / part.decode("utf-8") for part in result.stdout.split(b"\0") if part})


def is_source(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return path.suffix == ".py" and (rel in SOURCE_FILES or rel.split("/", 1)[0] in SOURCE_DIRS)


def code_lines(path: Path) -> int:
    """공백·주석·독립된 docstring을 제외한 Python 코드 줄 수."""
    content = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(content, filename=str(path))
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                doc_lines.update(range(node.body[0].lineno, node.body[0].end_lineno + 1))
    statement_lines: set[int] = set()
    with path.open("rb") as stream:
        for token in tokenize.tokenize(stream.readline):
            if token.type in {tokenize.ENCODING, tokenize.ENDMARKER, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT}:
                continue
            statement_lines.update(range(token.start[0], token.end[0] + 1))
    return len(statement_lines - doc_lines)


def silent_handlers(path: Path) -> list[int]:
    """넓은 except가 예외를 재전파하거나 기록하지 않는 위치."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    methods = {"debug", "info", "warning", "warn", "error", "exception", "critical"}
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        types = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
        if node.type is not None and not any(isinstance(part, ast.Name) and part.id in {"Exception", "BaseException"} for part in types):
            continue
        reported = any(
            isinstance(part, ast.Raise)
            or isinstance(part, ast.Call) and (
                isinstance(part.func, ast.Name) and part.func.id == "print"
                or isinstance(part.func, ast.Attribute) and part.func.attr in methods
            )
            for stmt in node.body for part in ast.walk(stmt)
        )
        if not reported:
            found.append(node.lineno)
    return found


def test_functions(files: list[Path]) -> int:
    count = 0
    for path in files:
        if path.suffix != ".py" or not path.relative_to(ROOT).as_posix().startswith("tests/") or not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        count += sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_") for node in ast.walk(tree))
    return count


def ruff_violations(files: list[Path]) -> int | None:
    candidates = [
        [sys.executable, "-m", "ruff"],
        [str(ROOT.parent / "shared" / ".venv" / "Scripts" / "ruff.exe")],
        [str(ROOT.parent / "shared" / ".venv" / "bin" / "ruff")],
    ]
    command = candidates[0]
    probe = subprocess.run(command + ["--version"], cwd=ROOT, capture_output=True)
    if probe.returncode:
        command = next((item for item in candidates[1:] if Path(item[0]).is_file()), [])
    if not command:
        return None
    python_files = [str(path.relative_to(ROOT)) for path in files if path.suffix == ".py" and path.is_file()]
    result = subprocess.run(
        command + ["check", *python_files, "--output-format", "json"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.strip())
    return len(json.loads(result.stdout))


def guard() -> list[str]:
    """탐지기가 무력화돼 초록으로 통과하는 것을 막는다."""
    import tempfile

    errors = []
    with tempfile.TemporaryDirectory() as scratch:
        example = Path(scratch) / "sample.py"
        example.write_text("try:\n    work()\nexcept Exception:\n    pass\n", encoding="utf-8")
        if silent_handlers(example) != [3]:
            errors.append("guard: 조용한 except 표본을 잡지 못함")
        example.write_text("# 설명\ndef work():\n    \"\"\"설명\"\"\"\n    return 1\n", encoding="utf-8")
        if code_lines(example) != 2:
            errors.append("guard: 코드 줄 계산이 주석 또는 docstring을 잘못 셈")
    return errors


def check() -> list[str]:
    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    files = repo_files()
    problems = guard()
    active = {path.relative_to(ROOT).as_posix(): path for path in files if path.is_file() and is_source(path)}
    large = cfg["large_files"]
    for name, path in active.items():
        size = code_lines(path)
        if size > cfg["limits"]["max_code_lines"]:
            problems.append(f"{name}: 코드 {size}줄, 하드 상한 초과")
        elif size > cfg["limits"]["review_code_lines"] and name not in large:
            problems.append(f"{name}: 코드 {size}줄, 분할하거나 [large_files]에 이유 기록")
        elif name in large and size <= cfg["limits"]["review_code_lines"]:
            problems.append(f"{name}: 큰 파일 예외가 더는 필요하지 않음")
    for name, reason in large.items():
        if name not in active or not isinstance(reason, str) or not reason.strip():
            problems.append(f"{name}: 큰 파일 예외의 파일 또는 이유가 없음")
    found = [(name, line) for name, path in active.items() for line in silent_handlers(path)]
    if len(found) > cfg["baseline"]["silent_handlers"]:
        problems.append(f"조용한 넓은 except {len(found)}건 > 기준 {cfg['baseline']['silent_handlers']}건: {found}")
    elif len(found) < cfg["baseline"]["silent_handlers"]:
        problems.append(f"조용한 넓은 except가 {len(found)}건으로 감소함. 기준선을 낮출 것")
    tests = test_functions(files)
    if tests < cfg["baseline"]["test_functions"]:
        problems.append(f"테스트 함수 {tests}개 < 기준 {cfg['baseline']['test_functions']}개")
    elif tests > cfg["baseline"]["test_functions"]:
        problems.append(f"테스트 함수가 {tests}개로 증가함. 기준선을 올릴 것")
    ruff = ruff_violations(files)
    if ruff is None:
        problems.append("ruff가 없음: python -m pip install -r requirements-dev.txt")
    elif ruff > cfg["baseline"]["ruff"]:
        problems.append(f"ruff 위반 {ruff}건 > 기준 {cfg['baseline']['ruff']}건")
    elif ruff < cfg["baseline"]["ruff"]:
        problems.append(f"ruff 위반이 {ruff}건으로 감소함. 기준선을 낮출 것")
    print(f"품질 래칫: 소스 {len(active)}개, 조용한 예외 {len(found)}건, 테스트 함수 {tests}개, ruff {ruff}건")
    if problems:
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
    print("미검사: 예외 처리의 의미, 권한, 문서의 사실성, 로그 유출, 본사 규정 전체")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="실패 상세 표시 (기본값과 동일)")
    parser.parse_args()
    return bool(check())


if __name__ == "__main__":
    raise SystemExit(main())
