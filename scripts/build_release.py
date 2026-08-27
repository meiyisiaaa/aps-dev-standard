#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$")


def read_versions(root: Path) -> dict[str, str]:
    values = {}
    for line in (root / "VERSION").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and value.strip():
            values[key.strip()] = value.strip()
    if not values.get("APS_CLI") or not values.get("AI_PROJECT_STANDARD"):
        raise SystemExit("VERSION must define APS_CLI and AI_PROJECT_STANDARD")
    if any(not VERSION_RE.fullmatch(values[key]) for key in ("APS_CLI", "AI_PROJECT_STANDARD")):
        raise SystemExit("VERSION contains an unsafe version")
    return values


def payload_hashes(bundle: Path) -> dict[str, str]:
    package = bundle / "package"
    return {
        p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(package.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def refresh_manifest(bundle: Path) -> None:
    manifest_path = bundle / "package-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["payload_sha256"] = payload_hashes(bundle)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_release(root: Path, versions: dict[str, str]) -> None:
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)["\']', pyproject)
    if not match or match.group(1) != versions["APS_CLI"]:
        raise SystemExit("pyproject.toml version does not match VERSION APS_CLI")

    sys.path.insert(0, str(root / "src"))
    from aps_cli.installer import validate_bundle

    bundle_version, _ = validate_bundle(root / "src" / "aps_cli" / "bundle")
    if bundle_version != versions["AI_PROJECT_STANDARD"]:
        raise SystemExit("package manifest version does not match VERSION AI_PROJECT_STANDARD")


def tracked_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("release build requires a Git checkout") from exc
    return [root / name for name in result.stdout.decode("utf-8").split("\0") if name]

def main() -> int:
    ap = argparse.ArgumentParser(description="Build a verified APS release archive.")
    ap.add_argument("--refresh-manifest", action="store_true", help="rewrite payload checksums before building")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    versions = read_versions(root)
    bundle = root / "src" / "aps_cli" / "bundle"
    if args.refresh_manifest:
        refresh_manifest(bundle)
    validate_release(root, versions)
    version = versions["APS_CLI"]
    out = root / "dist"
    out.mkdir(exist_ok=True)
    for old in out.glob("APS_CLI_*"):
        if old.is_file(): old.unlink()
    zip_path = out / f"APS_CLI_{version}.zip"
    sha_path = out / f"APS_CLI_{version}.zip.sha256"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        base = f"APS_CLI_{version}"
        for p in tracked_files(root):
            rel = p.relative_to(root)
            if p.is_file():
                z.write(p, Path(base) / rel)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(zip_path)
    print(sha_path)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
