$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$tokenFile = Join-Path $PSScriptRoot '.pa_token'
if (-not (Test-Path -LiteralPath $tokenFile)) {
    throw 'Missing .pa_token. Run the watcher deployment once to save the PythonAnywhere API token.'
}

& python -u "$PSScriptRoot\deploy.py" `
    --user harith1mosul1tourist `
    --kind flask `
    --src "$PSScriptRoot" `
    --remote '/home/harith1mosul1tourist/harthwebsite' `
    --app 'app:app'

if ($LASTEXITCODE -ne 0) {
    throw "PythonAnywhere deployment failed with exit code $LASTEXITCODE."
}

$liveUrl = 'https://harith1mosul1tourist.pythonanywhere.com/'
$response = Invoke-WebRequest -Uri $liveUrl -UseBasicParsing -TimeoutSec 45
Write-Output "Verified $liveUrl - HTTP $($response.StatusCode)"
