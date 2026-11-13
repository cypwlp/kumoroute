# Security Policy

## Reporting

Please report security issues privately through GitHub Security Advisories when available, or contact the maintainers through the repository issue tracker without including secrets, subscription tokens, or personal data.

## Release Security

- KumoRoute does not provide proxy nodes or subscriptions.
- Release installers are currently unsigned. Windows SmartScreen and macOS Gatekeeper warnings are expected until code-signing credentials are configured.
- The application does not automatically download or execute unsigned installers.
- On Windows, the bundled mihomo process is attached to a kill-on-close Job Object and the NSIS installer checks it before replacing files.
- CI runs RustSec `cargo audit`, Python `pip-audit`, and generates an SBOM artifact.
- Diagnostics are generated locally and can be previewed before export. The exporter redacts URLs, IP addresses, log endpoints, and common secret fields.

## Supported Versions

Security fixes are applied to the latest release on the `main` branch.