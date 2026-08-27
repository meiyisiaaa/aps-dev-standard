#!/usr/bin/env python3
"""Static/runtime linter for the AI Development Standards v1.x.

No non-stdlib dependency is required. If PyYAML is available, project-state checks
become stricter. The script can validate the standards bundle alone or also audit a
Codex project runtime.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None

try:
    import yaml  # optional
except Exception:  # pragma: no cover
    yaml = None

EXPECTED_GATE = {"PENDING", "PASS", "REVISE", "HOLD", "STOP"}
EXPECTED_STAGE_TYPES = {"GATED", "EXECUTION_LOOP", "OBSERVATION_LOOP", "ROUTER"}


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.ok: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def pass_(self, msg: str) -> None:
        self.ok.append(msg)

    def emit(self) -> int:
        for msg in self.ok:
            print(f"PASS  {msg}")
        for msg in self.warnings:
            print(f"WARN  {msg}")
        for msg in self.errors:
            print(f"FAIL  {msg}")
        print(f"\nSummary: {len(self.ok)} passed, {len(self.warnings)} warnings, {len(self.errors)} failures")
        return 1 if self.errors else 0


def read(path: Path, report: Report) -> str:
    if not path.is_file():
        report.error(f"missing file: {path}")
        return ""
    return path.read_text(encoding="utf-8")


def validate_bundle(lifecycle: Path, artifact: Path, bootstrap: Path, report: Report) -> None:
    life = read(lifecycle, report)
    art = read(artifact, report)
    boot = read(bootstrap, report)
    if not life or not art or not boot:
        return

    lifecycle_version = re.search(r"\*\*Standard Version:\*\* `([^`]+)`", life)
    if not lifecycle_version:
        report.error("lifecycle standard version is missing")
    else:
        expected_version = lifecycle_version.group(1)
        for name, text in [("lifecycle", life), ("artifact", art)]:
            declared = re.search(r"\*\*Standard Version:\*\* `([^`]+)`", text)
            if declared and declared.group(1) == expected_version:
                report.pass_(f"{name} standard version = {expected_version}")
            else:
                report.error(f"{name} standard version does not match {expected_version}")
            if text.count("```") % 2 == 0:
                report.pass_(f"{name} markdown code fences are balanced")
            else:
                report.error(f"{name} markdown code fences are unbalanced")

    # Stage 01..23: only top-level numbered lifecycle stages, excluding standards sections 24+.
    stages = [int(n) for n in re.findall(r"(?m)^# (\d{1,2})\. ", life) if 1 <= int(n) <= 23]
    if stages == list(range(1, 24)):
        report.pass_("lifecycle contains exactly Stage 01-23 in order")
    else:
        report.error(f"Stage sequence mismatch: {stages}")

    required_lifecycle_sections = [
        "## 0.7 Context Loading & Budget",
        "## 0.13 Gate State Machine",
        "### 0.3.1 Stage Entry / Host Plan Mode",
        "### 0.3.2 Project Risk Profile / Workstream",
        "# 31. Agent Runtime Standard",
        "## 32.4 Skill Security Contract",
        "# 35. Multi-Agent Concurrency & Governance",
        "# 36. Standard Self-Validation",
    ]
    for s in required_lifecycle_sections:
        if s in life:
            report.pass_(f"lifecycle section present: {s}")
        else:
            report.error(f"missing lifecycle section: {s}")

    # Unified Gate enum.
    gate_block = re.search(r"## 0\.13 Gate State Machine(.*?)(?:\n---\n|\n# 1\.)", life, re.S)
    if not gate_block:
        report.error("Gate State Machine section not parseable")
    else:
        found = set(re.findall(r"(?m)^(PENDING|PASS|REVISE|HOLD|STOP)$", gate_block.group(1)))
        if found == EXPECTED_GATE:
            report.pass_("GateStatus enum is unified")
        else:
            report.error(f"GateStatus enum mismatch: {sorted(found)}")

    # Loop/router stages must explicitly close their transitions.
    for stage, marker in [(17, "## Transition Contract"), (21, "## Transition Contract"), (22, "## Transition Contract")]:
        m = re.search(rf"(?ms)^# {stage}\. .*?(?=^# {stage+1}\.|\Z)", life)
        if m and marker in m.group(0):
            report.pass_(f"Stage {stage} has explicit Transition Contract")
        else:
            report.error(f"Stage {stage} lacks explicit Transition Contract")

    # No legacy state as active source.
    legacy_patterns = [r"PROJECT_STATE\.md", r"→\s+DECISIONS\.md"]
    for p in legacy_patterns:
        if re.search(p, life + "\n" + art + "\n" + boot):
            report.error(f"legacy authoritative path still present: {p}")
    if ".ai/state.yaml" in life and ".ai/state.yaml" in art and ".ai/state.yaml" in boot:
        report.pass_("machine-readable project state is consistently referenced")

    for token in [".ai/registry.yaml", ".ai/cycles/<ACTIVE_CYCLE>/stages/", "09_WIREFRAMES/"]:
        if token in art:
            report.pass_(f"artifact layout contains {token}")
        else:
            report.error(f"artifact layout missing {token}")

    # Compare logical lifecycle outputs with physical artifact mapping.
    logical_files = set()
    for n in range(1, 24):
        m = re.search(rf"(?ms)^# {n}\. .*?(?=^# {n+1}\.|^# 24\.|\Z)", life)
        if not m:
            continue
        out = re.search(r"(?ms)^## 产物\n(.*?)(?=^## |^---|\Z)", m.group(0))
        if out:
            logical_files.update(re.findall(r"([0-9]{2}_[A-Z0-9_]+(?:\.md|\.json|/))", out.group(1)))
    mapped_files = set(re.findall(r"(?:/|→ )([0-9]{2}_[A-Z0-9_]+(?:\.md|\.json|/))", art))
    missing_map = sorted(logical_files - mapped_files)
    if missing_map:
        report.error(f"logical Stage outputs missing physical artifact mapping: {missing_map}")
    else:
        report.pass_("all logical Stage outputs have physical artifact mappings")

    required_art_sections = [
        "# 24. Multi-Agent Write Governance",
        "# 25. Evidence / Binary Retention",
        "# 26. Context Hygiene",
        "## 17.1 Release Readiness",
    ]
    for s in required_art_sections:
        if s in art:
            report.pass_(f"artifact section present: {s}")
        else:
            report.error(f"missing artifact section: {s}")

    if "不要先完整读取两份 Standard" in boot:
        report.pass_("bootstrap explicitly forbids eager full-standard loading")
    else:
        report.error("bootstrap does not enforce minimal-context loading")

    if "Single Writer" in boot and "compare-before-write" in boot:
        report.pass_("bootstrap includes governance concurrency controls")
    else:
        report.error("bootstrap missing concurrency controls")
    if ".ai/project-profile.json" in boot and ".ai/audit/transitions.jsonl" in boot and ".ai/release-readiness.json" in boot:
        report.pass_("bootstrap includes risk, transition audit, and release readiness paths")
    else:
        report.error("bootstrap is missing risk or release governance paths")

    if "Research Brief" in life and "当前对话" in life and "禁止只写文档后静默完成" in boot:
        report.pass_("research results require conversational delivery")
    else:
        report.error("research results are not required in the current conversation")
    plan_mode_markers = (
        "Stage 01、05、06、07、08、09、10、13、14、15、16、20",
        "Stage 22",
        "原生 Codex Plan 模式",
        "Host capability blocker",
    )
    if all(marker in life + "\n" + boot for marker in plan_mode_markers):
        report.pass_("high-impact Stage entry requires Codex Plan mode")
    else:
        report.error("Stage Plan mode entry policy is incomplete")
    stage_brief_markers = ("Stage User Brief", "目标", "输入", "已完成", "未完成", "用户决策", "确认影响", "验证结果")
    artifact_contract_markers = ("Artifact Contract", "Purpose", "Inputs", "Outputs", "Acceptance Criteria", "Current Status", "Blocking Decisions", "Next Stage")
    if all(marker in life + "\n" + art + "\n" + boot for marker in stage_brief_markers):
        report.pass_("each Stage requires a user brief")
    else:
        report.error("Stage User Brief contract is incomplete")
    if all(marker in art for marker in artifact_contract_markers):
        report.pass_("Stage Artifacts require acceptance contracts")
    else:
        report.error("Artifact Contract is incomplete")

    if "PENDING USER DECISION" in life or "PENDING USER DECISION" in boot:
        report.error("legacy pseudo GateStatus 'PENDING USER DECISION' remains in executable standard/prompt")


def read_codex_config() -> tuple[int, list[str]]:
    limit = 32768
    fallbacks: list[str] = []
    cfg = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    if cfg.is_file() and tomllib:
        try:
            data = tomllib.loads(cfg.read_text(encoding="utf-8"))
            limit = int(data.get("project_doc_max_bytes", limit))
            vals = data.get("project_doc_fallback_filenames", [])
            if isinstance(vals, list):
                fallbacks = [str(v) for v in vals]
        except Exception:
            pass
    return limit, fallbacks


def codex_instruction_chain(root: Path, cwd: Path) -> tuple[list[Path], int, int]:
    limit, fallbacks = read_codex_config()
    files: list[Path] = []
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    for name in ["AGENTS.override.md", "AGENTS.md"]:
        p = codex_home / name
        if p.is_file() and p.stat().st_size:
            files.append(p)
            break

    rel = cwd.resolve().relative_to(root.resolve()) if cwd.resolve() != root.resolve() else Path(".")
    dirs = [root]
    cur = root
    for part in rel.parts:
        if part == ".":
            continue
        cur = cur / part
        dirs.append(cur)
    names = ["AGENTS.override.md", "AGENTS.md", *fallbacks]
    for d in dirs:
        for name in names:
            p = d / name
            if p.is_file() and p.stat().st_size:
                files.append(p)
                break
    total = sum(p.stat().st_size for p in files)
    return files, total, limit


def parse_skill_name(skill_md: Path) -> str | None:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except Exception:
        return None
    m = re.match(r"\s*---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return None
    n = re.search(r"(?m)^name:\s*[\"']?([^\"'\n]+)", m.group(1))
    return n.group(1).strip() if n else None


def scan_skills(root: Path, cwd: Path) -> dict[str, list[tuple[str, Path]]]:
    out: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    locations: list[tuple[str, Path]] = []
    cur = cwd.resolve()
    root = root.resolve()
    while True:
        locations.append(("REPO", cur / ".agents" / "skills"))
        if cur == root:
            break
        if root not in cur.parents:
            break
        cur = cur.parent
    locations.extend([
        ("USER", Path.home() / ".agents" / "skills"),
        ("ADMIN", Path("/etc/codex/skills")),
    ])
    seen_dirs = set()
    for scope, base in locations:
        if base in seen_dirs or not base.is_dir():
            continue
        seen_dirs.add(base)
        for child in base.iterdir():
            skill_md = child / "SKILL.md" if child.is_dir() else None
            if skill_md and skill_md.is_file():
                name = parse_skill_name(skill_md)
                if name:
                    out[name].append((scope, skill_md))
    return out


PROFILE_RELEASE_CHECKS = {
    "NORMAL": {"lint", "build", "functional_qa", "rollback"},
    "LARGE": {"lint", "typecheck", "unit", "integration", "e2e", "performance", "migration", "security", "functional_qa", "monitoring", "rollback", "disaster_recovery", "on_call", "external_acceptance"},
    "REGULATED": {"lint", "typecheck", "unit", "integration", "e2e", "performance", "migration", "security", "privacy_compliance", "traceability", "security_approval", "functional_qa", "monitoring", "rollback", "audit_retention", "disaster_recovery", "on_call", "external_acceptance"},
}


def validate_project_governance(root: Path, state: dict, report: Report) -> None:
    profile_path = root / ".ai" / "project-profile.json"
    if not profile_path.is_file():
        report.error("missing project governance profile: .ai/project-profile.json")
        return
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if not isinstance(profile, dict):
            raise ValueError("profile must be a JSON object")
        risk = profile.get("risk_profile")
        if risk not in PROFILE_RELEASE_CHECKS:
            raise ValueError(f"invalid risk_profile: {risk}")
        if profile.get("schema_version") != 1:
            raise ValueError("profile schema_version must be 1")
        if not isinstance(profile.get("reviewed_at"), str) or not profile["reviewed_at"].strip():
            raise ValueError("profile reviewed_at must be non-empty")
        if not isinstance(profile.get("review_triggers"), list) or not profile["review_triggers"]:
            raise ValueError("profile review_triggers must be a non-empty list")
        workstreams = profile.get("workstreams")
        if not isinstance(workstreams, list):
            raise ValueError("profile workstreams must be a list")
        ids = []
        for item in workstreams:
            if not isinstance(item, dict) or not re.fullmatch(r"WS-[A-Z0-9][A-Z0-9_-]*", str(item.get("id", ""))):
                raise ValueError("profile contains an invalid workstream id")
            ids.append(item["id"])
        if len(ids) != len(set(ids)):
            raise ValueError("profile contains duplicate workstream ids")
        if risk in {"LARGE", "REGULATED"} and not workstreams:
            raise ValueError(f"{risk} profile requires at least one workstream")
        report.pass_(f"project governance profile is valid: {risk}")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        report.error(f"invalid project governance profile: {exc}")
        return

    audit_path = root / ".ai" / "audit" / "transitions.jsonl"
    if not audit_path.is_file():
        report.error("missing required transition audit log: .ai/audit/transitions.jsonl")
    elif audit_path.is_file():
        try:
            records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if not records:
                raise ValueError("transition audit log is empty")
            last = records[-1]
            if not isinstance(last, dict) or not isinstance(last.get("to_state"), dict):
                raise ValueError("last transition has no to_state")
            expected = {key: state.get(key) for key in ("cycle", "stage", "stage_type", "stage_status", "gate_status")}
            if isinstance(expected["stage"], str) and expected["stage"].isdigit():
                expected["stage"] = int(expected["stage"])
            if expected["gate_status"] in {"null", "None", ""}:
                expected["gate_status"] = None
            actual = {key: last["to_state"].get(key) for key in expected}
            if expected != actual:
                raise ValueError("last transition does not match state.yaml")
            report.pass_("transition audit log ends at the current state")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            report.error(f"invalid transition audit log: {exc}")

    stage = state.get("stage")
    gate = state.get("gate_status")
    if isinstance(stage, int) and (stage >= 21 or (stage == 20 and gate == "PASS")):
        readiness_path = root / ".ai" / "release-readiness.json"
        if not readiness_path.is_file():
            report.error("missing release readiness at release boundary: .ai/release-readiness.json")
        else:
            try:
                readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
                checks = readiness.get("checks", {}) if isinstance(readiness, dict) else {}
                missing = sorted(check for check in PROFILE_RELEASE_CHECKS[risk] if not isinstance(checks.get(check), dict) or checks[check].get("status") != "PASS")
                if readiness.get("profile") != risk or readiness.get("status") not in {"READY", "RELEASED"}:
                    report.error("release readiness profile/status is not ready")
                elif missing:
                    report.error(f"release readiness missing PASS checks: {missing}")
                else:
                    report.pass_("release readiness satisfies the risk profile")
            except (OSError, UnicodeError, json.JSONDecodeError, AttributeError) as exc:
                report.error(f"invalid release readiness: {exc}")

    cycle = state.get("cycle")
    if cycle:
        stages_root = root / ".ai" / "cycles" / str(cycle) / "stages"
        if stages_root.is_dir():
            for snapshot_path in stages_root.rglob("08_PRD_SNAPSHOT.md"):
                try:
                    snapshot_text = snapshot_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    report.error(f"cannot read PRD Snapshot {snapshot_path.relative_to(root)}: {exc}")
                    continue
                active = re.search(r"(?mi)^\s*-\s*Current Status\s*[：:]\s*ACTIVE\s*$", snapshot_text)
                if not active:
                    continue
                revision = re.search(r"(?mi)^\s*-\s*Source State Revision\s*[：:]\s*(\d+)\s*$", snapshot_text)
                current_revision = state.get("revision")
                if not revision:
                    report.error(f"active PRD Snapshot lacks Source State Revision: {snapshot_path.relative_to(root)}")
                elif str(current_revision).isdigit() and int(revision.group(1)) != int(current_revision):
                    report.error(f"active PRD Snapshot is stale: {snapshot_path.relative_to(root)}")


def validate_project(project_root: Path, cwd: Path, host: str, report: Report) -> None:
    root = project_root.expanduser().resolve()
    required_files = [
        root / "AGENTS.md",
        root / ".ai" / "state.yaml",
        root / ".ai" / "decisions.md",
        root / ".ai" / "registry.yaml",
        root / ".ai" / "schemas" / "state.schema.json",
        root / ".ai" / "schemas" / "registry.schema.json",
        root / ".ai" / "schemas" / "decision-request.schema.json",
        root / ".ai" / "schemas" / "project-profile.schema.json",
        root / ".ai" / "schemas" / "transition-record.schema.json",
        root / ".ai" / "schemas" / "release-readiness.schema.json",
        root / ".ai" / "templates" / "decision-request.json",
        root / ".ai" / "templates" / "project-profile.json",
        root / ".ai" / "templates" / "transition-record.json",
        root / ".ai" / "templates" / "release-readiness.json",
    ]
    for p in required_files:
        if p.exists():
            report.pass_(f"project runtime source exists: {p.relative_to(root)}")
        else:
            report.error(f"missing project runtime source: {p.relative_to(root)}")

    for p in [
        root / ".ai" / "schemas" / "state.schema.json",
        root / ".ai" / "schemas" / "registry.schema.json",
        root / ".ai" / "schemas" / "decision-request.schema.json",
        root / ".ai" / "schemas" / "project-profile.schema.json",
        root / ".ai" / "schemas" / "transition-record.schema.json",
        root / ".ai" / "schemas" / "release-readiness.schema.json",
    ]:
        if not p.is_file():
            continue
        try:
            schema = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(schema, dict) or schema.get("type") != "object" or not isinstance(schema.get("required"), list):
                report.error(f"invalid object schema structure: {p.relative_to(root)}")
            else:
                report.pass_(f"JSON schema parses: {p.relative_to(root)}")
        except (OSError, json.JSONDecodeError) as exc:
            report.error(f"cannot parse JSON schema {p.relative_to(root)}: {exc}")

    decision_template = root / ".ai" / "templates" / "decision-request.json"
    if decision_template.is_file():
        try:
            sample = json.loads(decision_template.read_text(encoding="utf-8"))
            required = {"schema_version", "id", "status", "cycle", "stage", "input_type", "question", "why_now", "options", "decision_card"}
            if not required.issubset(sample):
                report.error(f"decision request template missing keys: {sorted(required - set(sample))}")
            elif sample.get("schema_version") != 2:
                report.error("decision request template must use schema_version 2")
            elif sample.get("status") != "PENDING":
                report.error("decision request template must start in PENDING status")
            elif any(not option.get("tradeoffs") for option in sample.get("options", []) if isinstance(option, dict)):
                report.error("decision request template options must include tradeoffs")
            elif not isinstance(sample.get("decision_card"), dict):
                report.error("decision request template must include decision_card")
            else:
                report.pass_("decision request template parses and is pending")
        except (OSError, json.JSONDecodeError) as exc:
            report.error(f"cannot parse decision request template: {exc}")

    state = root / ".ai" / "state.yaml"
    if state.is_file():
        try:
            if yaml:
                data = yaml.safe_load(state.read_text(encoding="utf-8")) or {}
            else:
                data = {m.group(1): m.group(2) for m in re.finditer(r"(?m)^([a-zA-Z_]+):\s*(.*)$", state.read_text(encoding="utf-8"))}
            required = {"schema_version", "standard_version", "revision", "cycle", "stage", "stage_type", "stage_status", "gate_status"}
            missing = required - set(data)
            if missing:
                report.error(f"state.yaml missing keys: {sorted(missing)}")
            else:
                report.pass_("state.yaml has required governance keys")
            gate_raw = data.get("gate_status")
            stage_type = str(data.get("stage_type", ""))
            stage_status = str(data.get("stage_status", ""))
            if stage_status not in {"ACTIVE", "BLOCKED", "COMPLETE"}:
                report.error(f"invalid stage_status in state.yaml: {stage_status}")
            if stage_type not in EXPECTED_STAGE_TYPES:
                report.error(f"invalid stage_type in state.yaml: {stage_type}")
            if stage_type == "GATED":
                gate = str(gate_raw or "")
                if gate not in EXPECTED_GATE:
                    report.error(f"GATED stage has invalid gate_status: {gate_raw}")
            elif gate_raw not in (None, "", "null"):
                report.error(f"non-GATED stage must have gate_status=null, got: {gate_raw}")
            if not missing and stage_status in {"ACTIVE", "BLOCKED", "COMPLETE"} and stage_type in EXPECTED_STAGE_TYPES:
                validate_project_governance(root, data, report)
        except Exception as exc:
            report.error(f"cannot parse state.yaml: {exc}")

    if host.lower() == "codex":
        files, total, limit = codex_instruction_chain(root, cwd)
        pct = (total / limit * 100) if limit else 100.0
        if total >= limit:
            report.error(f"Codex instruction chain {total} bytes reaches/exceeds configured limit {limit}; files may be truncated")
        elif pct >= 75:
            report.warn(f"Codex instruction chain uses {pct:.1f}% of {limit} byte budget")
        else:
            report.pass_(f"Codex instruction chain uses {total}/{limit} bytes ({pct:.1f}%)")
        root_agents = root / "AGENTS.md"
        if root_agents.is_file() and root_agents.stat().st_size > 8192:
            report.warn(f"root AGENTS.md is {root_agents.stat().st_size} bytes; recommended routing target is <=8192")

        skills = scan_skills(root, cwd)
        duplicates = {n: xs for n, xs in skills.items() if len(xs) > 1}
        if not duplicates:
            report.pass_("no duplicate local Codex skill names found across scanned scopes")
        else:
            for name, refs in sorted(duplicates.items()):
                scopes = ", ".join(f"{s}:{p}" for s, p in refs)
                if any(s == "REPO" for s, _ in refs):
                    report.error(f"unresolved project skill name collision '{name}': {scopes}")
                else:
                    report.warn(f"skill name collision '{name}': {scopes}")


def main() -> int:
    configure_stdio()
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ai_root = here.parent
    ap.add_argument("--lifecycle", type=Path, default=ai_root / "standards" / "lifecycle.md")
    ap.add_argument("--artifact", type=Path, default=ai_root / "standards" / "artifact-state.md")
    ap.add_argument("--bootstrap", type=Path, default=ai_root / "bootstrap" / "bootstrap-prompt.txt")
    ap.add_argument("--project-root", type=Path)
    ap.add_argument("--cwd", type=Path)
    ap.add_argument("--host", default="codex", choices=["codex", "generic"])
    args = ap.parse_args()

    report = Report()
    validate_bundle(args.lifecycle, args.artifact, args.bootstrap, report)
    if args.project_root:
        cwd = args.cwd or args.project_root
        validate_project(args.project_root, cwd, args.host, report)
    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
