# 配置

## 文件

现场配置：`<root>/.optimize/codex-rules.json`

默认模板：`config/codex-rules.default.json`

初始化只补缺失字段，不覆盖现场值。修改规则时展示差异并经用户确认。Hanako 的 `.optimize/rules.json` 不读取、不覆盖。

## 字段

### schemaVersion

配置格式版本，目前为 1。

### root

默认治理根。应是绝对目录；不能是盘符根、用户主目录或 `$CODEX_HOME` 本体。

### projects

- `discovery`: 必须为 `native-project-list`。
- `managedRoots`: 上次运行观察到的项目路径；运行时由原生列表刷新。
- `slugStyle`: `english-kebab`。
- `scoreThreshold`: 默认 6。
- `crossDateThreshold`: 默认 2。
- `collaboration.enabled`: 开启跨 Agent 共享协议。
- `collaboration.protocol`: 默认指向 `.optimize/COLLABORATION.md`。
- `collaboration.coordinationDir`: 默认 `_temp/collaboration`。
- `collaboration.leaseMinutes`: 默认 30；范围 1–1440。
- `collaboration.sharedAgents`: 默认 `codex`、`hanako`。

### skeleton

默认目录列表。只补缺失，不删除已有结构。

### operation

- `planTtlMinutes`: 30
- `maxItemsPerBatch`: 100
- `maxBytesPerBatch`: 524288000
- `oversizedMB`: 50
- `checkpointKeep`: 20
- `trashRetentionDays`: 14
- `deepScanDefault`: false

### safety

- `protectCodexState`: true
- `followLinks`: false
- `automaticHighRisk`: false
- `hashBeforeMove`: false；普通同盘移动依赖原子重命名，跨盘后删源另行计算 SHA256
- `requireRegenerableEvidence`: true

### projectPromotion

- 权重与阈值
- `requireCrossDateForImplicit`: true
- `explicitProjectBypassesScore`: true
- `copyInUseOnly`: true
- `largeAssetPolicy`: `copy`

### restoration

- `trashDir`: `_temp/trash`
- `checkpointsDir`: `_temp/checkpoints`
- `plansDir`: `_temp/plans`
- `exportsDir`: `_temp/exports`

### textRewrite

- `enabled`: true
- `extensions`: text extension allowlist
- `protectedNames`: auth、配置、会话、数据库、凭据
- `maxBytes`: 文本文件的读取上限

## 根切换

1. 先创建新默认根混合骨架。
2. 检查新旧根路径冲突、同路径文件和空间。
3. 生成迁移计划，复制校验后软删旧内容。
4. 新规则写入新根的 `.optimize/codex-rules.json`。
5. 任何冲突都停止该批次并保留旧根。

配置格式不合法时拒绝执行写入动作，只保留只读诊断。缺失字段使用内嵌默认值，不静默重写现场配置。

