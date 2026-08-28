#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$")
RELEASE_ROOT_FILES = (
    "aps.py",
    "install_cli.py",
    "install.sh",
    "install.ps1",
    "install.cmd",
    "VERSION",
    "README.md",
    "QUICKSTART_中文.txt",
)


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
    files = []
    for current, directories, filenames in os.walk(package, followlinks=False):
        current_path = Path(current)
        assert_safe_path(package, current_path)
        for name in [*directories, *filenames]:
            path = current_path / name
            assert_safe_path(package, path)
        directories[:] = [name for name in directories if name != ".git"]
        files.extend(
            current_path / name
            for name in filenames
            if "__pycache__" not in (current_path / name).parts and not name.endswith(".pyc")
        )
    return {
        p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(files)
    }


def refresh_manifest(bundle: Path) -> None:
    manifest_path = bundle / "package-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["payload_sha256"] = payload_hashes(bundle)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_release(root: Path, versions: dict[str, str]) -> None:
    if versions["APS_CLI"] != versions["AI_PROJECT_STANDARD"]:
        raise SystemExit("VERSION APS_CLI and AI_PROJECT_STANDARD must match")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)["\']', pyproject)
    if not match or match.group(1) != versions["APS_CLI"]:
        raise SystemExit("pyproject.toml version does not match VERSION APS_CLI")

    sys.path.insert(0, str(root / "src"))
    from aps_cli.installer import validate_bundle

    bundle_version, _ = validate_bundle(root / "src" / "aps_cli" / "bundle")
    if bundle_version != versions["AI_PROJECT_STANDARD"]:
        raise SystemExit("package manifest version does not match VERSION AI_PROJECT_STANDARD")


def tracked_files(root: Path) -> set[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("release build requires a Git checkout") from exc
    return {Path(name.replace("/", os.sep)) for name in result.stdout.decode("utf-8").split("\0") if name}


def assert_safe_path(root: Path, path: Path) -> None:
    root = root.resolve()
    current = path
    while True:
        try:
            attributes = getattr(os.lstat(current), "st_file_attributes", 0)
        except FileNotFoundError as exc:
            raise SystemExit(f"release path is missing: {path}") from exc
        if current.is_symlink() or (os.name == "nt" and attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise SystemExit(f"release path contains a link or reparse point: {path}")
        if current == root:
            return
        if root not in current.parents:
            raise SystemExit(f"release path escapes root: {path}")
        current = current.parent


def release_files(root: Path, tracked: set[Path]) -> list[Path]:
    paths = [root / relative for relative in RELEASE_ROOT_FILES]
    payload = root / "src" / "aps_cli"
    if not payload.is_dir():
        raise SystemExit("release source tree is missing: src/aps_cli")
    for current, directories, filenames in os.walk(payload, followlinks=False):
        current_path = Path(current)
        assert_safe_path(root, current_path)
        for name in [*directories, *filenames]:
            assert_safe_path(root, current_path / name)
        directories[:] = [name for name in directories if name != ".git"]
    paths.extend(
        path
        for path in payload.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(payload).parts and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    expected = {path.relative_to(root) for path in paths}
    untracked_payload = [
        path.relative_to(root)
        for path in payload.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(payload).parts and "__pycache__" not in path.parts and path.suffix != ".pyc" and path.relative_to(root) not in tracked
    ]
    if untracked_payload:
        raise SystemExit(f"release source contains untracked payload file: {untracked_payload[0]}")
    missing_tracked = [relative for relative in expected if relative not in tracked]
    if missing_tracked:
        raise SystemExit(f"release source file is not tracked: {missing_tracked[0]}")
    for path in paths:
        assert_safe_path(root, path)
        if not path.is_file():
            raise SystemExit(f"release source path is not a regular file: {path.relative_to(root)}")
    return sorted(paths)


def publish_assets(zip_path: Path, sha_path: Path, zip_tmp: Path, sha_tmp: Path) -> None:
    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    committed = False
    try:
        for target in (zip_path, sha_path):
            if target.exists():
                backup = target.with_name(f".{target.name}.old-{uuid.uuid4().hex}")
                os.replace(target, backup)
                backups[target] = backup
        os.replace(zip_tmp, zip_path)
        installed.append(zip_path)
        os.replace(sha_tmp, sha_path)
        installed.append(sha_path)
        committed = True
    except Exception as exc:
        for target in reversed(installed):
            try:
                target.unlink()
            except FileNotFoundError:
                pass
        for target, backup in backups.items():
            if backup.exists():
                os.replace(backup, target)
        raise SystemExit(f"release output transaction failed: {exc}") from exc
    finally:
        for temporary in (zip_tmp, sha_tmp):
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        if committed:
            for backup in backups.values():
                try:
                    backup.unlink()
                except FileNotFoundError:
                    pass

def main() -> int:
    ap = argparse.ArgumentParser(description="Build a verified APS release archive.")
    ap.add_argument("--refresh-manifest", action="store_true", help="rewrite payload checksums before building")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    versions = read_versions(root)
    bundle = root / "src" / "aps_cli" / "bundle"
    tracked = tracked_files(root)
    release = release_files(root, tracked)
    if args.refresh_manifest:
        refresh_manifest(bundle)
    validate_release(root, versions)
    version = versions["APS_CLI"]
    out = root / "dist"
    out.mkdir(exist_ok=True)
    zip_path = out / f"APS_CLI_{version}.zip"
    sha_path = out / f"APS_CLI_{version}.zip.sha256"
    with tempfile.NamedTemporaryFile(dir=out, prefix=f".{zip_path.name}.", suffix=".tmp", delete=False) as handle:
        zip_tmp = Path(handle.name)
    with tempfile.NamedTemporaryFile(dir=out, prefix=f".{sha_path.name}.", suffix=".tmp", delete=False) as handle:
        sha_tmp = Path(handle.name)
    try:
        with zipfile.ZipFile(zip_tmp, "w", zipfile.ZIP_DEFLATED) as z:
            base = f"APS_CLI_{version}"
            for p in release:
                rel = p.relative_to(root)
                z.write(p, f"{base}/{rel.as_posix()}")
        digest = hashlib.sha256(zip_tmp.read_bytes()).hexdigest()
        sha_tmp.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
        publish_assets(zip_path, sha_path, zip_tmp, sha_tmp)
    finally:
        for temporary in (zip_tmp, sha_tmp):
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    print(zip_path)
    print(sha_path)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
