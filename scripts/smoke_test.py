#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(command))
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, end="")
    if result.returncode:
        raise SystemExit(result.returncode)


def run_python(*args: str, cwd: Path = ROOT) -> None:
    run([sys.executable, *args], cwd=cwd)


def run_python_expect_failure(*args: str, cwd: Path = ROOT) -> None:
    command = [sys.executable, *args]
    print("+", " ".join(command))
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, end="")
    if result.returncode == 0:
        raise SystemExit("command unexpectedly succeeded")


def snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def run_launcher(launcher: Path, args: list[str]) -> None:
    if sys.platform == "win32":
        command_line = subprocess.list2cmdline([str(launcher), *args])
        print("+", command_line)
        result = subprocess.run(command_line, cwd=ROOT, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(result.stdout, end="")
        if result.returncode:
            raise SystemExit(result.returncode)
    else:
        run([str(launcher), *args])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aps-smoke-") as raw_temp:
        temp = Path(raw_temp)
        project = temp / "source-project"
        run_python("aps.py", "init", str(project), "--host", "generic", "--no-launch", "--no-git")
        run_python("aps.py", "doctor", str(project), "--host", "generic", "--standard-only")

        before_repeat = snapshot_files(project)
        run_python_expect_failure("aps.py", "init", str(project), "--host", "generic", "--no-launch", "--force-mode")
        if snapshot_files(project) != before_repeat:
            raise SystemExit("repeated init changed the governed project")

        run_python("aps.py", "resume", str(project), "--host", "generic", "--no-launch")
        if snapshot_files(project) != before_repeat:
            raise SystemExit("resume changed a current governed project")

        adopted = temp / "adopted-project"
        adopted.mkdir()
        (adopted / "app.txt").write_text("existing project\n", encoding="utf-8")
        run_python("aps.py", "resume", str(adopted), "--host", "generic", "--no-launch")
        adopted_after = snapshot_files(adopted)
        run_python("aps.py", "resume", str(adopted), "--host", "generic", "--no-launch")
        if snapshot_files(adopted) != adopted_after:
            raise SystemExit("repeated resume changed an adopted project")

        nested = project / "nested"
        nested.mkdir()
        run_python_expect_failure("aps.py", "init", str(nested), "--host", "generic", "--no-launch", "--no-git")
        run_python_expect_failure("aps.py", "upgrade", str(nested), "--host", "generic")
        if snapshot_files(nested):
            raise SystemExit("nested init left files behind")

        run_python_expect_failure("aps.py", "rebaseline", str(project), "--host", "generic", "--no-launch")
        if snapshot_files(project) != before_repeat:
            raise SystemExit("unconfirmed rebaseline changed the governed project")
        run_python_expect_failure("aps.py", "rebaseline", str(project), "--host", "generic", "--no-launch", "--confirm")
        state = project / ".ai" / "state.yaml"
        state.write_text((project / ".ai" / "templates" / "state.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        run_python("aps.py", "rebaseline", str(project), "--host", "generic", "--no-launch", "--confirm")
        state.write_text(state.read_text(encoding="utf-8").replace("cycle: CYCLE-001", "cycle: CYCLE-002"), encoding="utf-8")
        run_python_expect_failure("aps.py", "rebaseline", str(project), "--host", "generic", "--no-launch", "--confirm")

        before_upgrade = snapshot_files(project)
        run_python("aps.py", "upgrade", str(project), "--host", "generic")
        if snapshot_files(project) != before_upgrade:
            raise SystemExit("same-version upgrade changed the governed project")

        managed = project / ".ai" / "standards" / "lifecycle.md"
        managed.write_bytes(managed.read_bytes() + b"\nlocal smoke edit\n")
        run_python("aps.py", "upgrade", str(project), "--host", "generic")
        incoming = list((project / ".ai" / "incoming").rglob("lifecycle.md"))
        if not incoming:
            raise SystemExit("upgrade did not preserve a locally modified managed file")
        before_repeat_conflict = snapshot_files(project)
        run_python("aps.py", "upgrade", str(project), "--host", "generic")
        if snapshot_files(project) != before_repeat_conflict:
            raise SystemExit("repeated conflict upgrade changed the project")

        run_python("aps.py", "upgrade", str(project), "--host", "generic", "--force-managed")
        expected = ROOT / "src" / "aps_cli" / "bundle" / "package" / "standards" / "lifecycle.md"
        if managed.read_bytes() != expected.read_bytes():
            raise SystemExit("force-managed upgrade did not install the bundled file")
        backups = snapshot_files(project / ".ai" / "archive" / "install-backups")
        if not backups:
            raise SystemExit("force-managed upgrade did not create a backup")
        run_python("aps.py", "upgrade", str(project), "--host", "generic", "--force-managed")
        if snapshot_files(project / ".ai" / "archive" / "install-backups") != backups:
            raise SystemExit("repeated force-managed upgrade created duplicate backups")

        run_python("scripts/build_release.py")
        archive = next((ROOT / "dist").glob("APS_CLI_*.zip"))
        extracted = temp / "release"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)
        installer = next(extracted.rglob("install_cli.py"))
        prefix = temp / "prefix"
        run_python(str(installer), "--prefix", str(prefix), cwd=extracted)
        release_project = temp / "release-project"
        launcher = prefix / ("Scripts/aps.cmd" if sys.platform == "win32" else "bin/aps")
        run_launcher(launcher, ["init", str(release_project), "--host", "generic", "--no-launch", "--no-git"])
        run_launcher(launcher, ["doctor", str(release_project), "--host", "generic", "--standard-only"])
    print("APS smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
