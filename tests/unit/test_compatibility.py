import json
from pathlib import Path
import tempfile
import unittest

from specromancy.adapters.base import ADAPTER_MANIFEST_PATH, _load_manifest
from specromancy.artifacts.frontmatter import parse_frontmatter
from specromancy.compatibility import (
    ADAPTER_MANIFEST_VERSION,
    ARTIFACT_SCHEMA_VERSION,
    PIPELINE_CONTRACT_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
    require_supported_version,
)
from specromancy.errors import ValidationError


class CompatibilityTests(unittest.TestCase):
    def test_independent_current_versions(self) -> None:
        self.assertEqual(PIPELINE_CONTRACT_VERSION, "1")
        self.assertEqual(RUN_MANIFEST_SCHEMA_VERSION, "1")
        self.assertEqual(ARTIFACT_SCHEMA_VERSION, "1")
        self.assertEqual(ADAPTER_MANIFEST_VERSION, 1)

    def test_future_pipeline_and_run_versions_are_rejected(self) -> None:
        for kind, value, supported in (
            ("Pipeline contract", "2", PIPELINE_CONTRACT_VERSION),
            ("Run manifest schema", "2", RUN_MANIFEST_SCHEMA_VERSION),
        ):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                require_supported_version(kind, value, supported)

    def test_future_artifact_version_is_rejected(self) -> None:
        document = (
            '---\nschema-version: "2"\nrun-id: "future-run"\n'
            'stage: "request"\nstatus: "ready"\n'
            'created-at: "2026-09-23T00:00:00Z"\n---\n\n# Request\n'
        )
        with self.assertRaisesRegex(ValidationError, "not supported"):
            parse_frontmatter(document)

    def test_future_adapter_manifest_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / ADAPTER_MANIFEST_PATH
            target.parent.mkdir(parents=True)
            target.write_text(
                json.dumps({"schema_version": 2, "files": [], "adapters": {}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValidationError, "unsupported"):
                _load_manifest(root, required=True)


if __name__ == "__main__":
    unittest.main()
