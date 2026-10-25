---
name: codex-optimizer
description: "优化大师（codex-optimizer）：治理 Codex 的默认工作根、日期任务目录、已添加项目、Codex 主目录、规则、技能、自动化和生成记忆。当用户说“优化大师”“初始化工作区”“优化工作区”“整理工作区”“扫描清理”“整理记忆”“建立项目”“把任务升级成项目”，或要清理可再生缓存、迁移旧日期任务、修复路径引用、压缩经验和处理过期状态时使用。"
metadata:
  short-description: 治理 Codex 工作区、项目、缓存、规则与记忆
---

# Codex 优化大师

把 Codex 的清理与整理做成可回滚的文件事务：默认根承接普通会话，`projects/` 承接长期工作，日期目录保留历史，Codex 主目录中的认证和运行状态受到严格保护。

## 动作菜单

用户只说“优化大师”或要求工作区治理但未指定动作时，展示：

```text
Codex 优化大师（codex-optimizer）—— 选一个动作

  01  初始化   建混合骨架 / 合并默认规则 / 注入工作约定 / 只读诊断
  02  优化     四板块扫描 / 风险分级 / 受控清理 / 项目升级
  03  整理     文件归位 / 引用修复 / 知识整理 / 日期目录收口
  ─────────────────────────────────────────────────────────
  00  功能     查看能做什么
```

用户回复编号或直接说动作名后执行对应动作。完成动作后回到菜单；只有用户明确要求连续执行时才串联下一步。`01` 完成后自动做一次只读诊断。

## 选择执行深度

沿用汉娜版的完整治理主线，让每步颗粒度与风险相称：

```text
识别范围 -> 分类 -> 简方案 -> 用户确认 -> 执行 -> 阶段验证 -> 一条记录
```

简单项目可把前三步合并为一次现场核对；危险动作必须在执行前展示可读方案。

- **快速归位**：用户已明确源目录或 Git URL 与项目名时，直接 `git clone` 或复制到 `projects/<slug>/`；仅补缺失的 `README.md` 和 `source.md`，读取一次目标结果并结束。目标 1–3 分钟。工具：

```powershell
python scripts/codex_optimizer.py quick-project --root "<root>" --source "<dir>" --slug "<slug>"
python scripts/codex_optimizer.py quick-project --root "<root>" --git-url "<url>" --slug "<slug>"
```

  只有用户明确要求搬走源目录时加 `--move`；默认保留源目录。目标已存在就停止，不覆盖。
- **协作编辑**：共享项目已有活跃租约、两个 Agent 将同时写入、要接管过期租约或实际移交时，才运行 `collaborate status/claim/handoff/release`。单 Agent 的短任务不创建合作事件。
- **安全清理**：删除、覆盖、跨盘移动、处理凭据/数据库/运行态，或来源不唯一时，使用完整的扫描、计划、风险分级和回滚事务；用大小、修改时间即可判断来源是否在计划后变化。只有跨盘复制后删源、文本冲突和发布包完整性才计算 SHA256。

快速归位只做一次目标目录核验；不写双份检查点，不运行全工作区 `diagnose`，也不为不删除来源的普通复制另做备份。
- **旧批次归档**：来源已在恢复区、原 batch 自带 manifest、目标只是换一个恢复区位置时，用
  `archive_batch` 一次完成预检、移动、索引和验证。不要临时写脚本、`py_compile`
  或给每个 batch 生成第二套事务；坏路径 batch 记入 skipped，其余继续。保留原
  manifest 就可恢复，不逐行重建或比对目录内容：

```powershell
python scripts/codex_optimizer.py archive-batch --root "<root>" --source-dir "<batch>"
```

`archive-batch` 从恢复区顶层选取批次，所以 `--source-dir` 应传恢复区根目录；
用户点名批次时重复传入 `--name "<批次>"`。

## 四个治理板块

| 板块 | 范围 | 默认处理 |
|---|---|---|
| 默认根 | `<root>`、日期目录、`projects/`、`storage/`、`inbox/`、`_temp/` | 文件治理、项目升级、回收和引用修复 |
| 已添加项目 | Codex 原生项目列表返回的工作根 | 与默认根共享规则；不得自行假设项目列表 |
| Codex 主目录 | `$CODEX_HOME`；默认 `~/.codex` | 审计元数据；只回收有重建证据的缓存，保护认证、会话、数据库、插件和技能正文 |
| 知识与规则 | `AGENTS.md`、`memories/`、skills、自动化 | 原生控制面优先；低风险严格项可自动，其他先审阅 |

先按需阅读：

- [结构与会话](references/01-structure-and-sessions.md)
- [清理与回收](references/02-cleanup-and-recovery.md)
- [项目迁移](references/03-project-migration.md)
- [知识与记忆](references/04-knowledge-and-memory.md)
- [自动化](references/05-automation.md)
- [通道与工具](references/06-channels-and-tools.md)
- [配置参考](references/07-configuration.md)
- [多 Agent 协作](references/08-collaboration.md)

## 环境对位

执行前必须读取现场：

1. 解析真实路径，核对默认根存在且不是盘符根、用户主目录或 `$CODEX_HOME` 本体。
2. 用 Codex 原生项目列表获取已添加项目，并作为 `--project-root` 传给诊断脚本。
3. 读取 `<root>/.optimize/codex-rules.json`；缺失字段可由 skill 默认值补齐，现值不覆盖。
4. 查看日期目录、项目文件、当前会话实际读写路径；文档里的示例路径不是现场事实。
5. 发现现场结构与默认值不同且无法安全判断时，只做只读报告。

路径规则：现场配置 > skill 默认规则 > 文档示例。只有现场实测能证明当前状态。

`OH-WorkSpace` 是 Hanako 与 Codex 共用的治理根。并发写作、接管租约或实际交接前读取 `<root>/.optimize/COLLABORATION.md`；单 Agent 的短任务不进租约流程。不要假定另一个 Agent 共享 cwd、打开的文件、环境变量或会话。

## 01 初始化

1. 用户提供自定义根时以该根为准；否则使用 `~/Desktop/OH-WorkSpace`。
2. 幂等创建混合骨架：

```text
projects/
storage/docs/
storage/backups/
storage/tools/
inbox/
_temp/screenshots/
_temp/data/
_temp/scratch/
_temp/exports/
_temp/jobs/
_temp/checkpoints/
_temp/trash/
_temp/plans/
.optimize/
```

3. 将 `config/codex-rules.default.json` 合并为 `<root>/.optimize/codex-rules.json`。只补缺失字段，不覆盖已有值；与 Hanako 的 `.optimize/rules.json` 完全隔离。
4. 创建或补齐 `<root>/.optimize/COLLABORATION.md`，写入跨 Agent 共享协议；保留 `rules.json` 原样。
5. 准备 `AGENTS.md` 标记块。写入全局 `~/.codex/AGENTS.md` 前先把最终块展示给用户；本项目已授权写入。只原位替换以下标记之间的内容。普通注入由原子写入和可用 `agents-preview` 复核支持，不再另建同内容备份：

```html
<!-- codex-optimizer:begin -->
<!-- codex-optimizer:end -->
```

标记块保持简短，只写默认根、项目主编辑位、日期目录历史规则、临时落点、规则文件和确认边界。详细阈值留在配置和参考中。
6. 不自动创建 Scheduled task。只展示 [自动化模板](references/05-automation.md) 中的每日和每周模板。
7. 初始化完成后运行一次只读诊断，展示摘要与候选项目；不清理、不迁移。

## 02 优化

严格使用：

```text
扫描 -> 分类 -> 方案 -> 风险分级 -> 确认 -> 执行 -> 一次验证
```

- `diagnose` 默认零写入。需要 CLI 已生成的报告或计划时显式加 `--json` 或 `--plan`；不要用 `--json <路径>`。
- `apply` 默认只展示计划。批量执行用一次事务；低风险缓存与临时项确认后可用
  `--execute`；项目复制、引用改写、唯一源处理和目录软删属于高风险批次，执行前展示动作摘要。
- 同一目标不要连续运行 `diagnose`、`apply --help`、临时脚本编译和多轮目录统计。
  计划已经保证边界与元数据时，执行后只核对状态、数量、目标存在性；manifest、
  transaction 和 CLI 输出已经覆盖的内容不重复写成第二份报告。
- 同一路径只保留当前可用版本。优先采用项目主版本；日期材料是否“在用”取自关联会话的实际文件访问和用户明确声明，不以 mtime 单独作因果判断。
- 只有存在 lockfile、构建清单或显式可再生规则等重建证据时，缓存才可自动回收。
- 搜索默认根、当前项目、`AGENTS.md`、skills、rules 和自动化中的关键引用；命中引用的文件不自动清理。
- Codex 主目录保护清单见 [清理与回收](references/02-cleanup-and-recovery.md)。

## 03 整理

文件与项目：

1. 用户明确说“作为项目”或指定 `projects/<slug>` 时，单次任务即可建立项目。
2. 非显式任务使用组合身份：项目名、README/AGENTS、git remote、内容 hash、关联会话和跨日期出现次数。默认跨日期或多次出现且综合评分达到 6 分后升级。
3. 项目目录使用语义英文 kebab-case；冲突追加 `-2`、`-3`。
4. 显式简单归位优先使用 `quick-project`，补齐 `README.md`、`source.md` 和简短项目 `AGENTS.md`；不预建空的 `work/`、`outputs/`，有文件时再创建。
5. 项目复制当前会话实际使用、产出的文档、源代码、脚本、配置模板、交付物和必要资产；排除缓存、环境、日志、凭据、数据库和临时件。不删除来源的普通复制保留来源即可，不另做逐文件 SHA256 或第二份备份；只有跨盘后删源、同名内容冲突或发布完整性才强校验。
6. 同名目标已存在且内容不同则不覆盖：进入项目的 `work/conflicts/<source-slug>/`，来源目录保留。
7. 项目成为唯一主编辑位。后续同项目工作直接进 `projects`，日期目录成为历史快照，不回写。
8. 已完整迁移的 `YYYY-MM-DD/<任务>` 目录，只有同时满足“无未迁移/唯一内容、无关键引用依赖、回收副本可恢复”才能整目录移入回收区。迁移后同轮即可软删，14 天恢复窗口仍保留。

知识：

- 原生 `/memories` 和设置优先。
- 严格低风险的完全重复项合并、格式修复可自动执行，并在事务里保留原文或一条恢复记录；压缩、语义合并、冲突处理、删除先展示差异并确认。
- 现场可验证事实优先。无法确定时保留双方并标记待裁决。
- 记忆文件可能与后台生成重写；下次运行发现 hash 变化时报告，不静默覆盖。

每次实际改动只写一条简明记录：操作、结果、恢复路径。快速归位由 `source.md`
承担，安全清理由批次 transaction 加一条检查点承担，旧批次归档由索引承担，
实际协作由交接事件承担。不要为同一动作再写全局报告、项目记录和复核清单。
细节见 [项目迁移](references/03-project-migration.md) 和
[知识与记忆](references/04-knowledge-and-memory.md)。

## CLI

安装后的脚本：

```powershell
python "$env:USERPROFILE\.codex\skills\codex-optimizer\scripts\codex_optimizer.py" diagnose --root "$env:USERPROFILE\Desktop\OH-WorkSpace"
```

日常子命令：

- `quick-project`：显式来源的快速复制、移动或 Git 克隆；无需清理级计划或第二份备份。
- `archive-batch`：将已带 manifest 的旧恢复批次直接软归档；坏路径批次跳过，成功后
  只输出批次、数量、索引路径和一条恢复命令。
- `diagnose`：只读扫描；可生成 JSON 报告或计划。
- `apply`：默认 dry-run；验证计划完整性、30 分钟有效期和相应的现场元数据后用 `--execute` 执行。
- `rollback`：按批次恢复回收文件、项目复制和文本改写；路径冲突时停止且不覆盖。
- `purge`：到期后只清空已有完整检查点的低风险回收批次；高风险继续保留。
- `init`：幂等补齐治理骨架和规则。

初始化与规则入口另有 `agents-preview`、`agents-inject`，只操作受标记包围的全局规则块；协作入口为 `collaborate`，语法是 `collaborate --root <root> status --target <path>`，不是 `collaborate status --root ...`。

默认诊断是限量元数据扫描；输出中的 `truncated: true` 表示仅完成了预算内统计。
需要完整元数据审计时显式加 `--deep`。这不会扩大写入或自动清理权限。

计划包含动作、源/目标、大小、mtime、风险、原因和引用保护。普通复制与同盘暂存不逐文件计算 SHA256；跨盘删源、文本冲突和发布包才强校验。所有批处理写事务日志，失败自动回滚已执行步骤。

## 安全底线

- 永不因年龄或名称直接删除；必须证明可再生且没有关键引用。
- 永不自动清理认证、配置、会话、历史会话、记忆、数据库/WAL、插件、skills、rules、MCP 凭据、密钥、`.env`、唯一源或运行态数据。
- 删除先进入 `_temp/trash/<batch>` 并写完整 JSONL manifest。14 天到期只自动清空安全类；高风险项继续保留。
- 跨盘复制先校验 SHA256 再移除源；默认不跟随符号链接、junction 或 reparse point，`--follow-links` 也不得跨治理边界。
- 不修改或删除原 Hanako 安装 `~/.hanako/skills/hana-optimizer`。
- 共享项目仅按租约协作；另一 Agent 仍持有有效租约时停止写入并报告，不把过期时间当作删除许可。

