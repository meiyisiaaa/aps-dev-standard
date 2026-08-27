from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BEGIN_AGENTS = "<!-- AI-PROJECT-STANDARD:BEGIN -->"
END_AGENTS = "<!-- AI-PROJECT-STANDARD:END -->"
BEGIN_GITIGNORE = "# >>> AI PROJECT STANDARD >>>"
END_GITIGNORE = "# <<< AI PROJECT STANDARD <<<"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_safe_version(value: object) -> bool:
    return isinstance(value, str) and bool(VERSION_RE.fullmatch(value))


def is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if os.name == "nt":
            attributes = getattr(os.lstat(path), "st_file_attributes", 0)
            return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except FileNotFoundError:
        return False
    return False


def _is_reparse_point(path: Path) -> bool:
    return is_reparse_point(path)


def assert_no_reparse(path: Path) -> None:
    current = path
    while True:
        if is_reparse_point(current):
            raise RuntimeError(f"安装路径不能包含符号链接或 Windows reparse point：{current}")
        if current.parent == current:
            return
        current = current.parent


def _assert_no_reparse(path: Path) -> None:
    assert_no_reparse(path)


def _validate_relative_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or any(ord(char) < 32 for char in value):
        raise RuntimeError(f"{label} 不是安全的相对路径：{value}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError(f"{label} 不是安全的相对路径：{value}")
    relative = Path(*parts)
    if relative.is_absolute() or relative.drive or ".." in relative.parts or "." in relative.parts:
        raise RuntimeError(f"{label} 不是安全的相对路径：{value}")
    return relative


def _validate_target(root: Path, relative: str, label: str) -> Path:
    path = root / _validate_relative_path(relative, label)
    _assert_no_reparse(path)
    if path.exists() and not path.is_file():
        raise RuntimeError(f"{label} 目标不是普通文件：{path}")
    return path


def _validate_directory(root: Path, relative: str) -> Path:
    path = root / _validate_relative_path(relative, "安装目录")
    _assert_no_reparse(path)
    if path.exists() and not path.is_dir():
        raise RuntimeError(f"安装目录目标不是目录：{path}")
    return path


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def atomic_write(path: Path, data: bytes) -> None:
    _assert_no_reparse(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def write_json_if_changed(path: Path, data: dict) -> bool:
    encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.is_file():
        try:
            if path.read_bytes() == encoded:
                return False
        except OSError:
            pass
    atomic_write(path, encoded)
    return True


def backup_file(root: Path, path: Path) -> Path | None:
    if not path.exists():
        return None
    _assert_no_reparse(path)
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    backup_rel = Path(*rel.parts[1:]) if rel.parts and rel.parts[0] == ".ai" else rel
    content_hash = sha256(path)
    dst = root / ".ai" / "archive" / "install-backups" / content_hash / backup_rel
    _assert_no_reparse(dst)
    if dst.exists():
        if dst.is_file() and sha256(dst) == content_hash:
            return None
        raise RuntimeError(f"备份路径碰撞或内容不匹配：{dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)
    return dst


def copy_file_atomic(src: Path, dst: Path) -> None:
    _assert_no_reparse(src)
    if not src.is_file():
        raise RuntimeError(f"安装源不是普通文件：{src}")
    _assert_no_reparse(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=dst.parent, prefix=f".{dst.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
        shutil.copy2(src, temporary)
        os.replace(temporary, dst)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def copy_file_if_changed(src: Path, dst: Path, src_hash: str) -> bool:
    if dst.is_file() and sha256(dst) == src_hash:
        return False
    copy_file_atomic(src, dst)
    return True


def _backup_destination(root: Path, path: Path) -> Path | None:
    if not path.exists():
        return None
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    backup_rel = Path(*rel.parts[1:]) if rel.parts and rel.parts[0] == ".ai" else rel
    return root / ".ai" / "archive" / "install-backups" / sha256(path) / backup_rel


def _prepare_marked_block(path: Path, begin: str, end: str, block: str) -> tuple[bytes, bytes, str]:
    old_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    begin_count = old_text.count(begin)
    end_count = old_text.count(end)
    if begin_count != end_count or begin_count > 1:
        raise RuntimeError(f"managed marker block is duplicated or incomplete: {path}")
    if begin_count == 1:
        prefix, rest = old_text.split(begin, 1)
        _, suffix = rest.split(end, 1)
        prefix = prefix.rstrip()
        suffix = suffix.lstrip("\n")
        separator = "\n\n" if prefix else ""
        new_text = prefix + separator + block.strip() + "\n" + suffix
        action = "update"
    else:
        separator = "\n\n" if old_text.strip() else ""
        new_text = old_text.rstrip() + separator + block.strip() + "\n"
        action = "append" if old_text.strip() else "create"
    return old_text.encode("utf-8"), new_text.encode("utf-8"), action


def update_marked_block(path: Path, begin: str, end: str, block: str, root: Path) -> str:
    old, new, action = _prepare_marked_block(path, begin, end, block)
    if new == old:
        return "unchanged"
    if path.exists():
        backup_file(root, path)
    atomic_write(path, new)
    return action


def validate_bundle(bundle: Path) -> tuple[str, dict[str, str]]:
    """Validate the embedded Standard and return its version and install mapping."""
    bundle = bundle.expanduser()
    _assert_no_reparse(bundle)
    manifest_path = bundle / "package-manifest.json"
    payload = bundle / "package"
    _assert_no_reparse(manifest_path)
    _assert_no_reparse(payload)
    manifest_src = load_json(manifest_path)
    version = manifest_src.get("version")
    if (
        manifest_src.get("name") != "ai-project-standard"
        or manifest_src.get("layout_version") != 1
        or not payload.is_dir()
        or not is_safe_version(version)
    ):
        raise RuntimeError("installer payload/manifest missing or version-mismatched")
    payload_hashes = manifest_src.get("payload_sha256", {})
    if not isinstance(payload_hashes, dict) or not payload_hashes:
        raise RuntimeError("package manifest has no payload checksums")
    payload_paths: set[str] = set()
    for rel, expected in payload_hashes.items():
        relative = _validate_relative_path(rel, "package manifest payload path")
        folded = relative.as_posix().casefold()
        if folded in payload_paths:
            raise RuntimeError(f"package manifest contains case-colliding payload paths: {rel}")
        payload_paths.add(folded)
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise RuntimeError(f"package manifest contains invalid checksum: {rel}")
        src = payload / relative
        _assert_no_reparse(src)
        if not src.is_file() or sha256(src) != expected:
            raise RuntimeError(f"package integrity check failed: {rel}")

    managed_files = manifest_src.get("managed_files")
    if not isinstance(managed_files, list) or not managed_files:
        raise RuntimeError("package manifest has no managed files")
    mapping: dict[str, str] = {}
    managed_paths: set[str] = set()
    for dst_rel in managed_files:
        if not isinstance(dst_rel, str) or not dst_rel.startswith(".ai/"):
            raise RuntimeError(f"package manifest contains unsafe managed path: {dst_rel}")
        _validate_relative_path(dst_rel, "package manifest managed path")
        folded_dst = dst_rel.casefold()
        if folded_dst in managed_paths:
            raise RuntimeError(f"package manifest contains case-colliding managed paths: {dst_rel}")
        managed_paths.add(folded_dst)
        src_rel = dst_rel.removeprefix(".ai/")
        _validate_relative_path(src_rel, "package manifest source path")
        if src_rel in mapping or src_rel not in payload_hashes:
            raise RuntimeError(f"package manifest managed file is not covered: {dst_rel}")
        mapping[src_rel] = dst_rel
    return version, mapping


@contextmanager
def install_lock(root: Path):
    lock_path = root / ".ai" / ".install.lock"
    _assert_no_reparse(lock_path)
    lock_existed = lock_path.exists()
    ai_existed = lock_path.parent.exists()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    acquired = False
    failed = False
    try:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            failed = True
            raise RuntimeError("another APS installation is in progress") from exc
        acquired = True
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            if acquired:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except BaseException:
        failed = True
        raise
    finally:
        handle.close()
        if failed and not lock_existed:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            if not ai_existed:
                try:
                    lock_path.parent.rmdir()
                except OSError:
                    pass


def install_standard(bundle: Path, root: Path, host: str = "codex", force_managed: bool = False, quiet: bool = False) -> dict:
    """Install/upgrade the embedded Standard into root without creating runtime project facts."""
    version, mapping = validate_bundle(bundle)
    payload = bundle / "package"

    root = root.expanduser()
    _assert_no_reparse(root)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise RuntimeError(f"project path is not a directory: {root}")
    _assert_no_reparse(root)

    with install_lock(root):
        old_manifest_path = root / ".ai" / "standard-manifest.json"
        old_manifest = load_json(old_manifest_path)
        old_hashes = old_manifest.get("installed_files", {}) if isinstance(old_manifest.get("installed_files", {}), dict) else {}

        dirs = [
            ".ai/standards", ".ai/bootstrap", ".ai/tools", ".ai/schemas", ".ai/templates",
            ".ai/runtime/hosts", ".ai/cycles", ".ai/archive", ".agents/skills",
        ]
        for rel in dirs:
            _validate_directory(root, rel)
        for rel in (".ai", ".ai/incoming", ".ai/archive/install-backups", ".agents"):
            _validate_directory(root, rel)

        managed_targets = list(mapping.values()) + ["AGENTS.md", ".gitignore", ".ai/standard-manifest.json"]
        for rel in managed_targets:
            _validate_target(root, rel, "安装目标")

        agents_path = root / "AGENTS.md"
        ignore_path = root / ".gitignore"
        agents_block_path = payload / "templates" / "AGENTS.block.md"
        ignore_fragment_path = payload / "gitignore.fragment"
        _assert_no_reparse(agents_block_path)
        _assert_no_reparse(ignore_fragment_path)
        if not agents_block_path.is_file() or not ignore_fragment_path.is_file():
            raise RuntimeError("installer payload is missing marker content")
        agents_block = agents_block_path.read_text(encoding="utf-8")
        ignore_body = ignore_fragment_path.read_text(encoding="utf-8").strip()
        ignore_block = f"{BEGIN_GITIGNORE}\n{ignore_body}\n{END_GITIGNORE}"
        marker_plans = [
            (agents_path, BEGIN_AGENTS, END_AGENTS, agents_block),
            (ignore_path, BEGIN_GITIGNORE, END_GITIGNORE, ignore_block),
        ]
        prepared_markers = [
            (path, *_prepare_marked_block(path, begin, end, block))
            for path, begin, end, block in marker_plans
        ]

        staged_dir = Path(tempfile.mkdtemp(prefix=".aps-install-", dir=root))
        stage_payload = staged_dir / "package"
        staged_sources: dict[str, Path] = {}
        try:
            for src_rel in mapping:
                src = payload / _validate_relative_path(src_rel, "payload source")
                staged = stage_payload / _validate_relative_path(src_rel, "staged payload path")
                staged.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, staged)
                staged_sources[src_rel] = staged

            installed_hashes: dict[str, str] = {}
            incoming: list[str] = []
            target_operations: list[tuple[Path, Path, str]] = []
            incoming_operations: list[tuple[Path, Path, str]] = []
            for src_rel, dst_rel in mapping.items():
                src = staged_sources[src_rel]
                dst = root / _validate_relative_path(dst_rel, "安装目标")
                src_hash = sha256(src)
                current_hash = sha256(dst) if dst.is_file() else None
                previous_hash = old_hashes.get(dst_rel)
                installed_hashes[dst_rel] = src_hash
                if current_hash == src_hash:
                    continue
                safe_to_replace = (not dst.exists()) or (previous_hash is not None and current_hash == previous_hash)
                if safe_to_replace or force_managed:
                    target_operations.append((src, dst, dst_rel))
                    continue
                incoming_rel = Path(*Path(dst_rel).parts[1:])
                incoming_dst = root / ".ai" / "incoming" / version / incoming_rel
                _assert_no_reparse(incoming_dst)
                if incoming_dst.exists() and not incoming_dst.is_file():
                    raise RuntimeError(f"incoming 目标不是普通文件：{incoming_dst}")
                if not incoming_dst.is_file() or sha256(incoming_dst) != src_hash:
                    incoming_operations.append((src, incoming_dst, dst_rel))
                incoming.append(dst_rel)

            install_manifest = dict(old_manifest) if isinstance(old_manifest, dict) else {}
            install_manifest.update(
                {
                    "name": "ai-project-standard",
                    "version": version,
                    "layout_version": 1,
                    "host_hint": host,
                    "installed_files": installed_hashes,
                    "local_modification_conflicts": incoming,
                }
            )
            if not install_manifest.get("installed_at"):
                install_manifest["installed_at"] = utc_now()
            manifest_data = (json.dumps(install_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            manifest_changed = not old_manifest_path.is_file() or old_manifest_path.read_bytes() != manifest_data

            operations = target_operations + incoming_operations
            snapshot_paths: set[Path] = {path for path, old, new, action in prepared_markers if old != new}
            if manifest_changed:
                snapshot_paths.add(old_manifest_path)
            for _, dst, _ in operations:
                snapshot_paths.add(dst)
            for path in tuple(snapshot_paths):
                if path.exists() and not path.is_file():
                    raise RuntimeError(f"安装提交目标不是普通文件：{path}")
                _assert_no_reparse(path)
                backup = _backup_destination(root, path)
                if backup is not None:
                    _assert_no_reparse(backup)
                    if backup.exists() and not backup.is_file():
                        raise RuntimeError(f"备份目标不是普通文件：{backup}")
                    snapshot_paths.add(backup)

            snapshots: dict[Path, tuple[bytes, int] | None] = {}
            for path in snapshot_paths:
                if path.exists():
                    if not path.is_file():
                        raise RuntimeError(f"安装快照目标不是普通文件：{path}")
                    snapshots[path] = (path.read_bytes(), path.stat().st_mode)
                else:
                    snapshots[path] = None

            created_dirs: list[Path] = []

            def ensure_dir(path: Path) -> None:
                _assert_no_reparse(path)
                if path.exists():
                    if not path.is_dir():
                        raise RuntimeError(f"安装目录目标不是目录：{path}")
                    return
                missing_dirs: list[Path] = []
                current = path
                while not current.exists():
                    missing_dirs.append(current)
                    if current.parent == current:
                        break
                    current = current.parent
                _assert_no_reparse(current)
                for directory in reversed(missing_dirs):
                    directory.mkdir()
                    created_dirs.append(directory)

            def ensure_parent(path: Path) -> None:
                ensure_dir(path.parent)

            def restore_snapshot(path: Path, snapshot: tuple[bytes, int] | None) -> None:
                if snapshot is None:
                    if path.exists() or path.is_symlink():
                        _assert_no_reparse(path)
                        path.unlink()
                    return
                data, mode = snapshot
                atomic_write(path, data)
                try:
                    path.chmod(mode)
                except OSError:
                    pass

            try:
                for rel in dirs:
                    ensure_dir(root / rel)
                ensure_dir(root / ".ai" / "incoming")
                ensure_dir(root / ".ai" / "archive" / "install-backups")

                for src, dst, _ in operations:
                    ensure_parent(dst)
                    if dst.exists():
                        backup = _backup_destination(root, dst)
                        if backup is not None:
                            ensure_parent(backup)
                            backup_file(root, dst)
                    copy_file_atomic(src, dst)
                    if dst.as_posix().endswith(".py"):
                        dst.chmod(dst.stat().st_mode | 0o111)

                for path, old, new, _ in prepared_markers:
                    if old == new:
                        continue
                    ensure_parent(path)
                    if path.exists():
                        backup = _backup_destination(root, path)
                        if backup is not None:
                            ensure_parent(backup)
                            backup_file(root, path)
                    atomic_write(path, new)

                if manifest_changed:
                    ensure_parent(old_manifest_path)
                    if old_manifest_path.exists():
                        backup = _backup_destination(root, old_manifest_path)
                        if backup is not None:
                            ensure_parent(backup)
                            backup_file(root, old_manifest_path)
                    atomic_write(old_manifest_path, manifest_data)
            except Exception as exc:
                try:
                    for path in sorted(snapshots, key=lambda item: len(item.parts), reverse=True):
                        restore_snapshot(path, snapshots[path])
                    for directory in sorted(created_dirs, key=lambda item: len(item.parts), reverse=True):
                        if directory.exists() and directory.is_dir() and not _is_reparse_point(directory):
                            try:
                                directory.rmdir()
                            except OSError:
                                pass
                except Exception as rollback_exc:
                    raise RuntimeError(f"安装提交失败且回滚也失败：{rollback_exc}") from exc
                raise

            changed = len(target_operations)
            changed += sum(1 for _, old, new, _ in prepared_markers if old != new)
        finally:
            shutil.rmtree(staged_dir, ignore_errors=True)

        if not quiet:
            if old_manifest.get("version") == version and changed == 0 and not incoming and not manifest_changed:
                print(f"OK    AI Project Standard {version} 已是当前版本：{root}")
            else:
                print(f"OK    AI Project Standard {version} 已安装到：{root}")
            if incoming:
                print(f"WARN  已保留 {len(incoming)} 个本地修改的托管文件；请检查 `.ai/incoming/{version}/`。")
        return {
            "changed": changed,
            "incoming": incoming,
            "manifest_changed": manifest_changed,
            "root": str(root),
            "version": version,
        }
