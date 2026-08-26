<!-- AI-PROJECT-STANDARD:BEGIN -->
# AI Project Standard Runtime

- Bootstrap entry: `.ai/bootstrap/bootstrap-prompt.txt`
- Lifecycle standard: `.ai/standards/lifecycle.md`
- Artifact/state standard: `.ai/standards/artifact-state.md`
- Runtime state: `.ai/state.yaml` when initialized
- Source registry: `.ai/registry.yaml` when initialized
- Decision log: `.ai/decisions.md` when initialized
- Standards lint: `python .ai/tools/standards-lint.py --project-root . --host codex`

Execution rules:
- Resolve current Stage and Source of Truth from project governance files; do not copy dynamic project state into this file.
- Use minimal context loading. Do not eagerly load complete Standards, old Cycles, or unrelated Artifacts for normal tasks.
- Do not bypass Gate / Transition, Change Control, Scope Control, Security Rules, or confirmed Decisions.
- When a `user_decision` blocker is required, ask the user in the current conversation using the full Decision Request; do not silently reduce multi-option or non-single-select decisions.
- After Market Research or Product Research, output a Research Brief in the current conversation and persist the full report in the Stage Artifact; use `aps research brief <ARTIFACT>` when available; do not finish silently after writing files.
- Global governance writes use the project Single Writer / revision / compare-before-write rules.
- For UI work, resolve the current Design System sources and project-level design Skill from the Registry. Do not assume a Skill exists or is valid until registered and verified.
<!-- AI-PROJECT-STANDARD:END -->
