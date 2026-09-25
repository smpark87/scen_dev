# OUTLOOK 로컬 실행은 공용 Python 환경을 사용한다.
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path (Split-Path -Parent $projectRoot) 'shared/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'shared/.venv가 없습니다. docs/SETUP.md를 확인하세요.'
}
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m outlook
    $appExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $appExitCode
