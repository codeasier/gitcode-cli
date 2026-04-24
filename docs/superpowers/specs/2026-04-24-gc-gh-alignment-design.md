# gc CLI gh 兼容性对齐设计

**日期：** 2026-04-24  
**状态：** 已确认，待用户审阅  
**范围：** 覆盖 `gc-vs-gh-diff-report.md` 中的 P0、P1、P2 全量路线图  
**目标优先级：** 最大化 `gh` 兼容性；对 GitCode API 做不到的行为，优先保留 `gh` 风格入口并提供最接近的降级行为

---

## 1. 目标

本设计的目标不是机械复制 GitHub CLI `gh`，而是把 `gc` 调整为：

- 凡是能合理映射到 GitCode 的 `gh` 语义，优先保持同名、同默认行为、同输出预期。
- 凡是 GitCode 做不到的地方，提供最接近的降级行为。
- 降级与差异必须显式暴露在 help、错误文案或结果提示中，避免“同名但误导”的伪兼容。

设计范围覆盖三阶段工作：

- **P0：** 修复最关键的伪兼容问题。
- **P1：** 补齐高频参数和命令能力。
- **P2：** 统一帮助文案与默认输出体验。

---

## 2. 总体架构

实现保持现有主路径不变：`commands/*.py` → `context/client` → `services/*` → GitCode API。

为避免兼容逻辑分散在各命令函数中，设计采用三层分工：

1. **命令语义层**  
   位置：`src/gitcode_cli/commands/*.py`  
   负责参数、默认值、交互入口、别名、无参默认行为，以及 `gh` 兼容语义。

2. **行为适配层**  
   建议新增：`src/gitcode_cli/cli_compat.py`  
   负责跨命令复用的兼容逻辑，例如 stdin/body-file/editor 输入装配、当前分支 PR 推断、默认 base branch 推断、多值参数归一化、统一降级提示。

3. **输出体验层**  
   位置：`src/gitcode_cli/formatters.py`  
   负责 list/view 默认文本渲染、`--json` 字段帮助元数据，以及统一的差异提示展示。

该设计遵循当前仓库的轻量结构，不引入不必要的新框架，也不把 CLI 兼容规则下沉到 service 层，除非确实需要新增 API 参数支持。

---

## 3. 文件落点与职责

### 3.1 现有文件

- **`src/gitcode_cli/commands/auth.py`**  
  处理 `auth login --with-token` 的 stdin 读取语义，以及相关 help/提示文案。

- **`src/gitcode_cli/commands/issue.py`**  
  承担 `issue` 侧参数兼容、别名、`status` 语义修正、`--web` 降级行为，以及默认文本输出接入。

- **`src/gitcode_cli/commands/pr.py`**  
  承担 `pr` 侧无参默认 PR 推断、`status` 语义修正、`--web`/`--fill`/`--dry-run` 等入口，以及 comment/review/merge 的高频参数补齐。

- **`src/gitcode_cli/formatters.py`**  
  提供统一的 list/view 文本渲染、`--json` 字段说明能力、限制提示文案渲染。

- **`src/gitcode_cli/services/issues.py` / `src/gitcode_cli/services/pulls.py`**  
  只做必要的小范围扩展；不承载 CLI 兼容策略本身。

- **`src/gitcode_cli/cli.py`**  
  如需扩展顶层帮助分区、示例入口或 formatting help 挂点，在这里做最小改动。

### 3.2 建议新增文件

- **`src/gitcode_cli/cli_compat.py`**  
  放置跨命令复用的兼容逻辑，包括：
  - 从 stdin / body-file / editor 获取正文
  - 当前分支关联 PR 推断
  - 默认 base branch 推断
  - repeatable flags / 多值参数归一化
  - `gh` 风格入口的降级策略判断与文案

### 3.3 测试文件

设计新增或扩展以下测试文件：

- `tests/commands/test_auth.py`
- `tests/commands/test_issue.py`
- `tests/commands/test_pr.py`
- `tests/test_formatters.py`
- `tests/test_cli_compat.py`

测试以单元测试与 CLI 集成测试为主，避免依赖真实 GitCode API。

---

## 4. 分阶段需求映射

### 4.1 P0：先消灭伪兼容

P0 只解决最容易误导 `gh` 用户的行为错位。

1. **`auth login --with-token`**  
   改为真正从 stdin 读取 token；如果未读到内容，再给出明确错误。

2. **`issue edit --remove-assignee` / `--remove-label`**  
   让已暴露参数真正生效；这是明确的实现缺陷。

3. **`issue create --web` / `pr create --web`**  
   不再采用“先创建再打开详情页”的误导性行为。  
   目标是提供最接近 GitCode Web 创建入口的降级实现；若 GitCode 无法直接支持，则必须在 help 或结果文案中明确说明。

4. **`issue status` / `pr status`**  
   调整为“与当前用户相关”的状态视图。若 GitCode API 无法完整复刻 `gh`，则提供明确的聚合降级语义，而不是继续简单列出当前仓库 open 列表。

5. **默认 base branch 推断**  
   移除硬编码 `master` 回退。优先使用仓库默认分支或更可靠的 git 推断；失败时显式要求用户传 `--base`。

### 4.2 P1：补齐高频参数与能力

P1 目标是让高频 issue / pr 工作流更接近 `gh`。

#### Issue

- `issue list`：补 `--web --milestone --mention`
- `issue view`：补 `--comments`
- `issue comment`：补 `--body-file --editor --web`
- `--label` 支持多值或 repeatable

#### PR

- `pr list`：补 `--assignee --draft --head --web`
- `pr view`：补 `--comments`，并支持无参默认当前分支关联 PR
- `pr comment`：补 `--body-file --editor --web`，并支持无参默认当前分支关联 PR
- `pr merge`：补 `--body --body-file --delete-branch --subject`
- `pr review`：补 `--body --comment --request-changes`
- `pr create`：补 `--fill --editor --dry-run --milestone`
- `--label --reviewer --assignee` 支持多值或 repeatable

补齐顺序优先围绕最常用链路：`list/view/create/comment/review/merge`。

### 4.3 P2：帮助与输出体验

P2 的目标是让 `gc` 不只是参数名像 `gh`，而是整体更接近 `gh` 的使用体验。

- help 中补充默认值、枚举值、示例
- `--json` 增加字段说明
- list / view 默认文本输出升级为更完整的结构化渲染
- 增加 formatting 帮助入口或等价说明
- 所有受 GitCode 限制的行为使用统一、稳定、可预期的提示文案

---

## 5. 数据流与降级策略

### 5.1 数据流

兼容逻辑按以下顺序介入：

1. **输入归一化**  
   统一处理 stdin / body-file / editor、多值参数、identifier、无参默认 PR 推断。

2. **能力判定**  
   判断用户请求是否能直接映射到 GitCode API，还是需要执行降级行为。

3. **服务调用**  
   可直接映射的继续走现有 `services`。

4. **输出适配**  
   用统一 formatter 渲染默认输出、字段说明和降级提示。

### 5.2 降级规则

为满足“尽量保留 `gh` 入口”的目标，统一采用以下规则：

- **能近似实现，就保留同名入口并降级。**  
  例如 `--web`，若不能复刻 GitHub Web 创建流，则打开最接近的 GitCode 创建页或相关页面，并在文案中说明。

- **不能合理映射，就显式报不支持。**  
  对 GitCode API 完全缺失、且无法构造合理替代体验的行为，不做假动作。

- **不允许 silent fallback 到误导行为。**  
  例如默认 base branch 不允许再悄悄回退到 `master`。

### 5.3 错误处理原则

- 只在系统边界做校验：CLI 输入、文件读取、git 状态、API 不支持。
- 错误文案必须告诉用户下一步，例如“请显式传 `--base`”。
- GitCode 限制导致的差异必须可见，不隐藏在实现里。
- 命令返回码和关键输出应通过测试固定下来，避免兼容性回退。

---

## 6. 测试策略与验收标准

### 6.1 单元测试

优先覆盖共享兼容逻辑与格式化逻辑。

**`tests/test_cli_compat.py`** 重点覆盖：
- stdin / body-file / editor 的优先级
- 默认 base branch 推断
- 当前分支关联 PR 推断
- repeatable flags / 多值参数归一化
- 降级策略选择

**`tests/test_formatters.py`** 重点覆盖：
- list/view 默认文本输出
- `--json` 字段过滤与字段说明
- 差异提示文案是否稳定

### 6.2 CLI 集成测试

使用 Click `CliRunner` 跑真实命令入口，mock service/client/git 边界。

优先覆盖：

- `auth login --with-token` 从 stdin 读取 token
- `issue edit --remove-*` 真正影响请求载荷
- `issue/pr status` 输出与当前用户相关的聚合结果
- `issue/pr create --web` 走新的降级或打开逻辑
- `pr view/comment/merge/review` 无参默认当前分支 PR
- `pr create --fill --dry-run`
- list/view 默认文本输出
- repeatable flags 多值输入行为

### 6.3 阶段验收标准

**P0 完成标准**
- 报告列出的 5 个关键伪兼容点全部修正
- 每个修正点都有对应 CLI 集成测试
- 不再存在“参数已声明但未生效”的行为

**P1 完成标准**
- 报告列出的高频参数和能力按设计补齐
- 每个新增参数都有 help 文案和至少一个测试
- 多值参数在 issue / pr 两侧语义一致

**P2 完成标准**
- list/view/help 输出升级完成
- `--json` 字段说明可发现
- GitCode 限制提示文案统一
- 关键帮助输出有断言测试或快照式保护

### 6.4 回归保护

每完成一个阶段，都应运行：

- 该阶段新增单元测试
- 全部 CLI 集成测试
- 至少一轮 issue / pr 主路径回归测试

---

## 7. 范围边界

本设计明确不追求以下目标：

- 不机械复刻 GitHub 专属且 GitCode 明显不具备的全部高级能力
- 不为当前仓库体量引入额外重量级抽象层
- 不把帮助和输出升级扩展成独立 UI 重构项目
- 不依赖真实 GitCode API 做验收主路径

设计原则是：**先保证语义可信，再补高频能力，最后提升体验。**

---

## 8. 结论

该设计将 `gc` 对齐 `gh` 的工作拆成清晰的三阶段路线：

- **P0：** 先修复误导性的伪兼容行为。
- **P1：** 补齐高频命令能力，使主要工作流接近 `gh`。
- **P2：** 统一帮助和默认输出，提升整体使用体验。

落地时以 `commands + cli_compat + formatters` 为核心结构，以单元测试和 CLI 集成测试作为验收手段，确保兼容性改动可验证、可回归、可逐步推进。
