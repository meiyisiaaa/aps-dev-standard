#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
CLI_VERSION = next(
    line.split("=", 1)[1].strip()
    for line in (ROOT / "VERSION").read_text(encoding="utf-8").splitlines()
    if line.startswith("APS_CLI=")
)


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(command))
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout, end="")
    if result.returncode:
        raise SystemExit(result.returncode)


def run_python(*args: str, cwd: Path = ROOT) -> None:
    run([sys.executable, *args], cwd=cwd)


def run_python_capture(*args: str, cwd: Path = ROOT) -> str:
    command = [sys.executable, *args]
    print("+", " ".join(command))
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout, end="")
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout


def run_python_capture_env(env_updates: dict[str, str], *args: str, cwd: Path = ROOT) -> str:
    command = [sys.executable, *args]
    print("+", " ".join(command), f"[env: {env_updates}]")
    environment = os.environ.copy()
    environment.update(env_updates)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout, end="")
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout


def run_python_with_input(input_text: str, *args: str, cwd: Path = ROOT) -> str:
    command = [sys.executable, *args]
    print("+", " ".join(command))
    result = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout, end="")
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout


def run_python_expect_failure_capture(*args: str, cwd: Path = ROOT) -> str:
    command = [sys.executable, *args]
    print("+", " ".join(command))
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout, end="")
    if result.returncode == 0:
        raise SystemExit("command unexpectedly succeeded")
    assert_single_next(result.stdout, " ".join(command))
    return result.stdout


def run_python_expect_failure(*args: str, cwd: Path = ROOT) -> None:
    command = [sys.executable, *args]
    print("+", " ".join(command))
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout, end="")
    if result.returncode == 0:
        raise SystemExit("command unexpectedly succeeded")


def assert_single_next(output: str, label: str) -> None:
    if output.count("NEXT") != 1:
        raise SystemExit(f"{label} did not provide exactly one NEXT action")


def snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def write_transition_audit(project: Path) -> None:
    """Write a valid fixture chain ending at the project's current state."""
    state_text = (project / ".ai" / "state.yaml").read_text(encoding="utf-8")

    def state_value(name: str) -> str:
        match = re.search(rf"(?m)^{re.escape(name)}:\s*(.+)$", state_text)
        if not match:
            raise SystemExit(f"fixture state is missing {name}")
        return match.group(1).strip()

    cycle = state_value("cycle")
    stage = int(state_value("stage"))
    stage_type = state_value("stage_type")
    stage_status = state_value("stage_status")
    gate_status = state_value("gate_status")
    gate_status = None if gate_status == "null" else gate_status
    revision = int(state_value("revision"))
    current = {
        "cycle": cycle,
        "stage": stage,
        "stage_type": stage_type,
        "stage_status": stage_status,
        "gate_status": gate_status,
    }
    template = json.loads(
        (project / ".ai" / "templates" / "transition-record.json").read_text(encoding="utf-8")
    )

    def record(event_id: str, number: int, from_state: dict | None, to_state: dict) -> dict:
        value = dict(template)
        value.update(
            {
                "event_id": event_id,
                "recorded_at": f"2026-08-27T00:00:0{number}+00:00",
                "revision": number,
                "from_state": from_state,
                "to_state": to_state,
            }
        )
        return value

    initial = {
        "cycle": cycle,
        "stage": 1,
        "stage_type": "GATED",
        "stage_status": "ACTIVE",
        "gate_status": "PENDING",
    }
    if stage == 1:
        records = [record("TRN-TEST-001", 1, None, current)]
    else:
        complete = {**initial, "stage_status": "COMPLETE", "gate_status": "PASS"}
        records = [
            record("TRN-TEST-001", 1, None, initial),
            record("TRN-TEST-002", 2, initial, complete),
            record("TRN-TEST-003", 3, complete, current),
        ]
        if revision < 3:
            raise SystemExit("fixture state revision must be at least 3 for a non-Stage-1 audit chain")

    audit = project / ".ai" / "audit" / "transitions.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
        encoding="utf-8",
    )


def safe_extract_zip(archive: Path, destination: Path) -> None:
    """Test the same archive boundary expected from the online installers."""
    seen: set[str] = set()
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            name = info.filename.replace("\\", "/")
            key = name.rstrip("/")
            if not key or name.startswith("/") or Path(key).drive or re.match(r"^[A-Za-z]:", key):
                raise ValueError(f"unsafe ZIP path: {name}")
            parts = key.split("/")
            if any(part in {"", ".", ".."} for part in parts) or any(ord(char) < 32 for char in name):
                raise ValueError(f"unsafe ZIP path: {name}")
            if key.casefold() in seen:
                raise ValueError(f"duplicate ZIP path: {name}")
            seen.add(key.casefold())
            if stat.S_IFMT((info.external_attr >> 16) & 0xFFFF) == stat.S_IFLNK:
                raise ValueError(f"ZIP link entry is not allowed: {name}")
            target = destination.joinpath(*parts)
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(info) as input_file, target.open("wb") as output:
                    shutil.copyfileobj(input_file, output)


def run_launcher(launcher: Path, args: list[str]) -> None:
    if sys.platform == "win32":
        command_line = subprocess.list2cmdline([str(launcher), *args])
        print("+", command_line)
        result = subprocess.run(
            command_line,
            cwd=ROOT,
            shell=True,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        print(result.stdout, end="")
        if result.returncode:
            raise SystemExit(result.returncode)
    else:
        run([str(launcher), *args])


def main() -> int:
    configure_stdio()
    from aps_cli.governance import PROFILE_RELEASE_CHECKS

    with tempfile.TemporaryDirectory(prefix="aps-smoke-") as raw_temp:
        temp = Path(raw_temp)
        release_requirements = json.loads(
            (ROOT / "src" / "aps_cli" / "bundle" / "package" / "tools" / "release-requirements.json").read_text(
                encoding="utf-8"
            )
        )
        if PROFILE_RELEASE_CHECKS != {key: tuple(value) for key, value in release_requirements.items()}:
            raise SystemExit("governance and bundled release requirements have drifted")
        help_output = run_python_capture("aps.py", "--help")
        if "典型路径" not in help_output or "aps decision request" not in help_output or "aps research brief" not in help_output:
            raise SystemExit("CLI help does not include Chinese scenarios and decision/research paths")
        project = temp / "source-project"
        run_python("aps.py", "init", str(project), "--host", "generic", "--no-launch", "--no-git")
        run_python("aps.py", "doctor", str(project), "--host", "generic", "--standard-only")
        bootstrap_prompt = (project / ".ai" / "bootstrap" / "bootstrap-prompt.txt").read_text(encoding="utf-8")
        required_prompt_markers = ("优点", "缺点", "适用条件", "主要风险", "直接回答原始研究问题", "分析关键证据", "用户需要 PRD 时", "prd-snapshot.md", "Stage User Brief", "不要每轮对话重复", "当前 Stage / Task", "下一阶段入口提醒", "不要求用户额外确认“Stage PASS”", "Impact Analysis", "定向验证", ".ai/templates/change-log.md", "adoption: true")
        if any(marker not in bootstrap_prompt for marker in required_prompt_markers):
            raise SystemExit("bootstrap prompt does not require decision and research analysis")
        planning_prompt_markers = ("原生 Codex Plan 模式", "已接受的计划", "不阻塞执行", "Stage 01、05、06、07、08、09、10、13、14、15、16、20")
        if any(marker not in bootstrap_prompt for marker in planning_prompt_markers):
            raise SystemExit("bootstrap prompt does not enforce portable planning")

        before_repeat = snapshot_files(project)
        if not (project / ".ai" / "templates" / "prd-snapshot.md").is_file():
            raise SystemExit("PRD Snapshot template was not installed")
        if not (project / ".ai" / "templates" / "change-log.md").is_file():
            raise SystemExit("Change Impact template was not installed")
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

        legacy = temp / "legacy-governed-project"
        run_python("aps.py", "init", str(legacy), "--host", "generic", "--no-launch", "--no-git")
        (legacy / ".ai" / "state.yaml").write_text(
            (legacy / ".ai" / "templates" / "state.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        legacy_resume = run_python_capture("aps.py", "resume", str(legacy), "--host", "codex", "--no-launch")
        if "尚未完成风险基线" not in legacy_resume or "APS Agent Handoff" not in legacy_resume:
            raise SystemExit("legacy governed project did not enter safe governance bootstrap")

        late_adoption = temp / "late-adoption-project"
        run_python("aps.py", "init", str(late_adoption), "--host", "generic", "--no-launch", "--no-git")
        for filename in ("decisions.md", "registry.yaml", "project-profile.json"):
            (late_adoption / ".ai" / filename).write_text(
                (late_adoption / ".ai" / "templates" / filename).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        late_state = late_adoption / ".ai" / "state.yaml"
        late_state.write_text(
            (late_adoption / ".ai" / "templates" / "state.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        late_state.write_text(
            late_state.read_text(encoding="utf-8").replace("stage: 1", "stage: 15"),
            encoding="utf-8",
        )
        adoption_record = json.loads(
            (late_adoption / ".ai" / "templates" / "transition-record.json").read_text(encoding="utf-8")
        )
        adoption_record.update(
            {
                "event_id": "TRN-ADOPTION-001",
                "recorded_at": "2026-08-27T00:00:01+00:00",
                "reason": "Existing project adoption at verified Stage 15",
                "to_state": {
                    "cycle": "CYCLE-001",
                    "stage": 15,
                    "stage_type": "GATED",
                    "stage_status": "ACTIVE",
                    "gate_status": "PENDING",
                },
                "evidence_refs": ["approved-plan.md"],
                "adoption": True,
            }
        )
        late_audit = late_adoption / ".ai" / "audit" / "transitions.jsonl"
        late_audit.parent.mkdir(parents=True, exist_ok=True)
        late_audit.write_text(json.dumps(adoption_record, ensure_ascii=False) + "\n", encoding="utf-8")
        run_python("aps.py", "doctor", str(late_adoption), "--host", "generic")
        adoption_record.pop("adoption")
        late_audit.write_text(json.dumps(adoption_record, ensure_ascii=False) + "\n", encoding="utf-8")
        unmarked_adoption = run_python_expect_failure_capture("aps.py", "status", str(late_adoption))
        if "adoption: true" not in unmarked_adoption:
            raise SystemExit("late-stage adoption without an explicit marker was accepted")

        ordinary = temp / "ordinary-project"
        ordinary.mkdir()
        (ordinary / "app.txt").write_text("ordinary project\n", encoding="utf-8")
        ordinary_before = snapshot_files(ordinary)
        ordinary_upgrade = run_python_expect_failure_capture("aps.py", "upgrade", str(ordinary), "--host", "generic")
        if "运行 `aps resume` 接管已有项目" not in ordinary_upgrade or snapshot_files(ordinary) != ordinary_before:
            raise SystemExit("upgrade took over an ordinary ungoverned project")

        empty = temp / "empty-project"
        empty.mkdir()
        empty_upgrade = run_python_expect_failure_capture("aps.py", "upgrade", str(empty), "--host", "generic")
        if "运行 `aps init` 初始化新项目" not in empty_upgrade or snapshot_files(empty):
            raise SystemExit("upgrade did not reject an empty directory")

        partial = temp / "partial-project"
        (partial / ".ai" / "standards").mkdir(parents=True)
        partial_lifecycle = ROOT / "src" / "aps_cli" / "bundle" / "package" / "standards" / "lifecycle.md"
        (partial / ".ai" / "standards" / "lifecycle.md").write_bytes(partial_lifecycle.read_bytes())
        partial_status = run_python_expect_failure_capture("aps.py", "status", str(partial))
        if "partial APS install" not in partial_status or "aps upgrade" not in partial_status:
            raise SystemExit("status did not classify an APS partial install")
        run_python("aps.py", "upgrade", str(partial), "--host", "generic")
        if not (partial / ".ai" / "standard-manifest.json").is_file():
            raise SystemExit("upgrade did not repair an APS partial install")

        manifest = project / ".ai" / "standard-manifest.json"
        manifest_before = manifest.read_bytes()
        manifest.write_text(manifest.read_text(encoding="utf-8").replace(f'"version": "{CLI_VERSION}"', '"version": "0.0.0"'), encoding="utf-8")
        mismatch_output = run_python_expect_failure_capture("aps.py", "resume", str(project), "--host", "generic", "--no-launch")
        if "REFUSE" not in mismatch_output or "aps upgrade" not in mismatch_output:
            raise SystemExit("version mismatch resume did not provide recovery guidance")
        manifest.write_bytes(manifest_before)

        manifest.write_text("{\n", encoding="utf-8")
        bad_manifest_status = run_python_expect_failure_capture("aps.py", "status", str(project))
        if "manifest" not in bad_manifest_status or "aps upgrade" not in bad_manifest_status:
            raise SystemExit("status did not reject a malformed manifest")
        manifest.write_bytes(manifest_before)
        managed_lifecycle = project / ".ai" / "standards" / "lifecycle.md"
        managed_lifecycle_bytes = managed_lifecycle.read_bytes()
        managed_lifecycle.unlink()
        missing_file_status = run_python_expect_failure_capture("aps.py", "status", str(project))
        if "托管文件缺失" not in missing_file_status or "aps upgrade" not in missing_file_status:
            raise SystemExit("status did not report a missing managed file")
        managed_lifecycle.write_bytes(managed_lifecycle_bytes)
        managed_lifecycle.write_bytes(managed_lifecycle_bytes + b"\nlocal smoke edit\n")
        modified_file_status = run_python_expect_failure_capture("aps.py", "status", str(project))
        if "托管文件已被本地修改" not in modified_file_status or "aps upgrade" not in modified_file_status:
            raise SystemExit("status did not report a modified managed file")
        managed_lifecycle.write_bytes(managed_lifecycle_bytes)

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
        profile = project / ".ai" / "project-profile.json"
        profile.write_text((project / ".ai" / "templates" / "project-profile.json").read_text(encoding="utf-8"), encoding="utf-8")
        write_transition_audit(project)
        (project / ".ai" / "registry.yaml").write_text(
            (project / ".ai" / "templates" / "registry.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (project / ".ai" / "decisions.md").write_text(
            (project / ".ai" / "templates" / "decisions.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        registry = project / ".ai" / "registry.yaml"
        registry_before_sequences = registry.read_bytes()
        registry.write_text(
            registry.read_text(encoding="utf-8").replace(
                "    load_policy: referenced-only\n  project_profile:",
                "    load_policy: referenced-only\n    related_paths:\n      - .ai/decisions.md\n  project_assets:\n    domain: Project Assets\n    path: mobile/components/\n    status: ACTIVE\n    load_policy: ui-task\n  project_profile:",
            ),
            encoding="utf-8",
        )
        sequence_registry_status = run_python_capture("aps.py", "status", str(project))
        if "Managed conflicts: 0" not in sequence_registry_status:
            raise SystemExit("Registry scalar sequence was not accepted")
        registry.write_bytes(registry_before_sequences)
        state_before_next_action = state.read_bytes()
        state.write_text(
            state.read_text(encoding="utf-8").replace(
                "next_action: null",
                'next_action:\n  action: "继续当前 Stage"\n  transition: "完成验证后更新 Gate"',
            ),
            encoding="utf-8",
        )
        nested_next_action_status = run_python_capture("aps.py", "status", str(project))
        if "Runtime state: present" not in nested_next_action_status:
            raise SystemExit("nested next_action was not accepted")
        state.write_bytes(state_before_next_action)
        state_before_chinese = state.read_bytes()
        state.write_text(state.read_text(encoding="utf-8").replace("updated_by: coordinator", "updated_by: 协调器"), encoding="utf-8")
        utf8_fallback_lint = run_python_capture_env(
            {"PYTHONUTF8": "0"},
            "src/aps_cli/bundle/package/tools/standards-lint.py",
            "--project-root",
            str(project),
            "--host",
            "generic",
        )
        if "state.yaml has required governance keys" not in utf8_fallback_lint:
            raise SystemExit("UTF-8 fallback did not validate a Chinese state.yaml")
        try:
            import yaml  # type: ignore  # noqa: F401
        except Exception:
            if "fallback validation is advisory" not in utf8_fallback_lint:
                raise SystemExit("UTF-8 fallback did not identify advisory state validation")
        state.write_bytes(state_before_chinese)
        before_menu_cancel = snapshot_files(project)
        menu_output = run_python_with_input("3\nn\n", str(ROOT / "aps.py"), cwd=project)
        if "已取消 rebaseline" not in menu_output or snapshot_files(project) != before_menu_cancel:
            raise SystemExit("cancelled interactive rebaseline changed the project")
        run_python("aps.py", "rebaseline", str(project), "--host", "generic", "--no-launch", "--confirm")
        initial_status = run_python_capture("aps.py", "status", str(project))
        if "Next action:" not in initial_status or "Planning: reuse an accepted plan" not in initial_status:
            raise SystemExit("status did not provide the high-impact planning hint and next action")
        normal_state = state.read_text(encoding="utf-8")
        state.write_text(
            normal_state.replace("stage_status: ACTIVE", "stage_status: COMPLETE").replace("gate_status: PENDING", "gate_status: PASS"),
            encoding="utf-8",
        )
        write_transition_audit(project)
        complete_status = run_python_capture("aps.py", "status", str(project))
        complete_handoff = run_python_capture("aps.py", "resume", str(project), "--host", "generic", "--no-launch")
        for output in (complete_status, complete_handoff):
            if "不需要额外确认当前 Stage PASS" not in output or "下一阶段入口提醒" not in output or "高影响 Stage" not in output:
                raise SystemExit("completed Stage did not provide direct-transition and next-Stage planning guidance")
        state.write_text(normal_state, encoding="utf-8")
        write_transition_audit(project)
        codex_resume = run_python_capture_env({"PATH": ""}, "aps.py", "resume", str(project), "--host", "codex")
        if "Codex CLI was not found" not in codex_resume or "will not auto-launch" in codex_resume:
            raise SystemExit("Codex resume still blocked a normal session for a planning hint")
        state.unlink()
        missing_state_status = run_python_capture("aps.py", "status", str(project))
        missing_state_resume = run_python_capture_env({"PATH": ""}, "aps.py", "resume", str(project), "--host", "codex")
        if "not initialized" not in missing_state_status or "Codex CLI was not found" not in missing_state_resume or "will not auto-launch" in missing_state_resume:
            raise SystemExit("missing state did not provide an ordinary Codex resume path")
        state.write_text(normal_state, encoding="utf-8")
        invalid_states = (
            normal_state.replace("stage: 1", "stage: 99"),
            normal_state.replace("gate_status: PENDING", "gate_status: UNKNOWN"),
            normal_state.replace("stage_type: GATED", "stage_type: EXECUTION_LOOP"),
            normal_state.replace("updated_by: coordinator", "unexpected_state_field: true\nupdated_by: coordinator"),
            normal_state.replace("revision: 1", "revision: 1\nrevision: 2"),
        )
        for invalid_state in invalid_states:
            state.write_text(invalid_state, encoding="utf-8")
            invalid_status = run_python_expect_failure_capture("aps.py", "status", str(project))
            invalid_resume = run_python_expect_failure_capture("aps.py", "resume", str(project), "--host", "generic", "--no-launch")
            invalid_doctor = run_python_expect_failure_capture("aps.py", "doctor", str(project), "--host", "generic", "--standard-only")
            if (
                "Runtime state" not in invalid_status
                or "NORMAL" in invalid_status
                or "APS Agent Handoff" in invalid_resume
                or "state.yaml" not in invalid_doctor
            ):
                raise SystemExit("malformed state was treated as a normal resumable state")
        state.write_bytes(b"\xff\xfe\xfd")
        invalid_encoding_status = run_python_expect_failure_capture("aps.py", "status", str(project))
        invalid_encoding_resume = run_python_expect_failure_capture("aps.py", "resume", str(project), "--host", "generic", "--no-launch")
        if "Runtime state" not in invalid_encoding_status or "doctor --standard-only" not in invalid_encoding_status or "APS Agent Handoff" in invalid_encoding_resume:
            raise SystemExit("non-UTF8 state was not rejected with the state recovery path")
        state.unlink()
        state.mkdir()
        invalid_state_path_doctor = run_python_expect_failure_capture("aps.py", "doctor", str(project), "--host", "generic", "--standard-only")
        if "必须是普通文件" not in invalid_state_path_doctor or "aps doctor --standard-only" not in invalid_state_path_doctor:
            raise SystemExit("non-file state path did not use the safe recovery path")
        state.rmdir()
        state.write_text(normal_state, encoding="utf-8")
        state.write_text(normal_state.replace("revision: 1", "revision: 3").replace("stage: 1", "stage: 17").replace("stage_type: GATED", "stage_type: EXECUTION_LOOP").replace("gate_status: PENDING", "gate_status: null"), encoding="utf-8")
        write_transition_audit(project)
        normal_status = run_python_capture("aps.py", "status", str(project))
        if "Planning: no high-impact entry planning is required." not in normal_status:
            raise SystemExit("status incorrectly required planning for an execution Stage")
        normal_readiness = json.loads((project / ".ai" / "templates" / "release-readiness.json").read_text(encoding="utf-8"))
        normal_readiness.update({"profile": "NORMAL", "status": "READY", "target_environment": "staging", "checks": {name: {"status": "PASS", "evidence_refs": [f"TEST-{name.upper()}"]} for name in ("lint", "build", "functional_qa", "rollback")}, "reviewed_at": "2026-08-27T00:00:04+00:00"})
        (project / ".ai" / "release-readiness.json").write_text(json.dumps(normal_readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        state.write_text(normal_state.replace("revision: 1", "revision: 3").replace("stage: 1", "stage: 22").replace("stage_type: GATED", "stage_type: ROUTER").replace("gate_status: PENDING", "gate_status: null").replace("active_change_refs: []", "active_change_refs: [CHANGE-001]"), encoding="utf-8")
        write_transition_audit(project)
        change_status = run_python_capture("aps.py", "status", str(project))
        if "Planning: reuse an accepted plan" not in change_status or "Active changes: CHANGE-001" not in change_status or "Impact Analysis" not in change_status:
            raise SystemExit("status did not expose the active Change planning route")
        state.write_text(normal_state, encoding="utf-8")
        profile_bytes = profile.read_bytes()
        audit = project / ".ai" / "audit" / "transitions.jsonl"
        if audit.exists():
            audit.unlink()
        profile_data = json.loads(profile_bytes)
        profile_data["risk_profile"] = "LARGE"
        profile_data["workstreams"] = [{"id": "WS-CORE", "name": "核心工作流", "status": "ACTIVE", "owner": "team", "depends_on": []}]
        profile.write_text(json.dumps(profile_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        missing_audit = run_python_expect_failure_capture("aps.py", "status", str(project))
        if "Transition" not in missing_audit or "transitions.jsonl" not in missing_audit:
            raise SystemExit("large profile did not require transition audit")
        transition = json.loads((project / ".ai" / "templates" / "transition-record.json").read_text(encoding="utf-8"))
        transition["recorded_at"] = "2026-08-27T00:00:01+00:00"
        audit.parent.mkdir(parents=True, exist_ok=True)
        audit.write_text(json.dumps(transition, ensure_ascii=False) + "\n", encoding="utf-8")
        run_python("aps.py", "status", str(project))
        audit.write_text(json.dumps({**transition, "evidence_refs": []}, ensure_ascii=False) + "\n", encoding="utf-8")
        missing_evidence = run_python_expect_failure_capture("aps.py", "status", str(project))
        if "evidence_refs" not in missing_evidence:
            raise SystemExit("transition without evidence was accepted")
        audit.write_text(json.dumps(transition, ensure_ascii=False) + "\n", encoding="utf-8")
        complete_state = {**transition["to_state"], "stage_status": "COMPLETE", "gate_status": "PASS"}
        broken_last = {
            **transition,
            "event_id": "TRN-BROKEN-003",
            "recorded_at": "2026-08-27T00:00:03+00:00",
            "revision": 3,
            "from_state": complete_state,
            "to_state": {**complete_state, "stage": 2, "stage_status": "ACTIVE", "gate_status": "PENDING"},
        }
        complete_record = {
            **transition,
            "event_id": "TRN-BROKEN-002",
            "recorded_at": "2026-08-27T00:00:02+00:00",
            "revision": 2,
            "from_state": transition["to_state"],
            "to_state": complete_state,
        }
        audit.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in (transition, complete_record, broken_last)) + "\n",
            encoding="utf-8",
        )
        broken_audit = run_python_expect_failure_capture("aps.py", "status", str(project))
        if "最后状态" not in broken_audit or "transitions.jsonl" not in broken_audit:
            raise SystemExit("transition audit mismatch was not rejected")
        non_initial = {
            **transition,
            "event_id": "TRN-NONINITIAL-001",
            "from_state": complete_state,
            "to_state": {**complete_state, "stage": 2, "stage_status": "ACTIVE", "gate_status": "PENDING"},
        }
        audit.write_text(json.dumps(non_initial, ensure_ascii=False) + "\n", encoding="utf-8")
        non_initial_output = run_python_expect_failure_capture("aps.py", "status", str(project))
        if "第一条记录必须从空状态开始" not in non_initial_output:
            raise SystemExit("non-initial transition audit chain was accepted")
        profile.write_bytes(profile_bytes)
        write_transition_audit(project)
        codex_handoff = run_python_capture_env({"PATH": ""}, "aps.py", "init", str(temp / "codex-mode-project"), "--host", "codex", "--no-git")
        if "Codex CLI was not found" not in codex_handoff or "可审查计划" not in codex_handoff or "will not auto-launch" in codex_handoff:
            raise SystemExit("Codex init did not provide a normal session path with planning guidance")
        cycle_two_complete_wrong_stage = (
            normal_state.replace("revision: 1", "revision: 3")
            .replace("cycle: CYCLE-001", "cycle: CYCLE-002")
            .replace("stage: 1", "stage: 22")
            .replace("stage_type: GATED", "stage_type: ROUTER")
            .replace("stage_status: ACTIVE", "stage_status: COMPLETE")
            .replace("gate_status: PENDING", "gate_status: null")
        )
        state.write_text(cycle_two_complete_wrong_stage, encoding="utf-8")
        write_transition_audit(project)
        registry = project / ".ai" / "registry.yaml"
        registry_before = registry.read_bytes()
        registry.write_text(
            """schema_version: 1
standard_version: "__CLI_VERSION__"
revision: 1
sources:
  broken_source:
    domain: Broken Source
    path: ../outside
    status: ACTIVE
    load_policy: stage
artifacts: {}
dependencies: {}
critical_skills: {}
""".replace("__CLI_VERSION__", CLI_VERSION),
            encoding="utf-8",
        )
        bad_registry_doctor = run_python_expect_failure_capture("aps.py", "doctor", str(project), "--host", "generic", "--standard-only")
        bad_registry_status = run_python_expect_failure_capture("aps.py", "status", str(project))
        bad_registry_resume = run_python_expect_failure_capture("aps.py", "resume", str(project), "--host", "generic", "--no-launch")
        for output, label in (
            (bad_registry_doctor, "bad registry doctor"),
            (bad_registry_status, "bad registry status"),
            (bad_registry_resume, "bad registry resume"),
        ):
            assert_single_next(output, label)
            if "registry.yaml.sources.broken_source.path" not in output or "templates/registry.yaml" not in output:
                raise SystemExit(f"{label} did not provide precise Registry repair guidance")
        if "APS Agent Handoff" in bad_registry_resume:
            raise SystemExit("bad Registry generated a normal resume handoff")
        registry.write_bytes(registry_before)
        registry.write_text(
            """schema_version: 1
standard_version: "__CLI_VERSION__"
revision: 1
revision: 2
sources:
  duplicate_source:
    domain: Duplicate Source
    path: .ai/standards/lifecycle.md
    status: ACTIVE
    load_policy: stage
artifacts: {}
dependencies: {}
critical_skills: {}
""".replace("__CLI_VERSION__", CLI_VERSION),
            encoding="utf-8",
        )
        duplicate_registry = run_python_expect_failure_capture("aps.py", "status", str(project))
        if "字段重复" not in duplicate_registry:
            raise SystemExit("duplicate Registry fields were accepted")
        registry.write_bytes(registry_before)

        from aps_cli import cli as cli_module

        original_load_runtime_state = cli_module.load_runtime_state
        try:
            cli_module.load_runtime_state = lambda _root: (_ for _ in ()).throw(RuntimeError("simulated reparse point"))
            _, runtime_error = cli_module.runtime_state(project)
        finally:
            cli_module.load_runtime_state = original_load_runtime_state
        if runtime_error != "simulated reparse point":
            raise SystemExit("runtime_state did not normalize reparse errors")

        wrong_stage_rebaseline = run_python_expect_failure_capture("aps.py", "rebaseline", str(project), "--host", "generic", "--no-launch", "--confirm")
        if "Stage 23" not in wrong_stage_rebaseline:
            raise SystemExit("rebaseline accepted a completed non-Stage-23 cycle")
        state.write_text(normal_state.replace("cycle: CYCLE-001", "cycle: CYCLE-002"), encoding="utf-8")
        write_transition_audit(project)

        decision_dir = project / ".ai" / "cycles" / "CYCLE-002" / "stages" / "01-idea" / "decision-requests"
        decision_dir.mkdir(parents=True)
        decision_path = decision_dir / "DEC-001.json"
        decision_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "id": "DEC-001",
                    "status": "PENDING",
                    "cycle": "CYCLE-002",
                    "stage": 1,
                    "input_type": "single_select",
                    "question": "选择产品入口",
                    "why_now": "两个方向会导致不同产品路线",
                    "decision_card": {
                        "impact": {
                            "code": "影响入口和核心路由实现",
                            "documentation": "需要更新产品方向和使用说明",
                            "time": "约 1-2 个工作日",
                        },
                        "confirmation_method": "回复 A 或 B，并说明理由",
                    },
                    "options": [
                        {
                            "id": "A",
                            "title": "方案 A",
                            "summary": "快速验证",
                            "tradeoffs": ["优点：验证速度快", "缺点：长期控制较弱"],
                        },
                        {
                            "id": "B",
                            "title": "方案 B",
                            "summary": "长期控制",
                            "tradeoffs": ["优点：长期可控", "缺点：初期成本较高"],
                        },
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
        request_output = run_python_capture("aps.py", "decision", "request", str(decision_path), str(project))
        if "decision card" not in request_output or "pros/cons" not in request_output:
            raise SystemExit("decision request did not require a complete decision card")
        invalid_decision_path = decision_dir / "DEC-INVALID.json"
        invalid_decision = json.loads(decision_path.read_text(encoding="utf-8"))
        invalid_decision["id"] = "DEC-INVALID"
        invalid_decision["stage"] = True
        invalid_decision["options"][0]["id"] = ""
        invalid_decision_path.write_text(json.dumps(invalid_decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        invalid_decision_output = run_python_expect_failure_capture("aps.py", "decision", "request", str(invalid_decision_path), str(project))
        if "stage" not in invalid_decision_output:
            raise SystemExit("invalid decision request was accepted")
        run_python("aps.py", "decision", "list", str(project))
        status_output = run_python_capture("aps.py", "status", str(project))
        if "Pending decisions: DEC-001" not in status_output:
            raise SystemExit("status did not show the pending decision")
        run_python("aps.py", "decision", "show", "DEC-001", str(project))
        answer_output = run_python_capture("aps.py", "decision", "answer", "DEC-001", "B", str(project), "--reason", "长期控制更适合当前目标")
        if "Gate PASS" not in answer_output or "NEXT" not in answer_output:
            raise SystemExit("decision answer did not explain Gate impact and next step")
        run_python("aps.py", "decision", "show", "DEC-001", str(project))
        if json.loads(decision_path.read_text(encoding="utf-8"))["status"] != "RESOLVED":
            raise SystemExit("decision request status was not resolved")
        state_text = state.read_text(encoding="utf-8")
        if "pending_decision_refs: []" not in state_text or "user_decision" in state_text:
            raise SystemExit("decision answer did not clear the pending blocker")
        decisions = (project / ".ai" / "decisions.md").read_text(encoding="utf-8")
        if "## DEC-001" not in decisions or "Decision: B" not in decisions or "Impact:" not in decisions or "Confirmation:" not in decisions:
            raise SystemExit("decision answer was not written to the decision log")
        repeated_answer = run_python_capture("aps.py", "decision", "answer", "DEC-001", "A", str(project))
        if "already recorded" not in repeated_answer:
            raise SystemExit("repeated decision answer was not idempotent")

        multi_path = decision_dir / "DEC-002.json"
        multi_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "id": "DEC-002",
                    "status": "PENDING",
                    "cycle": "CYCLE-002",
                    "stage": 1,
                    "input_type": "multi_select",
                    "question": "选择需要保留的能力",
                    "why_now": "多个能力可以独立组合",
                    "decision_card": {
                        "impact": {
                            "code": "影响能力开关和组合逻辑",
                            "documentation": "更新能力清单",
                            "time": "约半天",
                        },
                        "confirmation_method": "回复要保留的选项 ID",
                    },
                    "options": [
                        {"id": "A", "title": "能力 A", "tradeoffs": ["优点：收益明确", "缺点：增加维护面"]},
                        {"id": "B", "title": "能力 B", "tradeoffs": ["优点：实现简单", "缺点：覆盖范围较小"]},
                        {"id": "C", "title": "能力 C", "tradeoffs": ["优点：扩展性好", "缺点：验证成本较高"]},
                        {"id": "D", "title": "能力 D", "tradeoffs": ["优点：可暂缓投入", "缺点：当前价值无法兑现"]},
                    ],
                    "recommended": "A",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run_python("aps.py", "decision", "request", str(multi_path), str(project))
        handoff_before = snapshot_files(project)
        handoff_output = run_python_capture("aps.py", "resume", str(project), "--host", "generic", "--no-launch")
        if (
            "Current APS handoff:" not in handoff_output
            or "Pending decisions: DEC-002" not in handoff_output
            or "=== APS Agent Handoff ===" not in handoff_output
            or "```text" not in handoff_output
            or "不写入项目文件" not in handoff_output
        ):
            raise SystemExit("resume handoff did not include the pending decision")
        if snapshot_files(project) != handoff_before:
            raise SystemExit("resume handoff changed the project workspace")
        run_python("aps.py", "decision", "answer", "DEC-002", "A,C", str(project))
        decisions = (project / ".ai" / "decisions.md").read_text(encoding="utf-8")
        if "## DEC-002" not in decisions or "Decision: A, C" not in decisions:
            raise SystemExit("multi-select decision answer was not recorded")

        cancel_path = decision_dir / "DEC-003.json"
        cancel_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "id": "DEC-003",
                    "status": "PENDING",
                    "cycle": "CYCLE-002",
                    "stage": 1,
                    "input_type": "approval",
                    "question": "是否继续该实验",
                    "why_now": "实验方向已被范围调整取代",
                    "decision_card": {
                        "impact": {
                            "code": "影响实验任务和相关分支",
                            "documentation": "更新实验记录",
                            "time": "取消可立即释放时间",
                        },
                        "confirmation_method": "回复 YES 或 NO",
                    },
                    "options": [
                        {"id": "YES", "title": "继续", "tradeoffs": ["优点：保留已有投入", "缺点：偏离当前范围"]},
                        {"id": "NO", "title": "停止", "tradeoffs": ["优点：减少浪费", "缺点：已有实验不再延续"]},
                    ],
                    "recommended": "NO",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run_python("aps.py", "decision", "request", str(cancel_path), str(project))
        cancel_output = run_python_capture("aps.py", "decision", "cancel", "DEC-003", str(project), "--reason", "实验已被范围调整取代")
        if "NEXT" not in cancel_output:
            raise SystemExit("decision cancel did not provide a next step")
        if json.loads(cancel_path.read_text(encoding="utf-8"))["status"] != "CANCELLED":
            raise SystemExit("decision cancel did not close the request")
        decisions = (project / ".ai" / "decisions.md").read_text(encoding="utf-8")
        if "## DEC-003" not in decisions or "Decision: CANCELLED" not in decisions:
            raise SystemExit("cancelled decision was not written to the decision log")
        cancel_before_repeat = snapshot_files(project)
        repeated_cancel = run_python_capture("aps.py", "decision", "cancel", "DEC-003", str(project))
        if "already cancelled" not in repeated_cancel or snapshot_files(project) != cancel_before_repeat:
            raise SystemExit("repeated decision cancel was not idempotent")

        research_dir = project / ".ai" / "cycles" / "CYCLE-002" / "stages" / "02-market-research"
        research_dir.mkdir(parents=True)
        research_path = research_dir / "02_MARKET_RESEARCH.md"
        research_path.write_text(
            """# Market Research

## Research Brief

研究问题 / 范围：验证目标用户是否有持续需求。
方法与来源（含日期）：用户评论和访谈，2026-08-26。
关键发现：问题高频且当前替代成本高。
结论 / 建议：先验证细分场景。
未确定项：付费意愿仍需验证。
待决策项：是否进入该细分市场。

## Evidence

- Source: sample evidence
""",
            encoding="utf-8",
        )
        brief_output = run_python_capture("aps.py", "research", "brief", str(research_path), str(project))
        if "Research Brief:" not in brief_output or "结论 / 建议" not in brief_output:
            raise SystemExit("research brief was not rendered")
        missing_research = research_dir / "MISSING_BRIEF.md"
        missing_research.write_text("# Missing\n\n## Research Brief\n\n研究问题：只填写了范围。\n", encoding="utf-8")
        missing_output = run_python_expect_failure_capture("aps.py", "research", "brief", str(missing_research), str(project))
        if "Research Brief is missing" not in missing_output or "研究摘要缺少字段" not in missing_output:
            raise SystemExit("missing Research Brief fields did not provide repair guidance")
        snapshot_dir = project / ".ai" / "cycles" / "CYCLE-002" / "stages" / "08-requirements"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        current_revision = int(re.search(r"(?m)^revision:\s*(\d+)", state.read_text(encoding="utf-8")).group(1))
        snapshot = snapshot_dir / "08_PRD_SNAPSHOT.md"
        snapshot.write_text(f"# PRD Snapshot\n\n- Current Status：ACTIVE\n- Source State Revision：{current_revision}\n", encoding="utf-8")
        run_python("aps.py", "status", str(project))
        snapshot.write_text(snapshot.read_text(encoding="utf-8").replace(f"Source State Revision：{current_revision}", "Source State Revision：1"), encoding="utf-8")
        stale_snapshot = run_python_expect_failure_capture("aps.py", "status", str(project))
        if "PRD Snapshot" not in stale_snapshot or "Source State Revision" not in stale_snapshot or "aps status" not in stale_snapshot or "doctor --standard-only" in stale_snapshot:
            raise SystemExit("stale PRD Snapshot was not rejected")
        snapshot.unlink()
        run_python("aps.py", "doctor", str(project), "--host", "generic")

        release_governance = temp / "release-governance-project"
        run_python("aps.py", "init", str(release_governance), "--host", "generic", "--no-launch", "--no-git")
        release_state = release_governance / ".ai" / "state.yaml"
        release_state_text = (release_governance / ".ai" / "templates" / "state.yaml").read_text(encoding="utf-8")
        release_state_text = release_state_text.replace("revision: 1", "revision: 3").replace("stage: 1", "stage: 21").replace("stage_type: GATED", "stage_type: OBSERVATION_LOOP").replace("gate_status: PENDING", "gate_status: null")
        release_state.write_text(release_state_text, encoding="utf-8")
        write_transition_audit(release_governance)
        for runtime_file in ("decisions.md", "registry.yaml"):
            (release_governance / ".ai" / runtime_file).write_text(
                (release_governance / ".ai" / "templates" / runtime_file).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        release_profile = release_governance / ".ai" / "project-profile.json"
        release_profile_data = json.loads((release_governance / ".ai" / "templates" / "project-profile.json").read_text(encoding="utf-8"))
        release_profile_data["risk_profile"] = "REGULATED"
        release_profile_data["workstreams"] = [{"id": "WS-CORE", "name": "核心工作流", "status": "ACTIVE", "owner": "compliance-team", "depends_on": []}]
        release_profile.write_text(json.dumps(release_profile_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        missing_readiness = run_python_expect_failure_capture("aps.py", "status", str(release_governance))
        if "Release readiness" not in missing_readiness or "release-readiness.json" not in missing_readiness:
            raise SystemExit("release boundary did not require readiness evidence")
        checks = {name: {"status": "PASS", "evidence_refs": [f"TEST-{name.upper()}"]} for name in ("lint", "typecheck", "unit", "integration", "e2e", "performance", "migration", "security", "privacy_compliance", "traceability", "security_approval", "functional_qa", "monitoring", "rollback", "audit_retention", "disaster_recovery", "on_call", "external_acceptance")}
        readiness = json.loads((release_governance / ".ai" / "templates" / "release-readiness.json").read_text(encoding="utf-8"))
        readiness.update({"release_id": "REL-001", "profile": "REGULATED", "status": "READY", "target_environment": "production", "checks": checks, "workstream_refs": ["WS-CORE"], "reviewed_at": "2026-08-27T00:00:03+00:00", "approved_by": "release-owner"})
        (release_governance / ".ai" / "release-readiness.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        run_python("aps.py", "doctor", str(release_governance), "--host", "generic")

        before_upgrade = snapshot_files(project)
        run_python("aps.py", "upgrade", str(project), "--host", "generic")
        if snapshot_files(project) != before_upgrade:
            raise SystemExit("same-version upgrade changed the governed project")

        managed = project / ".ai" / "standards" / "lifecycle.md"
        expected = ROOT / "src" / "aps_cli" / "bundle" / "package" / "standards" / "lifecycle.md"
        managed.write_bytes(managed.read_bytes() + b"\nlocal smoke edit\n")
        run_python("aps.py", "upgrade", str(project), "--host", "generic")
        incoming = list((project / ".ai" / "incoming").rglob("lifecycle.md"))
        if not incoming:
            raise SystemExit("upgrade did not preserve a locally modified managed file")
        conflict_status = run_python_expect_failure_capture("aps.py", "status", str(project))
        conflict_resume = run_python_expect_failure_capture("aps.py", "resume", str(project), "--host", "generic", "--no-launch")
        if "未解决" not in conflict_status or "aps upgrade" not in conflict_status or "APS Agent Handoff" in conflict_resume:
            raise SystemExit("managed conflict did not block status/resume recovery")
        managed.write_bytes(expected.read_bytes())
        run_python("aps.py", "upgrade", str(project), "--host", "generic")
        merged_status = run_python_capture("aps.py", "status", str(project))
        if "Managed conflicts: 0" not in merged_status:
            raise SystemExit("manual managed-file merge did not clear the conflict")
        managed.write_bytes(managed.read_bytes() + b"\nlocal smoke edit again\n")
        run_python("aps.py", "upgrade", str(project), "--host", "generic")
        before_repeat_conflict = snapshot_files(project)
        run_python("aps.py", "upgrade", str(project), "--host", "generic")
        if snapshot_files(project) != before_repeat_conflict:
            raise SystemExit("repeated conflict upgrade changed the project")

        run_python("aps.py", "upgrade", str(project), "--host", "generic", "--force-managed")
        if managed.read_bytes() != expected.read_bytes():
            raise SystemExit("force-managed upgrade did not install the bundled file")
        backups = snapshot_files(project / ".ai" / "archive" / "install-backups")
        if not backups:
            raise SystemExit("force-managed upgrade did not create a backup")
        run_python("aps.py", "upgrade", str(project), "--host", "generic", "--force-managed")
        if snapshot_files(project / ".ai" / "archive" / "install-backups") != backups:
            raise SystemExit("repeated force-managed upgrade created duplicate backups")

        collision = temp / "collision-project"
        (collision / ".ai" / "standards").mkdir(parents=True)
        (collision / ".ai" / "standards" / "lifecycle.md").write_bytes(expected.read_bytes())
        (collision / "AGENTS.md").mkdir()
        collision_before = snapshot_files(collision)
        collision_output = run_python_expect_failure_capture("aps.py", "upgrade", str(collision), "--host", "generic")
        if "项目边界不安全" not in collision_output or snapshot_files(collision) != collision_before:
            raise SystemExit("directory collision did not fail before modifying the project")

        transaction_project = temp / "transaction-project"
        run_python("aps.py", "init", str(transaction_project), "--host", "generic", "--no-launch", "--no-git")
        transaction_files = [
            transaction_project / ".ai" / "standards" / "lifecycle.md",
            transaction_project / ".ai" / "standards" / "artifact-state.md",
        ]
        for path in transaction_files:
            path.unlink()
        transaction_before = snapshot_files(transaction_project)
        sys.path.insert(0, str(ROOT / "src"))
        from aps_cli import installer as installer_module

        original_copy_file_atomic = installer_module.copy_file_atomic
        copy_calls = {"count": 0}

        def fail_on_second_copy(source: Path, destination: Path) -> None:
            copy_calls["count"] += 1
            if copy_calls["count"] == 2:
                raise RuntimeError("simulated commit failure")
            original_copy_file_atomic(source, destination)

        installer_module.copy_file_atomic = fail_on_second_copy
        try:
            try:
                installer_module.install_standard(ROOT / "src" / "aps_cli" / "bundle", transaction_project, host="generic", quiet=True)
            except RuntimeError as exc:
                if "simulated commit failure" not in str(exc):
                    raise
            else:
                raise SystemExit("simulated installer commit failure did not fail")
        finally:
            installer_module.copy_file_atomic = original_copy_file_atomic
        if copy_calls["count"] < 2 or snapshot_files(transaction_project) != transaction_before:
            raise SystemExit("installer commit failure did not fully roll back")

        unsafe_bundle = temp / "unsafe-bundle"
        shutil.copytree(ROOT / "src" / "aps_cli" / "bundle", unsafe_bundle)
        unsafe_manifest_path = unsafe_bundle / "package-manifest.json"
        unsafe_manifest = json.loads(unsafe_manifest_path.read_text(encoding="utf-8"))
        unsafe_manifest["version"] = f"../{CLI_VERSION}"
        unsafe_manifest_path.write_text(json.dumps(unsafe_manifest), encoding="utf-8")
        try:
            installer_module.validate_bundle(unsafe_bundle)
        except RuntimeError:
            pass
        else:
            raise SystemExit("unsafe bundle version was accepted")

        unsafe_bundle_path = temp / "unsafe-bundle-path"
        shutil.copytree(ROOT / "src" / "aps_cli" / "bundle", unsafe_bundle_path)
        unsafe_path_manifest_path = unsafe_bundle_path / "package-manifest.json"
        unsafe_path_manifest = json.loads(unsafe_path_manifest_path.read_text(encoding="utf-8"))
        unsafe_path_manifest["payload_sha256"]["../escape.txt"] = "0" * 64
        unsafe_path_manifest_path.write_text(json.dumps(unsafe_path_manifest), encoding="utf-8")
        try:
            installer_module.validate_bundle(unsafe_bundle_path)
        except RuntimeError:
            pass
        else:
            raise SystemExit("unsafe bundle payload path was accepted")

        malicious_zip = temp / "malicious.zip"
        with zipfile.ZipFile(malicious_zip, "w") as archive_file:
            archive_file.writestr("../escape.txt", "must not extract")
        try:
            safe_extract_zip(malicious_zip, temp / "malicious-extract")
        except ValueError:
            pass
        else:
            raise SystemExit("ZIP path traversal was accepted")
        if "Test-SafeZip" not in (ROOT / "install.ps1").read_text(encoding="utf-8") or "extractall" in (ROOT / "install.sh").read_text(encoding="utf-8"):
            raise SystemExit("online installer ZIP safety boundary is missing")

        symlink_bundle = temp / "symlink-bundle"
        try:
            shutil.copytree(ROOT / "src" / "aps_cli" / "bundle", symlink_bundle)
            symlink_payload = symlink_bundle / "package" / "standards" / "lifecycle.md"
            symlink_payload.unlink()
            symlink_payload.symlink_to(symlink_bundle / "package" / "standards" / "artifact-state.md")
        except (OSError, NotImplementedError):
            print("WARN  当前环境不允许创建 symlink，跳过 symlink smoke")
        else:
            try:
                installer_module.validate_bundle(symlink_bundle)
            except RuntimeError:
                pass
            else:
                raise SystemExit("symlink bundle payload was accepted")

        linked_project = temp / "linked-project"
        try:
            linked_project.symlink_to(project, target_is_directory=True)
        except (OSError, NotImplementedError):
            print("WARN  当前环境不允许创建项目 symlink，跳过 project boundary smoke")
        else:
            linked_status = run_python_expect_failure_capture("aps.py", "status", str(linked_project))
            if "项目边界不安全" not in linked_status:
                raise SystemExit("project symlink was followed by status")

        linked_research = research_dir / "LINKED.md"
        try:
            linked_research.symlink_to(research_path)
        except (OSError, NotImplementedError):
            print("WARN  当前环境不允许创建 Research Artifact symlink，跳过 research link smoke")
        else:
            linked_research_output = run_python_expect_failure_capture(
                "aps.py",
                "research",
                "brief",
                str(linked_research.relative_to(project)),
                str(project),
            )
            if "符号链接" not in linked_research_output and "reparse" not in linked_research_output:
                raise SystemExit("Research Artifact symlink was followed")

        pseudo_research = research_dir / "PSEUDO_KEYWORDS.md"
        pseudo_research.write_text(
            """# Pseudo\n\n## Research Brief\n\n正文提到 Question、Method、Key Findings、Conclusion、Uncertainty 和 Pending Decisions，引用中也出现这些词。\n""",
            encoding="utf-8",
        )
        pseudo_output = run_python_expect_failure_capture("aps.py", "research", "brief", str(pseudo_research), str(project))
        if "Research Brief is missing" not in pseudo_output or "研究问题 / 范围" not in pseudo_output:
            raise SystemExit("Research Brief pseudo-keyword content was accepted")

        cp1252_status = run_python_capture_env({"PYTHONIOENCODING": "cp1252"}, "aps.py", "status", str(project))
        if "Project:" not in cp1252_status or "Managed conflicts: 0" not in cp1252_status:
            raise SystemExit("cp1252 environment did not produce stable UTF-8 CLI output")

        run_python("scripts/build_release.py", "--refresh-manifest")
        archive = ROOT / "dist" / f"APS_CLI_{CLI_VERSION}.zip"
        with zipfile.ZipFile(archive) as release_zip:
            names = {name.split("/", 1)[1] for name in release_zip.namelist() if "/" in name}
        allowed = {
            "aps.py",
            "install_cli.py",
            "install.sh",
            "install.ps1",
            "install.cmd",
            "VERSION",
            "README.md",
            "QUICKSTART_中文.txt",
            *{
                path.relative_to(ROOT).as_posix()
                for path in (ROOT / "src" / "aps_cli").rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            },
        }
        if names != allowed:
            raise SystemExit(f"release archive contents are not allowlisted: {sorted(names ^ allowed)[:3]}")
        extracted = temp / "release"
        with zipfile.ZipFile(archive) as bundle:
            safe_extract_zip(archive, extracted)
        installer = next(extracted.rglob("install_cli.py"))
        prefix = temp / "prefix"
        collision_prefix = temp / "collision-prefix"
        collision_bin = collision_prefix / ("Scripts" if sys.platform == "win32" else "bin")
        collision_bin.parent.mkdir(parents=True)
        collision_bin.write_text("not a directory\n", encoding="utf-8")
        collision_output = run_python_expect_failure_capture(str(installer), "--prefix", str(collision_prefix), cwd=extracted)
        if "目录" not in collision_output or (collision_prefix / "share" / "aps-cli" / "current").exists():
            raise SystemExit("CLI installer directory collision left a partial installation")
        run_python(str(installer), "--prefix", str(prefix), cwd=extracted)
        release_project = temp / "release-project"
        launcher = prefix / ("Scripts/aps.cmd" if sys.platform == "win32" else "bin/aps")
        run_launcher(launcher, ["init", str(release_project), "--host", "generic", "--no-launch", "--no-git"])
        run_launcher(launcher, ["doctor", str(release_project), "--host", "generic", "--standard-only"])

        monorepo = temp / "monorepo"
        monorepo.mkdir()
        run(["git", "init"], cwd=monorepo)
        monorepo_project = monorepo / "project"
        run_python("aps.py", "init", str(monorepo_project), "--host", "generic", "--no-launch")
        if (monorepo_project / ".git").exists() or (monorepo_project / ".git").is_symlink():
            raise SystemExit("init created a nested Git repository inside an existing monorepo")
        (monorepo_project / ".ai" / "state.yaml").write_text(
            (monorepo_project / ".ai" / "templates" / "state.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        for runtime_file in ("decisions.md", "registry.yaml"):
            (monorepo_project / ".ai" / runtime_file).write_text(
                (monorepo_project / ".ai" / "templates" / runtime_file).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        (monorepo_project / ".ai" / "project-profile.json").write_text(
            (monorepo_project / ".ai" / "templates" / "project-profile.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        write_transition_audit(monorepo_project)
        run_python("aps.py", "doctor", str(monorepo_project), "--host", "generic")
    print("APS smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
