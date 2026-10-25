# Codex Optimizer 项目说明

这里是项目源和发布内容的唯一主编辑位置。

## 当前阶段

- 状态：`v0.1.0` 发布候选。
- Codex 安装副本从本目录复制生成。
- 默认治理根：`C:\Users\Administrator\Documents\Codex`。
- 规则：`.optimize/codex-rules.json`，与 Hanako 的 `rules.json` 隔离。

## 本地入口

- 源码：`C:\Users\Administrator\Documents\Codex\projects\codex-optimizer`
- 安装：`C:\Users\Administrator\.codex\skills\codex-optimizer`
- 入口：`SKILL.md`
- 执行器：`scripts/codex_optimizer.py`
- 测试：`tests/`
- 发布包：`dist/codex-optimizer.skill.zip`

## 验证

```powershell
python -m unittest discover -s tests -v
$env:PYTHONUTF8 = "1"
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .
```
