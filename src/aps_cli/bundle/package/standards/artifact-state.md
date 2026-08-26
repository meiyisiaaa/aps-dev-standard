# AI 项目 Artifact & State 标准（Project Artifact & State Standard）

**Standard Version:** `1.2.0`<br>
**Status:** `ACTIVE`  
**Companion Lifecycle Standard:** `1.2.0`

> 本标准约束 AI 在项目中创建、读取、更新、验证、同步、迁移和归档 Artifact 与项目状态。  
> `.ai/standards/lifecycle.md`定义生命周期与执行 Contract；本标准定义项目状态如何持久化以及哪个 Source of Truth 具有权威性。

---

# 0. 标准约定

## 0.1 规范语言

本标准沿用生命周期标准中的：

```text
MUST / MUST NOT
SHOULD / SHOULD NOT
MAY
```

## 0.2 Artifact 定义

Artifact 包括但不限于：

```text
Markdown 文档
JSON / YAML 状态文件
Design Token
代码中的 Component / Pattern
Agent Skill
测试 / Eval Case
截图 / Visual Baseline
配置文件
Migration / Schema
```

“文档协议”不意味着所有状态都必须写成 Markdown。机器可验证状态 SHOULD 使用结构化格式或实际代码作为 Source of Truth。

## 0.3 Artifact Metadata

关键 Artifact SHOULD 能确定：

```text
Artifact ID / Name
Status
Authoritative Source
Owner / Maintainer（需要时）
Dependencies
Last Verified
Related Decisions / Requirements
Gate / Stage
```

不要求把所有字段机械写进每个文件；可以由 Registry、目录结构或工具维护，但必须可查询。

---

# 1. 总规则

AI 在执行项目时：

```text
所有标记为“产物”的文件
必须实际创建或更新到项目中
不得只在聊天中输出
```

每次进入新阶段时：

```text
检查对应文件是否存在
↓
不存在 → 创建
↓
已存在 → 读取
↓
根据当前阶段结果更新
↓
检查相关文档是否需要同步
↓
确认写入成功
```

禁止：

```text
只在聊天中说“已更新”
只生成内容但不落盘
无理由覆盖用户已确认内容
创建重复文档
同一事实在多个文件中互相冲突
把未验证假设写成已确认结论
```

---

# 2. 项目治理工作区与初始化

项目治理数据 MUST 与产品源码分离。默认结构：

```text
project/
├── AGENTS.md
├── .ai/
│   ├── state.yaml
│   ├── decisions.md
│   ├── registry.yaml
│   ├── runtime/
│   │   └── hosts/       # 每个 Agent Host 独立 Adapter / Capability State
│   ├── cycles/
│   │   └── CYCLE-001/
│   │       ├── stages/
│   │       └── evidence/
│   └── archive/          # 仅放不再参与当前上下文的治理资产，需要时创建
├── src/
├── tests/
└── ...
```

如果 Standard 本身被复制进项目，SHOULD 放入 `.ai/standards/` 或其他明确的只读治理目录，并由 `AGENTS.md` / `registry.yaml` 引用；不得要求普通 Task 每次完整读取。

第一次接管项目时：

```text
检测 repo root
↓
检查 / 创建根 `AGENTS.md`
↓
检查 / 创建 `.ai/state.yaml`
↓
检查 / 创建 `.ai/decisions.md`
↓
检查 / 创建 `.ai/registry.yaml`
↓
初始化 active cycle
↓
验证目录和 schema
```

固定 Registry：`.ai/registry.yaml`。不得把 Registry 随意散落到 Stage 文档或 Bootstrap 文档中。

已有项目不得直接覆盖；必须读取、验证 schema / version，并按 Migration Standard 增量接管。

新 Cycle MUST 分配稳定 ID（例如 `CYCLE-002`），在 `.ai/cycles/<CYCLE-ID>/` 下创建新的 Stage 空间。旧 Cycle 中未再被 Registry 指向的历史 Artifact 默认 `archive-never-default`；仍作为当前 Active Source of Truth 的 Artifact MAY 继续被 Registry 引用，并保留其实际 load policy，直到被新 Artifact 正式 supersede。不得为了“让路径看起来属于当前 Cycle”无意义复制仍有效的 Contract。

# 3. AGENTS.md

## 作用

`AGENTS.md` 是 Agent Runtime 的项目入口与长期执行约束，不是项目事实数据库。

它的职责：

```text
告诉 Agent 去哪里读取真实状态
告诉 Agent 去哪里读取已确认决策
声明长期有效的执行规则
声明关键禁止事项
路由到项目级 Skill / Source of Truth
声明 Change / Gate / Verification 入口
```

它 MUST NOT 复制 `.ai/state.yaml`、`.ai/decisions.md` 或阶段 Artifact 中会独立变化的完整内容。

---

## 初始内容

项目早期至少包含：

```text
# Project Runtime Entry

## Project State Source
→ `.ai/state.yaml`

## Decision Source
→ `.ai/decisions.md`

## Lifecycle Standard Source
→ `.ai/registry.yaml` 中 Lifecycle Standard Source（项目内推荐 `.ai/standards/lifecycle.md`）

## Artifact / State Standard Source
→ `.ai/registry.yaml` 中 Artifact Standard Source（项目内推荐 `.ai/standards/artifact-state.md`）

## Current Stage Resolution
→ 从 `.ai/state.yaml` 读取，不在此复制

## Research Rules

## Execution Rules

## Forbidden Actions

## Change Control

## Gate / Verification Rules
```

---

## Product DNA 确认后追加

只增加入口与不可绕过的执行约束：

```text
# Product Contract

## Product DNA Source
→ `.ai/registry.yaml` 中当前有效的 Product DNA Source

## Anti-Homogeneity Source
→ `.ai/registry.yaml` 中当前有效的 Anti-Homogeneity Source

## Critical Product Invariants
→ 只记录必须在每次执行上下文中显式可见、且稳定的极少数禁令；不得复制完整 Product DNA
```

---

## Requirements 确认后追加

```text
# Requirement Contract

## Requirements Source
→ `.ai/registry.yaml` 中当前有效的 Requirements Source

## Requirement Index / Schema
→ 项目实际结构化来源（存在时）

## Critical Runtime Constraints
→ 仅保留会导致实现直接违规的少量约束；其余引用 Source
```

---

## UI / Design System 确认后追加

`AGENTS.md` 不复制完整设计规范，只写设计执行入口：

```text
# Design Execution

## Design System Source

## Visual Reference

## Token Source of Truth

## Component / Pattern Source of Truth

## Motion Source of Truth

## Design System Agent Skill

## Reuse Policy
Reuse → Compose → Extend → Create

## Critical UI Forbidden Actions
```

详细视觉规则由 `.ai/registry.yaml` 解析到当前 Cycle 的 Design System Source；实际值留在 Token / 代码；Agent 执行流程留在 Design System Skill。

---

## Architecture 确认后追加

```text
# Technical Execution

## Architecture Source
→ `.ai/registry.yaml` 中当前有效的 Architecture Source

## Database Source
→ `.ai/registry.yaml` 中当前有效的 Database Source

## API Source
→ `.ai/registry.yaml` 中当前有效的 API Source

## AI Contract Source
→ `.ai/registry.yaml` 中当前有效的 AI Contract Source（适用时）

## Critical Technical Invariants
→ 仅记录不可绕过的边界，不复制完整架构文档
```

---

## Security Review 后追加

```text
# Security Execution

## Security Review Source
→ `.ai/registry.yaml` 中当前有效的 Security Review Source

## Risk Register Source
→ `.ai/registry.yaml` 中当前有效的 Risk Register Source

## Critical Security Forbidden Actions
→ 只记录必须在执行入口显式可见的禁令
```

---

## Project Bootstrap 后追加

```text
# Engineering Runtime

## Repository / Project Structure Source
→ `.ai/registry.yaml` 中当前有效的 Bootstrap Source / 实际仓库

## Code / Naming Rules

## Test Commands

## Build Commands

## CI / Deployment Entry

## Agent Host

## Project Skill Discovery Location

## Critical Skills
```

---

## 更新规则

只有以下内容适合写入 `AGENTS.md`：

```text
长期稳定的执行入口
Source of Truth 路径
Agent Host / Skill 路由
必须在每次执行前可见的少量不变量
明确禁止事项
测试 / Build / Verification 入口
Change / Gate 规则
```

不要把以下内容塞进去：

```text
Current Stage / Current Scope 的副本
Confirmed Decisions 的副本
大段 Product DNA
完整 Requirements
完整 Architecture / Security 文档
大段调研资料
完整 Design System 内容
完整 Token / Component / Motion 规格
Design System Skill 的重复副本
临时讨论
未经确认的假设
单个任务细节
大量历史记录
完整会议记录
```

动态状态属于 `.ai/state.yaml`；决策属于 `.ai/decisions.md`；阶段知识属于对应 Stage Artifact。

---

# 4. `.ai/decisions.md`

## 作用

记录用户已经确认的重要决策。

任何重大方向确定后，AI 自动追加记录。

Stage Artifact / Task 若需要引用决策，MUST 使用 `DEC-*` 引用；不得复制一份可独立修改的“确认决策正文”作为第二真源。

---

## 记录格式

```text
## DEC-XXX

Date:
Stage:

Problem:

Options:

Decision:

Reason:

Trade-off:

Affected Areas:

Revisit Condition:
```

---

## 必须记录的决策

```text
目标市场选择
MVP 范围
Product DNA
核心交互
UI 主方向
UI / Motion 基座选择（重大时）
Reference UI 确认
关键技术栈
重大第三方依赖
核心数据模型
重大安全取舍
发布决策
重大 Scope 变化
```

---

## 不需要记录

```text
小型代码修复
普通命名
无影响的格式调整
自动测试修复
低风险实现细节
```

---

# 5. `.ai/state.yaml`

## 作用

这是当前项目运行状态的唯一机器可读 Source of Truth。它 MUST 保持小、当前、可比较；不得承载历史日志。

推荐最小 Schema：

```yaml
schema_version: 1
standard_version: "1.2.0"
revision: 1

cycle: CYCLE-001
stage: 1
stage_type: GATED
stage_status: ACTIVE
gate_status: PENDING  # 非 GATED Stage 必须为 null

current_goal: ""
scope_ref: SCOPE-001
blockers: []
pending_decision_refs: []
active_change_refs: []
major_risk_refs: []

next_action: null
updated_at: null
updated_by: coordinator
```

规则：

```text
只保存当前状态，不复制 Decision / Requirement / Research 正文
历史由 Git、Change Log、Decision Log、Cycle Artifact 保存
revision 每次治理写入必须 +1
stage_status 只允许 ACTIVE / BLOCKED / COMPLETE
GATED Stage 的 gate_status 只允许 PENDING / PASS / REVISE / HOLD / STOP
非 GATED Stage 的 gate_status MUST 为 null
需要用户决策时新增 blocker；GATED Stage 同时 gate_status=PENDING，非 GATED Stage 同时 stage_status=BLOCKED
```

## 更新时机

```text
进入新 Stage / Transition
Gate 状态变化
出现或解除 blocker
用户确认重大 Decision
Scope / Active Change 变化
Runtime 变化只在影响项目 Transition / blocker 时同步状态；Host capability 本身写入 per-host Runtime Adapter
Release / Cycle Review
```

全局状态写入遵守 Multi-Agent Single Writer 与 compare-before-write 规则。

# 6. 阶段 Artifact 布局与自动创建

阶段 Artifact MUST 隔离在当前 Cycle 下，不堆在仓库根目录。

基础路径：

```text
.ai/cycles/<ACTIVE_CYCLE>/stages/<NN-stage>/
```

默认映射：

```text
01 Idea
→ 01-idea/01_IDEA.md

02 Market Research
→ 02-market-research/02_MARKET_RESEARCH.md

03 Product Research
→ 03-product-research/03_PRODUCT_RESEARCH.md
→ 03-product-research/03_COMPETITOR_MATRIX.md

04 Reuse Base Research
→ 04-reuse-base-research/04_REUSE_BASE_RESEARCH.md

05 Opportunity
→ 05-opportunity/05_OPPORTUNITY.md

06 Product DNA
→ 06-product-dna/06_PRODUCT_DNA.md
→ 06-product-dna/06_ANTI_HOMOGENEITY_RULES.md

07 Function
→ 07-function/07_FUNCTIONS.md
→ 07-function/07_MVP.md
→ 07-function/07_CORE_LOOP.md

08 Requirements
→ 08-requirements/08_REQUIREMENTS.md

09 UX
→ 09-ux/09_USER_FLOW.md
→ 09-ux/09_IA.md
→ 09-ux/09_STATE_MODEL.md
→ 09-ux/09_WIREFRAMES/

10 UI / Design System
→ 10-design-system/10_VISUAL_DNA.md
→ 10-design-system/10_DESIGN_SYSTEM.md

11 Reference Prototype
→ 11-reference-prototype/11_PROTOTYPE.md
→ 11-reference-prototype/11_VISUAL_REFERENCE.md

12 Validation
→ 12-validation/12_VALIDATION_REPORT.md
→ 12-validation/12_ISSUES.md

13 Architecture
→ 13-architecture/13_ARCHITECTURE.md
→ 13-architecture/13_DATABASE.md
→ 13-architecture/13_API.md
→ 13-architecture/13_AI_SPEC.md

14 Security / Risk Review
→ 14-security/14_SECURITY_REVIEW.md
→ 14-security/14_RISK_REGISTER.md

15 Project Bootstrap
→ 15-bootstrap/15_BOOTSTRAP.md

16 Task Engineering
→ 16-task-engineering/16_TASKS.md
→ 16-task-engineering/16_TASKS.json

17 AI Build
→ 不强制创建 Stage 文档；Task-local execution evidence 进入 Task Source / evidence

18 Functional QA
→ 18-functional-qa/18_FUNCTIONAL_QA.md
→ 18-functional-qa/18_AI_EVAL.md

19 Visual / UX QA
→ 19-visual-ux-qa/19_VISUAL_QA.md
→ 19-visual-ux-qa/19_UX_QA.md
→ 19-visual-ux-qa/19_DIFF_REPORT.md

20 Release
→ 20-release/20_RELEASE_CHECKLIST.md
→ 20-release/20_RELEASE_NOTES.md

21 Observe
→ 21-observe/21_METRICS.md
→ 21-observe/21_FEEDBACK.md

22 Iterate
→ 22-iterate/22_ITERATION_BACKLOG.md
→ 22-iterate/22_CHANGE_LOG.md

23 Cycle Review
→ 23-cycle-review/23_CYCLE_REVIEW.md
→ 23-cycle-review/23_DEBT.md
→ 23-cycle-review/23_NEXT_CYCLE.md
```

Project Bootstrap 的运行资产（Token、UI primitives、Components、Patterns、Motion Presets、Skill）属于实际源码 / `.agents/skills`，不复制到 `.ai/cycles/`。其真实路径记录在 `.ai/registry.yaml`。

没有内容时不创建空壳文件；只有真实进入 Stage 或产生有效证据时创建。

# 7. 文档更新规则

## 7.1 不重复创建

如果文件已经存在：

```text
先读取
↓
判断已有内容是否仍有效
↓
保留用户已确认内容
↓
增量修改
```

不要创建：

```text
PRODUCT_DNA_v2.md
PRODUCT_DNA_final.md
PRODUCT_DNA_final2.md
```

除非用户明确要求版本分叉。

---

## 7.2 用户确认内容保护

用户确认后的内容视为锁定状态。

AI 不得自行改写其核心含义。

需要改变时：

```text
发现问题
↓
说明原因
↓
说明影响
↓
向用户提问
↓
用户确认
↓
更新原文档
↓
写入 `.ai/decisions.md`
```

---

## 7.3 假设与事实分离

文档中重要内容使用：

```text
Fact
Inference
Hypothesis
Decision
```

未经验证：

```text
不得从 Hypothesis 自动升级为 Fact
```

---

# 8. Dependency Graph 与跨 Artifact 同步

项目 MUST 维护可推断的 Artifact Dependency Graph。上游 Decision、Requirement、Schema、Design Source 或 Skill Contract 变化时，AI 必须先执行 Impact Analysis，再更新真正受影响的下游 Artifact。

不得使用“全文搜索然后机械替换”代替依赖分析。

当一个上游决策变化时，AI 必须检查所有下游依赖。

例如：

```text
MVP 改变
```

检查：

```text
FUNCTIONS
REQUIREMENTS
UX
UI
PROTOTYPE
ARCHITECTURE
TASKS
QA
```

---

再例如：

```text
Product DNA 改变
```

检查：

```text
UX
Visual DNA
Design System
Visual Reference
Design Tokens
Motion Presets
Design System Agent Skill
Prototype
AGENTS.md
```

---

再例如：

```text
UI 主方向 / Design System 基座改变
```

检查：

```text
Visual DNA
Design System
Visual Reference
Design Tokens
Components
Patterns
Motion Presets
Design System Agent Skill
AGENTS.md
TASKS
Visual QA
```

只有真正受影响的 Source of Truth 才更新。

---

再例如：

```text
核心 API / Schema 改变
```

检查：

```text
ARCHITECTURE
DATABASE
API
AI_SPEC
TASKS
TESTS
AGENTS.md
```

---

同步时不得机械修改。

先判断：

```text
是否真正受影响
```

只更新受影响文档。

---

# 9. Gate / Transition 持久化规则

GATED Stage 的 Gate 状态写入 `.ai/state.yaml`，Stage Artifact 只记录对应 Gate Evidence / Snapshot。

唯一 `GateStatus`：

```text
PENDING / PASS / REVISE / HOLD / STOP
```

Stage Artifact 末尾推荐：

```text
## Gate

Status: PASS / REVISE / HOLD / STOP / PENDING
State Revision:
Evidence Refs:
Blocker Refs:
Pending Decision Refs:
Failure Route:
Next Transition:
```

需要用户决策时：

```text
GateStatus: PENDING
blockers:
  - type: user_decision
    ref: <pending-decision-ref>
```

不得创造 `PENDING USER DECISION` 等第二套 GateStatus。

EXECUTION_LOOP / OBSERVATION_LOOP / ROUTER Stage 按 Lifecycle Standard 写 Transition / Exit Evidence，不伪造 Gate。

# 10. 用户提问规则

需要提问时，AI 不要丢一个宽泛问题。

应输出：

```text
问题是什么
为什么现在必须决定
有哪些选项
每个选项的主要影响
AI 推荐
需要用户确认什么
```

例如：

```text
需要决定认证方案。

A. Clerk
优点：
接入快。

代价：
长期 Vendor Lock-in 较高。

B. Auth.js
优点：
控制力高。

代价：
维护成本更高。

推荐：
当前 MVP 使用 Clerk。

请确认 A / B。
```

用户确认后：

```text
写入 `.ai/decisions.md`
同步 `.ai/state.yaml`
同步相关阶段文档
需要时同步 AGENTS.md
```

### 10.1 Decision Request

需要用户决策时，先在当前 Cycle 的当前 Stage 下创建结构化 Decision Request：

```text
.ai/cycles/<ACTIVE_CYCLE>/stages/<NN-stage>/decision-requests/DEC-XXX.json
```

请求格式由 `.ai/schemas/decision-request.schema.json` 约束。它可以表达：

```text
single_select
multi_select
free_text
number
ranking
approval
matrix
```

完整候选项、证据引用、推荐项和取舍必须保留在 Decision Request 中；`.ai/state.yaml` 只保存 `user_decision` blocker 和 `pending_decision_refs`，不复制决策正文。

Host 交互优先级：

```text
Codex Plan 原生用户输入（仅限 Plan mode）
→ Host 支持的结构化输入
→ 对话中的结构化问题
→ 手动 `aps decision answer`
```

Codex Plan 的一次提问可以只展示当前最小的一组单选项，但这只是 Host UI 限制，不是 APS 决策模型限制。选项超过 UI 能力时，必须分轮提问、改用自由输入或回退到对话，并保留完整候选集。

### 10.2 Research Brief

Market Research / Product Research 完成后，必须在当前对话输出 Research Brief，同时写入完整 Stage Artifact。Brief 至少包含：

```text
研究问题 / 范围
方法与来源（含日期）
关键发现
结论 / 建议
未确定项
待决策项
```

对话中的 Brief 用于让用户及时看见结果；CLI 可用时运行 `aps research brief <ARTIFACT>` 输出当前摘要。完整报告和证据仍以 Stage Artifact 为准。不得只落盘而静默结束，也不得为了省上下文省略关键结论、证据边界或待决策项。

---

# 11. Change Control

任何已经通过 Gate 的内容发生重大变化，创建 Change 记录。

可写入：

```text
22_CHANGE_LOG.md
```

格式：

```text
## CHANGE-XXX

Date:

Requested Change:

Reason:

Affected Stages:

Affected Files:

Impact:

Revalidation Required:

User Decision:
```

---

# 12. Scope Control

所有阶段和任务必须维护：

```text
In Scope
Out of Scope
```

AI 发现额外问题时：

```text
记录 Issue
```

不要直接修改。

如果确实需要纳入：

```text
提出 Scope Change
↓
用户确认
↓
更新 Scope
↓
更新相关文档
```

---

# 13. Atomic Task 文件规则

Task Engineering 阶段生成的每个原子任务至少包含：

```text
TASK

GOAL

CONTEXT

INPUT

OUTPUT

FILES ALLOWED

FILES READ-ONLY

CONSTRAINTS

INTERFACES

DESIGN SOURCES

VISUAL REFERENCE

DESIGN SYSTEM IMPACT

STATES

ACCEPTANCE CRITERIA

TESTS

OUT OF SCOPE

OUTPUT REQUIREMENTS
```

任务完成后记录：

```text
Status
Changed Files
Tests Run
Result
Known Issues
```

---

# 14. Definition of Done 写入规则

任务不能因为代码完成就标记 Done。

只有以下全部满足：

```text
需求实现
Acceptance Criteria 通过
测试通过
视觉验证完成
交互验证完成
响应式验证完成
UI Task 符合 Design System / Reference UI
新增可复用 UI 能力已同步系统（如适用）
安全要求未被破坏
没有超 Scope
Review 完成
必要文档更新
必要监控存在
```

才允许：

```text
Status: DONE
```

否则：

```text
Status: BLOCKED
或
Status: NEEDS FIX
```

---

# 15. 文档质量规则

所有项目文档应：

```text
短
明确
可执行
可验证
避免重复
避免营销语言
避免空泛总结
```

优先：

```text
结论
证据
约束
决策
状态
下一步
```

不要写成教程或说明书。

设计系统额外遵循：

```text
设计决策 → 文档
可枚举视觉值 → Token / 代码
组件行为与 API → 实际组件代码 / Component Workbench
AI 执行方法 → Design System Agent Skill
入口与关键禁令 → AGENTS.md
```

同一规则不在多个 Authoritative Source 中复制维护；副本只能是引用、缓存或生成物，并必须能够追溯到权威来源。

---

# 16. 项目接管规则

当 AI 第一次读取已有项目时：

```text
读取 AGENTS.md
读取 `.ai/state.yaml`
读取 `.ai/decisions.md`
读取当前阶段相关文档
检查代码仓库
检查已有任务
检查当前 Gate
前端项目检查 Design System / Visual Reference / Token / Component / Pattern / Motion Source
检查 Design System Agent Skill 是否与当前项目一致（存在时）
检测当前 Agent Host 与项目记录是否一致
验证项目级 Skill discovery / trigger 是否仍有效（使用 Skill 时）
```

然后输出：

```text
当前阶段
当前状态
已确认决策
阻塞项
文档缺口
建议下一步
```

如果发现：

```text
文档与代码冲突
多个文档互相冲突
`.ai/state.yaml` 过期
AGENTS.md 与已确认决策冲突
Design System 文档与 Token / 代码冲突
Design System Agent Skill 引用了不存在或过期的设计来源
```

先报告，不自行选择一个版本作为真相。

---

# 17. 项目结束 / 周期结束

完成 Cycle Review 后：

更新：

```text
`.ai/state.yaml`
`.ai/decisions.md`
`.ai/registry.yaml`
根 `AGENTS.md`（仅在长期入口变化时）
当前 Cycle 的 Stage 23 Artifact
```

将：

```text
当前周期临时规则
```

从 `AGENTS.md` 中清理。

保留：

```text
仍长期有效的规则
仍有效的技术约束
仍有效的 Design System 入口
仍有效的 Design Token / Component / Pattern / Motion Source
仍有效的 Design System Agent Skill
仍有效的安全规则
```

下一轮从实际需要的阶段重新进入。

不得默认直接从 Build 开始。

---

# 18. `.ai/registry.yaml` — Source / Dependency / Context Registry

## 18.1 原则

`.ai/registry.yaml` 是固定 Registry Source，不得由每个 Stage 自行选择位置。

它至少记录：

```text
Domain → Authoritative Source
Artifact → Dependencies
Artifact → Status / Version / Last Verified
Artifact → Context Load Policy
Critical Skill → Host / Discovery / Version / Last Verified
```

推荐最小领域：

| Domain | Authoritative Source | Default Load Policy |
|---|---|---|
| Lifecycle Standard | 项目配置的标准路径 | stage/on-demand |
| Artifact Standard | 项目配置的标准路径 | bootstrap/on-demand |
| Project State | `.ai/state.yaml` | always-minimal |
| Decisions | `.ai/decisions.md` | referenced-only |
| Requirements | 当前有效的 Stage 08 Requirements Artifact（可继承自前一 Cycle） | stage/task |
| Visual DNA | 当前有效的 Stage 10 Visual DNA Artifact（可继承自前一 Cycle） | ui-task |
| Design Rules | 当前有效的 Stage 10 Design System Artifact（可继承自前一 Cycle） | ui-task |
| Visual Values | Token Source | ui-task |
| Component Behavior | Component Source / Workbench | ui-task |
| Pattern Behavior | Pattern Source | ui-task |
| Motion | Motion Source | ui-task |
| Agent Procedure | Project Agent Skill | trigger-only |
| Agent Host Adapter | `.ai/runtime/hosts/<HOST-ID>.yaml` | bootstrap/runtime |
| Agent Routing | 根 `AGENTS.md` | host-managed |
| Task State | 当前 Cycle Task Source | task |

`load_policy` 推荐：

```text
always-minimal
stage
task
trigger-only
on-demand
archive-never-default
```

同一 Domain MUST 只有一个 Authoritative Source。Stage Artifact 若引用用户决策，只记录 `DEC-*` 引用；不得复制成第二份独立 Decision 真源。

## 18.2 Conflict Resolution

```text
标记 Conflict
↓
读取权威 Source / Decision Ref
↓
执行 Impact Analysis
↓
需要用户决策 → 新增 user_decision blocker；GATED 时 GateStatus=PENDING，非 GATED 时 stage_status=BLOCKED
↓
修复权威源
↓
更新真正受影响的派生项
↓
Validation / Regression
```

不得通过“最新修改时间”自动决定真相。

# 19. Artifact Lifecycle

统一状态：

```text
ABSENT
↓
DRAFT
↓
ACTIVE
↓
SUPERSEDED / DEPRECATED
↓
ARCHIVED / RETIRED
```

规则：

```text
DRAFT 不得被下游当作已确认 Contract，除非明确允许实验使用。
ACTIVE 必须满足对应 Gate / Validation。
SUPERSEDED 必须指向替代 Artifact。
ARCHIVED / RETIRED 不得继续被 AGENTS / Skill / Task 引用。
```

Agent Skill 使用：

```text
DRAFT → VALIDATED → ACTIVE → DEPRECATED → RETIRED
```

---

# 20. Identifier & Traceability Standard

关键对象使用稳定 ID：

```text
DEC-XXX
REQ-XXX
RISK-XXX
CHANGE-XXX
TASK-XXX
TEST-XXX
EVAL-XXX
SCOPE-XXX
CYCLE-XXX
```

涉及 P0 / 高风险功能时，至少应能从 QA 结果追溯到：

```text
TEST / EVAL
→ TASK
→ REQ
→ DEC / Evidence
```

ID 一旦发布 SHOULD NOT 因排序变化重新编号。

---

# 21. Agent Runtime & Skill Synchronization

## 21.1 Per-host Runtime Adapter

Agent Host 是执行环境，不是全局项目状态。项目 MUST 为需要支持的 Host 分离记录能力，推荐：

```text
.ai/runtime/hosts/<HOST-ID>.yaml
```

每个 Host Adapter 至少可确定：

```text
host_id
host_version / capability_version（可取得时）
project_instruction_entry
project_skill_discovery_locations
implicit_invocation_support
explicit_invocation_method
instruction_budget / relevant limits
tool / permission constraints
fallback
last_verified
```

多个 Host 可以同时存在，彼此不得覆盖。当前运行的 Agent 在 Bootstrap 时检测自己的 Host，然后读取 / 验证对应 Adapter。

Codex 等支持仓库级 Skill 的 Host，应优先使用仓库内项目级 Skill，使项目 clone 后能够恢复能力，而不是依赖用户机器的全局 Skill。

## 21.2 Skill Changes

以下变化必须检查相关 Host Adapter 和 Skill：

```text
Design System Source 路径变化
Token / Component / Pattern / Motion Source 变化
AGENTS 路由变化
Host Discovery 规则变化
Skill Trigger / Description 变化
Skill Procedure 变化
```

修改关键 Skill 时：

```text
先增加 / 更新失败或目标 Eval Case
↓
修改 Skill
↓
Static Validate
↓
Discovery Validate
↓
Trigger Eval
↓
Execution Eval
↓
Regression Eval
↓
更新对应 Host Adapter Last Verified / Change Log
```

Skill 不得因为 Agent 临时偏好自行修改生产规则。

# 22. Artifact Schema & Machine-readable State

当数据需要被 Agent 稳定解析、比较、验证或自动化处理时，SHOULD 使用 JSON / YAML / 代码结构而不是自由文本。

适合结构化的对象：

```text
Tasks
Requirements Index
Risk Register
Eval Cases
Design Tokens
Source Registry
Dependency Registry
Runtime Capability State
```

Markdown 主要承载：

```text
上下文
证据解释
设计 / 产品理由
Trade-off
用户决策背景
```

结构化文件必须有明确 schema 或稳定字段约定；schema 发生破坏性变化时必须执行 Migration。

`.ai/state.yaml`、`.ai/registry.yaml` MUST 保持可被普通 parser 读取，不得混入大段 Markdown 正文。

普通 Task 默认只加载 Registry 指向的最小必要 Artifact；旧 Cycle 的 `load_policy` 默认 `archive-never-default`。

---

# 23. Version / Migration Standard

以下变化 SHOULD 记录 Standard / Schema Version：

```text
Task schema 变化
Project State schema 变化
Token schema 变化
Skill Contract 结构变化
Artifact Registry 结构变化
```

破坏性变更流程：

```text
提出 Migration
↓
列出受影响 Artifact / Tool / Skill
↓
备份或确认可回滚
↓
执行迁移
↓
运行 Validation / Regression
↓
更新 Version / Last Verified
```

禁止因为模板升级而无条件覆盖已有项目的已确认内容。

---

# 24. Multi-Agent Write Governance

全局治理 Artifact 使用 Single Writer：

```text
`.ai/state.yaml`
`.ai/decisions.md`
`.ai/registry.yaml`
根 `AGENTS.md`
Global Gate / Change Control
```

只有 Coordinator / Orchestrator 可提交这些变更。执行 Agent / 子 Agent 可提出 Patch、Decision Proposal、Evidence，但不得直接覆盖。

`.ai/state.yaml` 的 `revision` 是并发控制基线。写入前必须 compare-before-write；revision 已变化则重新读取和合并。

Task-local Code、Tests、Evidence MAY 并行，但必须遵守 Task 的 Files Allowed / Ownership；两个并行 Task 触碰同一 Source of Truth 时必须序列化。

---

# 25. Evidence / Binary Retention

Visual Diff、截图、Trace、Benchmark、生成报告等 Evidence MUST 有保留策略，避免 Git 和上下文无限增长。

默认：

```text
临时 CI 截图 / Diff → CI Artifact，不提交 Git
稳定 Golden Baseline → 只有被 QA / Regression 真正消费时才提交
大二进制 → 使用项目支持的 LFS / Artifact Store，不直接堆普通 Git 历史
旧 Cycle Evidence → 默认不进入普通 Agent Context
```

每类 Evidence SHOULD 记录 retention / owner / reference，而不是把所有原始输出写入 Markdown。

---

# 26. Context Hygiene

工作区干净不等于上下文自动干净。项目 MUST 同时控制物理布局和加载策略。

```text
根目录：只保留运行入口和产品工程文件
`.ai/`：治理状态、Cycle Artifact、Registry、Evidence 索引
`.agents/skills/`：项目 Skill
旧 Cycle / Archive：默认不加载
```

`AGENTS.md` MUST 保持为精简路由；`.ai/state.yaml` MUST 保持为当前状态；`.ai/registry.yaml` MUST 负责发现，而不是让 Agent 全目录扫描后全部读取。

---

# 27. Version Control & Ephemeral State

项目可迁移性要求稳定治理资产进入版本控制，但运行噪声不得污染 Git。

默认 SHOULD 版本控制：

```text
根 `AGENTS.md`
`.ai/state.yaml`（只在治理状态真正变化时更新）
`.ai/decisions.md`
`.ai/registry.yaml`
`.ai/cycles/**` 中有效 Stage Artifact
`.ai/runtime/hosts/**` 中稳定 Host Adapter
`.agents/skills/**` 中项目级 Skill
被 Regression 实际消费的 Golden Baseline
```

默认 SHOULD NOT 版本控制：

```text
临时日志
模型原始长输出缓存
一次性截图 / Diff
下载缓存
Host 本机 Secret / Credential
临时 lock / scratch 文件
CI 可重新生成的中间产物
```

`.ai/state.yaml` 不得因每次 Session 启动、心跳或无语义变化的验证而更新；只有 Stage / Gate / Scope / blocker / Change 等项目治理状态变化时才修改，避免提交噪声。
