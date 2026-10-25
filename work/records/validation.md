# Validation Record

- Date: 2026-10-26
- Automated tests: 30 passed; 1 symlink creation test skipped by Windows policy.
- Skill structure: validated with `skill-creator/scripts/quick_validate.py`.
- Release builder: runtime allowlist and extracted-package checks passed.
- Read-only diagnostic: completed with the installed skill at
  `C:\Users\Administrator\.codex\skills\codex-optimizer`.
  - Root: `C:\Users\Administrator\Desktop\OH-WorkSpace` (1.1 GB)
  - Registered projects: 0 (0 B) in the final scoped run
  - Codex home inventory: 1.1 GB, bounded metadata scan
  - Cleanup candidates: 0
  - Project promotion candidates: 0
  - Estimated safe reclaimable: 0 B
  - Dated task directories: 0
  - Warning: the report was truncated by the default metadata scan budget.
- Global rules marker: injected with a backup and without changing unrelated
  content.
- Shared root `AGENTS.md`: Hanako's marker block was retained; a separate
  Codex collaboration block was added idempotently.
- Installation: all 15 runtime files in
  `C:\Users\Administrator\.codex\skills\codex-optimizer` match the project
  source by SHA256.
- Release package size and digest are recorded in `release.md`.

## Shared collaboration follow-up

- Project copy destinations now map to `work/` and `outputs/` and have a
  dedicated regression test.
- Shared-root leases, handoffs, protocol creation, shared markers, and CLI
  routing have test coverage.
- The shared root is `C:\Users\Administrator\Desktop\OH-WorkSpace`.
- Codex owns `.optimize/codex-rules.json`; Hanako retains
  `.optimize/rules.json`. Private homes, sessions, credentials, databases,
  memories, skills, and Git checkouts remain separate.
- Hanako's installed `hana-optimizer` copy matches its current source for the
  updated `SKILL.md` and collaboration reference. Its pre-update skill was
  backed up under the shared recovery area.
