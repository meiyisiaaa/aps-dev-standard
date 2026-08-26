#!/usr/bin/env python3
from __future__ import annotations

import json
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
        (project / ".ai" / "registry.yaml").write_text(
            (project / ".ai" / "templates" / "registry.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        run_python_expect_failure("aps.py", "rebaseline", str(project), "--host", "generic", "--no-launch", "--confirm")

        decision_dir = project / ".ai" / "cycles" / "CYCLE-002" / "stages" / "01-idea" / "decision-requests"
        decision_dir.mkdir(parents=True)
        decision_path = decision_dir / "DEC-001.json"
        decision_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "DEC-001",
                    "status": "PENDING",
                    "cycle": "CYCLE-002",
                    "stage": 1,
                    "input_type": "single_select",
                    "question": "选择产品入口",
                    "why_now": "两个方向会导致不同产品路线",
                    "options": [
                        {"id": "A", "title": "方案 A", "summary": "快速验证"},
                        {"id": "B", "title": "方案 B", "summary": "长期控制"},
                    ],
                    "recommended": "A",
                    "evidence_refs": ["01_IDEA.md"],
                    "affected_areas": ["Product DNA", "MVP"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run_python("aps.py", "decision", "request", str(decision_path), str(project))
        run_python("aps.py", "decision", "list", str(project))
        run_python("aps.py", "decision", "show", "DEC-001", str(project))
        run_python("aps.py", "decision", "answer", "DEC-001", "B", str(project), "--reason", "长期控制更适合当前目标")
        run_python("aps.py", "decision", "show", "DEC-001", str(project))
        if json.loads(decision_path.read_text(encoding="utf-8"))["status"] != "RESOLVED":
            raise SystemExit("decision request status was not resolved")
        state_text = state.read_text(encoding="utf-8")
        if "pending_decision_refs: []" not in state_text or "user_decision" in state_text:
            raise SystemExit("decision answer did not clear the pending blocker")
        decisions = (project / ".ai" / "decisions.md").read_text(encoding="utf-8")
        if "## DEC-001" not in decisions or "Decision: B" not in decisions:
            raise SystemExit("decision answer was not written to the decision log")
        run_python_expect_failure("aps.py", "decision", "answer", "DEC-001", "A", str(project))

        multi_path = decision_dir / "DEC-002.json"
        multi_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "DEC-002",
                    "status": "PENDING",
                    "cycle": "CYCLE-002",
                    "stage": 1,
                    "input_type": "multi_select",
                    "question": "选择需要保留的能力",
                    "why_now": "多个能力可以独立组合",
                    "options": [
                        {"id": "A", "title": "能力 A"},
                        {"id": "B", "title": "能力 B"},
                        {"id": "C", "title": "能力 C"},
                        {"id": "D", "title": "能力 D"},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run_python("aps.py", "decision", "request", str(multi_path), str(project))
        run_python("aps.py", "decision", "answer", "DEC-002", "A,C", str(project))
        decisions = (project / ".ai" / "decisions.md").read_text(encoding="utf-8")
        if "## DEC-002" not in decisions or "Decision: A, C" not in decisions:
            raise SystemExit("multi-select decision answer was not recorded")
        run_python("aps.py", "doctor", str(project), "--host", "generic")

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
