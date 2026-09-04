$c=Join-Path $PSScriptRoot 'cmd.ps1'; $o=Join-Path $PSScriptRoot 'out.txt'
$tag='{0:x8}_{1}' -f ($PSScriptRoot.ToLower().GetHashCode() -band 0x7fffffff),$PID
$to=Join-Path $env:TEMP "w_$tag.out"; $te=Join-Path $env:TEMP "w_$tag.err"
if(-not(Test-Path $c)){Set-Content $c '"ready"'}
Write-Host "`n  WATCHING cmd.ps1 -> out.txt`n  Anything written here RUNS. Close window to stop.`n  buffer: $to`n" -ForegroundColor Cyan
$last=(Get-Item $c).LastWriteTimeUtc
while($true){
  Start-Sleep -Milliseconds 1500
  $s=(Get-Item $c).LastWriteTimeUtc; if($s -eq $last){continue}; $last=$s
  Start-Sleep -Milliseconds 400
  $body=Get-Content $c -Raw; if(-not $body){continue}
  Write-Host "`n=== RUN $(Get-Date -F HH:mm:ss) ===" -ForegroundColor Cyan
  Remove-Item $to,$te -Force -EA SilentlyContinue; New-Item -Type File $to,$te -Force|Out-Null
  $sw=[Diagnostics.Stopwatch]::StartNew()
  $p=Start-Process powershell '-NoProfile','-ExecutionPolicy','Bypass','-File',$c -NoNewWindow -PassThru -RedirectStandardOutput $to -RedirectStandardError $te
  $n=0
  while(-not $p.HasExited){
    Start-Sleep -Milliseconds 500
    $L=@(Get-Content $to -EA SilentlyContinue)
    if($L.Count -gt $n){$L[$n..($L.Count-1)]|%{Write-Host $_}; $n=$L.Count}
    if($sw.Elapsed.TotalSeconds -gt 600){Stop-Process $p.Id -Force -EA SilentlyContinue;break}
  }
  Start-Sleep -Milliseconds 600
  $L=@(Get-Content $to -EA SilentlyContinue); if($L.Count -gt $n){$L[$n..($L.Count-1)]|%{Write-Host $_}}
  @("RUN $(Get-Date -F 'yyyy-MM-dd HH:mm:ss')  $([math]::Round($sw.Elapsed.TotalSeconds,1))s  exit=$($p.ExitCode)",
    '--- COMMAND ---',$body.TrimEnd(),'--- STDOUT ---',
    (Get-Content $to -Raw),'--- STDERR ---',(Get-Content $te -Raw)) -join "`r`n" | Set-Content $o -Encoding UTF8
  Write-Host "  -> out.txt" -ForegroundColor Green
}
