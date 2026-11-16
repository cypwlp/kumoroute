param(
  [Parameter(Mandatory=$true)][string]$Path
)

$signature = Get-AuthenticodeSignature -FilePath $Path
Write-Output "status=$($signature.Status) signer=$($signature.SignerCertificate.Subject)"
if ($signature.Status -ne "Valid") {
  exit 1
}
