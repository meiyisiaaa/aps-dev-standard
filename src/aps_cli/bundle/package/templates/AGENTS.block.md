<!-- AI-PROJECT-STANDARD:BEGIN -->
# AI Project Standard Runtime

- Bootstrap entry: `.ai/bootstrap/bootstrap-prompt.txt`
- Lifecycle standard: `.ai/standards/lifecycle.md`
- Artifact/state standard: `.ai/standards/artifact-state.md`
- Runtime state: `.ai/state.yaml` when initialized
- Source registry: `.ai/registry.yaml` when available
- Decision log: `.ai/decisions.md` when available
- Optional metadata: `.ai/project-profile.json`, `.ai/audit/transitions.jsonl`, `.ai/release-readiness.json`
- Standards lint: `python .ai/tools/standards-lint.py --project-root . --host codex`

Execution rules:
- Resolve current Stage and Source of Truth from project files; do not copy dynamic state into this file.
- Use minimal context loading. Read complete Standards, old Cycles, and unrelated Artifacts only when the task needs them.
- Treat the 23 Stage/Gate model as navigation and state recording. Ordinary flow conditions, plans, profiles, audits, release checklists, PRD Snapshots, Research Briefs, Stage User Briefs, Artifact Contracts, and Change records are used when useful; missing or stale auxiliary records produce a warning.
- Do not guess missing metadata, auto-pass a Gate, or overwrite user files. Pause only for unsafe paths, invalid runtime state, manifest/managed-file integrity failures, unconfirmed overwrite, a pending `user_decision`, explicit `HOLD` / `STOP`, or an `EXECUTION_LOOP` without an active task and without a concrete product request.
- Keep change cost proportional. Stay in the current Stage for local work; record a Change and route through Stage 22 only when the actual impact needs it. Use `.ai/templates/change-log.md` as an optional starting point.
- Product-first task routing: a concrete user request for a product bug or feature is sufficient authorization to implement directly; do not replace it with a task-list lookup or governance artifact. “继续” alone never authorizes a new task. In an `EXECUTION_LOOP`, set `active_task_ref` and `active_task_kind` only after the user explicitly names a `TASK-*`; if no active task and no concrete product request are present, ask for one instead of selecting by order, priority, dependency, or convenience.
- Only an explicitly authorized implementation task with a declared production change, or a concrete user product request that requires a production change, is product development. Verification, governance, and external tasks may run only when explicitly authorized and must not be presented as entering development.
- A pending decision blocks its affected path; do not fill the pause with unrelated audits, documents, upgrades, task lists, or another task. If no READY implementation task exists, report that fact and request a concrete product target.
- Decision Requests need the question, status, Cycle/Stage, input type, schema version, and id. Options, tradeoffs, recommendation, impact, and confirmation details are optional. A pending user decision still pauses its business path; answering it only clears that blocker.
- Research may be answered directly and persisted when needed. `aps research brief <ARTIFACT>` is a display helper; incomplete optional fields do not block ordinary work.
- A PRD Snapshot, Stage User Brief, or Artifact Contract is an auxiliary record when the task benefits from it; it does not create another Stage or automatic Gate.
- `NEXT` output is guidance, not a unique required command. Native Plan mode and risk/profile/release metadata are optional unless the user explicitly needs them.
- Global governance writes use the project Single Writer / lock / revision / compare-before-write rules. Actual state, Artifact, or verification evidence that the task relies on must be written and checked.
- For UI work, reuse registered Design System sources and project Skills when available; missing optional registry entries are warnings, not a reason to invent or block a normal implementation.
<!-- AI-PROJECT-STANDARD:END -->
