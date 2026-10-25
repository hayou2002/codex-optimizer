# Project Instructions

## Entry points

- Start with `SKILL.md`.
- Use `scripts/codex_optimizer.py` for diagnose, plan, apply, rollback, and
  recovery operations.
- Keep long-form operating detail in `references/`.

## Validation

```powershell
python -m unittest discover -s tests -v
$env:PYTHONUTF8 = "1"
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .
```

Do not treat a default bounded diagnostic as a complete inventory. Use
`--deep` only for an intentional deeper metadata audit.

## Project boundaries

- The installed copy under `C:\Users\Administrator\.codex\skills\codex-optimizer`
  is generated from this directory.
- The source lives in the shared `OH-WorkSpace/projects` directory used by both
  Codex and Hanako. Read `.optimize/COLLABORATION.md` before editing shared
  files; claim a lease for concurrent work and record handoffs plus checkpoints.
- `.optimize/codex-rules.json` belongs to Codex Optimizer.
- Hanako's `.optimize/rules.json` remains isolated.
- Each Agent keeps its own Git checkout, cwd, sessions, credentials, and
  private home. Never infer or edit those through the shared project.
- Do not copy credentials, session databases, runtime state, or caches here.
