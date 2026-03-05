"""
Build a combined CA certificate bundle:
  - macOS System keychain (includes corporate proxy CA)
  - macOS SystemRootCertificates keychain
  - macOS login keychain
  - certifi's bundled Mozilla roots

Output: certs/ca-bundle.pem
Run once after cloning:  python build_cert_bundle.py
"""
import certifi
import subprocess
import pathlib

KEYCHAINS = [
    "/Library/Keychains/System.keychain",
    "/System/Library/Keychains/SystemRootCertificates.keychain",
    str(pathlib.Path.home() / "Library/Keychains/login.keychain-db"),
]

pathlib.Path(".venv").mkdir(exist_ok=True)
out = pathlib.Path(".venv/ca-bundle.pem")

parts = []

for kc in KEYCHAINS:
    result = subprocess.run(
        ["security", "find-certificate", "-a", "-p", kc],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        parts.append(f"# --- {kc}\n" + result.stdout)

parts.append("# --- certifi mozilla bundle\n" + pathlib.Path(certifi.where()).read_text())

combined = "\n".join(parts)
out.write_text(combined)
print(f"✅  {out}  ({combined.count('BEGIN CERTIFICATE')} certificates)")
