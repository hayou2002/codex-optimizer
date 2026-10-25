from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    Path.home()
    / ".codex"
    / "skills"
    / ".system"
    / "skill-creator"
    / "scripts"
    / "quick_validate.py"
)


class SkillValidationTests(unittest.TestCase):
    def test_quick_validate_with_utf8_content(self) -> None:
        if not VALIDATOR_PATH.exists():
            self.skipTest("skill-creator quick_validate.py is unavailable")
        spec = importlib.util.spec_from_file_location(
            "quick_validate", VALIDATOR_PATH
        )
        assert spec and spec.loader
        validator = importlib.util.module_from_spec(spec)
        previous_read_text = Path.read_text

        def read_utf8(path: Path, *args: object, **kwargs: object) -> str:
            kwargs.setdefault("encoding", "utf-8")
            return previous_read_text(path, *args, **kwargs)

        Path.read_text = read_utf8
        try:
            spec.loader.exec_module(validator)
            valid, message = validator.validate_skill(PROJECT)
        finally:
            Path.read_text = previous_read_text
        self.assertTrue(valid, message)

    def test_release_builder_uses_runtime_allowlist(self) -> None:
        builder_path = PROJECT / "scripts" / "build_release.py"
        spec = importlib.util.spec_from_file_location(
            "build_release", builder_path
        )
        assert spec and spec.loader
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "codex-optimizer.skill.zip"
            result = builder.build(PROJECT, destination)
            self.assertTrue(destination.is_file())
            self.assertEqual(
                result["files"],
                list(builder.RUNTIME_FILES),
            )
            self.assertIn(
                "references/08-collaboration.md",
                result["files"],
            )
            checksum = (destination.parent / (
                destination.name + ".sha256"
            )).read_text(encoding="ascii")
            self.assertTrue(checksum.startswith(result["sha256"]))


if __name__ == "__main__":
    unittest.main()
