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
- When a `user_decision` blocker is required, present a decision card in the current conversation: why the decision is needed, every option's pros, cons, fit, and main risks, the recommendation, code/documentation/time impact, and the exact confirmation method. Use the full Decision Request and do not silently reduce multi-option or non-single-select decisions.
- After Market Research or Product Research, answer the original research question directly in the current conversation, analyze the key evidence, then output a Research Brief and persist the full report in the Stage Artifact; use `aps research brief <ARTIFACT>` when available as supporting output, not as a substitute for the answer; do not finish silently after writing files.
- Before a Stage is completed, blocked, paused, or handed to another conversation, output a one-page Stage User Brief in the current conversation with the goal, inputs, completed work, incomplete work, user decisions, confirmation impact, and verification results. The brief does not replace the Artifact Contract or its acceptance criteria.
- Global governance writes use the project Single Writer / revision / compare-before-write rules.
- For UI work, resolve the current Design System sources and project-level design Skill from the Registry. Do not assume a Skill exists or is valid until registered and verified.
<!-- AI-PROJECT-STANDARD:END -->
