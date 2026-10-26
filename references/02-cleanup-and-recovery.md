# 清理与回收

本流程只用于删除、覆盖、跨盘移动、敏感数据或来源不唯一的场景。用户给出明确目录或 Git URL 的普通项目归位应使用 `quick-project`，不要先生成清理计划。

旧恢复批次仅换位置、原批次已带可读 manifest 且源目录完整时，直接使用
`archive-batch`。它先整体预检，再逐批移动；路径、BOM 或 schema 不合格的批次
进入 `skipped`，不会阻止其它批次。不要把这类同盘软归档升级为临时脚本、字节编译、
逐行 manifest 重建或多轮状态审计。

## 分类

每个对象按两种属性分类：

- **再生性**：可再生、有证据可再生、不可再生、未知。
- **引用状态**：已引用、未引用、无法检查。

只有“有证据可再生、未引用、路径在允许范围”的对象能进入低风险自动回收。名称含 `cache`、`tmp` 或 `build` 不足以证明可再生。

可再生证据包括 lockfile、构建清单、已确认的包管理器缓存位置、显式登记的可再生规则，以及能从现有源完整重建的构建产物。

## 永不自动清理

- `auth.json`、认证凭据和 MCP OAuth 状态。
- `config.toml`、profile 和机器配置。
- `sessions/`、`archived_sessions/`、thread history、session index。
- `memories/` 和生成记忆数据库。
- `*.sqlite`、`*.db`、`*.sqlite-wal`、`*.sqlite-shm` 及其它运行数据库。
- `plugins/`、`skills/`、`rules/` 的安装正文。
- `.env`、私钥、证书私钥、secrets。
- 唯一源、运行态 world/data、Git working tree 内容和 `.git`。
- 被 `AGENTS.md`、rules、自动化和关键项目入口引用的文件。

Codex 主目录允许回收的对象严格限于明确可再生的缓存、临时文件和符合重建证据的旧产物。日志只做有限元数据/模式审计；旧日志只有在有配置支持能被 Codex 再生成且未引用时才可进入回收。

## 引用保护

清理前检索：

- 默认根中的 `AGENTS.md`、README 和项目入口。
- 当前项目文本文件。
- `.optimize/codex-rules.json`。
- 已安装 skills 的说明和自动化模板。
- 当前项目列表中的根。

二进制、凭据、会话和数据库只取元数据，不读取内容。引用索引仅用于保护，不保证所有可能的外部引用都能发现。

## 计划

`diagnose --plan` 生成 `_temp/plans` 下的 JSON：

- schemaVersion
- createdAt / expiresAt，默认 30 分钟
- root 与 projectRoots
- actions：move、trash、copy_project、rewrite_text、purge_trash
- 每项 source、destination、size、mtime、risk、reason、referenceHits
- planHash

`apply` 默认 dry-run。`--execute` 前重新校验根边界、文件存在、计划、大小和修改时间。现场变化则拒绝执行。计划阶段不预计算执行时不会使用的 SHA256。普通复制和同盘暂存不逐文件计算 SHA256；跨盘复制后删源、文本冲突和发布包完整性才强校验。

## 事务与回收区

删除 = 移入 `_temp/trash/<batch>/`，不是当场硬删。每批有：

```text
<batch>/
├── manifest.jsonl
├── items/
└── transaction.json
```

manifest 每行至少记录：

- batchId、timestamp
- from、to
- size、mtime；需要强校验的动作再记录 sha256
- category、risk、reason
- sourceRoot、rule

14 天后只自动硬删 risk=safe 且未见引用变化的条目；高风险和未知项继续保留。永久清理仍保留批次摘要和删除记录。

## 跨盘和失败

- 同盘：先放同目录临时名，再原子重命名。
- 跨盘：复制到目标临时路径，校验 SHA256，再替换目标并移除源。
- 批量执行写 transaction log。
- 任一步失败时自动逆序恢复已完成步骤；无法恢复时停止并报告冲突，不继续扩大影响。

## 空目录

只清理明确可再生的缓存空目录。项目、`storage`、`inbox`、`_temp` 结构格和日期目录本身即使为空也保留。

## 结果验证

逐项确认源状态、目标状态和引用状态；比较预估与实际释放空间。偏差超过 20% 时记录，不自动重新删除。

同一执行结果不要反复验证。一次 `archive-batch` 或 `apply` 的返回值、batch
manifest 和 `transaction.json` 已证明的动作，不再单独重扫全部目录、重算大小或
修补历史失败事务。正常结果只核对批次状态、动作数、源/目标存在性和一条恢复入口；
存在冲突或写失败时才定向复查。

