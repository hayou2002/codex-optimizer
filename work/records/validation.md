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
- Release verification:
  - GitHub repository is public and uses `main` as the default branch.
  - `v0.1.0` is a published, non-draft, non-prerelease tag release.
  - Release API reported a 44,779-byte ZIP with matching SHA256.
  - Downloading the Release asset again reproduced the same digest.
  - All 15 installed runtime files match the project source.
  - Raw `README.md`, `LICENSE`, and `SKILL.md` are present on `main`.
- kdocs:
  - Installed skill remains at `C:\Users\Administrator\.codex\skills\kdocs`.
  - CLI 2.7.1 resolves an authenticated token from the system keychain.
  - The extracted 2.7.6 package has 399 files; all 399 match the installed
    skill by SHA256.
- `good-learning`:
  - Installed at `C:\Users\Administrator\.codex\skills\good-learning`.
  - Upstream `SKILL.md` SHA256:
    `935043c22aaa18a974baffc493522996f628d754375d8478261054ea1deee123`.
  - `quick_validate.py` passes.

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
- Hanako collaboration commit:
  `66f993e587b393725f8776f321d527e85e0f7494` on public `main`.
  The raw remote skill entry and collaboration reference match local source.
