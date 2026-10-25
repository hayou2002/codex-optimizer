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
  Codex and Hanako. Claim a lease only when concurrency exists or a handoff
  occurs; ordinary single-Agent edits need no claim.
- Use `quick-project` for explicit local or Git project adoption. Keep the full
  plan and transaction for cleanup; use metadata checks for ordinary copies,
  and reserve SHA256 plus extra recovery for destructive or conflict paths.
- `.optimize/codex-rules.json` belongs to Codex Optimizer.
- Hanako's `.optimize/rules.json` remains isolated.
- Each Agent keeps its own Git checkout, cwd, sessions, credentials, and
  private home. Never infer or edit those through the shared project.
- Do not copy credentials, session databases, runtime state, or caches here.
