"""Small offline fixtures for the multi-GB publication/reconstruction path."""

import copy
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/release/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publisher = load("publish_base_models")
downloader = load("download_base_models")


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, content=b"0123456789abcdef"):
        original = self.root / "original.bin"
        original.write_bytes(content)
        parts = []
        for path, record in publisher.split_file(original, "nlu__weights", self.root, part_bytes=5):
            record["url"] = (
                f"https://github.com/{publisher.REPOSITORY}/releases/download/{publisher.TAG}/{path.name}"
            )
            parts.append(record)
        return {
            "path": "weights.bin",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "parts": parts,
        }

    def test_split_boundaries_and_reconstruction_preserve_original_bytes(self):
        for size in (1, 5, 6, 10, 16):
            with self.subTest(size=size):
                folder = self.root / str(size)
                folder.mkdir()
                original = folder / "original.bin"
                content = bytes(range(size))
                original.write_bytes(content)
                records = [r for _, r in publisher.split_file(original, "nlu__weights", folder, 5)]
                self.assertEqual(sum(p["size"] for p in records), size)
                self.assertTrue(all(p["size"] <= 5 for p in records))
                destination = folder / "restored.bin"
                downloader.restore_file(
                    {"size": size, "sha256": hashlib.sha256(content).hexdigest(), "parts": records},
                    destination,
                    folder,
                )
                self.assertEqual(destination.read_bytes(), content)

    def test_corrupt_part_never_leaves_a_target_or_partial_file(self):
        record = self.fixture()
        (self.root / record["parts"][0]["name"]).write_bytes(b"bad!!")
        target = self.root / "restored.bin"
        with self.assertRaises(ValueError):
            downloader.restore_file(record, target, self.root)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob("*.partial-*")), [])

    def test_bad_whole_file_hash_is_rejected_even_when_parts_match(self):
        record = self.fixture()
        record["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            downloader.restore_file(record, self.root / "restored.bin", self.root)
        self.assertFalse((self.root / "restored.bin").exists())

    def test_existing_different_file_is_never_overwritten(self):
        record = self.fixture()
        target = self.root / "restored.bin"
        target.write_bytes(b"user data")
        with self.assertRaises(ValueError):
            downloader.restore_file(record, target, self.root)
        self.assertEqual(target.read_bytes(), b"user data")

    def test_existing_matching_file_is_reused_without_reading_assets(self):
        record = self.fixture()
        target = self.root / "restored.bin"
        target.write_bytes((self.root / "original.bin").read_bytes())
        downloader.restore_file(record, target, self.root / "nonexistent")

    def test_asset_cannot_escape_release_or_local_directory(self):
        prefix = f"https://github.com/{publisher.REPOSITORY}/releases/download/{publisher.TAG}/"
        asset = self.fixture()["parts"][0]
        for name, url in (
            ("../private", prefix + "../private"),
            ("safe", "https://other.example/safe"),
            ("..\\private", prefix + "..\\private"),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                downloader.validate_asset({**asset, "name": name, "url": url}, prefix)

    def test_large_release_part_size_is_rejected(self):
        path = self.root / "small"
        path.write_bytes(b"x")
        with self.assertRaises(ValueError):
            list(publisher.split_file(path, "test", self.root, 2**31))

    def test_source_requires_pinned_revisions_and_weight_digests(self):
        source = __import__("json").loads(
            (ROOT / "models/base-models-source.json").read_text("utf-8")
        )
        publisher.validate_source(source)
        for field, value in (("revision", "main"), ("repo_id", "somebody/other-model")):
            altered = copy.deepcopy(source)
            altered["models"][0][field] = value
            with self.assertRaises(ValueError):
                publisher.validate_source(altered)
        altered = copy.deepcopy(source)
        altered["models"][0]["files"][0]["sha256"] = "invalid"
        with self.assertRaises(ValueError):
            publisher.validate_source(altered)

    def test_existing_remote_asset_requires_matching_digest_and_size(self):
        asset_path = self.root / "asset"
        asset_path.write_bytes(b"release bytes")
        expected = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        existing = {
            "name": "asset",
            "size": asset_path.stat().st_size,
            "digest": "sha256:" + expected,
            "browser_download_url": "https://github.com/verified",
        }
        with (
            patch.object(publisher, "api", return_value=[existing]),
            patch.object(publisher, "gh") as cli,
        ):
            result = publisher.upload(asset_path, publisher.TAG, 123)
            self.assertEqual(result["sha256"], expected)
            cli.assert_not_called()
        with (
            patch.object(
                publisher, "api", return_value=[{**existing, "digest": "sha256:" + "0" * 64}]
            ),
            patch.object(publisher, "gh") as cli,
        ):
            with self.assertRaises(ValueError):
                publisher.upload(asset_path, publisher.TAG, 123)
            cli.assert_not_called()

    def test_published_release_is_never_modified(self):
        with (
            patch.object(publisher, "api", return_value={"body": publisher.MARKER, "draft": False}),
            patch.object(publisher, "gh") as cli,
        ):
            with self.assertRaises(ValueError):
                publisher.release(publisher.TAG, "main", self.root)
            cli.assert_not_called()


if __name__ == "__main__":
    unittest.main()
