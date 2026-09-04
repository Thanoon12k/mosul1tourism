$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    py -m venv .venv
    & $pythonPath -m pip install --disable-pip-version-check -r requirements.txt
}

& $pythonPath app.py
