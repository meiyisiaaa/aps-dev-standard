<!-- AI-PROJECT-STANDARD:BEGIN -->
# AI Project Standard Runtime

- Bootstrap entry: `.ai/bootstrap/bootstrap-prompt.txt`
- Lifecycle standard: `.ai/standards/lifecycle.md`
- Artifact/state standard: `.ai/standards/artifact-state.md`
- Runtime state: `.ai/state.yaml` when initialized
- Source registry: `.ai/registry.yaml` when initialized
- Decision log: `.ai/decisions.md` when initialized
- Risk baseline: `.ai/project-profile.json` when initialized
- Transition audit: all projects maintain `.ai/audit/transitions.jsonl`; deeper evidence for LARGE / REGULATED projects
- Release readiness: `.ai/release-readiness.json` at the Release boundary
- Standards lint: `python .ai/tools/standards-lint.py --project-root . --host codex`

Execution rules:
- Resolve current Stage and Source of Truth from project governance files; do not copy dynamic project state into this file.
- Use minimal context loading. Do not eagerly load complete Standards, old Cycles, or unrelated Artifacts for normal tasks.
- Do not bypass Gate / Transition, Change Control, Scope Control, Security Rules, or confirmed Decisions.
- Keep change cost proportional: an in-scope Task that does not change a confirmed contract may use a delta update and targeted verification; a new behavior or changed gated source must use Stage 22 Impact Analysis and route to the earliest affected Stage. Reuse valid Artifacts, revalidate the dependency closure, and never omit mandatory Stage / Gate / Release checks. Use `.ai/templates/change-log.md` when a Change record is required.
- On first entry, upstream rework, or scope/direction change for Stage 01, 05, 06, 07, 08, 09, 10, 13, 14, 15, 16, or 20, switch to the Host's native Plan mode (Codex Host: Codex Plan mode) before changing files; after the plan is accepted, normal execution is allowed. Stage 22 requires the same when an Active Change exists. If the Host cannot open or verify Plan mode, stop and report a Host capability blocker instead of mutating the workspace.
- When a `user_decision` blocker is required, present a decision card in the current conversation: why the decision is needed, every option's pros, cons, fit, and main risks, the recommendation, code/documentation/time impact, and the exact confirmation method. Use the full Decision Request and do not silently reduce multi-option or non-single-select decisions.
- After Market Research or Product Research, answer the original research question directly in the current conversation, analyze the key evidence, then output a Research Brief and persist the full report in the Stage Artifact; use `aps research brief <ARTIFACT>` when available as supporting output, not as a substitute for the answer; do not finish silently after writing files.
- Do not create a new PRD Stage. When a one-page product view is needed, use Stage 08 Requirements as the core and derive a PRD Snapshot from current Stage 05–09 Artifacts and `DEC-*` references; the Snapshot is not a second Source of Truth or Gate.
- Once an ordinary Stage's Artifact, acceptance, Verification, and blocker conditions are satisfied, record `COMPLETE + PASS` and follow the Transition Contract without asking the user to confirm "Stage PASS" again. Stop for required user decisions, major scope/direction changes, HOLD / STOP, or Release approval.
- Before a Stage is completed, blocked, paused, or handed to another conversation, output a one-page Stage User Brief in the current conversation with the goal, inputs, completed work, incomplete work, user decisions, confirmation impact, next-stage entry reminder, and verification results. The brief does not replace the Artifact Contract or its acceptance criteria.
- Global governance writes use the project Single Writer / revision / compare-before-write rules.
- For UI work, resolve the current Design System sources and project-level design Skill from the Registry. Do not assume a Skill exists or is valid until registered and verified.
<!-- AI-PROJECT-STANDARD:END -->
