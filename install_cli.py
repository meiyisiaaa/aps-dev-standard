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


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def read_version(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "APS_CLI" and value.strip():
            return value.strip()
    raise RuntimeError("VERSION 中没有 APS_CLI 版本")


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


def _install() -> int:
    ap = argparse.ArgumentParser(description="无需 pip 安装 APS CLI")
    ap.add_argument("--prefix", type=Path, default=default_prefix(), help="安装前缀")
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

    print(f"OK    APS CLI {version} 安装完成。")
    print(f"安装位置：{app_root}")
    print(f"启动器：{launcher}")
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if str(bin_dir) not in path_parts:
        print("\nPATH 操作：")
        if os.name == "nt":
            print(f"将此目录加入 PATH：{bin_dir}")
            print(f'当前 PowerShell 会话：$env:Path += "{bin_dir}"')
            print("永久加入后请重新打开终端。")
            print(f"加入前可直接运行：{launcher}")
        else:
            print(f'将以下内容加入 shell profile：export PATH="{bin_dir}:$PATH"')
            print(f"加入前可直接运行：{launcher}")
    else:
        print(f"\nPATH：已包含 {bin_dir}")
    print("NEXT  进入项目目录后运行 `aps`；新项目用 `aps init --no-launch`，已有项目用 `aps resume --no-launch`。")
    return 0


def main() -> int:
    configure_stdio()
    try:
        return _install()
    except Exception as exc:
        print(f"FAIL  APS CLI 安装失败：{exc}", file=sys.stderr)
        print("原因：安装文件无法安全写入目标位置，或当前 Python/权限不满足要求。", file=sys.stderr)
        print("NEXT  检查 `--prefix` 目录权限后重试，例如：`python install_cli.py --prefix <PREFIX>`。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
