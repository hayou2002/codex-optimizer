# 多 Agent 共享工作区协作

## 适用范围

Hanako 与 Codex 共享同一个治理根 `OH-WorkSpace`。共享对象包括 `projects/`、`storage/`、`inbox/`、有寿命的 `_temp/` 文件以及根 `AGENTS.md`。两个 Agent 的安装、认证、会话、数据库、私密记忆、skills、automations 和 `.optimize` 规则文件仍分别管理。

同一工作区不等于同一进程，也不等于同一个 Git checkout。一个 Agent 不能假定另一个 Agent 正在运行、会读取自己的 cwd，或会自动看到未落盘的消息。

## 共享协议

协议正文位于 `<root>/.optimize/COLLABORATION.md`。运行协调状态位于：

```text
<root>/_temp/collaboration/
├── leases/
└── events.jsonl
```

租约只覆盖一个具体项目或共享文件，不锁整个根。默认 30 分钟过期；过期只表示可以重新指派，不代表原工作的文件可删除。

## 编辑流程

1. 读取根 `AGENTS.md`、`.optimize/COLLABORATION.md`、项目的 `README.md`、`source.md` 和项目 `AGENTS.md`。
2. 把目标解析成共享根内的绝对路径，并确认它与另一个 Agent 的私有状态不在同一个路径。
3. 用 `collaborate status` 查看租约。空闲则 `claim`，写明 Agent、目的和会话 ID。
4. 每次就地修改前核对文件 hash 或 Git 状态；发现租约期间内容变化时停止写入，记录差异。
5. 工作文件写 `work/`，交付物写 `outputs/`，来源与排除项写 `source.md`。
6. 运行验证并写检查点，覆盖改了什么、为什么、结果、恢复路径。
7. 通过 `handoff` 记录交接，再 `release` 租约。租约不能替代检查点。

## 并发与冲突

- 不同项目可以并行，不要求全根串行。
- 同一项目的不同文件在计划中明确互不依赖时可以减少锁的范围；默认先锁项目根，再精确到文件。
- 同名不同内容不覆盖。保留两份，使用 hash 判断，并把冲突摘要写入项目 `work/checkpoints/`。
- 文本合并必须验证编码、引用和验证命令；二进制冲突交给用户裁决。
- 另一 Agent 的 cwd、session、私有配置、凭据和数据库不纳入共享复制。
- Git 操作分别在自己的 checkout 中执行。强制推送、`reset --hard` 和跨 checkout 删除不作为协作捷径。

## 松锁与故障

- 租约过期后，新 Agent 可以 `claim --takeover`；先核对工作区 hash 和最后一个检查点。
- 原 Agent 恢复运行时先查状态；如果其他人已持有租约，停止写入并展示变更。
- 发现租约文件损坏时，不使用它阻塞清理或删除；只读报告，并保留文件供人工检查。
- 租约存在期间不自动回收目标、父项目或其唯一源。

## 共享项目模板

共享项目至少保留：

```text
projects/<slug>/
├── README.md
├── source.md
├── AGENTS.md
├── work/
│   └── checkpoints/
└── outputs/
```

项目级 `AGENTS.md` 写明共享根、入口、验证命令、租约位置、交接方式和本项目不能改动的私有路径。不要把 Hanako 或 Codex 的主目录误写成项目子目录。

## CLI

```powershell
$cli = "$env:USERPROFILE\.codex\skills\codex-optimizer\scripts\codex_optimizer.py"
python $cli collaborate status --root "$env:USERPROFILE\Desktop\OH-WorkSpace" --target "<project>"
python $cli collaborate claim --root "$env:USERPROFILE\Desktop\OH-WorkSpace" --target "<project>" --agent codex --purpose "implement feature" --session-id "<id>"
python $cli collaborate handoff --root "$env:USERPROFILE\Desktop\OH-WorkSpace" --target "<project>" --agent codex --next-agent hanako --summary "tests pass; source map updated"
python $cli collaborate release --root "$env:USERPROFILE\Desktop\OH-WorkSpace" --target "<project>" --agent codex
```

`handoff` 只追加事件，不替用户发送消息。

## 与治理的关系

- 清理前检查活跃租约和最后的检查点。租约覆盖的共享项目不进入自动回收。
- 项目迁移时保留 `source.md`、hash、排除项和迁移状态，不因另一个 Agent 曾看过目录而视为完成迁移。
- 检查点写入共享根 `_temp/checkpoints/`；项目内部另写 `work/checkpoints/`。
- 多根失败隔离：一个项目失败不回滚无关项目；同批次内部仍按事务约束执行。
