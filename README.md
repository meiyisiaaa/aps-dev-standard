# APS — AI Project Standard CLI

APS installs and operates the AI Project Standard inside new or existing software projects.

## Publish this repository once

After creating a GitHub repository, bind the distribution files to it:

```bash
python scripts/configure_repository.py OWNER/REPO
git status --short
# Review the changed paths, then stage only the files intended for release.
git add -- <reviewed-files>
git diff --cached --check
git commit -m "Configure APS distribution"
git push
```

Then tag a release:

```bash
git tag v1.3.6
git push origin v1.3.6
```

When changing files under `src/aps_cli/bundle/package/`, refresh their manifest checksums before committing:

```bash
python scripts/build_release.py --refresh-manifest
```

GitHub Actions builds `APS_CLI_1.3.6.zip` and its SHA-256 file and attaches them to the Release.
The online installers verify that SHA-256 file and fail closed when no verified Release asset is available.

## One-line install

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/meiyisiaaa/aps-dev-standard/main/install.sh | sh
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/meiyisiaaa/aps-dev-standard/main/install.ps1 | iex
```

After installation:

```bash
cd your-project
aps
```

## First use and recovery

新项目：

```bash
aps init
```

默认由 APS 恢复或启动 Host；只想复制 `APS Agent Handoff` 时加 `--no-launch`。Bootstrap 完成后运行：

```bash
aps doctor
aps status
```

Bootstrap 时必须让用户确认项目风险级别并写入 `.ai/project-profile.json`：`NORMAL`（普通）、`LARGE`（大型）或 `REGULATED`（强合规）。所有项目维护 `.ai/audit/transitions.jsonl`；大型项目按模块 / 工作流填写 `workstreams`，不增加新的 Stage。到 Stage 20 Release 边界时，按级别补齐 `.ai/release-readiness.json`。普通 Stage 满足 Artifact、验收、Verification 和 blocker 条件后，可直接记录 `COMPLETE + PASS` 并进入 Transition Contract 指定的下一 Stage，不要求用户额外确认“Stage PASS”；用户决策、重大范围 / 方向变化、HOLD / STOP 和 Release approval 仍需确认。

已有项目：

```bash
aps resume
```

`resume` 会按实际项目状态恢复或启动 Host；需要只输出可复制 handoff 时加 `--no-launch`。在有效 manifest 存在后，重复 `resume` 只恢复状态，不升级或修改项目。普通已有项目不要用 `upgrade` 越权接管；半安装或损坏的 APS 残留才使用 `upgrade` 修复；空目录使用 `init`。

首次接管已有项目时，以真实当前状态初始化 `CYCLE-001`：首条 Transition 可使用 `from_state: null`、`adoption: true` 和实际 Evidence refs 直接落在当前 Stage。不要补写虚假的 Stage 01–14 PASS，也不要仅为此创建 Rebaseline Cycle；后续 Transition 仍必须满足正常的 `COMPLETE` / Gate `PASS` 约束。

遇到阻塞时先运行 `aps status`，只执行输出的唯一 `NEXT`。运行状态缺失或损坏时，先运行 `aps doctor --standard-only` 获取第一项问题；`doctor` 不会替你猜测或改写坏状态，需人工修复 `.ai/state.yaml` 后再运行 `aps resume --no-launch`。Standard 版本不匹配或出现托管文件冲突时，先审查 `.ai/incoming/<version>/`，人工合并后再运行 `aps upgrade`；APS 不会自动合并本地修改。除非明确接受“备份后覆盖”，不要使用 `--force-managed`。

如果 `.ai/project-profile.json`、Transition 审计或 Release readiness 损坏，APS 会 fail-closed；按 `status` / `doctor` 输出的唯一 `NEXT` 修复，不要把风险级别猜成 `NORMAL`，也不要手动把 Gate 改成 PASS。

Or directly:

```bash
aps init
aps resume
aps rebaseline --confirm
aps doctor
aps status
aps upgrade
aps research brief .ai/cycles/CYCLE-001/stages/02-market-research/02_MARKET_RESEARCH.md
```

Command boundaries are deliberate: `init` is for a new project, `resume` adopts an existing project once and is read-only after a valid Standard manifest exists, and `upgrade` is the only normal command that updates installed Standard files. `rebaseline` requires initialized runtime state and explicit confirmation; an incomplete non-initial Cycle must be resumed before another one is created:

```bash
aps rebaseline --confirm
```

Repeating `resume` or a same-version `upgrade` is a no-op and should not dirty the project workspace. Do not use `init --force-mode` to bypass an existing project; use `resume` to adopt it.

When a major product, technical, UX, or scope choice is required, create a structured Decision Request under the active Cycle and register it:

```bash
aps decision request .ai/cycles/CYCLE-001/stages/01-idea/decision-requests/DEC-001.json
```

Ask the user in the current conversation with a structured question. Before asking for the answer, explain every option's advantages, disadvantages, fit, and main risks; distinguish evidence from inference when relevant. If you recommend one, explain why and what evidence would change the recommendation. Keep the full candidate set in the Decision Request; multi-select, ranking, free-text, numeric, and larger decisions may use staged prompts or free-form conversation. Record the answer with:

Each new Decision Request is a Decision Card: it records why the decision is needed, the recommendation and per-option tradeoffs, the code/documentation/time impact, and the exact confirmation method. Existing legacy requests remain answerable and should be enriched before they are presented again.

```bash
aps decision answer DEC-001 A
```

Use `aps decision list` and `aps decision show DEC-001` to inspect pending requests. A selected option does not pass a Gate automatically; complete the required Artifact and Validation first.

决策路径：登记后先在当前对话展示完整 Decision Card，再回答或取消；`aps decision answer` 和 `aps decision cancel` 都会打印下一步。用户选择只解除对应 blocker，不代表 Gate PASS。

If the request is no longer needed, close it explicitly:

```bash
aps decision cancel DEC-001 --reason "scope changed"
```

After switching conversations, run `aps status` or `aps resume --no-launch` to print the current Cycle, blockers, pending decisions, and next action. For Market / Product Research, answer the original question directly in the current conversation, analyze the evidence, then keep the full report in the Stage Artifact and expose the user-facing summary with `aps research brief <ARTIFACT>`.

Before ending, pausing, blocking, or handing off any Stage, output a one-page Stage User Brief in the current conversation with: goal, inputs, completed work, incomplete work, user decisions, confirmation impact, next-stage entry reminder, and verification results. Once an ordinary Stage satisfies its Artifact, acceptance, Verification, and blocker conditions, it may record `COMPLETE + PASS` and follow the Transition Contract without asking the user to confirm "Stage PASS" again. The Stage Artifact must also contain or reference an Artifact Contract with its purpose, inputs, outputs, acceptance criteria, current status, blocking decisions, and next stage. A written document alone does not mean the Stage is complete.

交接优化：Stage User Brief 只在阶段完成、阻塞、暂停或切换对话时输出，不要求每轮重复；完成结果必须提醒 Transition Contract 指定的下一 Stage，以及高影响入口是否应复用已接受计划或先写简短计划；handoff 只携带当前 Stage / Task 和直接引用，旧 Cycle 与完整 Standard 按需读取。大型项目的并行 Task 只交接变更文件、接口影响、依赖状态和 Evidence refs，由 Coordinator 统一更新全局治理状态。

增量变更：仍在已确认 Scope / Requirements 内、且不改变已确认契约的局部 Task 留在当前 Stage，只做差异更新和定向验证；新增行为、修改已通过 Gate 的内容或改变技术 / 安全 / Release 约束时，进入 Stage 22，使用 `.ai/templates/change-log.md` 做 Impact Analysis，路由到最早受影响 Stage。保留未受影响的有效 Artifact；依赖不清楚时扩大验证范围，不能用“只改一个文件”跳过必需 Gate 或 Release 检查。

研究路径：先在当前对话直接回答原始问题并分析关键证据，再把完整报告写入 Stage Artifact；使用 `aps research brief <ARTIFACT>` 展示摘要。Artifact 必须包含稳定的 `## Research Brief` 标识和六类必需字段，缺失时按 CLI 提示补齐。

PRD 路径：APS 不增加独立 PRD Stage。Stage 08 `08_REQUIREMENTS.md` 仍是需求核心来源；需要单页产品视图时，可将 `.ai/templates/prd-snapshot.md` 复制到当前 Cycle 的 `08-requirements/08_PRD_SNAPSHOT.md`，并只引用 Stage 05–09 的有效 Artifact 与 `DEC-*`。它是可选派生汇总，不是第二个 Source of Truth，也不新增 Gate。

High-impact Stage entry needs a concise accepted plan before material workspace changes: Stage 01, 05, 06, 07, 08, 09, 10, 13, 14, 15, 16, and 20; Stage 22 needs the same when an Active Change exists. An explicit plan accepted in the current conversation is sufficient. Native Codex Plan mode is optional, not a Gate: if unavailable, record or reference the accepted plan and continue; `aps` may launch a normal Codex session.

## Temporary use before repository configuration

The installers also accept a repository override.

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/install.sh | APS_REPO=OWNER/REPO sh
```

PowerShell:

```powershell
$env:APS_REPO='OWNER/REPO'; irm https://raw.githubusercontent.com/OWNER/REPO/main/install.ps1 | iex
```

For temporary source-archive use when no Release exists, explicitly opt in:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/install.sh | APS_REPO=OWNER/REPO APS_ALLOW_MAIN_FALLBACK=1 sh
```

PowerShell:

```powershell
$env:APS_REPO='OWNER/REPO'; $env:APS_ALLOW_MAIN_FALLBACK='1'; irm https://raw.githubusercontent.com/OWNER/REPO/main/install.ps1 | iex
```

## Project footprint

APS keeps project governance isolated:

```text
project/
├── AGENTS.md
├── .agents/
│   └── skills/
└── .ai/
    ├── standards/
    ├── bootstrap/
    ├── tools/
    ├── schemas/
    ├── project-profile.json
    ├── audit/transitions.jsonl  # 所有项目
    ├── release-readiness.json   # Stage 20 边界
    ├── runtime/
    ├── cycles/
    └── archive/
```

The product source tree stays separate from AI governance assets.
