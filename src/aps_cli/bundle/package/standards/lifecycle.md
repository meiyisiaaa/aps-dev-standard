# AI 产品开发生命周期标准（Full-Cycle Engineering Standard）

**Standard Version:** `1.3.7`<br>
**Status:** `ACTIVE`  
**Companion Artifact Standard:** `1.3.7`

> 本标准定义 AI 参与产品开发时的统一生命周期、Stage Contract、Gate、Agent Runtime、Skill、验证、追踪和变更参考。
> 23 个 Stage/Gate 用于导航和状态记录；普通流程条件不自动成为 CLI 阻塞。不得用未确认假设替代重大决策，不得把聊天内容视为已经落盘的项目状态。
> 项目产物的创建、状态、Source of Truth、同步和生命周期由`.ai/standards/artifact-state.md`约束。

---

# 0. 标准总则

## 0.1 规范语言

本文档使用以下规范强度：

```text
MUST / 必须
违反即不符合本标准，相关 Gate 不得 PASS。

MUST NOT / 禁止
任何情况下不得执行，除非经过明确 Change Control 并由用户确认。

SHOULD / 应
默认遵守；偏离时必须记录原因、影响和替代验证。

SHOULD NOT / 不应
默认避免；若采用必须说明理由。

MAY / 可
根据项目实际情况选择。
```

本标准只定义项目可控层的执行优先级，绝不高于 Agent Host、系统安全策略、平台权限或更高优先级运行时指令。

项目可控层冲突时，优先级：

```text
当前用户明确指令 / 明确批准的 Change
↓
已确认且仍有效的 Decision
↓
本标准中的 MUST / MUST NOT
↓
项目 AGENTS.md 中长期有效规则
↓
当前 Stage / Task Contract
↓
SHOULD / MAY
```

当前用户指令若改变已锁定 Decision，MUST 先进入 Change Control；不得把一次临时指令静默覆盖为长期规则。

## 0.2 标准对象

本标准约束以下对象：

```text
Stage
Gate
Artifact
Decision
Requirement
Risk
Change
Task
Test / Eval
Agent Host
Agent Skill
Source of Truth
```

关键对象 SHOULD 使用稳定 ID，以支持跨文档追踪：

```text
DEC-XXX      决策
REQ-XXX      需求
RISK-XXX     风险
CHANGE-XXX   变更
TASK-XXX     任务
TEST-XXX     测试
EVAL-XXX     Agent / AI Eval
DS-XXX       Design System 规则或资产（需要时）
SCOPE-XXX    Scope 版本 / 边界
CYCLE-XXX    开发周期
```

## 0.3 Stage Contract

所有 Stage SHOULD 具有明确的 Transition Contract，但不同 Stage 类型不强制伪造相同的 Gate；缺少普通流程记录时可继续工作并在 status/doctor 中提示。

Stage Type：

```text
GATED
以 GateStatus 决定是否进入下一阶段。默认类型。

EXECUTION_LOOP
以 Task / Work Item 的完成条件循环执行。Stage 17 使用。

OBSERVATION_LOOP
持续采集证据，按退出条件转入 Iterate 或 Cycle Review。Stage 21 使用。

ROUTER
不直接产出产品功能，而把 Change 路由回真正受影响的 Stage。Stage 22 使用。
```

需要推进或交接时，每个 Stage 通常可确定：

```text
Stage ID / Name
Stage Type
Purpose
Preconditions
Inputs
Required Actions
Outputs
Verification
Transition Contract
Failure Route
Downstream Dependencies
```

### 0.3.1 Stage Entry / Planning

计划是复杂任务的辅助工具，不是固定 Stage 清单、Gate 或 CLI 执行前提。任务需要时可以在当前对话或工作区写一份简短计划；简单任务直接执行并做相关验证。原生 Codex Plan 模式可选，Host 不支持时继续使用普通会话。

Stage 22 是可用的变更记录和路由位置。只有实际改变已确认契约、Scope 或下游影响时才需要记录 Change 并路由；普通局部改动不因 Stage 编号自动暂停。

### 0.3.2 Project Risk Profile / Workstream

项目可以按需要记录风险级别，存在 `.ai/project-profile.json` 时 APS 会检查；缺失时不猜测为 `NORMAL`，也不阻塞普通流程：

| Machine ID | 中文含义 | 额外要求 |
|---|---|---|
| `NORMAL` | 普通 | 保留基础验证和回滚；需要历史追踪时再记录 Transition 审计 |
| `LARGE` | 大型 | 按模块 / 工作流拆分 `workstreams`，按实际影响增加集成、性能、迁移、监控、灾备、值班和外部验收；审计深度按需增加 |
| `REGULATED` | 强合规 | 在大型项目要求上增加隐私 / 合规、可追溯性、审批和审计留存证据 |

风险级别不是新的 Stage，也不能替代实际安全、质量和发布判断。需要更深 Evidence、Release readiness 或审计时再补齐；大型项目可以并行执行不同 workstream 的 Task / Artifact，但全局 Cycle、Gate 和状态仍由 Coordinator 单写。

`.ai/audit/transitions.jsonl` 是可选的历史记录。存在时应包含 from/to state、原因、Actor 和 Evidence refs；格式或链路问题只产生提示，不能替代 Git、Decision Log 或 Stage Artifact。

Transition 审计只能证明当前文件中的格式、顺序和状态链路可校验，不能单独证明历史行未被人为修改或 Evidence 真实有效；需要完整可信度时，仍须结合 Git 历史、仓库权限和人工审查。

阶段完成、阻塞、暂停或交接时，可以在当前对话输出一页 Stage User Brief。普通 Stage 完成后可记录 `COMPLETE + PASS` 并按 Transition Contract 继续，不要求额外的“Stage PASS”确认。以下字段是推荐内容，不是普通流程门禁：

```text
目标：这一阶段解决什么问题
输入：依赖哪些前置结果
已完成：实际产出了什么
未完成：还缺什么
用户决策：需要确认什么
确认影响：确认后进入哪一步
下一阶段入口提醒：Transition Contract 指定的下一 Stage；复杂任务可复用已接受计划或先写简短计划，原生 Plan 模式可选
验证结果：哪些检查已经通过
```

Stage User Brief 是用户交接摘要，不是完成证明；实际需要的 Artifact、验收条件和 Gate / Transition 仍按任务风险与用户目标执行。

### 0.3.3 Proportional Change / Incremental Validation

23 个 Stage 是统一的导航契约，不代表每个小改动都要从头重跑。变更按实际影响范围处理：

```text
仍在已确认 Scope / Requirements 内，且不改变已确认 UX、UI、Architecture、Security 或 Release 条件
→ 留在当前 Stage / Task
→ 只更新真正受影响的 Artifact
→ 执行该 Task 和受影响链路的最小必要验证

改变已通过 Gate 的内容、用户行为 / 流程、设计基座、技术 / 安全约束，或由真实反馈触发
→ 需要时记录 Change 并使用 Stage 22 Iterate 路由
→ 重新验证实际受影响的 Stage 及其下游依赖

改变产品目标、重大 Scope、风险级别或 Release 条件
→ 进入 Change Control 和用户决策
→ 必要时在当前 Cycle 关闭后创建新的 Rebaseline Cycle
```

需要记录 Change 时，建议说明 Change ID、Scope Delta、受影响 Stage/Artifact、复用范围、验证集合和 Release 影响；可使用 `.ai/templates/change-log.md` 作为起点。

增量验证可以减少无关重复检查。依赖图缺失、引用无法解析或影响范围不确定时，再扩大验证范围；不把普通记录缺失伪装成安全阻塞。

规则：

```text
明确的安全前置条件未满足 → 不得开始主执行
Input 缺失但可通过代码 / 调研 / 已有 Artifact 确定 → AI 自行补齐
Input 缺失且属于关键决策 → 标记 user_decision blocker；GATED Stage 使用 GateStatus=PENDING，其他 Stage 使用 stage_status=BLOCKED
用户或发布目标明确要求的 Output / Verification 未完成 → 不记录对应的完成状态
GateStatus=REVISE → 路由回真正产生问题的上游 Stage
GateStatus=STOP → 停止当前开发周期
EXECUTION_LOOP / OBSERVATION_LOOP / ROUTER → 按需要定义 Exit / Route 条件，不默认等同 PASS
```

本标准各阶段中的：

```text
目标   = Purpose
执行   = Required Actions
检查   = Verification
产物   = Outputs
Gate / Transition = Transition Contract
```

阶段默认 Preconditions：上游关键 Gate 已 PASS，且所有被引用的已确认 Decision 仍有效。
阶段默认 Inputs：当前 `.ai/state.yaml`、`.ai/decisions.md`、`.ai/registry.yaml`、上游有效 Artifact，以及该阶段明确引用的代码 / Source of Truth。

本标准各 Stage 的“产物”文件名是逻辑 Artifact 名称；实际物理路径 MUST 由 Artifact Standard 按当前 Cycle 布局解析，不得据此把所有文件写入仓库根目录。

## 0.4 Source of Truth 原则

同一事实或规则 MUST 只有一个 Authoritative Source。其他位置只允许引用，不允许维护第二份可独立变化的副本。

默认职责：

```text
当前项目状态              → `.ai/state.yaml`
用户已确认重大决策        → `.ai/decisions.md`
阶段结论                  → 对应阶段 Artifact
机器可枚举设计值          → Token / Code
组件行为与 API            → Component Source / Workbench
Pattern 实现               → Pattern Source
Agent 执行方法             → Agent Skill
Agent 路由与关键禁令       → 根目录 `AGENTS.md`
任务结构化状态             → Task Source / 16_TASKS.json
```

若发现两个 Authoritative Source 冲突，MUST 报告冲突，不得自行挑选一个作为真相。

## 0.5 Traceability

对影响实现和验收的关键需求，SHOULD 建立最短追踪链：

```text
Decision / Evidence
↓
REQ
↓
UX / Design / Architecture Contract
↓
TASK
↓
TEST / EVAL
↓
QA / Release Evidence
```

任何 P0 缺陷应能反向定位到对应 Requirement / Task / Test。

## 0.6 Agent Runtime 原则

Agent Skill 不假定固定宿主。Project Bootstrap MUST：

```text
检测 Agent Host
↓
检测 Host 能力
↓
解析项目级 Skill Discovery Location
↓
安装 / 生成 Skill
↓
验证 Skill 可发现
↓
验证正确触发
↓
执行最小 Smoke Eval
```

Host-specific 路径属于 Adapter，不属于核心标准。

示例：Codex 项目级 Skill 使用仓库内的 `.agents/skills/`；其他 Agent Host 按其项目级 discovery 规则适配。若 Host 不支持项目级 Skill，MUST 通过 `AGENTS.md` 或等效机制提供可执行 fallback，并记录能力差异。

## 0.7 Context Loading & Budget

标准文档是可检索的权威参考，不是每个任务都必须完整注入的 Prompt。Agent MUST 采用分层加载：

```text
L0 — Runtime Minimum
Host 自动加载的项目指令 + `.ai/state.yaml` + 当前 Task / Skill metadata

L1 — Current Stage
只读取当前 Stage Contract、当前 Stage Artifact、直接上游有效 Contract

L2 — Task Contract
只读取 Task 显式引用的 REQ / DEC / Design / Architecture / Security Source

L3 — On-demand Evidence
历史调研、旧 Cycle、详细 Reference、完整报告，仅在实际需要时读取
```

规则：

```text
MUST NOT 在普通 Task 启动时默认完整加载两份 Standard
MUST NOT 默认加载全部历史 Cycle / Decision / Research
MUST 通过 `.ai/registry.yaml` 和当前 Task 的引用定位最小必要上下文
SHOULD 在上下文增长时优先释放已完成阶段的详细材料，只保留结论引用
```

Host Adapter MUST 记录当前 Host 的 instruction / context 约束，并为项目设置安全余量。

Codex 当前行为示例（Bootstrap 时仍需实时验证）：项目指令从根目录向当前工作目录合并，`project_doc_max_bytes` 默认 32 KiB。项目 SHOULD 将实际 AGENTS 指令链控制在该 Host 上限的约 75% 以内，并让根 `AGENTS.md` 保持为精简路由文件，而不是知识库。

## 0.8 Verification 层级

项目验证分为：

```text
Static Validation
Runtime / Build Validation
Functional Test
Integration / E2E
Visual / UX QA
Security Validation
Agent Skill Discovery / Trigger / Execution Eval
Regression
```

“文件存在”不等于“能力可用”；“Skill 存在”不等于“Skill 可发现或会正确执行”。

## 0.9 完整开发周期

```text
01 Idea
↓
02 Market Research
↓
03 Product Research
↓
04 Reuse Base Research
↓
05 Opportunity
↓
06 Product DNA
↓
07 Function
↓
08 Requirements
↓
09 UX
↓
10 UI / Design System
↓
11 Reference Prototype
↓
12 Validation
↓
13 Architecture
↓
14 Security / Risk Review
↓
15 Project Bootstrap
↓
16 Task Engineering
↓
17 AI Build
↓
18 Functional QA
↓
19 Visual / UX QA
↓
20 Release
↓
21 Observe
↓
22 Iterate
↓
23 Cycle Review
```

## 0.10 每阶段执行顺序

```text
读取已有信息
↓
检查缺失与冲突
↓
必要时向用户提问
↓
执行调研 / 设计 / 分析 / 开发
↓
整理阶段产物
↓
自检
↓
提交 Gate
```

## 0.10.1 研究结果交付

Market Research、Product Research，以及其他产生外部证据的 Research 可以在当前对话直接回答，也可以按需要把完整报告落盘到 Stage Artifact。`aps research brief <ARTIFACT>` 只是摘要展示工具；缺少某些 Brief 字段时给出 WARN，不阻塞普通工作。若研究结论确实需要用户选择，再登记 `user_decision` blocker。

## 0.11 必须向用户提问的情况

```text
目标不明确
关键需求存在多种解释
两个方案会导致不同产品方向
需要改变已确认的 Product DNA
需要改变 MVP 范围
需要改变核心 UX
需要改变 UI 主方向
需要新增重大依赖
需要改变核心数据模型
需要接受明显技术锁定
需要牺牲核心体验换技术便利
发现原假设与证据冲突
发现重大安全 / 合规风险
需要扩大 Scope
需要跳过既定 Gate
```

可以通过调研、代码、文档或现有上下文确定的问题，不向用户提问。

决策交互应在当前对话完成，不依赖 Host UI。Decision Request 的最小字段是问题、状态、Cycle/Stage、输入类型、schema version 和 id；候选项、取舍、推荐、影响和确认方式按问题需要填写。需要展示时可以使用完整决策卡，但不要求普通请求填写固定表单；不得把自由输入或复杂问题伪装成单选。

## 0.12 研究结论标记

```text
Fact
已有证据支持

Inference
根据证据推断

Hypothesis
尚未验证

Decision
用户已确认
```

## 0.13 Gate State Machine

所有 GATED Stage 只允许以下 `GateStatus`：

```text
PENDING
验证、必要输入或决策尚未完成；不得进入下一 GATED Stage。

PASS
Contract 与 Verification 满足，可进入 Transition 指定的下一阶段。

REVISE
存在可修复缺陷，必须返回 Failure Route 指定阶段。

HOLD
当前方向仍有效，但主动暂停当前周期或等待外部条件。

STOP
终止当前开发周期。
```

`user_decision`、`external_dependency`、`missing_evidence`、`runtime_failure` 等可以作为 blocker 记录，不是额外 GateStatus；只有待处理 `user_decision`、明确 `HOLD` / `STOP`、运行状态不可解析或安全/完整性错误自动暂停 CLI，其他普通 blocker 只作提示并保留记录。

只有包含需要用户决策、重大范围 / 方向变化、HOLD / STOP 或 Release approval 的 Gate 才需要用户确认；普通 Stage PASS 不要求额外确认。

Gate 记录 MUST 包含：

```text
Status
Date / Revision
Evidence / Verification
Blocker Refs（PENDING / HOLD 时）
Open Questions
Pending Decision Refs
Failure Route（REVISE 时）
Next Transition
```

任何自动化、Agent 或子任务均无权把需要用户决策的 `PENDING` 静默改为 `PASS`。

---

# 1. Idea

## 目标

把灵感转成明确问题。

## 执行

明确：

```text
目标用户
使用场景
触发条件
当前行为
核心问题
当前方案
当前方案缺陷
计划解决的部分
明确不解决的部分
MVP 假设
```

核心问题可写成：

```text
当 ______ 发生时，
用户需要 ______，
但当前只能通过 ______，
导致 ______。
```

MVP 只保留：

```text
一个核心用户
一个核心场景
一个核心任务
一个核心结果
```

## 检查

- [ ] 用户具体
- [ ] 场景具体
- [ ] 问题不是功能描述
- [ ] 当前替代方案明确
- [ ] 问题与解决方案分离
- [ ] MVP 有边界
- [ ] 未验证假设已标记

## 产物

`01_IDEA.md`

## Gate

以下情况 `REVISE`：

```text
目标用户过泛
问题不明确
MVP 过大
核心场景不成立
关键假设无法继续判断
```

---

# 2. Market Research

## 目标

验证需求是否真实，并找到最适合切入的细分市场。

## 执行

### 2.1 市场范围

```text
行业
细分领域
地区
用户类型
B2C / B2B / Prosumer
使用者
决策者
付款者
```

### 2.2 需求证据

优先：

```text
用户评论
社区讨论
论坛
Reddit
知乎
小红书
抖音
X
Discord
产品评价
招聘需求
企业采购
真实工作流
行业资料
用户访谈
```

每条重要证据记录：

```text
来源
日期
用户类型
问题
当前行为
反映出的需求
```

### 2.3 当前解决成本

```text
时间
人力
软件
订阅
外包
学习
机会成本
```

### 2.4 需求结构

识别：

```text
谁最痛
谁最频繁
谁最主动解决
谁最容易触达
谁最可能付费
```

### 2.5 市场变化

```text
技术
平台
政策
用户行为
成本
竞争
```

### 2.6 候选切入口

每个候选写：

```text
用户
场景
问题
当前替代
进入难点
验证方法
```

## 检查

- [ ] 有多个独立需求证据
- [ ] 不只依赖行业报告
- [ ] 使用者和付款者已区分
- [ ] 当前解决成本明确
- [ ] 存在具体细分场景
- [ ] 关键证据有来源和日期
- [ ] 证据不足处已标记

## 产物

`02_MARKET_RESEARCH.md`

## Gate

需要确定：

```text
优先进入哪个细分市场
哪些用户暂不考虑
是否继续
```

存在多个明显不同方向时，向用户提问。

---

# 3. Product Research

## 目标

理解现有解法，找到可复用模式、行业惯性和未解决缺口。

## 执行

### 3.1 调研池

```text
直接竞品
间接竞品
替代工具
开源项目
用户自建流程
行业老产品
新兴 AI 产品
```

### 3.2 产品定位

```text
目标用户
核心场景
首页承诺
首次价值
商业模式
```

### 3.3 核心流程

实际检查：

```text
注册
首次进入
核心输入
处理过程
结果
二次操作
保存
分享
导出
再次使用
```

记录：

```text
动作
页面
反馈
摩擦
亮点
```

### 3.4 功能

```text
解决什么问题
在哪个流程出现
使用频率
是否核心
```

### 3.5 UX

```text
导航
信息架构
输入方式
核心交互
等待
错误
恢复
```

### 3.6 UI / Design System

实际检查：

```text
布局与信息密度
字体与层级
色彩与 Surface
导航与页面 Archetype
组件与 Pattern
状态设计
动效语言
响应式策略
可访问性
视觉辨识度
```

同时识别：

```text
使用了哪些成熟 UI / Primitive 基座
使用了哪些动效 / Icon / Chart 基座
哪些是通用能力
哪些是真正形成产品差异的自有设计
哪些模式已经严重同质化
```

### 3.7 真实反馈

重点找：

```text
差评
退款原因
迁移原因
抱怨
功能请求
长期痛点
```

### 3.8 模式分类

```text
已验证有效
值得借鉴
行业惯性
明显缺陷
严重同质化
可以重构
```

## 检查

- [ ] 不只看头部竞品
- [ ] 实际走过核心流程
- [ ] 看过真实用户负面反馈
- [ ] 已识别行业默认模式
- [ ] 已找到未解决缺口
- [ ] 已明确禁止直接复制的模式

## 产物

```text
03_PRODUCT_RESEARCH.md
03_COMPETITOR_MATRIX.md
```

## Gate

必须能回答：

```text
该学什么
该避开什么
哪个缺口值得切入
哪些模式已经被验证
哪些模式只是惯性
```

---

# 4. Reuse Base Research

## 目标

确定非核心能力的复用方案，优先采用成熟基座，把自研投入留给产品差异化能力。

## 执行

### 4.1 通用能力

```text
Starter
Auth
Billing
Email
Storage
Database
Search
Analytics
Admin
Permission
CMS
Queue
Observability
Deployment
Testing
AI SDK
```

### 4.2 UI / Design Base

前端项目额外调研：

```text
UI Component Library
Headless / Primitive Library
Form / Data Grid
Motion Library
Icon Library
Chart / Visualization
Editor / Canvas（需要时）
Storybook / Component Workbench（需要时）
已有 Design System / Theme
```

优先研究成熟方案，不默认自研基础控件和动画引擎。

重点判断：

```text
行为能力是否成熟
Accessibility 是否可靠
Keyboard / Focus 是否完整
是否容易主题化
是否能被项目直接拥有或扩展
是否会强绑视觉风格
代码和 API 是否容易被 AI 理解
文档和生态是否稳定
与技术栈是否匹配
```

### 4.3 候选来源

优先：

```text
官方方案
成熟 SaaS
稳定开源项目
成熟 Starter
成熟组件 / Primitive 库
成熟动效库
现有代码资产
```

### 4.4 评估

```text
能力范围
维护状态
接入成本
修改难度
扩展性
文档质量
Accessibility
主题化能力
代码可控性
AI 可读性
锁定风险
替换成本
许可证
Bundle / 性能影响
```

### 4.5 产品限制

```text
是否限制 UI
是否限制交互
是否限制数据模型
是否限制部署
是否侵入核心业务
是否迫使产品呈现明显模板风格
```

### 4.6 分类

```text
直接复用
主题化后复用
封装后复用
参考实现
自己开发
禁止引入
```

UI 基座还要明确：

```text
哪些能力交给成熟库
哪些视觉由项目 Token 接管
哪些交互由项目 Pattern 接管
哪些品牌表达必须自有
```

## 原则

```text
成熟通用能力优先复用
产品差异化能力优先自有
组件库不是 Design System
动效库不是 Motion Language
不因为使用成熟基座接受默认视觉
```

## 检查

- [ ] 所有通用基础能力都做过复用判断
- [ ] UI / Primitive / Motion 等前端基座已做复用判断
- [ ] 核心能力没有交给不可控基座
- [ ] UI / UX 不会被基座绑死
- [ ] 基座可以被项目主题化或替换
- [ ] 锁定风险明确
- [ ] 替换路径基本可行
- [ ] 没有为了“原创”重复实现成熟底层能力

## 产物

`04_REUSE_BASE_RESEARCH.md`

## Gate

存在以下情况时向用户提问：

```text
两个基座长期影响差异明显
存在明显锁定风险
为了复用必须牺牲核心体验
UI 基座会显著改变既定视觉方向
需要引入重大前端依赖
```

---

# 5. Opportunity

## 目标

基于前四阶段决定是否正式进入产品设计。

## 汇总

只保留：

```text
最强需求证据
最大未验证假设
最优细分市场
主要竞品
核心缺口
可复用基座
最大风险
最快验证方式
```

## 产物

`05_OPPORTUNITY.md`

## Gate

该阶段仍使用统一 `GateStatus`。用户业务选择映射为：

```text
GO   → PASS
WAIT → HOLD
STOP → STOP
```

由用户决策。`GO / WAIT / STOP` 是业务选择，不是第二套 Gate 状态枚举。

---

# 6. Product DNA

## 目标

锁定产品的核心身份与差异化边界。

## 执行

### 6.1 Worldview

```text
我们如何理解这个问题
行业通常如何理解
我们的不同点
```

### 6.2 Core Mechanism

```text
输入
↓
核心处理
↓
中间结构
↓
结果
```

核心机制不能只是：

```text
调用 LLM
聊天
生成内容
```

### 6.3 User Identity

```text
用户使用产品时扮演什么角色
产品强化什么能力或身份
```

### 6.4 Interaction Signature

```text
最高频动作
最有记忆点动作
最能代表核心机制的动作
```

### 6.5 Visual Character

限制在 3~5 个关键词。

### 6.6 Language Character

明确：

```text
按钮
菜单
提示
错误
AI 输出
```

### 6.7 Anti-homogeneity Rules

写明：

```text
不做什么
不长什么样
不直接使用哪些行业默认模式
```

重点检查：

```text
Sidebar + Dashboard
全 Card 化
ChatGPT 式聊天框
Bento Grid
紫蓝渐变
大圆角
玻璃拟态
模板 Hero
模板 Pricing
模板 AI 文案
```

## 检查

- [ ] 核心机制清楚
- [ ] 与主要竞品存在机制差异
- [ ] 核心交互与价值直接相关
- [ ] 视觉性格明确
- [ ] 语言性格明确
- [ ] 禁止项明确
- [ ] 差异不是纯装饰

## 产物

```text
06_PRODUCT_DNA.md
06_ANTI_HOMOGENEITY_RULES.md
```

## Gate

由用户确认。

确认后，后续不得擅自改变。

---

# 7. Function

## 目标

把核心价值转成最小功能系统。

## 执行

### 7.1 用户目标

每个目标只写一个结果。

### 7.2 用户动作

把目标拆成必要动作。

### 7.3 系统能力

每个动作映射系统能力。

### 7.4 Feature

只保留真正需要产品化的能力。

### 7.5 分级

```text
P0 = MVP
P1 = MVP 后优先
P2 = 后续
P3 = 暂不做
```

### 7.6 定义 P0

```text
触发
输入
处理
输出
成功
失败
限制
权限
```

### 7.7 Core Loop

```text
触发
↓
行动
↓
系统响应
↓
获得价值
↓
形成结果 / 资产
↓
再次使用
```

## 检查

- [ ] P0 全部对应真实用户目标
- [ ] 没有“为了完整”加入的功能
- [ ] P0 有异常路径
- [ ] MVP 独立产生核心价值
- [ ] Core Loop 完整

## 产物

```text
07_FUNCTIONS.md
07_MVP.md
07_CORE_LOOP.md
```

## Gate

MVP 范围由用户确认。

---

# 8. Requirements

## 目标

把“功能要做什么”进一步约束成“系统必须达到什么条件”。

## 执行

### 8.1 Functional Requirements

补充 Function 中尚未明确的行为约束：

```text
输入限制
输出要求
权限
状态
边界条件
异常行为
数据保留
```

### 8.2 Performance

明确需要时的目标：

```text
首屏
接口响应
AI 响应
上传
导出
并发
长任务
```

### 8.3 Compatibility

明确：

```text
浏览器
Desktop
Tablet
Mobile
操作系统
最低屏幕宽度
```

### 8.4 Accessibility

明确：

```text
Keyboard
Focus
Contrast
Screen Reader
Reduced Motion
```

### 8.5 SEO / Shareability

项目需要时明确：

```text
Indexing
Metadata
Open Graph
Structured Data
Public URL
```

### 8.6 Data

明确：

```text
保存什么
保存多久
谁能访问
是否可导出
是否可删除
是否需要备份
```

### 8.7 Cost Constraints

AI / SaaS / API 项目需要明确：

```text
单次任务成本
单用户成本
第三方 API 成本
Token 使用
存储成本
```

### 8.8 Internationalization

需要时明确：

```text
语言
时区
日期
货币
文本扩展
RTL
```

### 8.9 PRD 汇总视图（可选）

APS 不增加独立的 PRD Stage。PRD 是对 Stage 05–09 当前有效结论的派生汇总，用于让用户、Agent 和非 APS 参与者快速理解产品契约；它不是第二个 Requirements Source，也不新增 Gate。

需要一页产品文档时，在 Stage 08 形成初版 PRD Snapshot，并使用稳定来源引用：

```text
问题 / 目标 / 非目标       → Stage 05 Opportunity、Stage 06 Product DNA
MVP / Core Loop / 功能     → Stage 07 Function
功能与非功能约束           → Stage 08 Requirements
用户流程 / 状态 / 线框      → Stage 09 UX（完成后补充引用）
决策与未确定项             → DEC-* / 当前 blocker
验收与指标                 → Requirements / Validation / QA
```

PRD Snapshot 的关键结论最好回指当前有效 Artifact 或 `DEC-*`；来源变化时按需更新汇总。PRD Snapshot 缺失或过期时只作提示，不替代 Requirements、UX、Architecture 或 Security 的验收，也不单独推动 Stage Transition。

## 检查

- [ ] 核心性能要求明确
- [ ] 支持设备 / 浏览器明确
- [ ] 数据生命周期明确
- [ ] Accessibility 基线明确
- [ ] AI 成本和延迟有边界
- [ ] 非功能要求没有留到开发时猜

## 产物

```text
08_REQUIREMENTS.md
可选：08_PRD_SNAPSHOT.md（仅引用 Stage 05–09 的当前有效 Artifact）
```

## Gate

如果某项约束会显著改变 UX、架构或成本，向用户提问。若创建 PRD Snapshot，按需检查来源引用；Stage 08 的实际目标和验证仍以 Requirements Artifact 为准。

---

# 9. UX

## 目标

设计用户完成任务的完整路径。

## 执行

### 9.1 主流程

```text
进入
↓
识别入口
↓
输入
↓
系统处理
↓
结果
↓
后续动作
```

### 9.2 首次使用

```text
Onboarding
权限
引导
Demo
Empty
```

### 9.3 重复使用

```text
快速进入
恢复上下文
复用历史
减少重复输入
```

### 9.4 失败流程

```text
输入错误
接口失败
AI 失败
超时
断网
权限失败
资源不存在
```

### 9.5 恢复路径

```text
下一步
保留什么
是否可重试
是否需要重新开始
```

### 9.6 Information Architecture

```text
一级导航
二级导航
页面关系
对象层级
主要入口
快捷入口
```

### 9.7 State Model

```text
default
loading
empty
success
error
disabled
partial
offline
permission denied
```

### 9.8 Wireframe

只解决：

```text
结构
顺序
层级
操作位置
信息密度
```

## 检查

- [ ] 首次流程完整
- [ ] 重复使用更高效
- [ ] 失败都有恢复
- [ ] 状态完整
- [ ] 核心任务无多余层级
- [ ] IA 稳定
- [ ] Wireframe 覆盖核心页面

## 产物

```text
09_USER_FLOW.md
09_IA.md
09_STATE_MODEL.md
09_WIREFRAMES/
```

## Gate

核心流程和 IA 由用户确认。

---

# 10. UI / Design System

## 目标

在原型和正式开发前，确定项目自己的视觉语言、成熟 UI / 动效基座使用方式，以及 AI 后续必须遵循的设计执行规则。

Design System 不从零制造全部组件，而是：

```text
成熟基础能力
+
Project Visual DNA
+
Design Tokens
+
Project Patterns
+
Reference UI
+
Design System Agent Skill
```

## 执行

### 10.1 输入检查

必须读取：

```text
Product DNA
Anti-homogeneity Rules
Requirements
UX / IA / State Model
Reuse Base Research
已有品牌资产
已有 UI（若有）
```

如果视觉方向仍存在多个明显不同选择，先在当前对话逐项说明每个方向的优点、缺点、适用条件和主要风险，再分轮筛选或接受自由输入；不得为了简化提问静默合并或删除视觉方向。

### 10.2 Visual Direction

每个候选方向至少说明：

```text
Typography
Density
Geometry
Surface
Color
Layout
Motion
Brand Expression
与竞品的距离
实现成本
```

方向可以组合，但最终必须形成一个明确主方向。

### 10.3 Visual DNA

确定：

```text
Visual Metaphor
信息密度
排版性格
空间节奏
Geometry
Surface Philosophy
Color Strategy
Icon Character
Motion Character
Brand Moments
```

Visual DNA 描述“为什么长这样”，不是组件 API 清单。

### 10.4 UI / Motion Base Strategy

根据第 4 阶段调研结果确定：

```text
Component / Primitive Base
Motion Base
Icon Base
Chart / Visualization Base（需要时）
Editor / Canvas Base（需要时）
```

对每个基座明确：

```text
直接使用什么
主题化什么
封装什么
禁止使用什么默认样式
什么时候允许绕过
替换边界
```

不得因为采用成熟库而继承其默认产品视觉。

### 10.5 Design Tokens

定义至少两层：

```text
Primitive Tokens
↓
Semantic Tokens
```

只有存在明确复用价值时再增加：

```text
Component Tokens
```

覆盖需要的：

```text
Color
Typography
Spacing
Radius
Border
Shadow / Elevation
Size
Motion
Breakpoints
Z-index（需要时）
```

原则：

```text
设计值必须有语义来源
避免页面硬编码随机值
Token 应可被代码和设计工具消费
实际落盘格式在 Project Bootstrap 按技术栈确定
```

### 10.6 Component Strategy

此阶段不提前制造完整组件库，也不维护静态 `COMPONENT_SPEC` 大全。

定义组件决策顺序：

```text
Reuse
↓
Compose
↓
Extend
↓
Create
```

只有现有系统无法合理表达真实需求时才创建新组件。

需要区分：

```text
Primitive
Component
Pattern
Feature-specific UI
```

一次性需求不得为了“设计系统完整”强行抽象。

### 10.7 Pattern Strategy

Pattern 必须从真实用户流程和 Reference UI 中生长。

优先识别：

```text
Page Header
Search / Filter / Sort
Form Section
List / Detail
Master / Detail
Settings Group
Empty / Error / Loading
Bulk Action
Upload Flow
AI Generation State
Inspector
Command / Quick Action
```

只有跨场景稳定复用后才进入项目 Pattern 层。

### 10.8 Motion Language

成熟动效库负责底层能力，项目负责动效语言。

明确：

```text
Duration
Easing / Spring
Distance
Scale
Opacity
Enter / Exit
Layout Transition
Feedback
Loading
Reduced Motion
```

统一使用项目 Motion Preset，不让每个页面自行发明参数。

### 10.9 Reference UI Plan

选择 3~5 个最能代表产品的核心界面作为 Reference Screens。

至少覆盖：

```text
核心任务
高信息密度场景
关键结果
复杂状态 / 交互
关键响应式场景
```

同时定义：

```text
为什么选它
必须稳定的视觉特征
允许变化的范围
需要压力测试的内容和状态
```

### 10.10 Design System Agent Skill Contract

定义项目级 Design System Agent Skill 的 Contract；实际运行资产在 Project Bootstrap 落盘。

Skill Contract MUST 定义：

```text
Identity
Trigger / Non-trigger
Scope
Inputs
Dependencies
Source of Truth
Procedure
Outputs
Forbidden Actions
Failure Handling
Host Compatibility
Validation
Evals
Lifecycle
```

Skill MUST 让 UI Agent 按以下顺序工作：

```text
读取 Visual DNA / Design System
↓
读取 Token / Motion Source
↓
检查已有 Components / Patterns
↓
对照 Reference UI
↓
识别页面 / Pattern
↓
Reuse → Compose → Extend → Create
↓
实现
↓
Visual / Responsive / Accessibility / Design-System QA
```

Skill MUST NOT 复制完整设计规则，只引用项目里的真实 Source of Truth。

Skill 的行为变更必须来自可记录的 Failure Signal / 新能力 / 用户决策，并通过 Eval + Regression 后才能进入 ACTIVE。

### 10.11 Anti-homogeneity Check

逐页追问：

```text
为什么是这个布局
为什么是这个导航
为什么需要 Card
为什么需要 Chat
为什么需要 Dashboard
为什么需要渐变
为什么使用这个动效
为什么需要这个新组件
```

没有产品理由则删除或回退到更基础的表达。

## 检查

- [ ] UI 主方向明确
- [ ] Visual DNA 可执行
- [ ] UI / Motion 基座已明确使用边界
- [ ] Token 层级清楚
- [ ] 没有提前制造无需求组件
- [ ] Reuse → Compose → Extend → Create 已成为统一策略
- [ ] Reference Screens 已选定
- [ ] Motion Language 已定义
- [ ] Agent Skill 执行逻辑已定义
- [ ] 核心界面不会直接继承组件库默认模板感
- [ ] 去掉 Logo 仍保留识别特征

## 产物

```text
10_VISUAL_DNA.md
10_DESIGN_SYSTEM.md
```

其中 `10_DESIGN_SYSTEM.md` 只记录：

```text
设计原则
UI / Motion 基座决策
Token 结构
Component / Pattern 策略
Motion Language
Reference UI 规则
Agent Skill 执行要求
Anti-patterns
```

不维护可以从代码、Token 或组件工作台直接读取的重复信息。

## Gate

由用户确认：

```text
UI 主方向
Visual DNA
UI / Motion 基座策略
Reference UI 选择
```

确认后进入 Reference Prototype。

---

# 11. Reference Prototype

## 目标

用少量高代表性界面验证完整体验和 Design System 是否成立，并建立后续 AI 开发的视觉基准。

## 执行

### 11.1 Reference Screens

优先制作第 10 阶段选定的 3~5 个核心界面。

必须覆盖：

```text
首次进入或核心入口
核心任务
核心结果
关键二次操作
复杂信息密度
Loading / Empty / Error
关键移动端或窄屏状态
```

这些界面不是“展示稿”，而是后续实现的视觉基准。

### 11.2 Prototype

原型必须：

```text
可操作
使用真实文案
使用接近真实的数据
包含关键状态
包含关键响应式
体现已确认的 Visual DNA
体现 UI / Motion 基座策略
```

可以使用最适合项目的方式实现：

```text
设计工具原型
代码原型
现有组件工作台
混合方式
```

不强制使用某一种设计工具。

### 11.3 Design-System Stress Test

使用：

```text
长标题
长列表
空数据
大量数据
异常数据
错误返回
多语言 / 文本扩展（需要时）
Reduced Motion
Keyboard / Focus
```

检查现有 Token、组件基座、Pattern 和 Motion Language 是否足够表达真实需求。

### 11.4 System Feedback

发现缺口时分类：

```text
Visual DNA 问题
Token 缺口
Base Library 限制
Component 缺口
Pattern 缺口
Feature-specific 特例
Motion 缺口
```

只修改真正暴露的问题，不为了完整性扩展 Design System。

### 11.5 Visual Reference

为 Reference Screens 记录：

```text
界面位置 / 链接 / 截图
关键设计决策
必须保持的特征
允许变化范围
已验证状态
```

后续 Task 和 AI Build 必须引用这些基准，而不是凭记忆复现。

## 检查

- [ ] 核心流程可走通
- [ ] Reference Screens 足以代表产品视觉语言
- [ ] 状态完整
- [ ] 数据接近真实
- [ ] 移动端关键场景可用
- [ ] 主要交互可实际体验
- [ ] Design System 在真实页面中成立
- [ ] 基座默认视觉已被项目语言覆盖
- [ ] 已发现的系统缺口已分类

## 产物

```text
11_PROTOTYPE.md
11_VISUAL_REFERENCE.md
```

## Gate

由用户确认：

```text
核心体验是否成立
Reference UI 是否可作为后续视觉基准
是否进入 Validation
```

---

# 12. Validation

## 目标

在工程投入前发现产品、功能、UX、UI 问题。

## 执行

### 12.1 任务

例如：

```text
完成一次核心任务
找到一个历史结果
处理一次失败
完成一次二次操作
```

### 12.2 记录行为

```text
第一次点击
犹豫
错误点击
返回
停顿
误解
需要解释的位置
```

### 12.3 记录问题

```text
现象
位置
用户行为
可能根因
所属阶段
严重程度
```

### 12.4 路由问题

```text
定位 → Product DNA
功能 → Function
约束 → Requirements
流程 → UX
视觉 → UI
文案 → Language
状态 → UX / UI
```

## 检查

- [ ] 核心任务无需解释
- [ ] 用户知道下一步
- [ ] 错误后能恢复
- [ ] 没有关键误解
- [ ] 核心交互清晰
- [ ] 信息层级清楚

## 产物

```text
12_VALIDATION_REPORT.md
12_ISSUES.md
```

## Gate

未通过不得进入 Architecture。

---

# 13. Architecture

## 目标

把已经确认的产品转换成最小可维护技术方案。

## 执行

### 13.1 模块

```text
Frontend
Backend
Database
AI
Storage
Queue
Auth
Permission
Billing
Analytics
Observability
Deployment
Security
```

### 13.2 职责

```text
负责什么
不负责什么
输入
输出
依赖
```

### 13.3 数据模型

```text
核心实体
字段
关系
状态
生命周期
```

### 13.4 API

```text
method
path
input
output
error
permission
idempotency
```

### 13.5 AI Contract

```text
model
input schema
output schema
prompt
tool access
timeout
retry
fallback
eval
```

### 13.6 复用基座落位

```text
直接接入
封装后接入
替换
自研
```

### 13.7 Failure

```text
失败
重试
降级
回滚
用户提示
日志
告警
```

### 13.8 Observability

至少：

```text
error
latency
cost
usage
AI success
```

## 检查

- [ ] 核心实体明确
- [ ] 核心接口明确
- [ ] AI Schema 明确
- [ ] 失败恢复明确
- [ ] 基座位置明确
- [ ] 没有明显过度设计
- [ ] 观测方式明确

## 产物

```text
13_ARCHITECTURE.md
13_DATABASE.md
13_API.md
13_AI_SPEC.md
```

## Gate

存在长期架构取舍时向用户提问。

---

# 14. Security / Risk Review

## 目标

在开发前确认安全、隐私、权限和合规边界。

## 执行

### 14.1 数据分类

列出：

```text
公开数据
用户数据
敏感数据
密钥
支付数据
身份数据
企业数据
上传文件
AI 上下文
```

### 14.2 数据流

确认：

```text
数据从哪里进入
存在哪里
发送给哪些第三方
谁能访问
何时删除
是否进入日志
是否进入 AI Provider
```

### 14.3 Auth / Permission

检查：

```text
登录
Session
角色
资源权限
跨用户访问
管理员权限
API 权限
```

### 14.4 Secrets

确认：

```text
API Key
Token
Webhook Secret
Database Credential
Environment Variables
```

不得进入：

```text
前端
日志
仓库
错误信息
```

### 14.5 AI 风险

AI 产品检查：

```text
Prompt Injection
Tool Permission
Data Exfiltration
Untrusted Input
Model Output Trust
Action Confirmation
Tool Scope
```

### 14.6 文件 / 输入

检查：

```text
类型验证
大小
恶意文件
HTML / Markdown 注入
URL
上传权限
```

### 14.7 Logging

确认：

```text
敏感字段脱敏
错误日志
审计日志
AI 请求日志
数据最小化
```

### 14.8 Compliance

仅在项目涉及对应领域时加载：

```text
隐私
支付
医疗
金融
儿童
企业合规
数据地域
```

## 检查

- [ ] 敏感数据已识别
- [ ] 第三方数据流明确
- [ ] 权限边界明确
- [ ] Secrets 管理明确
- [ ] AI 工具权限受控
- [ ] 日志不会泄漏敏感信息
- [ ] 删除 / 导出要求明确
- [ ] 必要合规项已识别

## 产物

```text
14_SECURITY_REVIEW.md
14_RISK_REGISTER.md
```

## Gate

存在重大安全、隐私或合规风险时，向用户提问，不得直接进入开发。

---

# 15. Project Bootstrap

## 目标

在业务开发前建立稳定、可测试、可部署的工程基座。

## 执行

### 15.1 Repository

```text
初始化仓库
默认分支
.gitignore
README 基础信息
```

### 15.2 Runtime / Package

```text
运行时版本
包管理器
依赖锁定
版本策略
```

### 15.3 Project Structure

建立：

```text
源码
测试
配置
脚本
公共组件
服务
类型
静态资源
```

### 15.4 Environment

明确：

```text
local
preview
staging
production
```

并建立：

```text
.env.example
环境变量说明
Secret 注入方式
```

### 15.5 Code Quality

配置：

```text
lint
format
typecheck
pre-commit（需要时）
```

### 15.6 Testing

初始化：

```text
unit
integration
E2E
test fixtures
mock strategy
```

### 15.7 CI

至少运行：

```text
install
lint
typecheck
test
build
```

### 15.8 Deployment

完成最小可用：

```text
Preview 可部署
Staging 可部署
Production 路径明确
```

### 15.9 Observability

接入最小能力：

```text
error tracking
structured logs
basic metrics
```

### 15.10 Design System Bootstrap

前端项目根据第 10 阶段决策，把设计系统真正落到仓库。

建立或接入：

```text
选定的 Component / Primitive Base
选定的 Motion Base
Icon / Chart Base（需要时）
Design Token Source
Theme / CSS 映射
Motion Presets
UI Components 入口
Project Patterns 入口
Reference UI 入口
Component Workbench / Storybook（复杂项目需要时）
```

Design Token 的实际格式按技术栈确定；需要跨工具交换时优先采用标准化、机器可读结构。

项目目录不强制固定，但必须让 AI 能明确找到：

```text
Token Source of Truth
Component Source of Truth
Pattern Source of Truth
Motion Source of Truth
Visual Reference
```

建立项目级 Design System Agent Skill。

Skill 只负责执行流程和引用真实来源，不复制整套设计规范。

首先执行 Host Adapter：

```text
识别当前 Agent Host
↓
解析项目级 Skill Discovery Location
↓
创建 / 安装 Skill
↓
检查 Host 是否允许 implicit invocation
↓
记录 fallback
```

例如 Codex 项目使用仓库级 `.agents/skills/design-system/`；其他 Host 采用自身支持的项目级位置。禁止为了某个 Host 把项目专属设计规则写入全局 / 系统 Skill，除非用户明确要求共享。

Skill 至少包含：

```text
Identity / Description
何时触发 / 何时不触发
需要先读取什么
Reuse → Compose → Extend → Create
什么时候允许新增 Component / Pattern
如何使用 Token / Motion Preset
如何对照 Reference UI
如何执行 Visual / Responsive / Accessibility / Design-System QA
发现系统缺口时如何回收
失败时如何退出或请求决策
```

项目 SHOULD 为关键 Skill 建立：

```text
Static Validator
Trigger Cases
Non-trigger Cases
Execution Smoke Cases
Regression Cases
CHANGELOG / Version Metadata（复杂项目）
```

`AGENTS.md` 只记录 Skill 入口和设计 Source of Truth 的路径，不重复复制完整 Design System。

### 15.11 Baseline

确认：

```text
项目能启动
空项目能构建
测试能执行
CI 能通过
Preview 能访问
设计 Token 可被代码消费（前端项目）
UI 基座可以正常使用（前端项目）
Motion Preset 可用（使用动效时）
Design System Skill 可被 Agent Host 发现且通过最小触发 / 执行验证（使用 Agent Skill 时）
```

## 检查

- [ ] 新环境可按文档启动
- [ ] 环境变量有模板
- [ ] lint / typecheck / test / build 可运行
- [ ] CI 已建立
- [ ] Preview 可访问
- [ ] Staging / Production 路径明确
- [ ] 基础错误追踪已接入
- [ ] 前端项目的设计基座已实际落盘
- [ ] Token / Component / Pattern / Motion 的 Source of Truth 可定位
- [ ] Design System Agent Skill 已建立、Host Adapter 已记录并通过 discovery / trigger smoke test，或明确不需要
- [ ] `AGENTS.md` 没有复制整套 Design System

## 产物

```text
15_BOOTSTRAP.md
AGENTS.md
实际工程配置与代码
Design Token Source（前端项目）
Motion Presets（需要时）
Design System Agent Skill（使用 Agent Skill 时）
```

实际文件路径由技术栈决定，并记录在 `15_BOOTSTRAP.md`。

## Gate

工程基座不能稳定运行时，不进入业务 Task。

---

# 16. Task Engineering

## 目标

把开发拆成 AI 可独立完成、独立验证的原子任务。

大型项目必须为每个 Task 标注所属 `workstream`（例如 `WS-CORE`），并在需要时记录 parent Task、依赖和跨 workstream 接口。不同 workstream 可以并行执行 Task-local Code / Tests / Evidence；修改全局 `state.yaml`、Gate、Decision、Registry 或共享 Schema 时仍由 Coordinator 单写，不能用并行任务绕过统一主线。

并行 Task 的最小交接只包含变更文件、接口影响、依赖状态和 Evidence refs；Coordinator 合并前必须重新检查跨 workstream 依赖，Task-local 完成不得直接推导全局 Gate PASS。

## 执行

```text
Epic
↓
Feature
↓
Task
↓
Atomic Task
```

每个 Atomic Task 必须包含：

```text
Goal
Context
Input
Output
Files Allowed
Files Read-only
Constraints
Interfaces
Design Sources
Visual Reference
Design System Impact
States
Acceptance Criteria
Tests
Out of Scope
```

每个 Task 还必须明确：

```text
Task Type：implementation / verification / governance / external
Production Change Expected：true / false
Authorization：explicit TASK-ID / continuation of active task
```

验收必须可观察。

禁止：

```text
体验良好
代码优雅
差不多符合设计
```

改为：

```text
375px 不横向溢出
网络失败显示 Retry
上传成功跳转详情
错误状态保留用户输入
```

## 检查

- [ ] 一个任务只有一个目标
- [ ] 文件范围明确
- [ ] 输入输出明确
- [ ] 验收可观察
- [ ] 测试可执行
- [ ] UI Task 已指定 Design Sources / Visual Reference
- [ ] 新增 Component / Pattern 时已说明 Design System Impact
- [ ] Out of Scope 明确

## 产物

```text
16_TASKS.md
16_TASKS.json
```

## Gate

如果 AI 仍需猜关键需求：

```text
继续拆或向用户提问
```

---

# 17. AI Build

## Entry Guard

Stage 17 不会替用户选择任务。进入或继续执行前必须先确认：

```text
active_task_ref = 明确的 TASK-*
active_task_kind = implementation / verification / governance / external
```

“继续”只延续当前 active task，不产生新的任务授权。没有 active task、当前任务已结束或当前任务被阻塞时，必须停止并请求明确 `TASK-*`；不得按顺序、优先级、依赖或便利性自动挑选下一个任务。

只有 `active_task_kind=implementation` 且 `Production Change Expected=true` 才算进入产品开发。验证、治理和外部验收任务可以单独执行，但不能被描述为开发，也不能用来填充被 blocker 暂停的开发路径。

## 固定执行顺序

```text
Read
↓
Plan
↓
Implement
↓
Test
↓
Visual Verify
↓
Review
↓
Fix
```

## Read

读取：

```text
Task
相关 Spec
Product DNA
Requirements
Design System
Visual Reference
Design System Agent Skill（UI Task）
Token / Component / Pattern / Motion Source（UI Task）
Architecture
Security Rules
相关代码
```

## Plan

先输出：

```text
修改目标
文件范围
实现顺序
风险
验证方式
明确不修改什么
```

## Implement

不得：

```text
扩大 Scope
顺手重构
顺手升级依赖
增加未要求功能
改变接口
擅自改变已确认 UI 方向
修改无关代码
绕过安全规则
```

UI Task 固定使用：

```text
Reuse
↓
Compose
↓
Extend
↓
Create
```

实现时：

```text
优先使用已有 Component / Pattern
使用项目 Token，不写无来源随机视觉值
使用项目 Motion Preset，不在页面内随意发明动效参数
只有真实需求无法由现有系统表达时才新增 Component / Pattern
Feature-specific UI 不强行沉淀为通用组件
```

如果新增了可复用能力，任务结束前同步对应 Source of Truth；不要只改页面代码。

## Test

执行：

```text
lint
typecheck
unit
integration
build
```

必要时：

```text
E2E
Agent Skill Static Validation
Agent Skill Trigger / Execution Eval
Visual Regression
```

修改 Agent Skill、Skill Source of Truth、触发描述或 Host Adapter 时，MUST 运行对应 Regression Eval。

## Visual Verify

前端任务：

```text
实际运行
截图
对照 Reference UI
检查 Visual DNA
检查 Design Token 使用
检查响应式
检查所有状态
检查 Keyboard / Focus
检查 Reduced Motion（有动效时）
```

如果项目已建立视觉回归能力，执行对应检查。

## Review

检查：

```text
超 Scope
回归
重复实现
无来源视觉值
不必要的新 Component / Pattern
Design System 漂移
复杂度
安全
UX
UI
状态遗漏
```

## Fix

只修已发现问题，不借机扩功能。

## Transition Contract

Stage Type：`EXECUTION_LOOP`。

单个 Atomic Task 使用：

```text
READY → IN_PROGRESS → DONE
                 ↘ NEEDS_FIX
                 ↘ BLOCKED
```

只有 Acceptance Criteria、所需 Test / Visual Verify / Security Check、Task-local Review 全部满足，任务才可标记 `DONE`。

进入 Stage 18 的 Exit Condition：

```text
当前 Scope 内所有 P0 / Release-blocking Task = DONE
且不存在未解决的 blocker
且 Task / Test Evidence 已落盘
```

未满足时继续 Stage 17，不得用 Stage Gate 假装完成。

---

# 18. Functional QA

## 执行

### Happy Path

核心成功流程。

### Edge Cases

边界输入。

### Failure Cases

```text
网络
接口
权限
AI
超时
资源缺失
```

### Regression

旧功能。

### AI Eval

```text
正确性
格式
一致性
失败恢复
延迟
成本
```

## 产物

```text
18_FUNCTIONAL_QA.md
18_AI_EVAL.md
```

## Gate

任何 P0 失败：

```text
REVISE
```

---

# 19. Visual / UX QA

## 执行

### Visual Diff

对照 Reference UI 和已确认 Visual DNA：

```text
spacing
typography
alignment
color
radius
border
size
hierarchy
density
surface
motion
```

### Design System Consistency

检查：

```text
是否使用正确 Token
是否出现无来源硬编码视觉值
是否重复实现已有 Component
是否绕过已有 Pattern
是否出现无理由 Variant
是否违反 Reuse → Compose → Extend → Create
是否偏离 UI / Motion Base 的使用边界
是否出现设计系统与代码不一致
是否需要把新能力回收进 Component / Pattern
```

### Responsive

至少：

```text
375
768
1024
1440+
```

具体断点以 Requirements 和 Design System 为准。

### State

```text
default
loading
empty
success
error
disabled
partial（需要时）
offline（需要时）
permission denied（需要时）
```

### Interaction

```text
hover
focus
press
keyboard
scroll
drag
modal
navigation
reduced motion
```

### Content Stress

```text
长标题
长列表
空数据
大量数据
特殊字符
多语言
```

### Visual Regression

项目具备组件工作台、截图基线或视觉回归工具时执行：

```text
Reference Screen Diff
关键 Component State Diff
关键 Breakpoint Diff
```

视觉回归结果不能代替人工判断信息层级和交互是否正确。

## 产物

```text
19_VISUAL_QA.md
19_UX_QA.md
19_DIFF_REPORT.md
```

## Gate

以下情况 `REVISE`：

```text
视觉明显偏离 Reference UI / Visual DNA
响应式破裂
核心交互与原型不同
信息层级失真
出现明显组件库默认模板感
出现 Design System 漂移
新增通用 UI 能力但未回收到系统
```

最终体验由用户确认。

---

# 20. Release

## 执行

### Preview

检查单任务结果。

### Staging

检查完整链路。

### Migration

确认：

```text
forward
rollback
backup
```

### Monitoring

确认：

```text
error
latency
business events
AI failures
```

### Rollback

明确：

```text
何时回滚
回滚版本
回滚方式
```

发布前执行：

```text
lint
typecheck
unit
integration
E2E
build
migration
security
functional QA
visual QA
monitoring
rollback
```

## 产物

```text
20_RELEASE_CHECKLIST.md
20_RELEASE_NOTES.md
可机器校验的 Release readiness：`.ai/release-readiness.json`
```

## Gate

发布由用户确认。`release-readiness.json` 只证明对应风险级别的技术 / 合规检查和 Evidence 已满足；用户确认不等于机器检查 PASS，机器检查 PASS 也不替代用户 Gate。

---

# 21. Observe

## 执行

### 技术

```text
error
latency
uptime
crash
database
queue
cost
```

### 产品

```text
activation
completion
time-to-value
retention
drop-off
adoption
conversion
```

### AI

```text
success
accuracy
hallucination
format
latency
retry
fallback
```

### 用户行为

```text
session replay
support
feedback
search terms
abandon points
```

只汇总：

```text
发生了什么
为什么重要
可能原因
证据
是否需要行动
```

## 产物

```text
21_METRICS.md
21_FEEDBACK.md
```

## Verification

- [ ] 数据时间窗明确
- [ ] 关键指标来源可追溯
- [ ] 事实、推断和假设已区分
- [ ] 异常信号有对应证据
- [ ] 未把短期噪声直接升级为产品结论

## Transition Contract

Stage Type：`OBSERVATION_LOOP`。

```text
证据不足 / 继续观察 → 留在 Stage 21
出现需要行动的可信 Signal → Stage 22 Iterate
当前 Cycle 目标已完成且无待处理 Signal → Stage 23 Cycle Review
重大风险 / 故障 → 直接路由至对应上游 Stage 或 Incident / Security 流程
```

Observation 不使用伪造的 PASS Gate；Transition 必须记录触发证据。

---

# 22. Iterate

## 执行

```text
Signal
↓
Cluster
↓
Problem
↓
Root Cause
↓
Stage Routing
↓
Change
↓
重新验证
```

路由：

```text
市场 → Market Research
竞品 → Product Research
基座 → Reuse Base Research
定位 → Product DNA
功能 → Function
约束 → Requirements
流程 → UX
视觉 / Design System → UI / Design System
技术 → Architecture
安全 → Security / Risk Review
工程基座 → Project Bootstrap
实现 → Build
AI → AI Spec / Eval
```

Stage 22 可用于记录 Impact Analysis 和路由。已确认 Scope 内且没有改变已确认契约的局部 Task 可以留在当前 Stage；只有实际影响下游契约或验证范围时，才路由到受影响的最早 Stage。

所有新增需求先进入 Backlog。

不得直接开发。

## 产物

```text
22_ITERATION_BACKLOG.md
22_CHANGE_LOG.md
```

## Verification

- [ ] 每个 Signal 已聚类或明确丢弃原因
- [ ] 选中的 Change 有根因和证据
- [ ] Change 已绑定稳定 ID
- [ ] 需要时已完成 Impact Analysis
- [ ] 需要时已路由到真正负责的 Stage
- [ ] 未绕过明确的安全或用户确认边界直接进入 Build

## Transition Contract

Stage Type：`ROUTER`。

```text
存在实际影响的 Change → 路由至受影响的最早 Stage，并按该 Stage 重新验证
仅有记录性 Backlog → 可返回 Observe、进入 Cycle Review 或继续当前工作
没有需要本 Cycle 处理的 Change → Stage 23 Cycle Review
```

Router 本身不产生 `PASS` 来绕过被路由 Stage 的 Gate。

---

# 23. Cycle Review

## 目标

正式关闭本轮开发，保留下一轮可直接继承的工程状态。

## 执行

### 23.1 目标完成情况

对照：

```text
最初目标
MVP
P0
核心指标
```

标记：

```text
完成
部分完成
取消
延期
```

### 23.2 偏差

记录：

```text
产品方向偏差
功能偏差
UX 偏差
UI 偏差
架构偏差
成本偏差
进度偏差
```

### 23.3 已知问题

整理：

```text
Bug
Product Debt
UX Debt
Design Debt
Technical Debt
Security Debt
Data Debt
```

### 23.4 临时方案

列出：

```text
临时 Patch
临时依赖
临时兼容逻辑
临时数据结构
人工操作
```

明确哪些必须在后续清理。

### 23.5 可复用资产

提炼：

```text
组件
Pattern
Design Token
Motion Preset
Design System Agent Skill
Reference UI
工具
脚本
测试能力
Prompt
Eval
基础模块
架构模式
调研资料
```

判断是否沉淀到下一项目。

同时检查 Design System：

```text
哪些 Component / Pattern 已稳定
哪些只是项目特例
哪些 Token / Motion Preset 已废弃
Reference UI 是否仍代表当前产品
Design System Agent Skill 是否与真实代码一致
是否存在未记录的 Design Debt
```

需要时精简系统，而不是只增不减。

同时执行 Skill Lifecycle Review：

```text
ACTIVE Skill 是否仍可被 Host 发现
Trigger 是否出现误触发 / 漏触发
Execution Eval 是否覆盖真实失败
过时 reference / script 是否存在
是否需要 DRAFT → VALIDATED → ACTIVE
是否存在应 DEPRECATED / RETIRED 的规则
```

Skill 修改前应先把真实 Failure Signal 固化为 Eval Case；修改后必须执行旧案例 Regression。

### 23.6 决策复查

检查 `.ai/decisions.md`：

```text
哪些仍有效
哪些需要重新评估
哪些只适用于本周期
```

### 23.7 下一周期入口

只保留：

```text
下一阶段目标
最高优先问题
必须偿还的债务
需要重新调研的假设
```

## 检查

- [ ] 本轮 Scope 状态清楚
- [ ] 所有未完成项都有去向
- [ ] 技术债 / 产品债已记录
- [ ] 临时方案已暴露
- [ ] 可复用资产已识别
- [ ] 下一轮入口明确

## 产物

```text
23_CYCLE_REVIEW.md
23_DEBT.md
23_NEXT_CYCLE.md
```

## Gate

本轮开发关闭。

下一轮从对应阶段重新进入，不默认从 Build 开始。

---

# 24. Change Control

任何已通过 Gate 的内容被修改时，按影响需要记录：

```text
Change ID
修改内容
原因
Scope Delta
影响阶段
影响功能
影响 Requirements
影响 UX
影响 UI
影响技术
影响安全
受影响 Artifact / 文件
仍可复用 Artifact 及理由
需要重新验证 / supersede 的 Artifact
最小验证集合
触发完整回归的条件
Release 影响
需要重新验证什么
```

会改变用户目标、重大 Scope、核心契约或安全边界的变更必须向用户提问。

如果变更仍在已确认 Scope 内，且没有改变已确认的产品、交互、设计、技术、安全或 Release 契约，可作为当前 Task 的增量修改并做相关验证。否则建议使用 Stage 22 记录并路由到受影响的最早 Stage。Router 不产生 PASS，也不允许用“只改了一个文件”掩盖实际的下游影响。

典型回退：

```text
核心交互变化
→ UX
→ UI
→ Prototype
→ Validation
→ Build
```

---

# 25. Scope Control

每个阶段、Feature、Task 必须明确：

```text
In Scope
Out of Scope
```

发现额外问题：

```text
记录 Issue
```

不得顺手修改。

---

# 26. Decision Log

重要决策记录到：

`.ai/decisions.md`

格式：

```text
Decision ID
Date
Problem
Options
Decision
Reason
Trade-off
Affected Areas
Revisit Condition
```

用户决策必须写入。

---

# 27. AGENTS.md

根 `AGENTS.md` 是 Host 自动发现的精简 Runtime Entry，不是普通 Task 的全量知识包。

它 SHOULD 只包含：

```text
`.ai/state.yaml` / `.ai/registry.yaml` 入口
Lifecycle / Artifact Standard 入口
当前 Host / Skill 路由
长期稳定的少量关键不变量
Forbidden Actions
Test / Build / Verification 入口
Change / Gate 规则
```

普通 Task MUST 根据 Context Loading Standard 和 `.ai/registry.yaml` 按需读取 Product DNA、Requirements、Architecture、Security、Design Sources，不得因为 `AGENTS.md` 存在就默认把它们全部载入上下文。

前端 / UI Task 在需要时读取：

```text
Design System Source
Visual Reference
Token Source
Component / Pattern Source
Motion Source
Design System Agent Skill
```

设计相关执行规则：

```text
Reuse → Compose → Extend → Create
Design QA / Responsive / Accessibility / Regression 按 Task 要求执行
详细视觉规则留在 Design System
实际值留在 Token / 代码
执行方法留在 Skill
```

`AGENTS.md` MUST NOT 复制完整 Product DNA、Decision Log、Requirements、Architecture、Design System 或历史状态。

---

# 28. Atomic Task Template

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

---

# 29. Definition of Done

一个任务只有以下全部满足才算完成：

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

---

# 30. 可插拔领域扩展

主流程固定；不同项目在对应位置加载额外模块。

## AI / Agent 产品

插入：

```text
AI Eval
Tool Permission
Prompt Injection
Model Fallback
Agent State
Human Confirmation
Cost Guardrail
```

## Mobile App

插入：

```text
iOS / Android Platform Rules
Native Permission
Offline
Push Notification
Deep Link
App Store / Play Store Release
Crash / Device QA
```

## Enterprise

插入：

```text
SSO
RBAC
Audit Log
Tenant Isolation
Data Residency
Enterprise Integration
Admin Control
```

## Financial / Medical / High-risk

插入：

```text
Compliance
Audit
Data Governance
Approval Flow
High-risk Action Confirmation
Stricter Security Review
```

## Data Product

插入：

```text
Data Source
ETL / ELT
Data Quality
Lineage
Freshness
Backfill
Schema Evolution
```

## Hardware / IoT

插入：

```text
Hardware
Firmware
Device Provisioning
Manufacturing
OTA
Failure Recovery
Physical QA
```

只有项目实际需要时加载，不把领域特有流程塞进通用主流程。

---

# 31. Agent Runtime Standard

## 31.1 Host Adapter

项目 MUST 把 Agent Host 视为可替换运行环境，不把核心开发标准绑定到单一产品。

每个 Host Adapter 至少记录：

```text
Host ID
Detected Version / Capability（可取得时）
Project Instruction Entry
Project Skill Discovery Location
Plan Mode Support / Invocation / Verification
Implicit Invocation Support
Explicit Invocation Method
Tool / Permission Constraints
Fallback Mechanism
Last Verified
Instruction Chain / Budget（Host 支持时）
Critical Skill Name Collision State
```

如果 Host 能力发生变化，必须重新执行受影响的 Runtime Validation。

对于 Codex Adapter，Bootstrap MUST 审计当前生效的 `AGENTS.md` / `AGENTS.override.md` 指令链，并检查从当前目录到 repo root、USER、ADMIN、SYSTEM scope 的关键 Skill 名称冲突。Codex 不会合并同名 Skill；项目关键 Skill 的同名歧义若未显式消解，Runtime Validation 不得通过。

## 31.2 Project vs User / System Skill

```text
项目专属知识 / Visual DNA / 项目 Pattern
→ Project-scoped Skill

跨项目稳定方法
→ User-scoped Skill（可选）

组织统一能力
→ Managed / System scope（仅在明确治理下）
```

项目 Skill MUST 可随仓库迁移；不得依赖开发者机器上的隐式私有状态才能正常执行。

## 31.3 Runtime Failure

出现以下情况时不得静默继续：

```text
Skill 不可发现
Skill 引用路径失效
Host 不支持预期能力
权限不足
Skill 与 AGENTS.md 冲突
Skill 与 Source of Truth 冲突
```

必须记录实际能力并选择运行时处置：

```text
FIX
FALLBACK
BLOCKED（GATED 时 GateStatus=PENDING；非 GATED 时 stage_status=BLOCKED，并记录 blocker）
STOP
```

---

# 32. Agent Skill Contract & Lifecycle

## 32.1 Skill Contract

关键 Skill 至少包含：

```text
Name / Identity
Description
Scope
Trigger
Non-trigger
Inputs
Source of Truth
Dependencies
Procedure
Outputs
Forbidden Actions
Failure Handling
Compatibility
Validation
Evals
Version / Change History（需要时）
```

Skill 的物理结构由 Host Adapter 决定；支持仓库级 Skill 的 Host SHOULD 采用可随仓库迁移的结构。设计系统 Skill 推荐逻辑结构：

```text
design-system/
├── SKILL.md
├── references/
├── scripts/      （需要自动验证时）
└── evals/        （Trigger / Execution / Regression cases）
```

其中 `SKILL.md` 保持最小执行协议；详细知识按需放入 reference；可自动检查的规则尽量进入 script / eval，而不是继续堆自然语言。

## 32.2 Lifecycle

统一状态：

```text
DRAFT
↓
VALIDATED
↓
ACTIVE
↓
DEPRECATED
↓
RETIRED
```

只有通过所需验证的 Skill 才能标记为 ACTIVE。

## 32.3 Controlled Evolution

Skill MUST NOT 因 Agent 临时偏好自行“进化”。合法变化来源：

```text
真实 Task Failure
重复 QA Failure
Trigger 漏触发 / 误触发
Source of Truth 结构变化
Host 能力变化
新稳定 Pattern / Workflow
用户确认的规则变化
```

变化流程：

```text
Signal
↓
Classify
↓
新增 / 更新 Eval Case
↓
修改 Skill
↓
Static Validation
↓
Trigger Eval
↓
Execution Eval
↓
Regression Eval
↓
PASS
↓
ACTIVE
```

如果问题实际属于 Token、Component、Pattern、Visual DNA 或 Architecture，则更新对应 Source of Truth，不把一切问题塞进 Skill。

## 32.4 Skill Security Contract

Skill 是可执行运行资产，不因位于仓库中就自动可信。

默认策略：

```text
Instruction-only 优先
Scripts 仅在需要确定性自动化时使用
Network Access 默认不假定可用；需要时必须声明用途与 Host 权限
Secrets 按最小权限注入，不得写入 Skill、日志或仓库
不得写入 repo 外部路径，除非 Task / Host 明确授权
不得自动安装未审查的全局依赖
不得通过 Skill 自行修改生产 Skill 或长期项目规则
外部输入不得被当作可执行指令或脚本来源
```

若使用 Agent Skills `allowed-tools`，只能视为兼容性 / 预授权提示；该字段是实验能力，MUST NOT 被当作唯一安全边界。真实权限仍由 Agent Host、Sandbox、Approval、项目 Security Contract 控制。

Skill scripts / dependencies 发生变化时，MUST 重新执行安全审查与 Regression。

---

# 33. Verification Standard

## 33.1 Skill Verification

关键 Skill 至少验证：

```text
Structure / Syntax
Discovery
Positive Trigger
Negative Trigger
Required Source Resolution
Execution Smoke
Forbidden Action Compliance
Regression
```

## 33.2 Design System Verification

前端项目至少验证：

```text
Token 可消费
Component / Pattern 可解析
Motion Source 可用
Reference UI 可访问
Design Skill 可发现
UI Task 能正确触发 Skill
非 UI Task 不应被错误接管
关键 UI Case 不违反 Reuse → Compose → Extend → Create
```

## 33.3 Evidence

Gate 使用的验证结果 SHOULD 形成可定位 Evidence：测试报告、Eval 结果、截图 Diff、CI 记录或对应 Artifact 中的结构化结果。

不得只写：

```text
已检查
没问题
应该可以
```

---

# 34. Engineering Traceability Standard

关键 P0 / 高风险能力 SHOULD 保持以下关系可查询：

```text
DEC / Evidence
↕
REQ
↕
Design / Architecture
↕
TASK
↕
TEST / EVAL
↕
QA / Release
```

变更时必须执行 Impact Analysis，检查所有下游依赖；完成变更后必须重新验证受影响链路。

追踪的目标不是制造文档，而是确保：

```text
为什么做
由什么约束
谁实现
怎么验证
改动会影响什么
```

都能被 AI 和人快速确定。

---

# 35. Multi-Agent Concurrency & Governance

项目 MAY 并行使用多个 Agent，但全局治理状态 MUST 有唯一写入者。

```text
Governance Artifacts
`.ai/state.yaml`
`.ai/decisions.md`
`.ai/registry.yaml`
根 `AGENTS.md`
关键 Gate / Change Control
→ Single Writer / Coordinator

Task-local Code / Tests / Evidence
→ 可并行，但必须遵守 Files Allowed / Ownership
```

若没有独立 Orchestrator，当前主 Agent 即视为 Coordinator。子 Agent / Worktree Agent MUST NOT 直接提交全局 Gate 或 Decision。

`.ai/state.yaml` MUST 包含单调递增 `revision`。治理写入采用 compare-before-write：

```text
读取 revision
↓
准备变更
↓
写入前重新确认 revision
↓
未变化 → 原子更新并 revision + 1
已变化 → 重新读取 / 合并 / 冲突处理，不得覆盖
```

并行 Task 若修改同一文件、同一 Schema 或同一 Source of Truth，必须先序列化或显式分片。

---

# 36. Standard Self-Validation

标准本身 MUST 可被静态检查，而不能仅依赖 Agent “读起来没问题”。

至少验证：

```text
Stage 01–23 是否完整存在
Stage Type / Transition 是否闭合
GateStatus 是否只使用统一枚举
所有 Output 是否有 Artifact 映射
Source of Truth 是否唯一
关键路径 / Skill 引用是否存在
AGENTS 指令链是否超 Host 预算
关键 Skill 是否存在同名冲突
Skill Contract / Eval 是否满足项目要求
Dependency Graph 是否存在断链
Schema Version 是否兼容
已 RETIRED / ARCHIVED Artifact 是否仍被 ACTIVE 来源引用
```

Standard / Template 修改后 SHOULD 运行 `standards-lint` 或等效检查，并保留结果。
