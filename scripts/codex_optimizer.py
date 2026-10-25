#!/usr/bin/env python3
"""Read-only diagnostics and rollbackable Codex workspace maintenance."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
DEFAULT_ROOT = Path.home() / "Desktop" / "OH-WorkSpace"
DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
PLAN_TTL_MINUTES = 30
CHECKPOINT_KEEP = 20
TRASH_RETENTION_DAYS = 14
OVERSIZED_BYTES = 50 * 1024 * 1024
MAX_ITEMS_PER_BATCH = 100
MAX_BYTES_PER_BATCH = 500 * 1024 * 1024
DEFAULT_LEASE_MINUTES = 30
PROJECT_WORK_NAMES = {
    "work", "docs", "src", "source", "scripts", "tests", "test",
    "config", "configs", "assets", "examples", "notes",
}
PROJECT_OUTPUT_NAMES = {
    "outputs", "output", "dist", "release", "releases",
}
TEXT_EXTENSIONS = {
    ".md", ".txt", ".json", ".jsonl", ".toml", ".yaml", ".yml", ".py",
    ".ps1", ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".gitignore",
}
CACHE_NAMES = {
    ".cache", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
CACHE_FILE_SUFFIXES = {".tmp"}
TEMP_NAMES = {"tmp", "temp"}
PROTECTED_CODEX_NAMES = {
    "auth.json", "config.toml", "config.toml.bak", "sessions",
    "archived_sessions", "memories", "plugins", "skills", "rules",
    "automations", "mcp_credentials", "credentials",
    "thread_history_1.sqlite", "logs_2.sqlite", "state_5.sqlite",
    "memories_1.sqlite", "queue_1.sqlite", "session_index.jsonl",
    ".codex-global-state.json", ".codex-global-state.json.bak",
}
PROTECTED_FILE_SUFFIXES = {
    ".sqlite", ".sqlite-wal", ".sqlite-shm", ".db", ".db-wal", ".db-shm",
    ".pem", ".key", ".pfx",
}
SKIP_SCAN_NAMES = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    "sessions", "archived_sessions", "memories", "plugins", "skills", "rules",
}
REFERENCE_INDEX_EXCLUDED_NAMES = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    "sessions", "archived_sessions", "memories", "plugins", "skills", "rules",
    "logs", "_temp", "dist", "build", ".next", "target",
}
RESTORE_METADATA_NAMES = {"transaction.json", "manifest.jsonl"}
REGENERABLE_EXAMPLES = {
    ".cache", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
DELIVERABLE_EXTENSIONS = {
    ".md", ".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".py", ".ps1", ".js", ".ts", ".tsx", ".jsx",
    ".html", ".css", ".json", ".toml", ".yaml", ".yml", ".csv",
}
SOURCE_EXTENSIONS = {
    ".py", ".ps1", ".js", ".ts", ".tsx", ".jsx", ".css", ".html",
    ".json", ".toml", ".yaml", ".yml",
}
EXCLUDED_PROJECT_PARTS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "cache", "tmp", "temp",
    "logs", "log",
}
PROTECTED_FILENAMES = {
    ".env", "auth.json", "credentials.json", "secrets.json",
}


class OptimizerError(RuntimeError):
    """A user-actionable validation or execution failure."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_within(path: Path, root: Path) -> bool:
    path = canonical(path)
    root = canonical(root)
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_protected_root(path: Path, root: Path, codex_home: Path) -> bool:
    resolved = canonical(path)
    user_home = canonical(Path.home())
    drive, _ = os.path.splitdrive(str(resolved))
    if resolved == Path(drive) / os.sep:
        return True
    if resolved in {user_home, canonical(codex_home)}:
        return True
    if not (is_within(resolved, root) or is_within(resolved, codex_home)):
        return True
    if is_within(resolved, codex_home):
        if resolved == canonical(codex_home):
            return True
    return False


def is_codex_sensitive_path(path: Path, codex_home: Path) -> bool:
    """Return whether a path belongs to Codex state that is never auto-cleaned."""
    resolved = canonical(path)
    codex_home = canonical(codex_home)
    if not is_within(resolved, codex_home):
        return any(part.lower() == ".git" for part in resolved.parts)
    relative_parts = resolved.relative_to(codex_home).parts
    lowered_parts = {part.lower() for part in relative_parts}
    if lowered_parts.intersection(PROTECTED_CODEX_NAMES):
        return True
    if resolved.name.lower() in PROTECTED_FILENAMES:
        return True
    if resolved.suffix.lower() in PROTECTED_FILE_SUFFIXES:
        return True
    return any(part.lower() == ".git" for part in relative_parts)


def guarded_path(path: Path, roots: Iterable[Path]) -> Path:
    resolved = canonical(path)
    if any(resolved == canonical(root) for root in roots):
        return resolved
    return resolved


def is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        import stat
        attrs = path.lstat().st_file_attributes  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def safe_iterdir(path: Path, follow_links: bool = False) -> Iterable[Path]:
    try:
        children = list(path.iterdir())
    except (OSError, PermissionError):
        return []
    for child in children:
        if is_reparse(child) and not follow_links:
            continue
        yield child


def path_aliases(path: Path) -> set[str]:
    """Return exact and normalized variants for path-text comparisons."""
    values = {
        str(path),
        str(canonical(path)),
        str(canonical_lexical(path)),
    }
    resolved = path.resolve(strict=False)
    values.add(str(resolved))
    current = resolved
    while True:
        parent = current.parent
        if parent == current:
            break
        current = parent
        values.add(str(current))
    drive, tail = os.path.splitdrive(str(path).replace("/", "\\"))
    if drive:
        values.add(drive.lower() + tail.lower())
    return {value for value in values if value}


def referenced_in_text(path: Path, text: str) -> bool:
    normalized_text = os.path.normcase(text.replace("/", "\\"))
    return any(
        os.path.normcase(alias.replace("/", "\\")) in normalized_text
        for alias in path_aliases(path)
    )


def canonical_lexical(path: Path) -> Path:
    """Normalize a path without following links or resolving short Windows names."""
    absolute = path.expanduser().absolute()
    return Path(os.path.normpath(str(absolute)))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(path: Path) -> str:
    """Hash a directory tree without following links or reparse points."""
    digest = hashlib.sha256()
    if not path.is_dir():
        return sha256_file(path)
    stack = [path]
    entries: list[Path] = []
    while stack:
        current = stack.pop()
        for child in safe_iterdir(current, follow_links=False):
            entries.append(child)
            if child.is_dir() and not is_reparse(child):
                stack.append(child)
    for item in sorted(
        entries,
        key=lambda entry: entry.relative_to(path).as_posix().casefold(),
    ):
        relative = item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if is_reparse(item):
            digest.update(b"link\0")
            try:
                digest.update(str(item.readlink()).encode("utf-8"))
            except OSError:
                digest.update(str(item.lstat().st_mtime_ns).encode("ascii"))
        elif item.is_dir():
            digest.update(b"dir\0")
        else:
            digest.update(b"file\0")
            digest.update(bytes.fromhex(sha256_file(item)))
    return digest.hexdigest()


def path_record(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise OptimizerError(f"Cannot stat {path}: {exc}") from exc
    record: dict[str, Any] = {
        "path": str(canonical(path)),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "is_dir": path.is_dir(),
    }
    if path.is_file():
        record["sha256"] = sha256_file(path)
    return record


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise OptimizerError(f"Required file does not exist: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OptimizerError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise OptimizerError(f"Expected a JSON object in {path}")
    return data


def write_json(path: Path, value: dict[str, Any], exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=path.name + ".tmp-",
        delete=False,
    ) as stream:
        stream.write(content)
        temp_path = Path(stream.name)
    try:
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def tree_size(path: Path, follow_links: bool = False) -> tuple[int, int]:
    """Return size/file count, returning partial metadata when the budget ends."""
    return tree_size_limited(path, follow_links=follow_links)[:2]


def tree_size_limited(
    path: Path,
    follow_links: bool = False,
    max_files: int | None = None,
    max_entries: int | None = None,
    skip_temp: bool = False,
) -> tuple[int, int, bool]:
    total = 0
    files = 0
    truncated = False
    entries = 0
    stack = [path]
    while stack:
        current = stack.pop()
        if current.is_dir():
            for child in safe_iterdir(current, follow_links):
                entries += 1
                if (
                    (max_files is not None and files >= max_files)
                    or (max_entries is not None and entries >= max_entries)
                ):
                    truncated = True
                    stack.clear()
                    break
                if skip_temp and child.name.lower() in TEMP_NAMES.union({
                    "_temp", "tmp", "temp", "cache", "caches", "logs",
                    "node_modules", ".venv", "venv", "env", "__pycache__",
                }):
                    continue
                if child.is_dir() and not is_reparse(child):
                    stack.append(child)
                elif child.is_file():
                    try:
                        total += child.stat().st_size
                        files += 1
                    except OSError:
                        pass
    return total, files, truncated


def count_manifest_files(path: Path) -> int:
    for name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod",
                 "requirements.txt", "Pipfile", "composer.json"):
        if (path / name).is_file():
            return 1
    return 0


def is_regenerable(path: Path) -> bool:
    if path.name in REGENERABLE_EXAMPLES:
        return True
    if path.name.endswith(tuple(CACHE_FILE_SUFFIXES)):
        return True
    if path.is_dir() and (path / "CACHEDIR.TAG").is_file():
        return True
    return False


def text_content_candidate(path: Path) -> bool:
    parent_names = {part.lower() for part in path.parts}
    return (
        path.is_file()
        and (path.suffix.lower() in TEXT_EXTENSIONS or path.name == ".gitignore")
        and path.name not in PROTECTED_FILENAMES
        and path.name not in PROTECTED_CODEX_NAMES
        and path.suffix.lower() not in PROTECTED_FILE_SUFFIXES
        and not parent_names.intersection({
            "memories", "sessions", "archived_sessions", "plugins", "skills",
            "rules",
        })
    )


def extract_text_refs(path: Path, old: str, limit: int = 1024 * 1024) -> int:
    if not text_content_candidate(path):
        return 0
    try:
        if path.stat().st_size > limit:
            return 0
        return path.read_text(encoding="utf-8").count(old)
    except (OSError, UnicodeDecodeError):
        return 0


def scan_reference_hits(roots: Iterable[Path], old_path: str, follow_links: bool = False) -> list[str]:
    hits: list[str] = []
    target = Path(old_path)
    for root in roots:
        if not root.exists():
            continue
        stack = [root]
        while stack:
            current = stack.pop()
            try:
                if current.is_dir():
                    for child in safe_iterdir(current, follow_links):
                        if child.is_dir():
                            if child.name not in SKIP_SCAN_NAMES:
                                stack.append(child)
                        elif text_content_candidate(child):
                            try:
                                text = child.read_text(encoding="utf-8")
                            except (OSError, UnicodeDecodeError):
                                continue
                            if referenced_in_text(target, text):
                                hits.append(str(canonical(child)))
                elif text_content_candidate(current):
                    try:
                        text = current.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        continue
                    if referenced_in_text(target, text):
                        hits.append(str(canonical(current)))
            except (OSError, PermissionError):
                continue
    return sorted(set(hits))


def scan_reference_index(
    roots: Iterable[Path],
    follow_links: bool = False,
    max_files: int = 20000,
    max_file_bytes: int = 1024 * 1024,
) -> dict[str, list[str]]:
    """Read a bounded metadata-oriented index once for all cleanup candidates."""
    by_alias: dict[str, list[str]] = {}
    files_seen = 0
    for root in roots:
        if not root.exists():
            continue
        stack = [root]
        while stack and files_seen < max_files:
            current = stack.pop()
            try:
                if current.is_dir():
                    for child in safe_iterdir(current, follow_links):
                        if child.is_dir():
                            if child.name not in REFERENCE_INDEX_EXCLUDED_NAMES:
                                stack.append(child)
                        elif text_content_candidate(child):
                            try:
                                if child.stat().st_size > max_file_bytes:
                                    continue
                                text = child.read_text(encoding="utf-8")
                            except (OSError, UnicodeDecodeError):
                                continue
                            files_seen += 1
                            normalized = os.path.normcase(
                                text.replace("/", "\\")
                            )
                            for alias in re.findall(
                                r"[a-z]:(?:\\|/)(?:[^\r\n`'\"<>|]*)",
                                normalized,
                            ):
                                alias = alias.rstrip(" .,);:]")
                                by_alias.setdefault(alias.lower(), []).append(
                                    str(canonical(child))
                                )
                            if files_seen >= max_files:
                                break
                elif text_content_candidate(current):
                    files_seen += 1
            except (OSError, PermissionError):
                continue
    return {
        alias: sorted(set(paths))
        for alias, paths in by_alias.items()
    }


def indexed_reference_hits(
    index: dict[str, list[str]],
    path: Path,
) -> list[str]:
    terms = [str(path)] + reference_terms(path, limit=100)
    resolved_path = str(path.resolve(strict=False))
    long_path = path.absolute()
    try:
        long_path = Path(str(long_path).replace(
            str(Path.home()).split("\\")[-1],
            str(Path.home()),
            1,
        ))
    except ValueError:
        pass
    terms.extend(
        value
        for value in (
            resolved_path,
            str(long_path),
            str(Path(resolved_path).parent),
            str(long_path.parent),
        )
        if value not in terms
    )
    hits: set[str] = set()
    resolved_terms = [
        value
        for term in terms
        for value in (term, str(Path(term).resolve(strict=False)))
    ]
    temp_tail_terms = [
        re.sub(
            r"^[a-z]:\\users\\[^\\]+",
            "",
            os.path.normcase(term.replace("/", "\\")),
        )
        for term in resolved_terms
    ]
    for normalized, paths in index.items():
        if any(
            os.path.normcase(term.replace("/", "\\")) in normalized
            or normalized in os.path.normcase(term.replace("/", "\\"))
            for term in resolved_terms
        ) or any(
            re.sub(r"^[a-z]:\\users\\[^\\]+", "", normalized).endswith(term)
            for term in temp_tail_terms
        ):
            hits.update(paths)
    return sorted(hits)


def reference_terms(path: Path, limit: int | None = 100) -> list[str]:
    """Return a bounded set of paths whose textual references protect a candidate."""
    values = [str(canonical(path))]
    if not path.is_dir():
        return values
    stack = [path]
    while stack and (limit is None or len(values) < limit):
        current = stack.pop()
        for child in safe_iterdir(current, follow_links=False):
            values.append(str(canonical(child)))
            if child.is_dir() and not is_reparse(child):
                stack.append(child)
            if limit is not None and len(values) >= limit:
                break
    return values


def dated_task_dirs(root: Path) -> list[Path]:
    results: list[Path] = []
    for child in safe_iterdir(root):
        if not child.is_dir():
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name):
            for task in safe_iterdir(child):
                if task.is_dir():
                    results.append(task)
    return results


def project_candidates(root: Path, task_dirs: list[Path]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    grouped: dict[str, list[tuple[Path, Path]]] = {}
    for task in task_dirs:
        files = [
            item
            for item in safe_iterdir(task, follow_links=False)
            if item.is_file()
            and item.suffix.lower() in DELIVERABLE_EXTENSIONS
            and item.name not in PROTECTED_FILENAMES
        ]
        if not files:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", task.name.lower()).strip("-") or "project"
        grouped.setdefault(slug, []).append((task, task.parent))
    for slug, occurrences in grouped.items():
        dates = {parent.name for _, parent in occurrences}
        all_files = [
            item
            for task, _ in occurrences
            for item in safe_iterdir(task, follow_links=False)
            if item.is_file()
            and item.suffix.lower() in DELIVERABLE_EXTENSIONS
            and item.name not in PROTECTED_FILENAMES
        ]
        score = 2 + min(3, len(all_files))
        if any(item.suffix.lower() in SOURCE_EXTENSIONS for item in all_files):
            score += 2
        if len(dates) >= 2:
            score += 2
        score = min(10, score)
        tasks = [str(canonical(task)) for task, _ in occurrences]
        candidates.append({
            "slug": slug,
            "tasks": tasks,
            "task": tasks[0],
            "score": score,
            "threshold": 6,
            "repeatedDates": len(dates),
            "reason": (
                "explicitly usable when the user names a project; otherwise "
                "promote only at the score threshold with repeated occurrence"
            ),
            "files": [str(canonical(item)) for item in all_files[:50]],
        })
    return candidates


def usage_ledger_path(root: Path) -> Path:
    return canonical(root) / "_temp" / "data" / "project-usage.jsonl"


def load_usage_ledger(root: Path) -> list[dict[str, Any]]:
    ledger = usage_ledger_path(root)
    if not ledger.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    records.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return records


def discover_used_files(
    root: Path, task: Path, session_ids: Iterable[str] | None = None,
) -> list[Path]:
    """Use recorded tool access; within a task fall back to project-like source files."""
    known_sessions = {str(item) for item in (session_ids or []) if item}
    allowed: dict[str, Path] = {}
    for record in load_usage_ledger(root):
        if known_sessions and str(record.get("sessionId", "")) not in known_sessions:
            continue
        raw = record.get("path")
        if not isinstance(raw, str):
            continue
        path = canonical(Path(raw))
        if is_within(path, task) and path.exists() and path.is_file():
            allowed[str(path)] = path
    if allowed:
        return sorted(allowed.values(), key=lambda item: str(item).lower())
    # Current sessions expose their access evidence to the agent. A deterministic
    # fallback keeps the CLI useful in isolated tests and offline use.
    results: list[Path] = []
    stack = [task]
    while stack:
        current = stack.pop()
        for item in safe_iterdir(current, follow_links=False):
            relative_parts = {part.lower() for part in item.relative_to(task).parts}
            if relative_parts & EXCLUDED_PROJECT_PARTS:
                continue
            if is_reparse(item):
                continue
            if item.is_dir():
                stack.append(item)
                continue
            if item.name in PROTECTED_FILENAMES:
                continue
            if item.suffix.lower() in DELIVERABLE_EXTENSIONS:
                results.append(item)
    return results


def project_destination_relative(source: Path, task: Path) -> Path:
    """Classify a migrated file as working material or a deliverable."""
    relative = source.relative_to(task)
    lowered = {part.lower() for part in relative.parts}
    if lowered & PROJECT_OUTPUT_NAMES:
        return Path("outputs") / relative
    if lowered & PROJECT_WORK_NAMES:
        return Path("work") / relative
    if relative.suffix.lower() in DELIVERABLE_EXTENSIONS:
        return Path("outputs") / relative
    return Path("work") / relative


def normalize_project_slug(value: str) -> str:
    """Return a safe semantic project slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise OptimizerError(
            "Project slug is empty after normalization; pass --slug with "
            "lowercase ASCII letters or digits."
        )
    return slug


def quick_project(
    root: Path,
    *,
    source: Path | None = None,
    git_url: str = "",
    slug: str = "",
    move: bool = False,
    description: str = "",
) -> dict[str, Any]:
    """Adopt one explicit project without the cleanup transaction workflow."""
    root = canonical(root)
    if (
        root == canonical(Path.home())
        or len(root.parts) <= 1
        or not root.is_dir()
    ):
        raise OptimizerError(f"Unsafe governance root: {root}")
    if bool(source) == bool(git_url):
        raise OptimizerError("Pass exactly one of --source or --git-url")
    if move and not source:
        raise OptimizerError("--move requires --source")

    raw_slug = slug
    source_path: Path | None = None
    if source is not None:
        source_path = canonical(source)
        if not source_path.exists() or not source_path.is_dir():
            raise OptimizerError(f"Project source is not a directory: {source_path}")
        if source_path in {
            canonical(Path.home()),
            canonical(Path(source_path.anchor)),
            DEFAULT_CODEX_HOME,
        }:
            raise OptimizerError(f"Unsafe project source: {source_path}")
        if is_within(
            source_path, canonical(DEFAULT_CODEX_HOME)
        ) and is_codex_sensitive_path(source_path, DEFAULT_CODEX_HOME):
            raise OptimizerError(f"Codex state path is not a project source: {source_path}")
        raw_slug = raw_slug or source_path.name
    else:
        remote_name = git_url.rstrip("/").rsplit("/", 1)[-1]
        if remote_name.endswith(".git"):
            remote_name = remote_name[:-4]
        raw_slug = raw_slug or remote_name

    base_slug = normalize_project_slug(raw_slug)
    projects = root / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    destination = projects / base_slug
    if destination.exists():
        raise OptimizerError(f"Project destination already exists: {destination}")
    if source_path is not None and (
        is_within(destination, source_path) or is_within(source_path, destination)
    ):
        raise OptimizerError("Source and destination overlap")

    ignored: list[str] = []
    if git_url:
        git = shutil.which("git")
        if not git:
            raise OptimizerError("git is required for --git-url")
        result = subprocess.run(
            [git, "clone", "--", git_url, str(destination)],
            text=True,
            capture_output=True,
        )
        if result.returncode:
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            detail = result.stderr.strip() or result.stdout.strip()
            raise OptimizerError(f"git clone failed: {detail}")
        adopted_from = git_url
        operation = "cloned"
    else:
        assert source_path is not None

        def ignore_items(directory: str, names: list[str]) -> set[str]:
            current = Path(directory)
            try:
                relative = current.relative_to(source_path)
            except ValueError:
                relative = Path()
            if ".git" in relative.parts:
                return set()
            skipped: set[str] = set()
            for name in names:
                candidate = current / name
                is_skipped = (
                    candidate.is_dir()
                    and name.lower() in {
                        "__pycache__", ".pytest_cache", ".mypy_cache",
                        ".ruff_cache", "node_modules", ".venv", "venv",
                    }
                ) or (
                    candidate.is_file()
                    and (
                        name.lower() in PROTECTED_FILENAMES
                        or candidate.suffix.lower() in {
                            ".pem", ".key", ".pfx", ".sqlite", ".sqlite-wal",
                            ".sqlite-shm", ".db", ".db-wal", ".db-shm",
                        }
                    )
                )
                if is_skipped:
                    skipped.add(name)
                    ignored.append(
                        (relative / name).as_posix()
                        if relative.parts else name
                    )
            return skipped

        if move:
            try:
                source_path.rename(destination)
                operation = "moved"
            except OSError:
                shutil.copytree(
                    source_path,
                    destination,
                    symlinks=True,
                    ignore=ignore_items,
                )
                shutil.rmtree(source_path)
                operation = "copied-and-removed-source"
        else:
            shutil.copytree(
                source_path,
                destination,
                symlinks=True,
                ignore=ignore_items,
            )
            operation = "copied"
        adopted_from = str(source_path)

    created_docs: list[str] = []
    created_project_record = not (destination / "AGENTS.md").exists()
    readme = destination / "README.md"
    if not readme.exists():
        summary = description.strip() or f"{base_slug} project."
        write_text_atomic(
            readme,
            f"# {base_slug}\n\n{summary}\n\n"
            "- Main edit location: this directory.\n"
            f"- Source: {adopted_from}\n",
        )
        created_docs.append("README.md")
    sources = destination / "source.md"
    if not sources.exists():
        write_text_atomic(
            sources,
            "# Project Source\n\n"
            f"- Project: `{base_slug}`\n"
            f"- Adopted from: `{adopted_from}`\n"
            f"- Method: `{operation}`\n"
            f"- Created: {iso_now()}\n",
        )
        created_docs.append("source.md")
    if created_project_record:
        write_text_atomic(
            destination / "AGENTS.md",
            "# Project Instructions\n\n"
            "- Start with `README.md`; read `source.md` for provenance.\n"
            "- Keep working files under `work/` and deliverables under `outputs/`.\n"
            "- Use `work/checkpoints/` only for changes that actually need recovery.\n"
            "- Do not copy credentials, databases, caches, or runtime logs here.\n",
        )
        created_docs.append("AGENTS.md")

    return {
        "status": "ready",
        "operation": operation,
        "project": str(destination),
        "source": adopted_from,
        "createdDocs": created_docs,
        "ignoredSensitiveOrCacheItems": sorted(ignored),
    }


def build_report(root: Path, codex_home: Path, project_roots: list[Path],
                 deep: bool = False, follow_links: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    root = canonical(root)
    codex_home = canonical(codex_home)
    projects = [canonical(item) for item in project_roots]
    scan_file_limit = 100000 if deep else 20000
    codex_file_limit = 25000 if deep else 5000
    if not root.exists():
        raise OptimizerError(f"Governance root does not exist: {root}")
    if not codex_home.exists():
        warnings.append("Codex home is missing; its categories were not scanned.")

    roots: list[dict[str, Any]] = []
    scan_paths = [(root, "governance")]
    scan_paths.extend((item, "registered-project") for item in projects)
    for path, kind in scan_paths:
        if not path.exists():
            warnings.append(f"Registered path is missing: {path}")
            continue
        size, files, truncated = tree_size_limited(
            path,
            follow_links=follow_links,
            max_files=scan_file_limit,
            max_entries=10000 if kind == "registered-project" and not deep else None,
            skip_temp=kind == "registered-project" and not deep,
        )
        roots.append({
            "kind": kind,
            "path": str(path),
            "bytes": size,
            "files": files,
            "truncated": truncated,
            "is_symlink": is_reparse(path),
        })

    codex_dirs: list[dict[str, Any]] = []
    for child in safe_iterdir(codex_home, follow_links):
        if child.is_dir():
            size, files, truncated = tree_size_limited(
                child,
                follow_links=follow_links,
                max_files=codex_file_limit,
            )
            codex_dirs.append({
                "name": child.name,
                "bytes": size,
                "files": files,
                "truncated": truncated,
                "protected": child.name in PROTECTED_CODEX_NAMES,
            })

    candidates: list[dict[str, Any]] = []
    for child in safe_iterdir(root, follow_links):
        if child.name in CACHE_NAMES and is_regenerable(child):
            size, files = tree_size(child, follow_links=False)
            candidates.append({
                "type": "cache",
                "path": str(canonical(child)),
                "bytes": size,
                "files": files,
                "risk": "low",
                "reason": "cache marker or known cache name",
            })
        elif child.is_file() and child.name.endswith(".tmp"):
            candidates.append({
                "type": "temporary",
                "path": str(canonical(child)),
                "bytes": child.stat().st_size,
                "files": 1,
                "risk": "low",
                "reason": "temporary suffix",
            })

    dated = dated_task_dirs(root)
    promotions = project_candidates(root, dated)
    if candidates:
        reference_index = scan_reference_index(
            [root] + projects,
            follow_links=follow_links,
            max_files=20000 if not deep else 100000,
        )
    else:
        reference_index = {}
    for item in candidates:
        hits = indexed_reference_hits(
            reference_index,
            Path(item["path"]),
        )
        if hits:
            item["references"] = hits
            item["risk"] = "high"
            item["reason"] += "; protected because referenced"

    if not deep:
        warnings.append("Default scan is metadata-only; pass --deep to analyze more files.")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": iso_now(),
        "root": str(canonical_lexical(root)),
        "codexHome": str(codex_home),
        "mode": "deep" if deep else "metadata",
        "projectRoots": [str(item) for item in projects],
        "totals": {
            "rootBytes": sum(item["bytes"] for item in roots if item["kind"] == "governance"),
            "projectBytes": sum(item["bytes"] for item in roots if item["kind"] == "registered-project"),
        "codexBytesApprox": sum(item["bytes"] for item in codex_dirs),
        },
        "roots": roots,
        "codexDirectories": codex_dirs,
        "datedTasks": len(dated),
        "cleanupCandidates": candidates,
        "projectCandidates": promotions,
        "warnings": warnings,
        "errors": errors,
        "estimatedSafeReclaimBytes": sum(
            item["bytes"] for item in candidates if item["risk"] == "low"
        ),
    }


def create_plan(
    report: dict[str, Any],
    root: Path,
    codex_home: Path,
    project_mode: str | None = None,
    session_ids: Iterable[str] | None = None,
    rewrite_references: bool = False,
    explicit_projects: Iterable[str] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    expires = now + dt.timedelta(minutes=PLAN_TTL_MINUTES)
    actions: list[dict[str, Any]] = []
    for candidate in report["cleanupCandidates"]:
        if candidate["risk"] != "low":
            continue
        path = Path(candidate["path"])
        try:
            record = path_record(path)
        except OptimizerError as exc:
            report["errors"].append(str(exc))
            continue
        actions.append({
            "kind": "trash",
            "source": record["path"],
            "destination": str(
                canonical(root) / "_temp" / "trash"
                / "<batch>" / "items" / path.name
            ),
            "sha256": "",
            "is_dir": record["is_dir"],
            "size": record["size"],
            "mtime": record["mtime"],
            "risk": "low",
            "reason": candidate["reason"],
            "references": candidate.get("references", []),
        })
    if project_mode == "promote":
        explicit = {
            re.sub(r"[^a-z0-9]+", "-", item.lower()).strip("-")
            for item in (explicit_projects or [])
        }
        for candidate in report["projectCandidates"]:
            if not (
                candidate["slug"] in explicit
                or (
                    int(candidate["score"]) >= int(candidate["threshold"])
                    and int(candidate.get("repeatedDates", 0)) >= 2
                )
            ):
                continue
            tasks = [Path(item) for item in candidate["tasks"]]
            files = sorted({
                str(path)
                for task in tasks
                for path in discover_used_files(root, task, session_ids)
            })
            if not files:
                continue
            destination = (
                canonical(root) / "projects" / candidate["slug"]
            )
            suffix = 2
            while destination.exists():
                destination = (
                    canonical(root) / "projects"
                    / f"{candidate['slug']}-{suffix}"
                )
                suffix += 1
            actions.append({
                "kind": "create_project",
                "source": "",
                "destination": str(destination),
                "sha256": "",
                "is_dir": True,
                "size": 0,
                "mtime": 0,
                "risk": "high",
                "reason": "project promotion score reached",
                "references": [],
                "projectSlug": candidate["slug"],
                "sourceTasks": [str(item) for item in tasks],
                "score": candidate["score"],
                "explicit": candidate["slug"] in explicit,
            })
            for source in files:
                source_path = Path(source)
                relative = Path(source_path.name)
                for task in tasks:
                    if is_within(source_path, task):
                        relative = project_destination_relative(source_path, task)
                        break
                actions.append({
                    "kind": "copy_project",
                    "source": str(source_path),
                    "destination": str(destination / relative),
                    "sha256": "",
                    "is_dir": False,
                    "size": source_path.stat().st_size,
                    "mtime": source_path.stat().st_mtime,
                    "risk": "high",
                    "reason": "used project file",
                    "references": [],
                    "projectSlug": candidate["slug"],
                    "sourceTasks": [str(item) for item in tasks],
                })
    if rewrite_references:
        old_new: dict[str, str] = {}
        for action in actions:
            if action["kind"] == "copy_project":
                old_new[action["source"]] = action["destination"]
        text_roots = [canonical(root)] + [canonical(item) for item in report["projectRoots"]]
        seen: set[str] = set()
        for old, new in old_new.items():
            for hit in scan_reference_hits(text_roots, old):
                if hit in seen:
                    continue
                seen.add(hit)
                path = Path(hit)
                try:
                    record = path_record(path)
                except OptimizerError:
                    continue
                actions.append({
                    "kind": "rewrite_text",
                    "source": str(path),
                    "destination": str(path),
                    "sha256": record["sha256"],
                    "is_dir": False,
                    "size": record["size"],
                    "mtime": record["mtime"],
                    "risk": "high",
                    "reason": f"replace {old} with {new}",
                    "references": [],
                    "oldText": old,
                    "newText": new,
                })
    body = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "codex-optimizer-plan",
        "createdAt": now.isoformat(timespec="seconds"),
        "expiresAt": expires.isoformat(timespec="seconds"),
        "root": str(canonical(root)),
        "codexHome": str(canonical(codex_home)),
        "projectRoots": report["projectRoots"],
        "actions": actions,
    }
    body["planHash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return body


def validate_plan(plan: dict[str, Any], root: Path, codex_home: Path) -> None:
    if plan.get("kind") != "codex-optimizer-plan":
        raise OptimizerError("Not a codex-optimizer plan")
    expected = plan.get("planHash")
    raw = dict(plan)
    raw.pop("planHash", None)
    actual = hashlib.sha256(
        json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if expected != actual:
        raise OptimizerError("Plan integrity hash does not match")
    try:
        expires = dt.datetime.fromisoformat(plan["expiresAt"])
    except (KeyError, ValueError) as exc:
        raise OptimizerError("Plan has invalid expiresAt") from exc
    if utc_now() > expires:
        raise OptimizerError("Plan expired")
    if canonical(Path(plan["root"])) != canonical(root):
        raise OptimizerError("Plan root does not match --root")
    if canonical(Path(plan["codexHome"])) != canonical(codex_home):
        raise OptimizerError("Plan Codex home does not match --codex-home")
    actions = plan.get("actions")
    if not isinstance(actions, list):
        raise OptimizerError("Plan actions must be a list")
    if len(actions) > MAX_ITEMS_PER_BATCH:
        raise OptimizerError("Plan exceeds the per-batch item limit")
    if sum(int(item.get("size", 0)) for item in actions) > MAX_BYTES_PER_BATCH:
        raise OptimizerError("Plan exceeds the per-batch byte limit")
    for action in actions:
        if action.get("kind") not in {
            "trash", "create_project", "copy_project", "rewrite_text",
        }:
            raise OptimizerError(f"Unsupported action: {action.get('kind')}")
        if action["kind"] == "trash" and action.get("risk") != "low":
            raise OptimizerError("Only low-risk trash actions can be automatic")
        if action["kind"] == "trash" and action.get("references"):
            raise OptimizerError("Referenced source cannot be moved")
        if action["kind"] == "create_project":
            continue
        if action["kind"] == "rewrite_text":
            path = canonical(Path(action["source"]))
            if not text_content_candidate(path):
                raise OptimizerError(f"Refusing to rewrite binary or protected file: {path}")
        else:
            source = canonical(Path(action["source"]))
            allowed_project_source = action["kind"] == "copy_project" and any(
                is_within(source, Path(project_root))
                for project_root in plan.get("projectRoots", [])
            )
            if (
                action["kind"] == "trash"
                and is_protected_root(source, root, codex_home)
            ):
                raise OptimizerError(f"Source is outside the permitted roots: {source}")
            if (
                action["kind"] == "copy_project"
                and not (
                    is_within(source, root)
                    or (
                        allowed_project_source
                        and not is_codex_sensitive_path(source, codex_home)
                    )
                )
            ):
                raise OptimizerError(
                    f"Project copy source is outside the permitted roots: {source}"
                )
            if action["kind"] == "copy_project":
                destination = canonical(Path(action["destination"]))
                if not is_within(destination, canonical(root) / "projects"):
                    raise OptimizerError(
                        f"Project destination is outside projects/: {destination}"
                    )
            if is_codex_sensitive_path(source, codex_home):
                raise OptimizerError(
                    f"Refusing to copy Codex state or secrets: {source}"
                )
            if not source.exists():
                raise OptimizerError(f"Source no longer exists: {source}")
            if action["kind"] == "trash":
                current = source.stat()
                if (
                    current.st_size != int(action.get("size", -1))
                    or abs(current.st_mtime - float(action.get("mtime", 0))) > 1
                ):
                    raise OptimizerError(f"Source metadata changed: {source}")
            elif (
                action["kind"] == "rewrite_text"
                and sha256_file(source) != action.get("sha256")
            ):
                raise OptimizerError(f"Text source changed: {source}")


def checkpoint_path(base: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return base / f"{stamp}-codex-optimizer.md"


def write_checkpoint(root: Path, batch_id: str, actions: list[dict[str, Any]],
                     rollback: str) -> Path:
    directory = canonical(root) / "_temp" / "checkpoints"
    path = checkpoint_path(directory)
    lines = [
        "# Codex Optimizer Checkpoint",
        "",
        f"- Time: {iso_now()}",
        f"- Batch: `{batch_id}`",
        f"- Actions: {len(actions)}",
        f"- Rollback: `{rollback}`",
        "",
        "## Actions",
        "",
    ]
    for item in actions:
        lines.append(f"- `{item['source']}` -> `{item['destination']}`")
    write_text_atomic(path, "\n".join(lines) + "\n")
    prune_checkpoints(directory, CHECKPOINT_KEEP)
    return path


def collaboration_paths(root: Path) -> tuple[Path, Path, Path]:
    base = canonical(root) / "_temp" / "collaboration"
    return base / "leases", base / "events.jsonl", base / "README.md"


def collaboration_relative_target(root: Path, target: Path) -> str:
    target = canonical(target)
    root = canonical(root)
    if not is_within(target, root):
        raise OptimizerError(f"Collaboration target is outside the governance root: {target}")
    if target == root:
        raise OptimizerError("Collaboration target cannot be the governance root itself")
    relative = target.relative_to(root).as_posix()
    if any(part.lower() in {".git", "sessions", "archived_sessions", "memories", "plugins", "skills"}
           for part in relative.split("/")):
        raise OptimizerError(f"Refusing to coordinate private or runtime path: {relative}")
    return relative


def active_lease(root: Path, target: str, now: float | None = None) -> dict[str, Any] | None:
    leases, _, _ = collaboration_paths(root)
    path = leases / (hashlib.sha256(target.encode("utf-8")).hexdigest()[:16] + ".json")
    if not path.exists():
        return None
    try:
        record = load_json(path)
        expires = dt.datetime.fromisoformat(record["expiresAt"]).timestamp()
    except (OptimizerError, KeyError, TypeError, ValueError):
        return None
    if expires <= (time.time() if now is None else now):
        path.unlink(missing_ok=True)
        return None
    return record


def collaboration_claim(
    root: Path,
    target: Path,
    agent: str,
    purpose: str,
    session_id: str = "",
    lease_minutes: int = DEFAULT_LEASE_MINUTES,
    takeover: bool = False,
) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", agent):
        raise OptimizerError("Agent name must be lowercase kebab-case")
    if not 1 <= lease_minutes <= 1440:
        raise OptimizerError("Lease duration must be between 1 and 1440 minutes")
    relative = collaboration_relative_target(root, target)
    leases, events, _ = collaboration_paths(root)
    leases.mkdir(parents=True, exist_ok=True)
    current = active_lease(root, relative)
    if current and current.get("agent") != agent:
        raise OptimizerError(
            f"Active lease held by {current.get('agent')} until {current.get('expiresAt')}"
        )
    if current and current.get("agent") == agent and not takeover:
        return {"status": "already-held", **current}
    now = utc_now()
    record = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "collaboration-lease",
        "agent": agent,
        "target": relative,
        "purpose": purpose,
        "sessionId": session_id,
        "createdAt": now.isoformat(timespec="seconds"),
        "expiresAt": (
            now + dt.timedelta(minutes=lease_minutes)
        ).isoformat(timespec="seconds"),
        "takeover": takeover,
    }
    path = leases / (hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16] + ".json")
    write_json(path, record)
    append_manifest(events, {
        "kind": "claim",
        "timestamp": iso_now(),
        "agent": agent,
        "target": relative,
        "purpose": purpose,
        "sessionId": session_id,
        "expiresAt": record["expiresAt"],
    })
    return {"status": "claimed", "lease": str(path), **record}


def collaboration_release(root: Path, target: Path, agent: str) -> dict[str, Any]:
    relative = collaboration_relative_target(root, target)
    current = active_lease(root, relative)
    if not current:
        return {"status": "not-held", "target": relative, "agent": agent}
    if current.get("agent") != agent:
        raise OptimizerError(f"Lease belongs to {current.get('agent')}")
    leases, events, _ = collaboration_paths(root)
    path = leases / (hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16] + ".json")
    path.unlink()
    append_manifest(events, {
        "kind": "release",
        "timestamp": iso_now(),
        "agent": agent,
        "target": relative,
    })
    return {"status": "released", "target": relative, "agent": agent}


def collaboration_handoff(
    root: Path,
    target: Path,
    agent: str,
    summary: str,
    next_agent: str,
    session_id: str = "",
) -> dict[str, Any]:
    relative = collaboration_relative_target(root, target)
    _, events, _ = collaboration_paths(root)
    events.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "kind": "handoff",
        "timestamp": iso_now(),
        "agent": agent,
        "nextAgent": next_agent,
        "target": relative,
        "summary": summary,
        "sessionId": session_id,
    }
    append_manifest(events, record)
    return {"status": "recorded", "event": str(events), **record}


def collaboration_status(root: Path, target: Path) -> dict[str, Any]:
    relative = collaboration_relative_target(root, target)
    record = active_lease(root, relative)
    return {
        "status": "active" if record else "free",
        "target": relative,
        "lease": record,
    }


def prune_checkpoints(directory: Path, keep: int) -> None:
    if not directory.exists():
        return
    checkpoints = sorted(
        (item for item in directory.iterdir()
         if item.is_file() and item.suffix.lower() == ".md"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old in checkpoints[keep:]:
        old.unlink(missing_ok=True)


def append_manifest(manifest: Path, record: dict[str, Any]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def move_transaction(source: Path, destination: Path) -> tuple[str, bool]:
    """Move atomically; verify only a cross-volume copy before removing source."""
    if not destination.parent.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise OptimizerError(f"Destination already exists: {destination}")
    source = canonical(source)
    destination = canonical(destination)
    try:
        os.replace(source, destination)
        kind = "directory" if destination.is_dir() else "file"
        digest = ""
        return digest, kind == "directory"
    except OSError as exc:
        if not (
            getattr(exc, "winerror", None) == 17
            or exc.errno == getattr(os, "EXDEV", 18)
        ):
            raise
    if source.is_dir():
        expected = tree_digest(source)
        shutil.copytree(source, destination, symlinks=True)
        actual = tree_digest(destination)
        if actual != expected:
            shutil.rmtree(destination, ignore_errors=True)
            raise OptimizerError(f"Copy validation failed: {source}")
        shutil.rmtree(source)
        return actual, True
    expected = sha256_file(source)
    with tempfile.NamedTemporaryFile(
        "wb", dir=destination.parent, prefix=destination.name + ".tmp-",
        delete=False,
    ) as stream:
        temp_path = Path(stream.name)
    try:
        shutil.copy2(source, temp_path)
        actual = sha256_file(temp_path)
        if actual != expected:
            raise OptimizerError(f"Copy validation failed: {source}")
        os.replace(temp_path, destination)
        source.unlink()
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return expected, False


def apply_plan(plan_path: Path, root: Path, codex_home: Path,
               execute: bool) -> dict[str, Any]:
    plan = load_json(plan_path)
    validate_plan(plan, root, codex_home)
    actions = plan["actions"]
    if not execute:
        return {
            "status": "dry-run",
            "root": str(canonical(root)),
            "actions": actions,
            "count": len(actions),
        }
    batch_id = dt.datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    batch_dir = canonical(root) / "_temp" / "trash" / batch_id
    manifest = batch_dir / "manifest.jsonl"
    transaction = batch_dir / "transaction.json"
    completed: list[dict[str, Any]] = []
    try:
        for action in actions:
            kind = action["kind"]
            if kind == "trash":
                source = canonical(Path(action["source"]))
                destination = batch_dir / "items" / source.name
                if destination.exists():
                    raise OptimizerError(f"Destination already exists: {destination}")
                actual_hash, _ = move_transaction(source, destination)
                record = {
                    "kind": "trash",
                    "batchId": batch_id,
                    "timestamp": iso_now(),
                    "from": str(source),
                    "to": str(destination),
                    "size": action["size"],
                    "sha256": actual_hash,
                    "category": "low-risk-cache-or-temporary",
                    "risk": "low",
                    "reason": action["reason"],
                    "sourceRoot": str(canonical(root)),
                }
                append_manifest(manifest, record)
                completed.append(record)
            elif kind == "create_project":
                destination = canonical(Path(action["destination"]))
                created = not destination.exists()
                access = project_access_snapshot(destination)
                project_actions = [
                    item for item in actions if (
                        item["kind"] == "copy_project"
                        and item.get("projectSlug") == action["projectSlug"]
                    )
                ]
                destination.mkdir(parents=True, exist_ok=True)
                scaffold_created = ensure_project_scaffold(
                    destination,
                    action["projectSlug"],
                    action.get("sourceTasks", []),
                    project_actions,
                )
                record = {
                    "kind": "create_project",
                    "batchId": batch_id,
                    "timestamp": iso_now(),
                    "path": str(destination),
                    "created": created,
                    "access": access,
                    "scaffoldCreated": scaffold_created,
                    "risk": "high",
                }
                completed.append(record)
            elif kind == "copy_project":
                source = canonical(Path(action["source"]))
                destination = canonical(Path(action["destination"]))
                current = source.stat()
                if (
                    current.st_size != int(action.get("size", -1))
                    or abs(current.st_mtime - float(action.get("mtime", 0))) > 1
                ):
                    raise OptimizerError(f"Source metadata changed: {source}")
                if destination.exists():
                    if (
                        destination.is_file()
                        and destination.stat().st_size == current.st_size
                    ):
                        continue
                    # Copy destinations are always under projects/<slug>.
                    parts = canonical(Path(action["destination"])).parts
                    project_index = parts.index("projects")
                    project_root = Path(*parts[:project_index + 2])
                    conflict = (
                        project_root / "work" / "conflicts"
                        / source.parent.name / destination.name
                    )
                    destination = conflict
                    counter = 2
                    while destination.exists():
                        destination = conflict.with_name(
                            f"{conflict.stem}-{counter}{conflict.suffix}"
                        )
                        counter += 1
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    "wb", dir=destination.parent,
                    prefix=destination.name + ".tmp-", delete=False,
                ) as stream:
                    temp_path = Path(stream.name)
                shutil.copy2(source, temp_path)
                if temp_path.stat().st_size != current.st_size:
                    temp_path.unlink(missing_ok=True)
                    raise OptimizerError(f"Project copy validation failed: {source}")
                os.replace(temp_path, destination)
                record = {
                    "kind": "copy_project",
                    "batchId": batch_id,
                    "timestamp": iso_now(),
                    "from": str(source),
                    "to": str(destination),
                    "size": action["size"],
                    "sha256": "",
                    "risk": "high",
                }
                completed.append(record)
            elif kind == "rewrite_text":
                source = canonical(Path(action["source"]))
                if not source.exists() or sha256_file(source) != action["sha256"]:
                    raise OptimizerError(f"Text changed before rewrite: {source}")
                text = source.read_text(encoding="utf-8")
                updated = text.replace(action["oldText"], action["newText"])
                write_text_atomic(source, updated)
                record = {
                    "kind": "rewrite_text",
                    "batchId": batch_id,
                    "timestamp": iso_now(),
                    "path": str(source),
                    "beforeText": text,
                    "beforeSha256": action["sha256"],
                    "afterSha256": sha256_file(source),
                    "risk": "high",
                }
                completed.append(record)
            else:
                raise OptimizerError(f"Unsupported action: {kind}")
            write_json(transaction, {
                "batchId": batch_id,
                "state": "in-progress",
                "completed": completed,
            })
        write_json(transaction, {
            "batchId": batch_id,
            "state": "complete",
            "completed": completed,
            "completedAt": iso_now(),
        })
    except Exception:
        for record in reversed(completed):
            if record["kind"] == "trash":
                source = Path(record["from"])
                destination = Path(record["to"])
                if destination.exists() and not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination), str(source))
            elif record["kind"] == "copy_project":
                destination = Path(record["to"])
                destination.unlink(missing_ok=True)
            elif record["kind"] == "rewrite_text":
                write_text_atomic(
                    Path(record["path"]),
                    record["beforeText"],
                )
            elif record["kind"] == "create_project" and record["created"]:
                restore_project_access(Path(record["path"]), record["access"])
            elif record["kind"] == "create_project":
                for raw in record.get("scaffoldCreated", []):
                    Path(raw).unlink(missing_ok=True)
        write_json(transaction, {
            "batchId": batch_id,
            "state": "rolled-back",
            "completed": completed,
            "failedAt": iso_now(),
        })
        raise
    rollback = (
        f'python scripts/codex_optimizer.py rollback --root "{canonical(root)}" '
        f'--batch-id "{batch_id}"'
    )
    checkpoint = write_checkpoint(canonical(root), batch_id, actions, rollback)
    return {
        "status": "executed",
        "batchId": batch_id,
        "count": len(actions),
        "checkpoint": str(checkpoint),
        "rollback": rollback,
    }


def rollback_batch(root: Path, batch_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{8}", batch_id):
        raise OptimizerError("Invalid batch ID")
    batch = canonical(root) / "_temp" / "trash" / batch_id
    transaction = load_json(batch / "transaction.json")
    if transaction.get("state") not in {"complete", "in-progress", "rolled-back"}:
        raise OptimizerError("Transaction is not rollbackable")
    completed = transaction.get("completed", [])
    for record in reversed(completed):
        if record["kind"] == "create_project":
            continue
        if record["kind"] == "trash":
            source = Path(record["from"])
            destination = Path(record["to"])
            if source.exists():
                raise OptimizerError(
                    f"Rollback conflict: original path is occupied: {source}"
                )
            if not destination.exists():
                raise OptimizerError(f"Rollback source is missing: {destination}")
        elif record["kind"] == "copy_project":
            if not Path(record["to"]).exists():
                raise OptimizerError(f"Project copy is missing: {record['to']}")
        elif record["kind"] == "rewrite_text":
            path = Path(record["path"])
            if not path.exists():
                raise OptimizerError(f"Rewritten file is missing: {path}")
            if sha256_file(path) != record["afterSha256"]:
                raise OptimizerError(f"Rewritten file changed after apply: {path}")
    restored: list[dict[str, str]] = []
    for record in reversed(completed):
        if record["kind"] == "trash":
            source = Path(record["from"])
            destination = Path(record["to"])
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(source))
            restored.append({"from": str(destination), "to": str(source)})
        elif record["kind"] == "copy_project":
            destination = Path(record["to"])
            if destination.exists():
                destination.unlink()
                restored.append({"from": str(destination), "to": "removed"})
        elif record["kind"] == "rewrite_text":
            path = Path(record["path"])
            write_text_atomic(path, record["beforeText"])
            restored.append({"from": "transaction text snapshot", "to": str(path)})
        elif record["kind"] == "create_project" and record["created"]:
            restore_project_access(Path(record["path"]), record["access"])
            restored.append({
                "from": record["path"],
                "to": "original path state restored",
            })
        elif record["kind"] == "create_project":
            for raw in record.get("scaffoldCreated", []):
                path = Path(raw)
                if path.is_file():
                    path.unlink(missing_ok=True)
    write_json(batch / "transaction.json", {
        **transaction,
        "state": "rolled-back",
        "rolledBackAt": iso_now(),
        "restored": restored,
    })
    return {
        "status": "rolled-back",
        "batchId": batch_id,
        "restored": restored,
    }


def project_access_snapshot(project: Path) -> dict[str, dict[str, str]]:
    """Record generated files/dirs so rollback can remove only newly created items."""
    values: dict[str, dict[str, str]] = {}
    if not project.exists():
        return values
    stack = [project]
    while stack:
        current = stack.pop()
        values[str(canonical(current))] = {
            "type": "dir" if current.is_dir() else "file",
            "sha256": sha256_file(current) if current.is_file() else "",
        }
        if current.is_dir():
            stack.extend(
                item for item in safe_iterdir(current)
                if not is_reparse(item)
            )
    return values


def restore_project_access(project: Path, before: dict[str, dict[str, str]]) -> None:
    if not project.exists():
        return
    before_paths = {canonical(Path(path)) for path in before}
    for path in sorted(
        (item for item in project.rglob("*") if not is_reparse(item)),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        if canonical(path) not in before_paths:
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
            else:
                path.unlink(missing_ok=True)
    if not before:
        try:
            project.rmdir()
        except OSError:
            pass


def ensure_project_scaffold(
    project: Path,
    slug: str,
    source_tasks: list[str],
    project_actions: list[dict[str, Any]],
) -> list[str]:
    """Create the project's stable entry documents without overwriting user files."""
    project.mkdir(parents=True, exist_ok=True)
    entries = {
        "README.md": (
            f"# {slug}\n\n"
            "## Purpose\n\n"
            "This project was promoted from Codex work that has continuing value.\n\n"
            "## Status\n\n"
            "- Primary edit location: this project directory.\n"
            "- Source history: see `source.md`.\n"
            "- Work files: `work/` when present.\n"
            "- Deliverables: `outputs/` when present.\n"
        ),
        "source.md": (
            f"# Project Sources\n\n"
            f"- Project slug: `{slug}`\n"
            f"- Created: {iso_now()}\n\n"
            "## Date task sources\n\n"
            + "".join(f"- `{task}`\n" for task in source_tasks)
            + "\n## Migrated files\n\n"
            + "".join(
                f"- `{awaiting['source']}` -> `{awaiting['destination']}`\n"
                for awaiting in project_actions
            )
        ),
        "AGENTS.md": (
            "# Project Instructions\n\n"
            "- Start with `README.md`; read `source.md` for provenance.\n"
            "- Keep working files under `work/` and deliverables under `outputs/`.\n"
            "- Use `work/checkpoints/` only for changes that actually need recovery.\n"
            "- Do not copy credentials, databases, caches, or runtime logs here.\n"
        ),
    }
    created: list[str] = []
    for name, content in entries.items():
        path = project / name
        if not path.exists():
            write_text_atomic(path, content)
            created.append(str(path))
    return created


def initialize_workspace(root: Path, codex_home: Path) -> dict[str, Any]:
    root = canonical(root)
    codex_home = canonical(codex_home)
    if (
        root == canonical(Path.home())
        or root == codex_home
        or not root.is_absolute()
        or len(root.parts) <= 1
    ):
        raise OptimizerError(f"Unsafe initialization root: {root}")
    root.mkdir(parents=True, exist_ok=True)
    template_path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "codex-rules.default.json"
    )
    template = load_json(template_path)
    directories = template.get("skeleton", {}).get("directories", [])
    created: list[str] = []
    for relative in directories:
        candidate = canonical(root / relative)
        if not is_within(candidate, root):
            raise OptimizerError(f"Invalid skeleton path: {relative}")
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            created.append(relative)
    coordination = root / "_temp" / "collaboration"
    for relative in ("leases",):
        candidate = coordination / relative
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            created.append(candidate.relative_to(root).as_posix())

    rules_path = root / ".optimize" / "codex-rules.json"
    merged: list[str] = []
    if rules_path.exists():
        current = load_json(rules_path)
    else:
        current = {}
    for key, value in template.items():
        if key not in current:
            current[key] = value
            merged.append(key)
    current["root"] = str(canonical_lexical(root))
    write_json(rules_path, current)
    collaboration_protocol_path = ensure_collaboration_protocol(root)
    return {
        "status": "initialized",
        "root": str(canonical_lexical(root)),
        "createdDirectories": created,
        "rules": str(rules_path),
        "collaborationProtocol": str(collaboration_protocol_path),
        "mergedTopLevelFields": merged,
    }


def agents_block(root: Path) -> str:
    return "\n".join([
        "<!-- codex-optimizer:begin -->",
        "## Codex Optimizer",
        "",
        f"- Default governance root: `{canonical(root)}`.",
        "- Treat `projects/<name>` as the primary edit location for long-lived work;",
        "  use `YYYY-MM-DD/<task>` for ordinary projectless sessions.",
        "- Keep project working files under the project's `work/` and deliverables",
        "  under `outputs/`.",
        "- Use `quick-project` for explicit local or Git projects. Keep the full",
        "  transaction for cleanup and strong checks for destructive changes;",
        "  use size and mtime for ordinary copies.",
        "- Hanako and Codex share this root. Claim a lease only when an active",
        "  lease exists for your target, work is concurrent, or a handoff occurs;",
        "  keep independent Git checkouts and never depend on another Agent's cwd.",
        "- Use `<root>/.optimize/codex-rules.json`; do not alter Hanako's",
        "  `.optimize/rules.json`, private Agent state, sessions, or credentials.",
        "- Cleanup must be evidence-backed and rollbackable. Never automatically",
        "  delete credentials, sessions, databases, plugins, skills, memories,",
        "  unique sources, or runtime data.",
        "<!-- codex-optimizer:end -->",
    ])


def preview_agents(codex_home: Path, root: Path) -> str:
    path = canonical(codex_home) / "AGENTS.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    block = agents_block(root)
    pattern = re.compile(
        r"<!-- codex-optimizer:begin -->.*?<!-- codex-optimizer:end -->",
        flags=re.DOTALL,
    )
    has_marker = pattern.search(existing)
    if has_marker:
        updated = pattern.sub(lambda _: block, existing)
    else:
        separator = "" if not existing or existing.endswith("\n\n") else (
            "\n" if existing.endswith("\n") else "\n\n"
        )
        updated = existing + separator + block + "\n"
    action = "replace" if has_marker else "append"
    return json.dumps({
        "path": str(path),
        "action": action,
        "content": updated,
    }, ensure_ascii=False, indent=2)


def inject_agents(codex_home: Path, root: Path) -> dict[str, Any]:
    path = canonical(codex_home) / "AGENTS.md"
    preview = json.loads(preview_agents(codex_home, root))
    write_text_atomic(path, preview["content"])
    return {
        "status": "injected",
        "path": str(path),
        "action": preview["action"],
    }


def preview_shared_agents(root: Path) -> str:
    path = canonical(root) / "AGENTS.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = re.sub(
        r"<!-- codex-optimizer-shared:begin -->.*?"
        r"<!-- codex-optimizer-shared:end -->",
        "",
        existing,
        flags=re.DOTALL,
    ).strip()
    block = "\n".join([
        "<!-- codex-optimizer-shared:begin -->",
        "## Codex + Hanako Shared Workspace",
        "",
        f"- Shared governance root: `{canonical(root)}`.",
        "- Shared projects are the primary edit location under `projects/<name>/`;",
        "  keep work in `work/` and deliverables in `outputs/`.",
        "- Claim a lease only when an active lease exists, work is concurrent, or",
        "  a handoff occurs; ordinary single-Agent edits need no claim.",
        "- Read `.optimize/COLLABORATION.md`; each Agent keeps its own checkout,",
        "  rules file, credentials, sessions, and private runtime state.",
        "- Never write another Agent's private home. Do not depend on another",
        "  Agent's working directory; use absolute paths from this shared root.",
        "- Cleanup requires evidence, a readable plan, and a rollback path.",
        "  Never automatically delete unique or runtime data.",
        "<!-- codex-optimizer-shared:end -->",
    ])
    pattern = re.compile(
        r"<!-- codex-optimizer-shared:begin -->.*?"
        r"<!-- codex-optimizer-shared:end -->",
        flags=re.DOTALL,
    )
    has_marker = pattern.search(existing)
    if has_marker:
        updated = pattern.sub(lambda _: block, existing)
    else:
        separator = "" if not existing or existing.endswith("\n\n") else (
            "\n" if existing.endswith("\n") else "\n\n"
        )
        updated = existing + separator + block + "\n"
    return json.dumps({
        "path": str(path),
        "action": "replace" if has_marker else "append",
        "block": block,
        "content": updated,
    }, ensure_ascii=False, indent=2)


def inject_shared_agents(root: Path) -> dict[str, Any]:
    root = canonical(root)
    path = root / "AGENTS.md"
    preview = json.loads(preview_shared_agents(root))
    write_text_atomic(path, preview["content"])
    return {
        "status": "injected",
        "path": str(path),
        "action": preview["action"],
    }


def collaboration_protocol(root: Path) -> str:
    return "\n".join([
        "<!-- collaboration-protocol:begin -->",
        "# Codex + Hanako Collaboration Protocol",
        "",
        f"- Shared governance root: `{canonical(root)}`.",
        "- Shared projects: `projects/<name>/`; work under `work/`, deliverables",
        "  under `outputs/`, provenance and migration state in `source.md`.",
        "- Check the lease directory when concurrency is plausible. Claim only",
        "  when another lease is active, work will overlap, or a handoff occurs.",
        "- A lease is a coordination signal, not proof of ownership. Stop when an",
        "  active lease belongs to another Agent or files changed unexpectedly.",
        "- Record actual handoffs with `collaborate handoff`; a quick project",
        "  adoption needs only its `source.md`, not a lease or checkpoint.",
        "- Keep separate Git checkouts. Never assume another Agent shares cwd, open",
        "  files, environment variables, sessions, credentials, or private state.",
        "- Do not edit another Agent's private home. Codex uses",
        "  `.optimize/codex-rules.json`; Hanako uses `.optimize/rules.json`.",
        "- Delete only after evidence, a readable plan, and a rollback path.",
        "  Use SHA256 when a cross-volume copy removes its source or content",
        "  conflicts; never automatically remove unique sources or runtime data.",
        "- For conflicts, preserve both versions and identify them by content.",
        "  Strong hashes are useful here. Do not",
        "  overwrite content merely because another Agent wrote it more recently.",
        "<!-- collaboration-protocol:end -->",
        "",
        "This file is a contract and reference. Runtime leases and handoffs live",
        "under `_temp/collaboration/`. The shared protocol does not merge private",
        "credentials, sessions, memories, or Agent-specific configuration.",
    ])


def ensure_collaboration_protocol(root: Path) -> Path:
    directory = canonical(root) / ".optimize"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "COLLABORATION.md"
    write_text_atomic(path, collaboration_protocol(root) + "\n")
    return path



def purge_safe_trash(root: Path, now: float | None = None) -> dict[str, Any]:
    """Remove only expired safe trash batches with an intact complete transaction."""
    root = canonical(root)
    trash = root / "_temp" / "trash"
    purged: list[str] = []
    retained: list[dict[str, str]] = []
    now = time.time() if now is None else now
    if not trash.exists():
        return {"purged": purged, "retained": retained}
    cutoff = now - TRASH_RETENTION_DAYS * 86400
    for batch in trash.iterdir():
        if not batch.is_dir():
            continue
        tx = batch / "transaction.json"
        if not tx.exists():
            retained.append({"batch": batch.name, "reason": "missing transaction"})
            continue
        try:
            transaction = load_json(tx)
        except OptimizerError:
            retained.append({"batch": batch.name, "reason": "invalid transaction"})
            continue
        if transaction.get("state") != "complete":
            retained.append({"batch": batch.name, "reason": "not complete"})
            continue
        if any(item.get("risk") != "low" for item in transaction.get("completed", [])):
            retained.append({"batch": batch.name, "reason": "high-risk item"})
            continue
        if batch.stat().st_mtime > cutoff:
            retained.append({"batch": batch.name, "reason": "within retention window"})
            continue
        shutil.rmtree(batch)
        purged.append(batch.name)
    return {"purged": purged, "retained": retained}


def archive_batch(
    root: Path,
    source_dir: Path,
    names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Move manifest-backed recovery batches; skip invalid batches and continue."""
    root = canonical(root)
    source_dir = canonical(source_dir)
    source_root = root / "_temp"
    if not source_dir.is_dir() or not is_within(source_dir, source_root):
        raise OptimizerError(f"Source directory must be inside {source_root}: {source_dir}")
    if is_reparse(source_dir):
        raise OptimizerError(f"Refusing reparse-point source: {source_dir}")

    candidates = sorted(
        item for item in safe_iterdir(source_dir, follow_links=False)
        if item.is_dir()
    )
    if names is not None:
        allowed = set(names)
        candidates = [item for item in candidates if item.name in allowed]
        missing = sorted(allowed - {item.name for item in candidates})
        if missing:
            raise OptimizerError(f"Requested batch not found: {', '.join(missing)}")

    eligible: list[tuple[Path, int]] = []
    skipped: list[dict[str, str]] = []
    for candidate in candidates:
        manifest = candidate / ".manifest.jsonl"
        try:
            if is_reparse(candidate):
                raise OptimizerError("batch is a reparse point")
            if not manifest.is_file():
                raise OptimizerError("missing .manifest.jsonl")
            if any(is_reparse(item) for item in candidate.rglob("*")):
                raise OptimizerError("batch contains a reparse point")
            count = 0
            for line in manifest.read_text(encoding="utf-8-sig").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict) or "from" not in record or "to" not in record:
                    raise OptimizerError("manifest entry lacks from/to")
                source_path = Path(str(record["from"]))
                destination_path = Path(str(record["to"]))
                if not source_path.is_absolute() or not destination_path.is_absolute():
                    raise OptimizerError("manifest entry uses a relative path")
                if "反悔区" not in destination_path.parts:
                    raise OptimizerError("manifest destination is not a recovery batch")
                count += 1
            if not count:
                raise OptimizerError("manifest is empty")
            eligible.append((candidate, count))
        except (OSError, UnicodeError, json.JSONDecodeError, OptimizerError) as exc:
            skipped.append({"name": candidate.name, "reason": str(exc)})

    if not eligible:
        return {"status": "nothing-to-do", "moved": [], "skipped": skipped}

    batch_id = dt.datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    destination_root = root / "_temp" / "archive" / "legacy-trash" / batch_id
    index = destination_root / "archive-index.jsonl"
    transaction = destination_root / "transaction.json"
    moved: list[dict[str, Any]] = []
    try:
        for source, count in eligible:
            destination = destination_root / source.name
            if destination.exists():
                raise OptimizerError(f"Archive target already exists: {destination}")
            shutil.move(str(source), str(destination))
            record = {
                "kind": "legacy-archive",
                "name": source.name,
                "from": str(source),
                "to": str(destination),
                "manifestEntries": count,
                "timestamp": iso_now(),
            }
            moved.append(record)
            append_manifest(index, record)
            write_json(transaction, {
                "batchId": batch_id,
                "state": "in-progress",
                "completed": moved,
            })
        write_json(transaction, {
            "batchId": batch_id,
            "state": "complete",
            "completed": moved,
            "skipped": skipped,
            "completedAt": iso_now(),
        })
    except Exception:
        for record in reversed(moved):
            source = Path(record["from"])
            destination = Path(record["to"])
            if destination.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
        write_json(transaction, {
            "batchId": batch_id,
            "state": "rolled-back",
            "completed": moved,
            "skipped": skipped,
            "failedAt": iso_now(),
        })
        raise

    return {
        "status": "complete",
        "batchId": batch_id,
        "moved": [record["name"] for record in moved],
        "skipped": skipped,
        "index": str(index),
        "transaction": str(transaction),
    }


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def diagnostic_summary(report: dict[str, Any]) -> str:
    cleanup = len(report["cleanupCandidates"])
    low = sum(1 for item in report["cleanupCandidates"] if item["risk"] == "low")
    candidates = len(report["projectCandidates"])
    return "\n".join([
        "Codex Optimizer diagnostic summary",
        f"- Root: {report['root']} ({format_bytes(report['totals']['rootBytes'])})",
        f"- Registered projects: {len(report['projectRoots'])} ({format_bytes(report['totals']['projectBytes'])})",
        f"- Codex home inventory: {format_bytes(report['totals']['codexBytesApprox'])}"
        + (
            " (bounded)"
            if any(
                item.get("truncated")
                for item in report["codexDirectories"]
            )
            else ""
        ),
        f"- Cleanup candidates: {cleanup} ({low} low risk)",
        f"- Project promotion candidates: {candidates}",
        f"- Estimated safe reclaimable: {format_bytes(report['estimatedSafeReclaimBytes'])}",
        f"- Dated task directories: {report['datedTasks']}",
        f"- Warnings: {len(report['warnings'])}",
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex_optimizer.py",
        description="Diagnose Codex workspaces and execute rollbackable cleanup plans.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
        subparser.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
        subparser.add_argument(
            "--project-root", type=Path, action="append", default=[],
            help="A Codex-added project path; repeat for multiple projects.",
        )

    diagnose = sub.add_parser("diagnose", help="Run a read-only diagnostic.")
    common(diagnose)
    diagnose.add_argument("--json", action="store_true", help="Write a JSON report.")
    diagnose.add_argument("--plan", action="store_true", help="Write a cleanup plan.")
    diagnose.add_argument(
        "--promote-projects", action="store_true",
        help="Include eligible project-promotion actions in the plan.",
    )
    diagnose.add_argument(
        "--explicit-project",
        action="append",
        default=[],
        help="Declare a project slug that the user explicitly wants to create.",
    )
    diagnose.add_argument(
        "--session-id", action="append", default=[],
        help="Related Codex session IDs whose usage ledger entries are relevant.",
    )
    diagnose.add_argument(
        "--rewrite-references", action="store_true",
        help="Include textual reference rewrites in a project plan.",
    )
    diagnose.add_argument("--deep", action="store_true", help="Enable deeper metadata checks.")
    diagnose.add_argument(
        "--follow-links", action="store_true",
        help="Inspect links only if they remain inside an allowed root.",
    )

    quick = sub.add_parser(
        "quick-project",
        help="Adopt one explicit local or Git project without a cleanup plan.",
    )
    common(quick)
    quick_source = quick.add_mutually_exclusive_group(required=True)
    quick_source.add_argument("--source", type=Path)
    quick_source.add_argument("--git-url")
    quick.add_argument("--slug", default="")
    quick.add_argument("--description", default="")
    quick.add_argument(
        "--move",
        action="store_true",
        help="Relocate a local source instead of copying it.",
    )

    archive = sub.add_parser(
        "archive-batch",
        help="Archive manifest-backed recovery batches in one transaction.",
    )
    common(archive)
    archive.add_argument("--source-dir", type=Path, required=True)
    archive.add_argument("--name", action="append", default=[])

    apply = sub.add_parser("apply", help="Validate and optionally execute a plan.")
    common(apply)
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--execute", action="store_true")

    rollback = sub.add_parser("rollback", help="Restore a completed batch.")
    common(rollback)
    rollback.add_argument("--batch-id", required=True)

    purge = sub.add_parser("purge", help="Purge expired safe trash batches.")
    common(purge)
    purge.add_argument("--execute", action="store_true")
    purge.add_argument("--older-than-days", type=int, default=TRASH_RETENTION_DAYS)

    init = sub.add_parser("init", help="Initialize the mixed governance skeleton.")
    common(init)
    init.add_argument("--dry-run", action="store_true")

    agents_preview = sub.add_parser(
        "agents-preview", help="Print the exact codex-optimizer AGENTS.md block."
    )
    common(agents_preview)

    agents_inject = sub.add_parser(
        "agents-inject", help="Inject the authorized codex-optimizer AGENTS.md block."
    )
    common(agents_inject)

    shared_preview = sub.add_parser(
        "shared-agents-preview",
        help="Preview the shared Codex/Hanako project AGENTS.md block.",
    )
    common(shared_preview)

    shared_inject = sub.add_parser(
        "shared-agents-inject",
        help="Inject the shared Codex/Hanako project AGENTS.md block.",
    )
    common(shared_inject)

    collaborate = sub.add_parser(
        "collaborate",
        help="Inspect or manage shared project leases and handoffs.",
    )
    common(collaborate)
    collab = collaborate.add_subparsers(dest="collab_action", required=True)
    claim = collab.add_parser("claim")
    claim.add_argument("--target", type=Path, required=True)
    claim.add_argument("--agent", default="codex")
    claim.add_argument("--purpose", required=True)
    claim.add_argument("--session-id", default="")
    claim.add_argument("--lease-minutes", type=int, default=DEFAULT_LEASE_MINUTES)
    claim.add_argument("--takeover", action="store_true")
    release = collab.add_parser("release")
    release.add_argument("--target", type=Path, required=True)
    release.add_argument("--agent", default="codex")
    status = collab.add_parser("status")
    status.add_argument("--target", type=Path, required=True)
    handoff = collab.add_parser("handoff")
    handoff.add_argument("--target", type=Path, required=True)
    handoff.add_argument("--agent", default="codex")
    handoff.add_argument("--next-agent", required=True)
    handoff.add_argument("--summary", required=True)
    handoff.add_argument("--session-id", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = canonical(args.root)
    codex_home = canonical(args.codex_home)
    try:
        if args.command == "diagnose":
            report = build_report(
                root,
                codex_home,
                args.project_root,
                deep=args.deep,
                follow_links=args.follow_links,
            )
            print(diagnostic_summary(report))
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            if args.json:
                output = root / "_temp" / "exports" / f"{stamp}-codex-optimizer.json"
                write_json(output, report, exclusive=False)
                print(f"JSON report: {output}")
            if args.plan:
                plan = create_plan(
                    report,
                    root,
                    codex_home,
                    project_mode="promote" if args.promote_projects else None,
                    session_ids=args.session_id,
                    rewrite_references=args.rewrite_references,
                    explicit_projects=args.explicit_project,
                )
                output = root / "_temp" / "plans" / f"{stamp}-codex-optimizer-plan.json"
                write_json(output, plan, exclusive=False)
                print(f"Plan: {output} ({len(plan['actions'])} actions)")
            return 0
        if args.command == "quick-project":
            result = quick_project(
                root,
                source=args.source,
                git_url=args.git_url or "",
                slug=args.slug,
                move=args.move,
                description=args.description,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "archive-batch":
            result = archive_batch(root, args.source_dir, args.name or None)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "apply":
            result = apply_plan(args.plan, root, codex_home, args.execute)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "rollback":
            result = rollback_batch(root, args.batch_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "purge":
            trash = root / "_temp" / "trash"
            if not args.execute:
                result = purge_safe_trash(
                    root,
                    now=time.time() - (
                        max(0, args.older_than_days - TRASH_RETENTION_DAYS) * 86400
                    ),
                )
                print(json.dumps({"status": "dry-run", **result}, ensure_ascii=False, indent=2))
            else:
                result = purge_safe_trash(root)
                print(json.dumps({"status": "executed", **result}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "init":
            if args.dry_run:
                print(json.dumps({
                    "status": "dry-run",
                    "root": str(root),
                    "codexHome": str(codex_home),
                }, ensure_ascii=False, indent=2))
            else:
                print(json.dumps(
                    initialize_workspace(root, codex_home),
                    ensure_ascii=False,
                    indent=2,
                ))
            return 0
        if args.command == "agents-preview":
            print(preview_agents(codex_home, root))
            return 0
        if args.command == "agents-inject":
            print(json.dumps(
                inject_agents(codex_home, root),
                ensure_ascii=False,
                indent=2,
            ))
            return 0
        if args.command == "shared-agents-preview":
            print(preview_shared_agents(root))
            return 0
        if args.command == "shared-agents-inject":
            print(json.dumps(
                inject_shared_agents(root),
                ensure_ascii=False,
                indent=2,
            ))
            return 0
        if args.command == "collaborate":
            if args.collab_action == "claim":
                result = collaboration_claim(
                    root,
                    args.target,
                    args.agent,
                    args.purpose,
                    args.session_id,
                    args.lease_minutes,
                    args.takeover,
                )
            elif args.collab_action == "release":
                result = collaboration_release(root, args.target, args.agent)
            elif args.collab_action == "status":
                result = collaboration_status(root, args.target)
            elif args.collab_action == "handoff":
                result = collaboration_handoff(
                    root,
                    args.target,
                    args.agent,
                    args.summary,
                    args.next_agent,
                    args.session_id,
                )
            else:
                raise OptimizerError(
                    f"Unsupported collaboration action: {args.collab_action}"
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    except OptimizerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

