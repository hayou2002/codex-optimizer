# Date Task Migration

## Source

- Original source:
  `C:\Users\Administrator\Documents\Codex\2026-10-25\https-wpsai-wpscdn-cn-skillhub-pro`
- Files: 402
- Bytes: 5,584,281
- Source session: `01a172fd-f417-7230-aa5f-f8a1938d4ce1`

## Primary locations

- Codex Optimizer source:
  `C:\Users\Administrator\Desktop\OH-WorkSpace\projects\codex-optimizer`
- Published repository:
  `https://github.com/hayou2002/codex-optimizer`
- Source material archive:
  `C:\Users\Administrator\Desktop\OH-WorkSpace\storage\docs\codex-manual\`
- WPS Kdocs package:
  `C:\Users\Administrator\Desktop\OH-WorkSpace\storage\tools\kdocs-2.7.6\`
- Installed Kdocs skill:
  `C:\Users\Administrator\.codex\skills\kdocs`

## Verification

- Project source is committed and pushed.
- Codex manual files: 2 of 2 match archived SHA256 values.
- Kdocs expanded files: 399 of 399 match the installed skill by SHA256.
- Kdocs package SHA256:
  `a2ac3fbe58e3995e11cd1c56b63ec2a10b31bea2a6af06ce78ff235c51ea63f3`
- Configurable text references to the source date path: 0.
- Reparse points in the source date directory: 0.
- Recovery copy files: 402 of 402 match the source by SHA256.

## Soft-delete batch

- Batch:
  `C:\Users\Administrator\Desktop\OH-WorkSpace\_temp\trash\date-task-https-wpsai-wpscdn-cn-skillhub-pro-20261026T183200`
- Manifest: `manifest.jsonl`
- Transaction record: `transaction.json`
- Risk: high
- Automatic purge: disabled
- Retention: 14 days, after which high-risk content remains until reviewed

The original date task is retained. Codex holds it as the current session's
working directory, so native directory relocation failed with a file-in-use
error. The recovery payload is complete and verified.

## Relocation and rollback

After this Codex session closes and the original directory is no longer in use,
move it atomically into the batch's `original` directory:

```powershell
$source = 'C:\Users\Administrator\Documents\Codex\2026-10-25\https-wpsai-wpscdn-cn-skillhub-pro'
$batch = 'C:\Users\Administrator\Desktop\OH-WorkSpace\_temp\trash\date-task-https-wpsai-wpscdn-cn-skillhub-pro-20261026T183200'
[System.IO.Directory]::Move($source, (Join-Path $batch 'original'))
```

To roll back after relocation, move `original` back to the source path when
that path is empty and no process has the source directory open. To recover
from the copies, use `manifest.jsonl` to recreate each source path and verify
each SHA256 before treating the rollback as complete.
