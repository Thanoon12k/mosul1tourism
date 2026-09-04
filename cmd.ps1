$ErrorActionPreference='Continue'
Set-Location $PSScriptRoot
$tokenFile = Join-Path $PSScriptRoot '.pa_token'
if (-not (Test-Path $tokenFile)) {
  Write-Output 'No .pa_token yet - opening a prompt window (check your screen)...'
  Add-Type -AssemblyName Microsoft.VisualBasic
  $tokenValue = [Microsoft.VisualBasic.Interaction]::InputBox(
        "Paste your PythonAnywhere API token.`r`n`r`nGet it at:`r`nhttps://www.pythonanywhere.com/account/#api_token",
        'PythonAnywhere API token', '')
  if ([string]::IsNullOrWhiteSpace($tokenValue)) {
    Write-Output '! cancelled - no token'
    exit 1
  }
  Set-Content -LiteralPath $tokenFile -Value $tokenValue.Trim() -NoNewline -Encoding ascii
  Write-Output ('  saved .pa_token ({0} chars)' -f $tokenValue.Trim().Length)
}

& python -u "$PSScriptRoot\deploy.py" `
  --user harith1mosul1tourist `
  --kind flask `
  --src "$PSScriptRoot" `
  --remote '/home/harith1mosul1tourist/harthwebsite' `
  --app 'app:app' 2>&1 | ForEach-Object { Write-Output $_ }
$deployExit = $LASTEXITCODE
Write-Output ('deploy_exit=' + $deployExit)
if ($deployExit -ne 0) { exit $deployExit }

[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
foreach ($verifyUrl in @(
  'https://harith1mosul1tourist.pythonanywhere.com/',
  'https://harith1mosul1tourist.pythonanywhere.com/static/css/style.css',
  'https://harith1mosul1tourist.pythonanywhere.com/static/images/hotels/ramada-mosul.avif'
)) {
  try {
    $verifyResponse = Invoke-WebRequest $verifyUrl -UseBasicParsing -TimeoutSec 45
    Write-Output ("{0}`n    HTTP {1}  {2} bytes  type={3}" -f $verifyUrl,$verifyResponse.StatusCode,$verifyResponse.RawContentLength,$verifyResponse.Headers['Content-Type'])
    $titleMatch = ([regex]'<title>(.*?)</title>').Match($verifyResponse.Content)
    if ($titleMatch.Success) { Write-Output ('    TITLE: ' + $titleMatch.Groups[1].Value) }
  } catch {
    Write-Output ("{0}`n    FAILED: {1}" -f $verifyUrl,$_.Exception.Message)
  }
}
