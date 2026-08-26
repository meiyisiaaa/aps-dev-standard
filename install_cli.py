#!/usr/bin/env python3
"""Offline installer for the `aps` command. No pip or third-party dependencies."""
from __future__ import annotations

import argparse
import os
import shutil
import site
import sys
import uuid
from pathlib import Path


def default_prefix() -> Path:
    if os.name == "nt":
        return Path(site.USER_BASE)
    return Path.home() / ".local"


def read_version(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "APS_CLI" and value.strip():
            return value.strip()
    raise RuntimeError("APS_CLI version not found in VERSION")


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def promote_directory(staged: Path, target: Path) -> None:
    backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
    had_target = target.exists() or target.is_symlink()
    moved_target = False
    completed = False
    try:
        if had_target:
            target.replace(backup)
            moved_target = True
        staged.replace(target)
        completed = True
    except Exception:
        if moved_target and (target.exists() or target.is_symlink()):
            remove_path(target)
        if moved_target and (backup.exists() or backup.is_symlink()):
            backup.replace(target)
        raise
    finally:
        if completed and (backup.exists() or backup.is_symlink()):
            remove_path(backup)


def main() -> int:
    ap = argparse.ArgumentParser(description="Install APS CLI without pip")
    ap.add_argument("--prefix", type=Path, default=default_prefix(), help="installation prefix")
    args = ap.parse_args()

    src_root = Path(__file__).resolve().parent
    version = read_version(src_root / "VERSION")
    prefix = args.prefix.expanduser().resolve()
    app_root = prefix / ("share" if os.name != "nt" else "share") / "aps-cli"
    version_root = app_root / version
    current_root = app_root / "current"
    bin_dir = prefix / ("Scripts" if os.name == "nt" else "bin")

    app_root.mkdir(parents=True, exist_ok=True)
    staged_version = app_root / f".{version}.staging-{uuid.uuid4().hex}"
    staged_current = app_root / f".current.staging-{uuid.uuid4().hex}"
    try:
        staged_version.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_root / "aps.py", staged_version / "aps.py")
        shutil.copytree(src_root / "src" / "aps_cli", staged_version / "src" / "aps_cli")
        shutil.copy2(src_root / "VERSION", staged_version / "VERSION")
        promote_directory(staged_version, version_root)

        # Copy instead of symlink for Windows and restricted environments.
        shutil.copytree(version_root, staged_current)
        promote_directory(staged_current, current_root)
    finally:
        for temporary in (staged_version, staged_current):
            if temporary.exists() or temporary.is_symlink():
                remove_path(temporary)

    bin_dir.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).resolve()
    if os.name == "nt":
        launcher = bin_dir / "aps.cmd"
        launcher.write_text(
            f'@echo off\r\n"{python}" "{current_root / "aps.py"}" %*\r\n',
            encoding="utf-8",
        )
    else:
        launcher = bin_dir / "aps"
        launcher.write_text(
            f'#!/bin/sh\nexec "{python}" "{current_root / "aps.py"}" "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)

    print(f"Installed APS CLI {version}")
    print(f"Launcher: {launcher}")
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if str(bin_dir) not in path_parts:
        print("\nPATH note:")
        if os.name == "nt":
            print(f"Add this directory to PATH: {bin_dir}")
            print(f'Current PowerShell session: $env:Path += "{bin_dir}"')
            print("Open a new terminal after adding it permanently.")
            print(f"Until then run: {launcher}")
        else:
            print(f'Add this to your shell profile: export PATH="{bin_dir}:$PATH"')
            print(f"Until then run: {launcher}")
    else:
        print("\nRun: aps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
