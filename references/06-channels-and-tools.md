# 通道与工具

| 需求 | 首选通道 |
|---|---|
| 已添加 Codex 项目 | 原生 `list_projects` / Codex 项目列表 |
| Scheduled task | 原生 automation 工具/界面 |
| Codex memories 开关与使用 | `/memories`、Settings > Personalization |
| Skills 安装、启用、停用 | `$CODEX_HOME/skills` 与配置中原生 skill 控制 |
| 插件安装与管理 | 原生插件管理工具/界面 |
| 文件扫描、计划、事务 | `scripts/codex_optimizer.py` |
| 文件内容读取 | 普通文件工具；认证和数据库只取元数据 |
| GitHub 发布 | `gh` 或已连接的 GitHub 能力 |
| 跨 Agent 共享根协作 | `.optimize/COLLABORATION.md` + `collaborate` 子命令 |

## 文件事务

- 计划生成后，用 CLI 验证和执行。
- 涉及已添加项目时，把项目根显式传入。
- 修改前核对路径真实化结果与 root/project 边界。
- 默认不跟随链接。
- 项目冲突以 hash 判断。

## 不可越过的通道

- 不通过手工删除插件目录实现卸载。
- 不直接改 Codex 会话数据库或 SQLite 状态。
- 不把认证 token 输出到对话、日志或报告。
- 不用 shell 字符串拼接执行用户路径；参数以独立 argv 传递。
- 不用 `git reset --hard`、强制 push 或强删回收区绕过事务。

## 交互

- 失败后先说明未完成范围，再恢复本批次。
- 用户只想查看时保持 diagnose 零写入。
- 高风险动作展示计划摘要；低风险动作在执行后仍报告批次。

