from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer import gcode_preview, gcode_source
from five_axis_slicer.gcode_preview import GCodeLoadCancelled, load_gcode
from five_axis_slicer.gcode_source import (
    GCodeSourceIndex,
    GCodeSourceIndexCancelled,
    application_cache_dir,
)
from five_axis_slicer.manufacturing.preview_kinematics import (
    GENERIC_XYZAC_AC_SEMANTICS,
)


class CacheResilienceTests(unittest.TestCase):
    def test_source_signature_hash_can_be_cancelled_between_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "large.gcode"
            source.write_bytes(b"G1 X0 Y0 E0.1\n" + b"x" * (2 * 1024 * 1024))
            state = {"cancelled": False, "update_sizes": []}

            class CancellingDigest:
                def update(self, chunk: bytes) -> None:
                    state["update_sizes"].append(len(chunk))
                    state["cancelled"] = True

                def hexdigest(self) -> str:
                    return "0" * 64

            with patch.object(
                gcode_source.hashlib,
                "sha256",
                return_value=CancellingDigest(),
            ):
                with self.assertRaises(GCodeSourceIndexCancelled):
                    GCodeSourceIndex(
                        source,
                        root / "cache",
                        cancel_check=lambda: bool(state["cancelled"]),
                    )

            self.assertEqual(state["update_sizes"], [1024 * 1024])
            self.assertFalse((root / "cache").exists())

    def test_source_index_survives_cache_replace_failure_and_cleans_temps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.gcode"
            cache = root / "explicit-cache"
            source.write_text("G1 X0 Y0\nG1 X1 Y0 E0.1\n", encoding="utf-8")

            with patch.object(
                gcode_source.os,
                "replace",
                side_effect=PermissionError("read-only cache"),
            ):
                with GCodeSourceIndex(source, cache) as index:
                    self.assertEqual(index.line_count, 2)
                    self.assertEqual(index.read_line(2), "G1 X1 Y0 E0.1")
            self.assertEqual(list(cache.iterdir()), [])

    def test_source_index_cache_cancellation_propagates_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.gcode"
            cache = root / "cache"
            source.write_text("G1 X0 Y0\nG1 X1 Y0 E0.1\n", encoding="utf-8")
            cancelled = False
            real_save = gcode_source.np.save

            def save_then_cancel(*args: object, **kwargs: object) -> None:
                nonlocal cancelled
                real_save(*args, **kwargs)
                cancelled = True

            with patch.object(gcode_source.np, "save", side_effect=save_then_cancel):
                with self.assertRaises(GCodeSourceIndexCancelled):
                    GCodeSourceIndex(source, cache, cancel_check=lambda: cancelled)

            self.assertEqual(list(cache.iterdir()), [])

    def test_preview_load_survives_cache_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.gcode"
            source.write_text("G90\nM83\nG1 X1 Y0 E0.1\n", encoding="utf-8")
            progress: list[tuple[float, str]] = []

            with patch.object(
                gcode_preview,
                "_write_preview_cache",
                side_effect=PermissionError("read-only cache"),
            ):
                preview = load_gcode(
                    source,
                    progress_callback=lambda fraction, phase: progress.append((fraction, phase)),
                )

            self.assertEqual(preview.summary()["segment_count"], 1)
            self.assertEqual(progress[-1], (1.0, "ready"))

    def test_preview_cache_cancellation_is_not_downgraded_to_cache_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.gcode"
            source.write_text("G1 X1 Y0 E0.1\n", encoding="utf-8")

            with patch.object(
                gcode_preview,
                "_write_preview_cache",
                side_effect=GCodeLoadCancelled("cancelled during cache write"),
            ):
                with self.assertRaisesRegex(GCodeLoadCancelled, "cache write"):
                    load_gcode(source)

    def test_default_cache_paths_do_not_depend_on_current_working_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            working_directory = root / "working"
            user_cache = root / "user-cache"
            try:
                application_cache_dir.cache_clear()
                with (
                    patch.object(gcode_source, "_qt_cache_location", return_value=user_cache),
                    patch("pathlib.Path.cwd", return_value=working_directory),
                ):
                    source_cache = application_cache_dir("gcode_source_index")
                    preview_cache = gcode_preview._cache_stem(Path(__file__).resolve())
            finally:
                application_cache_dir.cache_clear()

            self.assertEqual(
                source_cache,
                user_cache / "5AxisSclicer_V2.0" / "gcode_source_index",
            )
            self.assertEqual(
                preview_cache.parent,
                user_cache / "5AxisSclicer_V2.0" / "gcode_preview_cache",
            )

    def test_unwritable_qt_cache_location_uses_temporary_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qt_cache = root / "locked-profile"
            temporary_root = root / "process-temp"
            real_temporary_file = tempfile.TemporaryFile

            def probe(*args: object, **kwargs: object):
                if Path(kwargs["dir"]) == qt_cache / "5AxisSclicer_V2.0" / "fallback_test":
                    raise PermissionError("profile cache is read-only")
                return real_temporary_file(*args, **kwargs)

            try:
                application_cache_dir.cache_clear()
                with (
                    patch.object(gcode_source, "_qt_cache_location", return_value=qt_cache),
                    patch.object(
                        gcode_source.tempfile,
                        "gettempdir",
                        return_value=str(temporary_root),
                    ),
                    patch.object(gcode_source.tempfile, "TemporaryFile", side_effect=probe),
                ):
                    selected = application_cache_dir("fallback_test")
            finally:
                application_cache_dir.cache_clear()

            self.assertEqual(
                selected,
                temporary_root / "5AxisSclicer_V2.0" / "fallback_test",
            )

    def test_source_signature_is_a_loaded_file_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.gcode"
            original = b"G1 X0 Y0\nG1 X1 Y0 E0.1\n"
            source.write_bytes(original)

            with GCodeSourceIndex(source, root / "cache") as index:
                signature = index.source_signature

            source.write_bytes(b"G1 X99 Y99\n")
            self.assertEqual(index.source_signature, signature)
            self.assertEqual(signature["size_bytes"], len(original))
            self.assertEqual(signature["sha256"], hashlib.sha256(original).hexdigest())

    def test_preview_cache_identity_includes_content_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "same_metadata.gcode"
            source.write_bytes(b"G1 X0 Y0 E0.1\n")
            original_stat = source.stat()
            first = gcode_preview._cache_stem(source)

            source.write_bytes(b"G1 X9 Y9 E9.9\n")
            os.utime(
                source,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )
            second = gcode_preview._cache_stem(source)

            self.assertEqual(source.stat().st_size, original_stat.st_size)
            self.assertEqual(source.stat().st_mtime_ns, original_stat.st_mtime_ns)
            self.assertNotEqual(first, second)

    def test_preview_cache_identity_includes_confirmed_controller_semantics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "rotary.gcode"
            source.write_text("G1 X1 Y0 A30 E0.1\n", encoding="utf-8")

            unconfirmed = gcode_preview._cache_stem(source)
            confirmed = gcode_preview._cache_stem(
                source,
                controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
            )

            self.assertNotEqual(unconfirmed, confirmed)


if __name__ == "__main__":
    unittest.main()
