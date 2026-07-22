from __future__ import annotations

import hashlib
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.package_assets import (  # noqa: E402
    IMPELLER_FOUR_PANEL_REFERENCE,
    PACKAGE_DIRECTORY,
)


class PackageAssetTests(unittest.TestCase):
    EXPECTED_REFERENCE_SHA256 = (
        "28fba3b49b6a8e7525a0850ba69f866d8e9f0a6a835c455a487c7c04dc99df58"
    )

    def test_reference_image_is_resolved_inside_package(self) -> None:
        expected = PACKAGE_DIRECTORY / "assets" / "impeller_four_panel_reference.png"
        self.assertEqual(IMPELLER_FOUR_PANEL_REFERENCE, expected)
        self.assertTrue(IMPELLER_FOUR_PANEL_REFERENCE.is_file())
        digest = hashlib.sha256(IMPELLER_FOUR_PANEL_REFERENCE.read_bytes()).hexdigest()
        self.assertEqual(digest, self.EXPECTED_REFERENCE_SHA256)

    def test_pyproject_includes_png_package_data(self) -> None:
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        package_data = re.search(
            r"\[tool\.setuptools\.package-data\]\s+"
            r"five_axis_slicer\s*=\s*\[(?P<patterns>[^\]]+)\]",
            project,
        )
        self.assertIsNotNone(package_data)
        self.assertIn('"assets/*.png"', package_data.group("patterns"))


if __name__ == "__main__":
    unittest.main()
