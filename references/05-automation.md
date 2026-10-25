# 自动化

初始化只提供模板，不自动创建 Codex Scheduled task。创建、修改或删除任务必须通过当前会话中的原生自动化工具/界面。

## 每日只读巡检

建议每天运行一次，保持无写入：

```text
Use $codex-optimizer for a daily read-only Codex workspace check.

The governance root is <ROOT>. Get currently added Codex projects from the native
project list and pass them explicitly to scripts/codex_optimizer.py diagnose.

Scan the default root, date directories, managed projects, and the protected
CODEX_HOME categories. Read metadata only for secrets and databases. Report:
1. total size by governance zone,
2. stale temporary or clearly regenerable cache candidates,
3. project promotion candidates and their evidence,
4. broken references,
5. memory/rule drift and conflicts,
6. estimated safe reclaimable space.

Do not write reports, move files, delete anything, alter memory, edit AGENTS.md,
or create projects. If nothing needs attention, return one quiet summary.
```

## 每周整理

建议每周一次；是否实际执行仍由用户选择动作：

```text
Use $codex-optimizer to perform the weekly tidy workflow for <ROOT>.

Get the added Codex projects from the native project list. Diagnose first and
generate a plan. Apply only low-risk evidence-backed cache cleanup. Before
high-risk project migration, reference rewrites, unique-source handling, memory
deletion, or removal of a date directory, show the concrete proposed actions.

Use the current and related session file-access evidence to decide which files
are actually in use. Existing projects are the primary edit location. Validate
hashes and references before moving date directories to trash.

Write the global and affected project checkpoints. Keep checkpoints to the latest
20. Report reclaimed space, project changes, conflicts, retained items, and the
rollback batch IDs.
```

## Prompt 约束

- 使用绝对路径，但让 runtime 重新核对根和项目列表。
- 明确 schema、计划 TTL 和执行权限。
- prompt 自包含；不能依赖某个旧会话仍存在。
- 不自动再次创建定时任务。
- 初始化提示一次即可，避免每次运行都创建重复任务。

## 失败处理

- 任务 cwd 不符：按显式绝对根继续或只报告，不猜测旧位置。
- 项目路径缺失：停止该根，报告登记失效。
- 扫描超时：缩小为元数据浅扫，记录未覆盖范围。
- 计划失效或 hash 改变：重新诊断，不执行旧计划。
- 执行中断：用批次 manifest 和 transaction log 恢复。

