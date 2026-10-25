#!/usr/bin/env python3
"""Build a release ZIP containing only the files required to run the skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path


RUNTIME_FILES = (
    "SKILL.md",
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "agents/openai.yaml",
    "config/codex-rules.default.json",
    "scripts/codex_optimizer.py",
    "references/01-structure-and-sessions.md",
    "references/02-cleanup-and-recovery.md",
    "references/03-project-migration.md",
    "references/04-knowledge-and-memory.md",
    "references/05-automation.md",
    "references/06-channels-and-tools.md",
    "references/07-configuration.md",
    "references/08-collaboration.md",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(source: Path, destination: Path) -> dict[str, object]:
    source = source.resolve()
    destination = destination.resolve()
    missing = [name for name in RUNTIME_FILES if not (source / name).is_file()]
    if missing:
        raise SystemExit("Missing runtime files: " + ", ".join(missing))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=destination.parent,
        prefix=destination.name + ".tmp-",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for name in RUNTIME_FILES:
                archive.write(
                    source / name,
                    arcname=f"codex-optimizer/{name}",
                )
        with zipfile.ZipFile(temporary) as archive:
            names = sorted(archive.namelist())
        expected = sorted(f"codex-optimizer/{name}" for name in RUNTIME_FILES)
        if names != expected:
            raise SystemExit("Release ZIP contents do not match runtime allowlist")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    size = destination.stat().st_size
    digest = sha256_file(destination)
    checksum = destination.with_name(destination.name + ".sha256")
    checksum.write_text(
        f"{digest}  {destination.name}\n",
        encoding="ascii",
    )
    return {
        "zip": str(destination),
        "sha256": digest,
        "bytes": size,
        "checksum": str(checksum),
        "files": list(RUNTIME_FILES),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "dist"
        / "codex-optimizer.skill.zip",
    )
    args = parser.parse_args()
    result = build(args.source, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
