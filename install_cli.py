#!/usr/bin/env python3
"""Offline installer for the `aps` command. No pip or third-party dependencies."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import site
import stat
import sys
import tempfile
import uuid
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$")


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
            version = value.strip()
            if not VERSION_RE.fullmatch(version):
                raise RuntimeError(f"VERSION 版本不安全：{version}")
            return version
    raise RuntimeError("VERSION 中没有 APS_CLI 版本")


def is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if os.name == "nt":
            return bool(getattr(os.lstat(path), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except FileNotFoundError:
        return False
    return False


def assert_no_reparse(path: Path) -> None:
    current = path
    while True:
        if is_reparse_point(current):
            raise RuntimeError(f"安装路径不能包含符号链接或 Windows reparse point：{current}")
        if current.parent == current:
            return
        current = current.parent


def remove_path(path: Path) -> None:
    if is_reparse_point(path) or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def promote_directory(staged: Path, target: Path) -> None:
    assert_no_reparse(staged)
    assert_no_reparse(target)
    assert_no_reparse(target.parent)
    backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
    had_target = target.exists() or target.is_symlink()
    if had_target and not target.is_dir():
        raise RuntimeError(f"安装目标不是目录：{target}")
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


def write_launcher_atomic(path: Path, content: str, mode: int | None = None) -> None:
    assert_no_reparse(path)
    if path.exists() and not path.is_file():
        raise RuntimeError(f"启动器目标不是普通文件：{path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.tmp-",
            suffix="",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _install() -> int:
    ap = argparse.ArgumentParser(description="无需 pip 安装 APS CLI")
    ap.add_argument("--prefix", type=Path, default=default_prefix(), help="安装前缀")
    args = ap.parse_args()

    src_root = Path(__file__).resolve().parent
    version = read_version(src_root / "VERSION")
    prefix = args.prefix.expanduser()
    assert_no_reparse(prefix)
    prefix = prefix.resolve()
    app_root = prefix / ("share" if os.name != "nt" else "share") / "aps-cli"
    version_root = app_root / version
    current_root = app_root / "current"
    bin_dir = prefix / ("Scripts" if os.name == "nt" else "bin")

    assert_no_reparse(app_root)
    assert_no_reparse(version_root)
    assert_no_reparse(current_root)
    assert_no_reparse(bin_dir)
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
        write_launcher_atomic(
            launcher,
            f'@echo off\r\n"{python}" "{current_root / "aps.py"}" %*\r\n',
        )
    else:
        launcher = bin_dir / "aps"
        write_launcher_atomic(
            launcher,
            f'#!/bin/sh\nexec "{python}" "{current_root / "aps.py"}" "$@"\n',
            mode=0o755,
        )

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
