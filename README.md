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
git tag v1.3.8
git push origin v1.3.8
```

When changing files under `src/aps_cli/bundle/package/`, refresh their manifest checksums before committing:

```bash
python scripts/build_release.py --refresh-manifest
```

GitHub Actions builds `APS_CLI_1.3.8.zip` and its SHA-256 file and attaches them to the Release.
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

项目风险级别、Transition audit 和 Release readiness 都是可选元数据；存在时 APS 会检查，缺失或过期只给出 WARN，不猜测为 `NORMAL`。普通 Stage 可在完成实际任务和相关验证后记录 `COMPLETE + PASS` 并按需进入 Transition Contract；用户决策、明确的 `HOLD` / `STOP`、安全边界、Release approval，以及 Stage 17 没有 active task 且没有具体产品请求仍保留为暂停条件。

任务执行硬规则：用户明确提出产品 bug、功能或可验收行为时，应直接进入实现，不先写审计或任务清单。`继续` 不会授权新任务，也不会按列表自动选择下一个任务；没有明确产品目标时才请求具体产品目标或 TASK-ID。只有 `implementation` 且预计修改生产代码或测试的任务，或明确要求生产代码变更的具体产品请求，才算进入开发；不得用审计、文档、升级或无关验证制造进度。

已有项目：

```bash
aps resume
```

`resume` 会按实际项目状态恢复或启动 Host；需要只输出可复制 handoff 时加 `--no-launch`。在有效 manifest 存在后，重复 `resume` 只恢复状态，不升级或修改项目。普通已有项目不要用 `upgrade` 越权接管；半安装或损坏的 APS 残留才使用 `upgrade` 修复；空目录使用 `init`。

遇到问题时先运行 `aps status` 查看提示。运行状态缺失或损坏时，先运行 `aps doctor --standard-only`；`doctor` 不会猜测或改写坏状态，需人工修复 `.ai/state.yaml` 后再运行 `aps resume --no-launch`。Standard 版本不匹配或出现托管文件冲突时，先审查 `.ai/incoming/<version>/`，人工合并后再运行 `aps upgrade`；APS 不会自动合并本地修改。除非明确接受“备份后覆盖”，不要使用 `--force-managed`。

如果 `.ai/project-profile.json`、Transition 审计、Release readiness、PRD Snapshot 或 Registry 缺失/过期/普通内容不完整，APS 会给出 WARN 并继续；路径、链接、不可安全读取、运行状态、manifest 和托管文件完整性问题仍会 fail-closed。不要把风险级别猜成 `NORMAL`，也不要手动把 Gate 改成 PASS。

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

Command boundaries are deliberate: `init` is for a new project, `resume` adopts an existing project once and is read-only after a valid Standard manifest exists, and `upgrade` is the only normal command that updates installed Standard files. `rebaseline` requires a valid runtime state and explicit confirmation; it does not require the current Cycle to have completed Stage 23:

```bash
aps rebaseline --confirm
```

Repeating `resume` or a same-version `upgrade` is a no-op and should not dirty the project workspace. Do not use `init --force-mode` to bypass an existing project; use `resume` to adopt it.

When a major product, technical, UX, or scope choice is required, create a structured Decision Request under the active Cycle and register it:

```bash
aps decision request .ai/cycles/CYCLE-001/stages/01-idea/decision-requests/DEC-001.json
```

Ask the user in the current conversation with a clear question. For complex choices, explain relevant evidence, tradeoffs and confirmation details; simple choices may use free text. The minimum Decision Request keeps the question, status, Cycle/Stage, input type, schema version and id. Options, tradeoffs, recommendation, impact and confirmation method are optional. Existing legacy requests remain answerable.

```bash
aps decision answer DEC-001 A
```

Use `aps decision list` and `aps decision show DEC-001` to inspect pending requests. A selected option does not pass a Gate automatically; complete the required Artifact and Validation first.

决策路径：登记后在当前对话确认问题；`aps decision answer` 和 `aps decision cancel` 都会打印下一步。用户回答只解除对应 blocker，不代表 Gate PASS。

If the request is no longer needed, close it explicitly:

```bash
aps decision cancel DEC-001 --reason "scope changed"
```

After switching conversations, run `aps status` or `aps resume --no-launch` to print the current Cycle, blockers, pending decisions, and next action. For Market / Product Research, answer the original question directly in the current conversation, analyze the evidence, then keep the full report in the Stage Artifact and expose the user-facing summary with `aps research brief <ARTIFACT>`.

Before a useful handoff, you may output a short Stage User Brief with goal, inputs, completed/incomplete work, decisions and verification. An ordinary Stage may record `COMPLETE + PASS` after its actual work and relevant validation; no extra "Stage PASS" confirmation is required. A Stage Artifact or Artifact Contract is an optional aid and does not by itself make work complete.

交接优化：Stage User Brief 只在有帮助时输出，不要求每轮重复；handoff 携带当前 Stage / Task 和直接引用即可，旧 Cycle 与完整 Standard 按需读取。大型项目的并行 Task 仍由 Coordinator 统一更新共享状态。

增量变更：仍在已确认 Scope / Requirements 内、且不改变已确认契约的局部 Task 留在当前 Stage，只做差异更新和定向验证；只有实际改变契约、Scope 或下游影响时，才使用 Stage 22 和 `.ai/templates/change-log.md` 记录并路由。保留未受影响的有效 Artifact；依赖不清楚时扩大验证范围。

研究路径：可在当前对话回答原始问题并按需把报告写入 Stage Artifact；使用 `aps research brief <ARTIFACT>` 展示摘要。`## Research Brief` 和字段是推荐结构，缺失或过期时提示补充，不阻塞普通工作。

PRD 路径：APS 不增加独立 PRD Stage。Stage 08 `08_REQUIREMENTS.md` 仍是需求核心来源；需要单页产品视图时，可将 `.ai/templates/prd-snapshot.md` 复制到当前 Cycle 的 `08-requirements/08_PRD_SNAPSHOT.md`，并只引用 Stage 05–09 的有效 Artifact 与 `DEC-*`。它是可选派生汇总，不是第二个 Source of Truth，也不新增 Gate。

复杂任务可以先写简短计划；没有计划或 Native Codex Plan mode 不会阻塞普通会话。Stage 22 是按实际影响使用的记录/路由位置，不是固定入口门禁。

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
    ├── audit/transitions.jsonl  # 按需使用
    ├── release-readiness.json   # 发布需要时
    ├── runtime/
    ├── cycles/
    └── archive/
```

The product source tree stays separate from AI governance assets.
