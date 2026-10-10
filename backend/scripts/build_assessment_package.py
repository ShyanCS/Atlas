"""Allowlisted source export; no environments, caches, databases or live geometry."""

import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
excluded = {
    ".venv",
    ".local",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".vite",
    "coverage",
    "staticfiles",
}
files = [ROOT / "render.yaml", ROOT / ".gitignore"]
for base in (ROOT / "backend", ROOT / "frontend"):
    for directory, folders, names in os.walk(base):
        folders[:] = [p for p in folders if p not in excluded and not p.endswith(".egg-info")]
        for name in names:
            path = Path(directory) / name
            if name.startswith(".env") and name not in {".env.example", ".env.deployment.example"}:
                continue
            if (
                name.startswith(".local")
                or ".sqlite3" in name
                or path.suffix in {".sqlite3", ".pyc", ".log", ".tsbuildinfo"}
                or name.startswith(".coverage")
            ):
                continue
            files.append(path)
files.extend((ROOT / "docs/deployment").glob("*.md"))
files.append(ROOT / "docs/implementation/DEPLOYMENT_READINESS_REPORT.md")
for path in (ROOT / "docs/implementation/evidence/deployment-preparation").rglob("*"):
    if (
        path.is_file()
        and path.name != "release-package-scan.json"
        and path.suffix in {".json", ".txt", ".png", ".md"}
    ):
        files.append(path)
known_secrets = []
for path in ROOT.glob(".env*"):
    if path.name.endswith(".example"):
        continue
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            if (
                any(word in name.upper() for word in ("KEY", "TOKEN", "SECRET"))
                and len(value) >= 12
            ):
                known_secrets.append(value.encode())
manifest = []
build_assets = []
for path in sorted((ROOT / "frontend/dist").rglob("*")):
    if path.is_file():
        content = path.read_bytes()
        if any(secret in content for secret in known_secrets):
            raise SystemExit("Known credential found in compiled frontend; no archive created.")
        if len(content) > 25 * 1024**2:
            raise SystemExit("Compiled asset exceeds the prepared Pages per-file size ceiling.")
        build_assets.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
for path in sorted(set(files)):
    content = path.read_bytes()
    if any(secret in content for secret in known_secrets):
        raise SystemExit("Known credential found in export content; no archive created.")
    manifest.append(
        {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    )
readme = """# Spotter Atlas assessment source release

Prepared locally; nothing has been deployed or published. See docs/deployment/SETUP.md
and docs/implementation/DEPLOYMENT_READINESS_REPORT.md for exact setup and remaining actions.
This archive includes app source/tests and sanitized current evidence. The full workspace
retains original assessments, designs and historical research separately.
Use backend/requirements.deploy.txt on Render, frontend/package-lock.json on Pages, and
the documented private hosted variables. Rebuild frontend with the selected HTTPS API URL.
No compiled local frontend, private environment, database, provider geometry, native weather
decoder, dependency directory or historical archive is included.
Do not enable hosted live access until the release permission switches are authorized.
"""
archive = ROOT / "spotter-atlas-assessment-release.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
    output.writestr("README.md", readme)
    for record in manifest:
        output.write(ROOT / record["path"], record["path"])
    output.writestr("SOURCE_MANIFEST.json", json.dumps(manifest, indent=2))
with zipfile.ZipFile(archive) as output:
    assert output.testzip() is None
    assert not any(part in excluded for name in output.namelist() for part in Path(name).parts)
    assert not any(
        secret in output.read(name) for name in output.namelist() for secret in known_secrets
    )
report = {
    "status": "PASS",
    "archive": archive.name,
    "bytes": archive.stat().st_size,
    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "files": len(manifest),
    "known_credential_matches": 0,
    "source_only": True,
    "compiled_frontend_known_credential_matches": 0,
    "build_assets": build_assets,
    "git_commit_scan": "Not available: no Git repository initialized or selected.",
    "manifest": manifest,
}
(ROOT / "docs/implementation/evidence/deployment-preparation/release-package-scan.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
print(json.dumps({key: value for key, value in report.items() if key != "manifest"}))
