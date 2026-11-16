param(
  [Parameter(Mandatory=$true)][ValidateSet('portable','rollback')][string]$Action,
  [string]$Archive = '',
  [Parameter(Mandatory=$true)][string]$AppDir,
  [Parameter(Mandatory=$true)][string]$Exe,
  [Parameter(Mandatory=$true)][string]$Backup
)
$ErrorActionPreference = 'Stop'
$updateRoot = Split-Path -Parent $Backup
$logPath = Join-Path $updateRoot 'apply-update.log'
Start-Transcript -Path $logPath -Append | Out-Null
function Wait-KumoRouteExit {
  for ($i = 0; $i -lt 80; $i++) {
    try {
      $stream = [System.IO.File]::Open($Exe, 'Open', 'ReadWrite', 'None')
      $stream.Close()
      return
    } catch { Start-Sleep -Milliseconds 500 }
  }
  throw 'KumoRoute 程式檔仍在執行，無法完成更新。'
}
function Restore-Backup {
  if (Test-Path -LiteralPath $Backup) {
    Copy-Item -Path (Join-Path $Backup '*') -Destination $AppDir -Recurse -Force
    Start-Process -FilePath $Exe -WorkingDirectory $AppDir
  }
}
try {
  Start-Sleep -Milliseconds 1200
  Wait-KumoRouteExit
  if ($Action -eq 'portable') {
    $temp = Join-Path $env:TEMP ('KumoRoute-update-' + [guid]::NewGuid().ToString('N'))
    try {
      Expand-Archive -LiteralPath $Archive -DestinationPath $temp -Force
      $source = Join-Path $temp 'KumoRoute'
      if (-not (Test-Path -LiteralPath (Join-Path $source 'KumoRoute.exe'))) { throw '更新 ZIP 內容不完整。' }
      Copy-Item -Path (Join-Path $source '*') -Destination $AppDir -Recurse -Force
    } finally {
      if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
    }
  } else {
    Copy-Item -Path (Join-Path $Backup '*') -Destination $AppDir -Recurse -Force
  }
  Start-Process -FilePath $Exe -WorkingDirectory $AppDir
} catch {
  ($_ | Out-String) | Add-Content -LiteralPath $logPath
  Restore-Backup
  exit 1
} finally {
  Stop-Transcript | Out-Null
}
