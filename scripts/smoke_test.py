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


def snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


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
    with tempfile.TemporaryDirectory(prefix="aps-smoke-") as raw_temp:
        temp = Path(raw_temp)
        help_output = run_python_capture("aps.py", "--help")
        if "典型路径" not in help_output or "aps decision request" not in help_output or "aps research brief" not in help_output:
            raise SystemExit("CLI help does not include Chinese scenarios and decision/research paths")
        project = temp / "source-project"
        run_python("aps.py", "init", str(project), "--host", "generic", "--no-launch", "--no-git")
        run_python("aps.py", "doctor", str(project), "--host", "generic", "--standard-only")
        bootstrap_prompt = (project / ".ai" / "bootstrap" / "bootstrap-prompt.txt").read_text(encoding="utf-8")
        required_prompt_markers = ("优点", "缺点", "适用条件", "主要风险", "直接回答原始研究问题", "分析关键证据", "用户需要 PRD 时", "prd-snapshot.md")
        if any(marker not in bootstrap_prompt for marker in required_prompt_markers):
            raise SystemExit("bootstrap prompt does not require decision and research analysis")
        plan_prompt_markers = ("Codex", "Plan 模式", "Stage 01、05、06、07、08、09、10、13、14、15、16、20", "Host capability blocker")
        if any(marker not in bootstrap_prompt for marker in plan_prompt_markers):
            raise SystemExit("bootstrap prompt does not enforce Plan mode entry")

        before_repeat = snapshot_files(project)
        if not (project / ".ai" / "templates" / "prd-snapshot.md").is_file():
            raise SystemExit("PRD Snapshot template was not installed")
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

        ordinary = temp / "ordinary-project"
        ordinary.mkdir()
        (ordinary / "app.txt").write_text("ordinary project\n", encoding="utf-8")
        ordinary_before = snapshot_files(ordinary)
        ordinary_upgrade = run_python_expect_failure_capture("aps.py", "upgrade", str(ordinary), "--host", "generic")
        if "aps resume --no-launch" not in ordinary_upgrade or snapshot_files(ordinary) != ordinary_before:
            raise SystemExit("upgrade took over an ordinary ungoverned project")

        empty = temp / "empty-project"
        empty.mkdir()
        empty_upgrade = run_python_expect_failure_capture("aps.py", "upgrade", str(empty), "--host", "generic")
        if "aps init --no-launch" not in empty_upgrade or snapshot_files(empty):
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
        manifest.write_text(manifest.read_text(encoding="utf-8").replace('"version": "1.2.2"', '"version": "0.0.0"'), encoding="utf-8")
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
        before_menu_cancel = snapshot_files(project)
        menu_output = run_python_with_input("3\nn\n", str(ROOT / "aps.py"), cwd=project)
        if "已取消 rebaseline" not in menu_output or snapshot_files(project) != before_menu_cancel:
            raise SystemExit("cancelled interactive rebaseline changed the project")
        run_python("aps.py", "rebaseline", str(project), "--host", "generic", "--no-launch", "--confirm")
        initial_status = run_python_capture("aps.py", "status", str(project))
        if "Next action:" not in initial_status or "Mode gate: PLAN (required on Stage entry)" not in initial_status:
            raise SystemExit("status did not provide the Stage Plan mode gate and next action")
        codex_resume = run_python_capture("aps.py", "resume", str(project), "--host", "codex")
        if "Plan mode is required" not in codex_resume or "will not auto-launch" not in codex_resume:
            raise SystemExit("Codex resume did not block a normal session for a Plan-required Stage")
        normal_state = state.read_text(encoding="utf-8")
        state.unlink()
        missing_state_status = run_python_capture("aps.py", "status", str(project))
        missing_state_resume = run_python_capture("aps.py", "resume", str(project), "--host", "codex")
        if "not initialized" not in missing_state_status or "will not auto-launch" not in missing_state_resume:
            raise SystemExit("missing state did not stay fail-closed for Codex resume")
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
            if "Runtime state" not in invalid_status or "NORMAL" in invalid_status or "APS Agent Handoff" in invalid_resume:
                raise SystemExit("malformed state was treated as a normal resumable state")
        state.write_bytes(b"\xff\xfe\xfd")
        invalid_encoding_status = run_python_expect_failure_capture("aps.py", "status", str(project))
        invalid_encoding_resume = run_python_expect_failure_capture("aps.py", "resume", str(project), "--host", "generic", "--no-launch")
        if "Runtime state" not in invalid_encoding_status or "doctor --standard-only" not in invalid_encoding_status or "APS Agent Handoff" in invalid_encoding_resume:
            raise SystemExit("non-UTF8 state was not rejected with the state recovery path")
        state.write_text(normal_state, encoding="utf-8")
        state.write_text(normal_state.replace("stage: 1", "stage: 17").replace("stage_type: GATED", "stage_type: EXECUTION_LOOP").replace("gate_status: PENDING", "gate_status: null"), encoding="utf-8")
        normal_status = run_python_capture("aps.py", "status", str(project))
        if "Mode gate: NORMAL (Plan mode not required)" not in normal_status:
            raise SystemExit("status incorrectly required Plan mode for an execution Stage")
        state.write_text(normal_state.replace("stage: 1", "stage: 22").replace("stage_type: GATED", "stage_type: ROUTER").replace("gate_status: PENDING", "gate_status: null").replace("active_change_refs: []", "active_change_refs: [CHANGE-001]"), encoding="utf-8")
        change_status = run_python_capture("aps.py", "status", str(project))
        if "Mode gate: PLAN (required on Stage entry)" not in change_status:
            raise SystemExit("status did not require Plan mode for an active Stage 22 change")
        state.write_text(normal_state, encoding="utf-8")
        codex_handoff = run_python_capture("aps.py", "init", str(temp / "codex-mode-project"), "--host", "codex", "--no-git")
        if "Plan mode is required" not in codex_handoff or "will not auto-launch" not in codex_handoff:
            raise SystemExit("Codex handoff did not block a normal session for a Plan-required Stage")
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
        run_python_expect_failure("aps.py", "decision", "answer", "DEC-001", "A", str(project))

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
        run_python("aps.py", "doctor", str(project), "--host", "generic")

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
        unsafe_manifest["version"] = "../1.2.2"
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
        archive = next((ROOT / "dist").glob("APS_CLI_*.zip"))
        extracted = temp / "release"
        with zipfile.ZipFile(archive) as bundle:
            safe_extract_zip(archive, extracted)
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
