$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "../.venv/Scripts/python.exe"
& $python -m ruff check app tests migrations
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $python -m mypy app
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $python -m pytest
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $python -m pip_audit -r (Join-Path $PSScriptRoot "../requirements.lock")
exit $LASTEXITCODE
