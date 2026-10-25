from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import shutil
import time
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts" / "codex_optimizer.py"
SPEC = importlib.util.spec_from_file_location("codex_optimizer", SCRIPT)
assert SPEC and SPEC.loader
optimizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(optimizer)


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "governance"
        self.codex_home = self.base / "codex-home"
        self.root.mkdir()
        self.codex_home.mkdir()
        for path in (
            "_temp/trash", "_temp/plans", "_temp/exports",
            "_temp/checkpoints", "_temp/data", "projects",
        ):
            (self.root / path).mkdir(parents=True, exist_ok=True)

    def write(self, relative: str, content: str = "hello") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def plan(self, actions: list[dict[str, object]]) -> tuple[Path, dict[str, object]]:
        now = dt.datetime.now(dt.timezone.utc)
        value = {
            "schemaVersion": optimizer.SCHEMA_VERSION,
            "kind": "codex-optimizer-plan",
            "createdAt": now.isoformat(timespec="seconds"),
            "expiresAt": (
                now + dt.timedelta(minutes=30)
            ).isoformat(timespec="seconds"),
            "root": str(self.root),
            "codexHome": str(self.codex_home),
            "projectRoots": [],
            "actions": actions,
        }
        value["planHash"] = optimizer.hashlib.sha256(
            json.dumps(
                value, sort_keys=True, ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        path = self.root / "_temp" / "plans" / "plan.json"
        optimizer.write_json(path, value)
        return path, value

    def trash_action(self, path: Path) -> dict[str, object]:
        record = optimizer.path_record(path)
        digest = record["sha256"] if path.is_file() else optimizer.tree_digest(path)
        return {
            "kind": "trash",
            "source": str(path),
            "destination": str(
                self.root / "_temp" / "trash" / "<batch>" / "items" / path.name
            ),
            "sha256": digest,
            "is_dir": path.is_dir(),
            "size": path.stat().st_size,
            "mtime": path.stat().st_mtime,
            "risk": "low",
            "reason": "test cache",
            "references": [],
        }


class DiagnosticTests(WorkspaceTestCase):
    def test_diagnose_is_read_only(self) -> None:
        (self.root / ".cache").mkdir()
        (self.root / ".cache" / "blob.bin").write_bytes(b"x")
        before = sorted(
            str(path.relative_to(self.root))
            for path in self.root.rglob("*")
        )
        report = optimizer.build_report(self.root, self.codex_home, [])
        after = sorted(
            str(path.relative_to(self.root))
            for path in self.root.rglob("*")
        )
        self.assertEqual(before, after)
        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(len(report["cleanupCandidates"]), 1)
        self.assertIn("codexBytesApprox", report["totals"])

    def test_plan_contains_directory_tree_hash(self) -> None:
        cache = self.root / ".cache"
        cache.mkdir()
        (cache / "blob.bin").write_text("cache", encoding="utf-8")
        report = optimizer.build_report(self.root, self.codex_home, [])
        plan = optimizer.create_plan(
            report,
            self.root,
            self.codex_home,
        )
        action = next(
            item for item in plan["actions"] if item["kind"] == "trash"
        )
        self.assertEqual(action["sha256"], optimizer.tree_digest(cache))

    def test_referenced_cache_is_protected(self) -> None:
        cache = self.root / ".cache" / "artifact.bin"
        cache.parent.mkdir()
        cache.write_text("cache", encoding="utf-8")
        self.write("README.md", f"Uses {cache}")
        report = optimizer.build_report(self.root, self.codex_home, [])
        candidate = next(
            item for item in report["cleanupCandidates"]
            if item["path"] == str(optimizer.canonical(cache.parent))
        )
        self.assertEqual(candidate["risk"], "high")
        self.assertTrue(candidate["references"])

    def test_project_candidate_detects_deliverables(self) -> None:
        task = self.root / "2026-10-25" / "sample"
        task.mkdir(parents=True)
        (task / "README.md").write_text("Project", encoding="utf-8")
        (task / "main.py").write_text("print('hi')", encoding="utf-8")
        report = optimizer.build_report(self.root, self.codex_home, [])
        self.assertEqual(report["projectCandidates"][0]["slug"], "sample")
        self.assertGreaterEqual(report["projectCandidates"][0]["score"], 6)


class PlanValidationTests(WorkspaceTestCase):
    def test_trash_and_rollback(self) -> None:
        cache = self.root / ".cache"
        cache.mkdir()
        (cache / "cache.bin").write_text("cache", encoding="utf-8")
        plan_path, _ = self.plan([self.trash_action(cache)])
        result = optimizer.apply_plan(
            plan_path, self.root, self.codex_home, execute=True
        )
        self.assertFalse(cache.exists())
        self.assertEqual(result["status"], "executed")
        manifest = (
            self.root / "_temp" / "trash" / result["batchId"] / "manifest.jsonl"
        )
        self.assertTrue(manifest.exists())
        optimizer.rollback_batch(self.root, result["batchId"])
        self.assertTrue(cache.exists())
        self.assertEqual((cache / "cache.bin").read_text(), "cache")

    def test_expired_plan_rejected(self) -> None:
        cache = self.root / ".cache"
        cache.mkdir()
        plan_path, value = self.plan([self.trash_action(cache)])
        value["expiresAt"] = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        ).isoformat(timespec="seconds")
        value["planHash"] = optimizer.hashlib.sha256(
            json.dumps(
                {key: val for key, val in value.items() if key != "planHash"},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        optimizer.write_json(plan_path, value)
        with self.assertRaisesRegex(optimizer.OptimizerError, "expired"):
            optimizer.apply_plan(
                plan_path, self.root, self.codex_home, execute=True
            )

    def test_hash_drift_rejected(self) -> None:
        cache = self.root / ".cache"
        cache.mkdir()
        plan_path, _ = self.plan([self.trash_action(cache)])
        (cache / "new.bin").write_text("changed", encoding="utf-8")
        with self.assertRaises(optimizer.OptimizerError):
            optimizer.apply_plan(
                plan_path, self.root, self.codex_home, execute=True
            )

    def test_cross_boundary_source_is_rejected(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        target = outside / "file.txt"
        target.write_text("outside", encoding="utf-8")
        action = self.trash_action(target)
        plan_path, _ = self.plan([action])
        with self.assertRaisesRegex(optimizer.OptimizerError, "outside"):
            optimizer.apply_plan(
                plan_path, self.root, self.codex_home, execute=True
            )

    def test_copy_from_registered_project_is_allowed(self) -> None:
        project = self.base / "external-project"
        project.mkdir()
        source = project / "src.py"
        source.write_text("print('ok')", encoding="utf-8")
        destination = (
            self.root / "projects" / "external" / "work" / "src.py"
        )
        action = {
            "kind": "copy_project",
            "source": str(source),
            "destination": str(destination),
            "sha256": optimizer.sha256_file(source),
            "size": source.stat().st_size,
            "risk": "high",
            "references": [],
            "reason": "explicit project source",
            "projectSlug": "external",
            "sourceTasks": [str(project)],
        }
        path, value = self.plan([])
        value["projectRoots"] = [str(project)]
        value["actions"] = [
            {
                "kind": "create_project",
                "source": "",
                "destination": str(self.root / "projects" / "external"),
                "sha256": "",
                "size": 0,
                "risk": "high",
                "references": [],
                "reason": "explicit project",
                "projectSlug": "external",
                "sourceTasks": [str(project)],
            },
            action,
        ]
        value["planHash"] = optimizer.hashlib.sha256(
            json.dumps(
                {key: val for key, val in value.items() if key != "planHash"},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        optimizer.write_json(path, value)
        result = optimizer.apply_plan(
            path, self.root, self.codex_home, execute=True
        )
        self.assertEqual(result["status"], "executed")
        self.assertEqual(destination.read_text(), "print('ok')")

    def test_plan_integrity_hash_is_required(self) -> None:
        cache = self.root / ".cache"
        cache.mkdir()
        (cache / "blob.bin").write_text("cache", encoding="utf-8")
        plan_path, value = self.plan([self.trash_action(cache)])
        value["actions"][0]["reason"] = "tampered"
        optimizer.write_json(plan_path, value)
        with self.assertRaisesRegex(
            optimizer.OptimizerError, "integrity hash"
        ):
            optimizer.apply_plan(
                plan_path, self.root, self.codex_home, execute=True
            )

    def test_codex_state_and_secret_paths_are_rejected(self) -> None:
        sensitive = {
            "auth.json": "secret",
            "config.toml": "[features]\n",
            "thread_history_1.sqlite": "database",
            "memories/note.md": "memory",
            "skills/sample/SKILL.md": "# skill",
            "sessions/session.jsonl": "{}",
            ".env": "TOKEN=secret",
        }
        for relative, content in sensitive.items():
            path = self.codex_home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            if path.name not in {"config.toml", "thread_history_1.sqlite"}:
                self.assertFalse(
                    optimizer.text_content_candidate(path),
                    relative,
                )
            with self.subTest(path=relative):
                with self.assertRaises(optimizer.OptimizerError):
                    optimizer.validate_plan(
                        {
                            "kind": "codex-optimizer-plan",
                            "schemaVersion": 1,
                            "root": str(self.root),
                            "codexHome": str(self.codex_home),
                            "expiresAt": (
                                dt.datetime.now(dt.timezone.utc)
                                + dt.timedelta(minutes=1)
                            ).isoformat(timespec="seconds"),
                            "actions": [{
                                "kind": "trash",
                                "source": str(path),
                                "destination": str(
                                    self.root / "_temp" / "trash"
                                    / "<batch>" / "items" / path.name
                                ),
                                "sha256": optimizer.path_record(path)["sha256"],
                                "size": path.stat().st_size,
                                "risk": "low",
                                "references": [],
                                "reason": "test",
                            }],
                            "planHash": "wrong",
                        },
                        self.root,
                        self.codex_home,
                    )


class RecoveryAndBoundaryTests(WorkspaceTestCase):
    def make_batch(
        self, name: str, risk: str, age_days: int
    ) -> Path:
        batch = self.root / "_temp" / "trash" / name
        batch.mkdir(parents=True)
        (batch / "items").mkdir()
        (batch / "items" / "cache.bin").write_text("cache", encoding="utf-8")
        optimizer.write_json(
            batch / "transaction.json",
            {
                "batchId": name,
                "state": "complete",
                "completed": [{
                    "kind": "trash",
                    "from": str(self.root / ".cache"),
                    "to": str(batch / "items" / "cache"),
                    "sha256": "a" * 64,
                    "risk": risk,
                }],
            },
        )
        old = time.time() - age_days * 86400
        os.utime(batch, (old, old))
        return batch

    def test_purge_removes_only_expired_low_risk_batches(self) -> None:
        old_safe = self.make_batch("20260101T000000-00000001", "low", 15)
        old_high = self.make_batch("20260101T000000-00000002", "high", 15)
        young_safe = self.make_batch("20260120T000000-00000003", "low", 1)
        result = optimizer.purge_safe_trash(self.root)
        self.assertFalse(old_safe.exists())
        self.assertTrue(old_high.exists())
        self.assertTrue(young_safe.exists())
        self.assertEqual(
            result["purged"], ["20260101T000000-00000001"]
        )
        retained = {item["batch"]: item["reason"] for item in result["retained"]}
        self.assertEqual(retained["20260101T000000-00000002"], "high-risk item")
        self.assertEqual(
            retained["20260120T000000-00000003"],
            "within retention window",
        )

    def test_default_scan_does_not_follow_reparse_points(self) -> None:
        outside = self.base / "outside-secret.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.root / "linked-secret.txt"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.assertEqual(optimizer.tree_size(self.root), (0, 0))
        self.assertEqual(optimizer.tree_size(self.root, follow_links=True), (7, 1))

    def test_default_tree_read_budget_marks_truncation(self) -> None:
        for index in range(8):
            (self.root / f"file-{index}.txt").write_text(
                "x",
                encoding="utf-8",
            )
        size, files, truncated = optimizer.tree_size_limited(
            self.root,
            max_entries=4,
        )
        self.assertTrue(truncated)
        self.assertLessEqual(files, 4)
        self.assertLess(size, 8)


class ProjectAndConfigurationTests(WorkspaceTestCase):
    def test_initialization_is_idempotent_and_preserves_values(self) -> None:
        rules = self.root / ".optimize" / "codex-rules.json"
        rules.parent.mkdir()
        rules.write_text(
            json.dumps({"schemaVersion": 1, "root": "custom-value"}),
            encoding="utf-8",
        )
        first = optimizer.initialize_workspace(self.root, self.codex_home)
        second = optimizer.initialize_workspace(self.root, self.codex_home)
        self.assertEqual(first["status"], "initialized")
        self.assertEqual(second["createdDirectories"], [])
        current = json.loads(rules.read_text(encoding="utf-8"))
        self.assertEqual(current["root"], str(optimizer.canonical(self.root)))
        self.assertIn("operation", current)

    def test_agents_injection_preserves_other_content(self) -> None:
        agents = self.codex_home / "AGENTS.md"
        agents.write_text("# Other rules\n\nKeep me.\n", encoding="utf-8")
        optimizer.inject_agents(self.codex_home, self.root)
        content = agents.read_text(encoding="utf-8")
        self.assertIn("Keep me.", content)
        self.assertIn("<!-- codex-optimizer:begin -->", content)
        optimizer.inject_agents(self.codex_home, self.root)
        content = agents.read_text(encoding="utf-8")
        self.assertEqual(content.count("<!-- codex-optimizer:begin -->"), 1)

    def test_project_promotion_and_rollback(self) -> None:
        task_one = self.root / "2026-10-24" / "sample-project"
        task_two = self.root / "2026-10-25" / "sample-project"
        task_one.mkdir(parents=True)
        task_two.mkdir(parents=True)
        (task_one / "README.md").write_text("one", encoding="utf-8")
        (task_two / "README.md").write_text("two", encoding="utf-8")
        (task_two / "main.py").write_text("print('two')", encoding="utf-8")
        report = optimizer.build_report(self.root, self.codex_home, [])
        plan = optimizer.create_plan(
            report, self.root, self.codex_home, project_mode="promote"
        )
        plan_path = self.root / "_temp" / "plans" / "project-plan.json"
        optimizer.write_json(plan_path, plan)
        result = optimizer.apply_plan(
            plan_path, self.root, self.codex_home, execute=True
        )
        project = self.root / "projects" / "sample-project"
        self.assertTrue((project / "README.md").exists())
        self.assertTrue((project / "source.md").exists())
        self.assertTrue((project / "AGENTS.md").exists())
        self.assertEqual(result["status"], "executed")
        optimizer.rollback_batch(self.root, result["batchId"])
        self.assertFalse(project.exists())

    def test_implicit_project_requires_cross_date_evidence(self) -> None:
        task = self.root / "2026-10-25" / "single-session"
        task.mkdir(parents=True)
        (task / "README.md").write_text("one", encoding="utf-8")
        (task / "main.py").write_text("print('one')", encoding="utf-8")
        report = optimizer.build_report(self.root, self.codex_home, [])
        plan = optimizer.create_plan(
            report,
            self.root,
            self.codex_home,
            project_mode="promote",
        )
        self.assertFalse(
            any(item["kind"] == "create_project" for item in plan["actions"])
        )

    def test_explicit_project_can_promote_single_session(self) -> None:
        task = self.root / "2026-10-25" / "single-session"
        task.mkdir(parents=True)
        (task / "README.md").write_text("one", encoding="utf-8")
        (task / "main.py").write_text("print('one')", encoding="utf-8")
        report = optimizer.build_report(self.root, self.codex_home, [])
        plan = optimizer.create_plan(
            report,
            self.root,
            self.codex_home,
            project_mode="promote",
            explicit_projects=["single-session"],
        )
        creates = [
            item for item in plan["actions"]
            if item["kind"] == "create_project"
        ]
        self.assertEqual(len(creates), 1)
        self.assertTrue(creates[0]["explicit"])

    def test_project_copy_uses_work_and_outputs_subtrees(self) -> None:
        task = self.root / "2026-10-25" / "classified-project"
        (task / "src").mkdir(parents=True)
        (task / "assets").mkdir()
        (task / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
        (task / "README.md").write_text("Project", encoding="utf-8")
        (task / "assets" / "logo.txt").write_text("asset", encoding="utf-8")
        report = optimizer.build_report(self.root, self.codex_home, [])
        plan = optimizer.create_plan(
            report,
            self.root,
            self.codex_home,
            project_mode="promote",
            explicit_projects=["classified-project"],
        )
        destinations = {
            Path(item["source"]).name: Path(item["destination"])
            for item in plan["actions"]
            if item["kind"] == "copy_project"
        }
        expected = {
            "main.py": (
                self.root / "projects" / "classified-project"
                / "work" / "src" / "main.py"
            ),
            "logo.txt": (
                self.root / "projects" / "classified-project"
                / "work" / "assets" / "logo.txt"
            ),
            "README.md": (
                self.root / "projects" / "classified-project"
                / "outputs" / "README.md"
            ),
        }
        for name, expected_path in expected.items():
            self.assertEqual(
                optimizer.canonical(destinations[name]),
                optimizer.canonical(expected_path),
            )

    def test_text_rewrite_and_rollback(self) -> None:
        target = self.write("README.md", "old/path/file.txt")
        action = {
            "kind": "rewrite_text",
            "source": str(target),
            "destination": str(target),
            "sha256": optimizer.sha256_file(target),
            "is_dir": False,
            "size": target.stat().st_size,
            "mtime": target.stat().st_mtime,
            "risk": "high",
            "reason": "test rewrite",
            "references": [],
            "oldText": "old/path",
            "newText": "new/path",
        }
        plan_path, _ = self.plan([action])
        result = optimizer.apply_plan(
            plan_path, self.root, self.codex_home, execute=True
        )
        self.assertEqual(target.read_text(), "new/path/file.txt")
        optimizer.rollback_batch(self.root, result["batchId"])
        self.assertEqual(target.read_text(), "old/path/file.txt")

    def test_agents_marker_preview_does_not_write(self) -> None:
        agents = self.codex_home / "AGENTS.md"
        agents.write_text("# Other", encoding="utf-8")
        preview = json.loads(
            optimizer.preview_agents(self.codex_home, self.root)
        )
        self.assertEqual(agents.read_text(), "# Other")
        self.assertIn("<!-- codex-optimizer:begin -->", preview["content"])

    def test_agents_marker_replacement_is_in_place(self) -> None:
        agents = self.codex_home / "AGENTS.md"
        agents.write_text(
            "# Before\n\n"
            "<!-- codex-optimizer:begin -->\n"
            "stale\n"
            "<!-- codex-optimizer:end -->\n\n"
            "# After\n",
            encoding="utf-8",
        )
        optimizer.inject_agents(self.codex_home, self.root)
        content = agents.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("# Before\n\n"))
        self.assertTrue(content.endswith("\n\n# After\n"))
        self.assertNotIn("stale", content)
        self.assertEqual(content.count("<!-- codex-optimizer:begin -->"), 1)

    def test_collaboration_lease_conflict_and_handoff(self) -> None:
        project = self.root / "projects" / "shared"
        project.mkdir(parents=True)
        claimed = optimizer.collaboration_claim(
            self.root,
            project,
            "codex",
            "implement feature",
            session_id="session-1",
        )
        self.assertEqual(claimed["status"], "claimed")
        repeated = optimizer.collaboration_claim(
            self.root,
            project,
            "codex",
            "continue same task",
            session_id="session-1",
        )
        self.assertEqual(repeated["status"], "already-held")
        status = optimizer.collaboration_status(self.root, project)
        self.assertEqual(status["lease"]["agent"], "codex")
        with self.assertRaisesRegex(optimizer.OptimizerError, "held by codex"):
            optimizer.collaboration_claim(
                self.root, project, "hanako", "review"
            )
        handoff = optimizer.collaboration_handoff(
            self.root,
            project,
            "codex",
            "tests pass, ready for review",
            "hanako",
            "session-1",
        )
        self.assertEqual(handoff["nextAgent"], "hanako")
        optimizer.collaboration_release(self.root, project, "codex")
        self.assertEqual(
            optimizer.collaboration_status(self.root, project)["status"],
            "free",
        )

    def test_collaboration_rejects_private_codex_paths(self) -> None:
        with self.assertRaisesRegex(
            optimizer.OptimizerError, "private or runtime"
        ):
            optimizer.collaboration_claim(
                self.root,
                self.root / "projects" / "shared" / ".git",
                "codex",
                "edit history",
            )

    def test_shared_agents_marker_is_idempotent(self) -> None:
        agents = self.root / "AGENTS.md"
        agents.write_text("# Shared instructions\n\nKeep me.\n", encoding="utf-8")
        optimizer.inject_shared_agents(self.root)
        optimizer.inject_shared_agents(self.root)
        content = agents.read_text(encoding="utf-8")
        self.assertIn("Keep me.", content)
        self.assertEqual(
            content.count("<!-- codex-optimizer-shared:begin -->"), 1
        )

    def test_shared_block_preserves_unrelated_agents_text(self) -> None:
        agents = self.root / "AGENTS.md"
        agents.write_text(
            "# Existing\n\n<!-- optimize-master:begin -->\nkeep\n"
            "<!-- optimize-master:end -->\n",
            encoding="utf-8",
        )
        preview = json.loads(optimizer.preview_shared_agents(self.root))
        self.assertNotIn("<!-- optimize-master:begin -->", preview["block"])
        self.assertNotIn("# Existing", preview["block"])
        self.assertIn("# Existing", preview["content"])
        self.assertIn("<!-- optimize-master:begin -->", preview["content"])

    def test_initialize_creates_shared_protocol(self) -> None:
        result = optimizer.initialize_workspace(self.root, self.codex_home)
        protocol = self.root / ".optimize" / "COLLABORATION.md"
        self.assertTrue(protocol.exists())
        self.assertEqual(
            optimizer.canonical(Path(result["collaborationProtocol"])),
            optimizer.canonical(protocol),
        )
        content = protocol.read_text(encoding="utf-8")
        self.assertIn("codex-rules.json", content)
        self.assertIn("rules.json", content)


if __name__ == "__main__":
    unittest.main()

