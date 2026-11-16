param(
  [string]$OutputPath = "tauri/tauri.signing.conf.json"
)

$ErrorActionPreference = "Stop"
$base64 = $env:WINDOWS_CERTIFICATE_BASE64
$password = $env:WINDOWS_CERTIFICATE_PASSWORD
if ([string]::IsNullOrWhiteSpace($base64) -or [string]::IsNullOrWhiteSpace($password)) {
  Write-Output "signing=disabled"
  exit 0
}

$pfxPath = Join-Path $env:RUNNER_TEMP "kumoroute-signing.pfx"
[System.IO.File]::WriteAllBytes($pfxPath, [Convert]::FromBase64String($base64))
$securePassword = ConvertTo-SecureString -String $password -AsPlainText -Force
$certificate = Import-PfxCertificate -FilePath $pfxPath -CertStoreLocation "Cert:\CurrentUser\My" -Password $securePassword
$config = @{
  bundle = @{
    windows = @{
      certificateThumbprint = $certificate.Thumbprint
      digestAlgorithm = "sha256"
      timestampUrl = "http://timestamp.digicert.com"
    }
  }
}
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output "signing=ready"
Write-Output "thumbprint=$($certificate.Thumbprint)"
