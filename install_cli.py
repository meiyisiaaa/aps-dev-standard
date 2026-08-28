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


def assert_no_reparse(path: Path, *, allow_ancestor_links: bool = False) -> None:
    first = True
    current = path
    while True:
        if is_reparse_point(current) and (first or not allow_ancestor_links):
            raise RuntimeError(f"安装路径不能包含符号链接或 Windows reparse point：{current}")
        if current.parent == current:
            return
        current = current.parent
        first = False


def remove_path(path: Path) -> None:
    if is_reparse_point(path) or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def promote_directory(staged: Path, target: Path, *, keep_backup: bool = False) -> Path | None:
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
        if completed and not keep_backup and (backup.exists() or backup.is_symlink()):
            remove_path(backup)
    return backup if completed and moved_target and keep_backup else None


def write_bytes_atomic(path: Path, data: bytes, mode: int | None = None) -> None:
    assert_no_reparse(path)
    if path.exists() and not path.is_file():
        raise RuntimeError(f"启动器目标不是普通文件：{path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.tmp-", suffix="", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def write_launcher_atomic(path: Path, content: str, mode: int | None = None) -> None:
    write_bytes_atomic(path, content.encode("utf-8"), mode=mode)


def snapshot_file(path: Path) -> tuple[bytes, int] | None:
    assert_no_reparse(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise RuntimeError(f"安装目标不是普通文件：{path}")
    return path.read_bytes(), path.stat().st_mode


def restore_file(path: Path, snapshot: tuple[bytes, int] | None) -> None:
    if snapshot is None:
        if path.exists() or path.is_symlink():
            remove_path(path)
        return
    write_bytes_atomic(path, snapshot[0], mode=snapshot[1])


def restore_directory(target: Path, backup: Path | None) -> None:
    if target.exists() or target.is_symlink():
        remove_path(target)
    if backup is not None and (backup.exists() or backup.is_symlink()):
        backup.replace(target)


def _install() -> int:
    ap = argparse.ArgumentParser(description="无需 pip 安装 APS CLI")
    ap.add_argument("--prefix", type=Path, default=default_prefix(), help="安装前缀")
    args = ap.parse_args()

    src_root = Path(__file__).resolve().parent
    version = read_version(src_root / "VERSION")
    prefix = args.prefix.expanduser()
    assert_no_reparse(prefix, allow_ancestor_links=True)
    prefix = prefix.resolve()
    share_root = prefix / "share"
    app_root = share_root / "aps-cli"
    version_root = app_root / version
    current_root = app_root / "current"
    bin_dir = prefix / ("Scripts" if os.name == "nt" else "bin")
    launcher = bin_dir / ("aps.cmd" if os.name == "nt" else "aps")

    for path in (prefix, share_root, app_root, version_root, current_root, bin_dir, launcher):
        assert_no_reparse(path)
    for path, label in (
        (prefix, "安装前缀"),
        (share_root, "共享安装目录"),
        (app_root, "APS 安装目录"),
        (version_root, "版本安装目录"),
        (current_root, "current 安装目录"),
        (bin_dir, "启动器目录"),
    ):
        if path.exists() and not path.is_dir():
            raise RuntimeError(f"{label}不是目录：{path}")
    launcher_snapshot = snapshot_file(launcher)
    source_tree = src_root / "src" / "aps_cli"
    for source in (src_root / "aps.py", src_root / "VERSION", source_tree):
        assert_no_reparse(source)
    if not source_tree.is_dir():
        raise RuntimeError(f"安装源缺少目录：{source_tree}")
    for current, directories, filenames in os.walk(source_tree, followlinks=False):
        for name in [*directories, *filenames]:
            assert_no_reparse(Path(current) / name)
    prefix_created = not prefix.exists()
    share_root_created = not share_root.exists()
    app_root_created = not app_root.exists()
    bin_dir_created = not bin_dir.exists()
    staged_version = app_root / f".{version}.staging-{uuid.uuid4().hex}"
    staged_current = app_root / f".current.staging-{uuid.uuid4().hex}"
    version_backup: Path | None = None
    current_backup: Path | None = None
    version_promoted = False
    current_promoted = False
    try:
        app_root.mkdir(parents=True, exist_ok=True)
        bin_dir.mkdir(parents=True, exist_ok=True)
        staged_version.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_root / "aps.py", staged_version / "aps.py")
        shutil.copytree(
            src_root / "src" / "aps_cli",
            staged_version / "src" / "aps_cli",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copy2(src_root / "VERSION", staged_version / "VERSION")
        version_backup = promote_directory(staged_version, version_root, keep_backup=True)
        version_promoted = True

        # Copy instead of symlink for Windows and restricted environments.
        shutil.copytree(version_root, staged_current)
        current_backup = promote_directory(staged_current, current_root, keep_backup=True)
        current_promoted = True

        python = Path(sys.executable).resolve()
        if os.name == "nt":
            write_launcher_atomic(
                launcher,
                f'@echo off\r\n"{python}" "{current_root / "aps.py"}" %*\r\n',
            )
        else:
            write_launcher_atomic(
                launcher,
                f'#!/bin/sh\nexec "{python}" "{current_root / "aps.py"}" "$@"\n',
                mode=0o755,
            )
    except Exception as exc:
        rollback_errors: list[str] = []
        try:
            restore_file(launcher, launcher_snapshot)
        except Exception as rollback_exc:
            rollback_errors.append(str(rollback_exc))
        if current_promoted:
            try:
                restore_directory(current_root, current_backup)
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if version_promoted:
            try:
                restore_directory(version_root, version_backup)
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        try:
            for temporary in (staged_version, staged_current):
                if temporary.exists() or temporary.is_symlink():
                    remove_path(temporary)
        except Exception as rollback_exc:
            rollback_errors.append(str(rollback_exc))
        if bin_dir_created and bin_dir.exists():
            try:
                bin_dir.rmdir()
            except OSError:
                pass
        if app_root_created and app_root.exists():
            try:
                app_root.rmdir()
            except OSError:
                pass
        if share_root_created and share_root.exists():
            try:
                share_root.rmdir()
            except OSError:
                pass
        if prefix_created and prefix.exists():
            try:
                prefix.rmdir()
            except OSError:
                pass
        if rollback_errors:
            raise RuntimeError(f"安装失败且回滚失败：{rollback_errors[0]}") from exc
        raise
    finally:
        for temporary in (staged_version, staged_current):
            if temporary.exists() or temporary.is_symlink():
                remove_path(temporary)
    for backup in (version_backup, current_backup):
        if backup is not None and (backup.exists() or backup.is_symlink()):
            try:
                remove_path(backup)
            except OSError:
                print(f"WARN  安装已完成，但无法清理旧版本备份：{backup}", file=sys.stderr)

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
    print("NEXT  进入项目目录后运行 `aps`；新项目用 `aps init`，已有项目用 `aps resume`；只想复制 handoff 时加 `--no-launch`。")
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
