import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from specromancy.io import (
    append_json_line,
    atomic_write_json,
    atomic_write_text,
    canonical_json,
    sha256_file,
    sha256_text,
)


class IoTests(unittest.TestCase):
    def test_canonical_json_sorts_keys_and_has_final_newline(self) -> None:
        self.assertEqual(canonical_json({"z": 1, "a": "é"}), '{\n  "a": "é",\n  "z": 1\n}\n')

    def test_atomic_write_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "state.json")
            target.write_text("old", encoding="utf-8")
            with mock.patch("specromancy.io.os.replace", wraps=os.replace) as replace:
                atomic_write_json(target, {"status": "ready"})
            replace.assert_called_once()
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"status": "ready"})
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])

    def test_atomic_text_uses_utf8_and_lf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "artifact.md")
            atomic_write_text(target, "héllo\nworld\n")
            self.assertEqual(target.read_bytes(), "héllo\nworld\n".encode())

    def test_text_hash_normalizes_line_endings(self) -> None:
        self.assertEqual(sha256_text("a\r\nb\r"), sha256_text("a\nb\n"))

    def test_file_hash_uses_raw_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "payload.bin")
            target.write_bytes(b"a\r\nb")
            self.assertEqual(sha256_file(target), hashlib.sha256(b"a\r\nb").hexdigest())

    def test_json_lines_are_compact_sorted_and_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "events.jsonl")
            append_json_line(target, {"z": 2, "a": 1})
            append_json_line(target, {"event": "second"})
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                '{"a":1,"z":2}\n{"event":"second"}\n',
            )


if __name__ == "__main__":
    unittest.main()

