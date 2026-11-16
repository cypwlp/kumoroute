# Windows Code Signing

KumoRoute can build unsigned releases. To enable Authenticode signing, configure these GitHub Actions repository secrets:

| Secret | Purpose |
|---|---|
| `WINDOWS_CERTIFICATE_BASE64` | Base64-encoded PFX/P12 code-signing certificate |
| `WINDOWS_CERTIFICATE_PASSWORD` | Password for the PFX/P12 file |

The release workflow imports the certificate into the current user's certificate store, generates `tauri/tauri.signing.conf.json`, and passes it to `tauri build --config`.

The signing configuration uses:

- `certificateThumbprint`: imported certificate SHA-1 thumbprint
- `digestAlgorithm`: `sha256`
- `timestampUrl`: `http://timestamp.digicert.com`

When the secrets are not configured, the workflow continues with an unsigned build and prints `signing=disabled`.

## Creating the Base64 value

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\to\certificate.pfx"))
```

Store the output as `WINDOWS_CERTIFICATE_BASE64`; never commit the PFX, password, or generated signing configuration.

## Verification

When signing is enabled, the workflow runs:

```powershell
Get-AuthenticodeSignature dist/KumoRoute-win-x64-setup.exe
```

The build fails unless the signature status is `Valid`.

## Local testing

Set the two environment variables and run:

```powershell
./scripts/prepare_windows_signing.ps1
cd tauri
tauri build --config tauri.signing.conf.json
```

For an EV certificate, follow the certificate provider's hardware/token and timestamping instructions. A newly issued certificate can still take time to build SmartScreen reputation.
