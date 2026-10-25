# Changelog

## 0.3.0 - 2026-10-26

- Add `archive-batch` for same-volume archival of legacy recovery batches that
  already carry manifests.
- Skip invalid legacy batches instead of restarting or hand-repairing the whole
  archive operation.
- Collapse repeated diagnostics, temporary helper compilation, transaction
  repair, and duplicate verification into one execution with one result check.

## 0.2.0 - 2026-10-26

- Add `quick-project` for explicit local and Git project adoption.
- Keep the full plan, hash, and rollback transaction for destructive or risky operations.
- Keep a concise project `AGENTS.md` while skipping empty `work/`/`outputs/` trees.
- Require collaboration leases only for actual overlap or handoffs.
- Use size and mtime validation for copies and staging; reserve SHA256 and extra backups for destructive, conflict, or release paths.
- Correct collaboration and diagnostic CLI examples.

## 0.1.0 - 2026-10-26

- First Codex-native release.
- Adds the initialization, optimize, tidy, and overview workflows.
- Adds standard-library diagnostics and rollbackable apply/rollback transactions.
- Adds project promotion, reference repair, cache recovery, memory curation, and automation templates.
- Adds Codex and Hanako shared-root leases, handoffs, conflict rules, and checkpoints.
- Establishes isolation from the original Hanako optimizer.

