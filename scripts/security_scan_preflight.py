"""본사 소스 검사 전에 중복 검사 경계를 확인한다."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    problems: list[str] = []
    debug_dir = ROOT / "debug"
    if debug_dir.exists():
        if not debug_dir.is_dir():
            problems.append("debug path is not a directory")
        else:
            entries = sorted(debug_dir.iterdir(), key=lambda path: path.name)
            if entries:
                names = ", ".join(path.name for path in entries[:10])
                remainder = f" and {len(entries) - 10} more" if len(entries) > 10 else ""
                problems.append(f"debug/ has {len(entries)} leftover entries: {names}{remainder}")

    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        problems.append(f"Cannot inspect Git worktrees: {result.stderr.strip()}")
    else:
        for line in result.stdout.splitlines():
            if not line.startswith("worktree "):
                continue
            worktree = Path(line.removeprefix("worktree ")).resolve()
            if worktree != ROOT and ROOT in worktree.parents:
                problems.append(f"Nested Git worktree: {worktree.relative_to(ROOT)}")

    if problems:
        print("Security scan preflight failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        print("Preserve active work; clean up finished artifacts, then retry.", file=sys.stderr)
        return 1

    print("Security scan preflight passed: no debug leftovers or nested Git worktrees.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
