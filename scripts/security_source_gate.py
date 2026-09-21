"""본사 자가점검의 작성 소스 회귀를 커밋 전과 CI에서 막는다.

본사 검사기의 모든 정규식을 복제하지 않는다. 확실한 위반은 전체 소스에서 막고,
맥락에 따라 안전할 수 있는 API는 새 사용만 검토 대상으로 올린다.
"""

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REVIEW_FILE = ROOT / "scripts" / "security_reviewed.json"
JS_SUFFIXES = {".js", ".mjs", ".jsx", ".ts", ".tsx"}
PYTHON_ROOTS = {"analysis", "extract", "scripts", "tests"}
JS_ROOTS = {"static/js", "tests/js"}

# 차단 규칙에는 안전한 사용을 숨기는 예외를 두지 않는다.
JS_BLOCK = {
    "JS-32": [
        re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}"),
        re.compile(r"\.catch\s*\(\s*(?:\([^)]*\)|[\w$]+)\s*=>\s*\{\s*\}\s*\)"),
        re.compile(r"\.catch\s*\(\s*function\s*\([^)]*\)\s*\{\s*\}\s*\)"),
    ],
    "JS-02": [
        re.compile(r"(?<![\w$.])eval\s*\("),
        re.compile(r"\bnew\s+Function\s*\("),
    ],
    "JS-04": [re.compile(r"\bdocument\.write\s*\(")],
}

# 이 API는 맥락에 따라 안전할 수 있다. 새 사용은 근거를 적어 검토한다.
JS_REVIEW = {
    "JS-04": [
        re.compile(r"\b(?:innerHTML|outerHTML)\s*=(?!=)"),
        re.compile(r"\binsertAdjacentHTML\s*\("),
        re.compile(r"\bdangerouslySetInnerHTML\b"),
    ],
    "JS-36": [re.compile(r"\bJSON\.parse\s*\(")],
    "JS-07": [
        re.compile(r"\b(?:window\.location(?:\.href)?|location\.href)\s*="),
        re.compile(r"\b(?:window\.)?location\.(?:assign|replace)\s*\("),
    ],
    "JS-21": [re.compile(r"\bMath\.random\s*\(")],
    "JS-38": [re.compile(r"\bconsole\.(?:log|debug)\s*\(")],
}


def _git(*args: str, missing_ok: bool = False) -> bytes:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if result.returncode and not missing_ok:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout if result.returncode == 0 else b""


def _tracked_paths() -> list[str]:
    return [path.decode("utf-8") for path in _git("ls-files", "-z").split(b"\0") if path]


def _changed_paths(base: str, head: str) -> list[str]:
    args = (
        ("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMRT")
        if head == ":"
        else ("diff", "--name-only", "-z", "--diff-filter=ACMRT", base, head)
    )
    return [path.decode("utf-8") for path in _git(*args).split(b"\0") if path]


def _source(ref: str, path: str) -> str:
    spec = f":{path}" if ref == ":" else f"{ref}:{path}"
    return _git("show", spec, missing_ok=True).decode("utf-8-sig", errors="replace")


def _authored(path: str) -> bool:
    path = path.replace("\\", "/")
    suffix = Path(path).suffix
    if suffix == ".py":
        return "/" not in path or path.split("/", 1)[0] in PYTHON_ROOTS
    return suffix in JS_SUFFIXES and any(path.startswith(root + "/") for root in JS_ROOTS)


def mask_js(source: str) -> str:
    """문자열·주석의 검사기 예제는 실행 코드로 취급하지 않는다."""
    chars = list(source)
    index = 0
    while index < len(chars):
        char = chars[index]
        following = chars[index + 1] if index + 1 < len(chars) else ""
        if char in ('"', "'", "`"):
            quote = char
            start = index
            index += 1
            while index < len(chars):
                if chars[index] == "\\":
                    index += 2
                    continue
                if chars[index] == quote:
                    index += 1
                    break
                index += 1
            for offset in range(start, min(index, len(chars))):
                if chars[offset] != "\n":
                    chars[offset] = " "
            continue
        if char == "/" and following in ("/", "*"):
            start = index
            index += 2
            if following == "/":
                while index < len(chars) and chars[index] != "\n":
                    index += 1
            else:
                while index + 1 < len(chars) and chars[index:index + 2] != ["*", "/"]:
                    index += 1
                index = min(index + 2, len(chars))
            for offset in range(start, index):
                if chars[offset] != "\n":
                    chars[offset] = " "
            continue
        index += 1
    return "".join(chars)


def _findings_for_js(path: str, source: str, review: bool) -> list[tuple[str, str, int, str]]:
    masked = mask_js(source)
    patterns = JS_REVIEW if review else JS_BLOCK
    found = []
    for rule, expressions in patterns.items():
        for expression in expressions:
            for match in expression.finditer(masked):
                line = masked.count("\n", 0, match.start()) + 1
                line_start = masked.rfind("\n", 0, match.start()) + 1
                line_end = masked.find("\n", match.end())
                if line_end < 0:
                    line_end = len(masked)
                code = " ".join(masked[line_start:line_end].split())
                found.append((rule, path, line, code))
    return found


def _safe_psycopg_composition(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    method = node.func
    if method.attr != "format" or not isinstance(method.value, ast.Call):
        return False
    constructor = method.value.func
    if not isinstance(constructor, ast.Attribute) or not isinstance(constructor.value, ast.Name):
        return False
    if (constructor.value.id, constructor.attr) != ("sql", "SQL"):
        return False
    values = [*node.args, *(keyword.value for keyword in node.keywords)]
    return bool(values) and all(
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and isinstance(value.func.value, ast.Name)
        and (value.func.value.id, value.func.attr) in {("sql", "Identifier"), ("sql", "Literal")}
        for value in values
    )


def _sql_shaped(node: ast.AST) -> bool:
    literals = [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]
    return any(
        re.search(
            r"\b(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|ALTER|DROP)\b",
            literal,
            re.IGNORECASE,
        )
        for literal in literals
    )


def _findings_for_python(path: str, source: str) -> list[tuple[str, str, int, str]]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        return [("PY-SYNTAX", path, error.lineno or 1, error.msg)]
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ExceptHandler)
            and len(node.body) == 1
            and isinstance(node.body[0], (ast.Pass, ast.Continue))
        ):
            found.append(("PY-37", path, node.lineno, " ".join(ast.unparse(node).split())))
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"execute", "executemany"} or not node.args:
            continue
        query = node.args[0]
        if _safe_psycopg_composition(query):
            continue
        if _sql_shaped(query) and (
            isinstance(query, (ast.JoinedStr, ast.BinOp))
            or (
                isinstance(query, ast.Call)
                and isinstance(query.func, ast.Attribute)
                and query.func.attr == "format"
            )
        ):
            found.append(("PY-01", path, node.lineno, " ".join(ast.unparse(query).split())))
    return found


def _scan(path: str, source: str, review: bool = False) -> list[tuple[str, str, int, str]]:
    if not _authored(path):
        return []
    if Path(path).suffix == ".py":
        return [] if review else _findings_for_python(path, source)
    return _findings_for_js(path, source, review)


def _reviewed() -> set[tuple[str, str, str]]:
    entries = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("security_reviewed.json must be a list")
    allowed = set()
    for entry in entries:
        if not all(
            isinstance(entry.get(key), str) and entry[key].strip()
            for key in ("rule", "path", "code", "reason")
        ):
            raise ValueError("Reviewed entries need rule, path, code and reason")
        if len(entry["reason"].strip()) < 20:
            raise ValueError("Reviewed reason is too short to explain the safe boundary")
        allowed.add((entry["rule"], entry["path"], entry["code"]))
    return allowed


def check(mode: str, base: str | None = None, head: str | None = None) -> list[tuple[str, str, int, str]]:
    paths = _tracked_paths() if mode == "all" else _changed_paths(base or "HEAD", head or ":")
    allowed = _reviewed()
    problems = []
    for path in paths:
        if not _authored(path):
            continue
        if mode == "all" and not (ROOT / path).is_file():
            continue
        newer = (
            (ROOT / path).read_text(encoding="utf-8-sig")
            if mode == "all"
            else _source(head or ":", path)
        )
        problems.extend(_scan(path, newer))
        if mode == "all":
            continue
        older = _source(base or "HEAD", path)
        previous = Counter((rule, code) for rule, _, _, code in _scan(path, older, review=True))
        for finding in _scan(path, newer, review=True):
            rule, filename, _, code = finding
            key = (rule, code)
            if previous[key]:
                previous[key] -= 1
            elif (rule, filename, code) not in allowed:
                problems.append(finding)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Check authored source security regressions.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="Check certain violations in all authored sources.")
    mode.add_argument("--staged", action="store_true", help="Check new risky APIs in staged changes.")
    mode.add_argument(
        "--range",
        nargs=2,
        metavar=("BASE", "HEAD"),
        help="Check new risky APIs between Git refs.",
    )
    args = parser.parse_args()
    if args.all:
        problems = check("all")
    elif args.staged:
        problems = check("staged", "HEAD", ":")
    else:
        problems = check("range", *args.range)
    if problems:
        for rule, path, line, code in problems:
            print(f"{rule} {path}:{line}: {code}", file=sys.stderr)
        print(
            "Fix blocked patterns. For context-dependent APIs, verify the boundary and add an exact "
            "entry with a Korean reason to scripts/security_reviewed.json.",
            file=sys.stderr,
        )
        return 1
    print(f'Security source gate passed ({"all" if args.all else "changed"} sources).')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
