from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
import string
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication

from five_axis_slicer import background_load
from five_axis_slicer import gcode_preview
from five_axis_slicer.background_load import ResultLoadCoordinator
from five_axis_slicer.gcode_preview import GCodeLoadCancelled, parse_gcode
from five_axis_slicer.gcode_source import GCodeSourceIndex
from five_axis_slicer.localization import TRANSLATIONS
from five_axis_slicer.models import SelectionState
from five_axis_slicer.project_io import PROJECT_VERSION, save_project
from five_axis_slicer.result_state import (
    IllustrativeProcessParameters,
    LoadRequest,
    LoadResult,
    ResultPreviewState,
)
from five_axis_slicer.step_loader import StepLoadCancelled


class _ClosableIndex:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class ResultStateAndProjectTests(unittest.TestCase):
    def test_translation_catalogs_have_symmetric_keys_and_placeholders(self) -> None:
        self.assertEqual(set(TRANSLATIONS), {"zh", "en"})
        self.assertEqual(set(TRANSLATIONS["zh"]), set(TRANSLATIONS["en"]))

        formatter = string.Formatter()
        for key in TRANSLATIONS["zh"]:
            zh_fields = {
                name
                for _, name, _, _ in formatter.parse(TRANSLATIONS["zh"][key])
                if name
            }
            en_fields = {
                name
                for _, name, _, _ in formatter.parse(TRANSLATIONS["en"][key])
                if name
            }
            self.assertEqual(zh_fields, en_fields, key)
            self.assertTrue(TRANSLATIONS["zh"][key].strip(), key)
            self.assertTrue(TRANSLATIONS["en"][key].strip(), key)

    def test_application_shell_uses_product_copy(self) -> None:
        visible_shell_keys = {
            "app_title",
            "operation_curve",
            "operation_freeform",
            "status_single_body",
            "gcode_viewer_entry",
        }
        visible_copy = (
            "".join(
                TRANSLATIONS[language][key]
                for language in ("zh", "en")
                for key in visible_shell_keys
            )
            .replace(" ", "")
            .casefold()
        )
        for forbidden in (
            "示意",
            "演示",
            "首版",
            "prototype",
            "demo",
            "outofscope",
            "(preview)",
            "（预览）",
        ):
            self.assertNotIn(forbidden.casefold(), visible_copy)

    def test_parameter_round_trip_and_project_save_do_not_parse_gcode(self) -> None:
        parameters = IllustrativeProcessParameters(
            layer_height_mm=0.25,
            print_speed_mm_min=900.0,
            extrusion_width_mm=0.52,
            nozzle_diameter_mm=0.4,
            shell_enabled=False,
            top_layers=6,
            bottom_layers=4,
        )
        state = ResultPreviewState(
            parameters=parameters, quality_mode="paper", show_travel=True
        )

        with patch("five_axis_slicer.gcode_preview.parse_gcode") as parse_mock:
            payload = state.to_json()
            restored = ResultPreviewState.from_json(payload)
            with tempfile.TemporaryDirectory() as tmp:
                project_path = save_project(
                    Path(tmp) / "project",
                    None,
                    SelectionState(),
                    result_preview_state=restored,
                )
                project_payload = json.loads(project_path.read_text(encoding="utf-8"))

        parse_mock.assert_not_called()
        self.assertEqual(restored.parameters, parameters)
        self.assertEqual(project_payload["version"], PROJECT_VERSION)
        self.assertEqual(project_payload["result_preview"]["schema_version"], 1)
        self.assertFalse(
            project_payload["result_preview"]["parameters_affect_toolpath"]
        )
        self.assertNotIn(
            "language",
            json.dumps(project_payload["result_preview"], ensure_ascii=False),
        )

    def test_project_without_result_namespace_keeps_root_schema_compatible(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = save_project(Path(tmp) / "project", None, SelectionState())
            payload = json.loads(project_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["version"], PROJECT_VERSION)
        self.assertNotIn("result_preview", payload)

    def test_load_state_rejects_stale_and_out_of_sequence_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_path = root / "old.gcode"
            new_path = root / "new.gcode"
            old_path.touch()
            new_path.touch()
            state = ResultPreviewState(active_gcode_path=old_path, status="ready")

            self.assertFalse(
                state.commit_load(LoadResult("orphan", gcode_path=new_path))
            )
            state.begin_load(LoadRequest("new", gcode_path=new_path))
            self.assertFalse(
                state.commit_load(LoadResult("stale", gcode_path=old_path))
            )
            self.assertFalse(state.fail_load("stale", "stale failure"))
            self.assertEqual(state.active_gcode_path, old_path.resolve())
            self.assertEqual(state.status, "loading")

            self.assertTrue(state.fail_load("new", "damaged source"))
            self.assertEqual(state.status, "error")
            self.assertEqual(state.active_gcode_path, old_path.resolve())

            state.begin_load(LoadRequest("retry", gcode_path=new_path))
            self.assertTrue(state.cancel_load("retry"))
            self.assertEqual(state.status, "ready")
            self.assertEqual(state.active_gcode_path, old_path.resolve())


class GCodeSourceIndexTests(unittest.TestCase):
    def test_line_window_search_wrap_stages_and_cached_reload(self) -> None:
        lines = [
            "; header",
            "G1 X0 Y0",
            ";叶轮1",
            "G1 F1200 X1 Y2 Z3 A90 C-10 E0.5",
            "Needle lower",
            "; 叶轮 2",
            "G1 NEEDLE",
            "tail",
            ";叶轮9",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "indexed.gcode"
            cache = root / "cache"
            source.write_text("\r\n".join(lines), encoding="utf-8")

            progress: list[tuple[float, str]] = []
            with GCodeSourceIndex(
                source, cache, progress_callback=lambda f, p: progress.append((f, p))
            ) as index:
                self.assertEqual(index.line_count, len(lines))
                self.assertEqual(
                    index.read_context(4, radius=2),
                    list(enumerate(lines[1:6], start=2)),
                )
                self.assertEqual(index.search("needle", start_line=1), 5)
                self.assertEqual(index.search("needle", start_line=6), 7)
                self.assertEqual(index.search("needle", start_line=8), 5)
                self.assertEqual(index.search("needle", start_line=8, forward=False), 7)
                self.assertEqual(index.search("needle", start_line=6, forward=False), 5)
                self.assertEqual(index.search("needle", start_line=4, forward=False), 7)
                self.assertEqual(index.representative_five_axis_line(), 4)
                self.assertEqual(
                    [
                        (stage.stage_id, stage.start_line, stage.end_line)
                        for stage in index.stages
                    ],
                    [("base", 1, 2), ("blade_1", 3, 5), ("blade_2", 6, 9)],
                )
            self.assertTrue(progress)
            self.assertEqual(progress[-1], (1.0, "source_index"))

            with GCodeSourceIndex(source, cache) as cached:
                self.assertEqual(cached.read_line(5), lines[4])
                self.assertEqual(
                    [stage.stage_id for stage in cached.stages],
                    ["base", "blade_1", "blade_2"],
                )

    def test_empty_file_has_safe_context_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "empty.gcode"
            source.touch()
            with GCodeSourceIndex(source, root / "cache") as index:
                self.assertEqual(index.line_count, 0)
                self.assertEqual(index.read_context(1), [])
                self.assertIsNone(index.search("G1"))
                self.assertIsNone(index.representative_five_axis_line())
                self.assertEqual([stage.stage_id for stage in index.stages], ["all"])


class PreviewCacheTests(unittest.TestCase):
    @staticmethod
    def _sparse_source(root: Path) -> tuple[Path, object]:
        source = root / "large.gcode"
        with source.open("wb") as stream:
            stream.truncate(25_000_000)
        preview = parse_gcode(
            ";LAYER_CHANGE\nG1 X0 Y0 Z0.2 F1200\nG1 X1 Y0 E0.1 A10 C20\n",
            source,
        )
        return source, preview

    @staticmethod
    def _cache_stem_factory(cache_root: Path):
        def cache_stem(
            _source_path: Path, version: str = gcode_preview.CACHE_VERSION
        ) -> Path:
            return cache_root / version

        return cache_stem

    def test_generation_manifest_commit_reloads_and_retires_previous_binary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, preview = self._sparse_source(root)
            cache_root = root / "cache"
            with patch.object(
                gcode_preview,
                "_cache_stem",
                side_effect=self._cache_stem_factory(cache_root),
            ):
                gcode_preview._write_preview_cache(preview)
                manifest_path = gcode_preview._cache_path(source)
                first_payload = self._read_manifest(manifest_path)
                first_binary = manifest_path.parent / first_payload["binary_arrays"]
                self.assertTrue(first_binary.exists())
                cached_summary = gcode_preview._load_preview_cache(source).summary()
                self.assertEqual(cached_summary["segment_count"], 2)
                self.assertEqual(cached_summary["render_index_source"], "cache")

                gcode_preview._write_preview_cache(preview)
                second_payload = self._read_manifest(manifest_path)
                second_binary = manifest_path.parent / second_payload["binary_arrays"]

            self.assertNotEqual(first_binary, second_binary)
            self.assertFalse(first_binary.exists())
            self.assertTrue(second_binary.exists())
            self.assertEqual(set(cache_root.iterdir()), {manifest_path, second_binary})

    def test_manifest_replace_failure_preserves_valid_generation_and_cleans_temps(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, preview = self._sparse_source(root)
            cache_root = root / "cache"
            stem_factory = self._cache_stem_factory(cache_root)
            with patch.object(gcode_preview, "_cache_stem", side_effect=stem_factory):
                gcode_preview._write_preview_cache(preview)
                manifest_path = gcode_preview._cache_path(source)
                before_manifest = manifest_path.read_bytes()
                before_files = set(cache_root.iterdir())
                real_replace = os.replace

                def fail_manifest_replace(
                    source_path: str | os.PathLike[str],
                    target_path: str | os.PathLike[str],
                ) -> None:
                    if Path(target_path) == manifest_path:
                        raise OSError("simulated manifest replace failure")
                    real_replace(source_path, target_path)

                with patch.object(
                    gcode_preview.os, "replace", side_effect=fail_manifest_replace
                ):
                    with self.assertRaisesRegex(OSError, "manifest replace"):
                        gcode_preview._write_preview_cache(preview)

            self.assertEqual(manifest_path.read_bytes(), before_manifest)
            self.assertEqual(set(cache_root.iterdir()), before_files)

    def test_cancellation_during_binary_write_leaves_no_partial_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _source, preview = self._sparse_source(root)
            cache_root = root / "cache"
            cancelled = False
            real_savez = gcode_preview.np.savez

            def save_then_cancel(*args: object, **kwargs: object) -> None:
                nonlocal cancelled
                real_savez(*args, **kwargs)
                cancelled = True

            with (
                patch.object(
                    gcode_preview,
                    "_cache_stem",
                    side_effect=self._cache_stem_factory(cache_root),
                ),
                patch.object(gcode_preview.np, "savez", side_effect=save_then_cancel),
            ):
                with self.assertRaises(GCodeLoadCancelled):
                    gcode_preview._write_preview_cache(
                        preview, cancel_check=lambda: cancelled
                    )

            self.assertTrue(cache_root.exists())
            self.assertEqual(list(cache_root.iterdir()), [])

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, object]:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)


class BackgroundLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _wait_until(self, predicate, *, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.001)
        self.fail("Timed out while waiting for the background loader")

    def test_success_commits_one_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "success.gcode"
            source.touch()
            preview = object()
            source_index = _ClosableIndex()
            coordinator = ResultLoadCoordinator()
            completed: list[LoadResult] = []
            failed: list[tuple[object, str]] = []
            coordinator.completed.connect(completed.append)
            coordinator.failed.connect(
                lambda request_id, message: failed.append((request_id, message))
            )
            with (
                patch.object(background_load, "load_gcode", return_value=preview),
                patch.object(
                    background_load, "GCodeSourceIndex", return_value=source_index
                ),
            ):
                coordinator.start(LoadRequest("success", gcode_path=source))
                self._wait_until(lambda: not coordinator.busy)

            self.assertEqual(failed, [])
            self.assertEqual(len(completed), 1)
            self.assertEqual(completed[0].request_id, "success")
            self.assertIs(completed[0].gcode_preview, preview)
            self.assertEqual(
                completed[0].source_audits["gcode"]["path"],
                str(source.resolve()),
            )
            self.assertEqual(completed[0].source_audits["gcode"]["size_bytes"], 0)
            self.assertIn("mtime_ns", completed[0].source_audits["gcode"])
            completed[0].close()
            self.assertTrue(source_index.closed)
            coordinator.deleteLater()

    def test_cancel_and_failure_are_reported_without_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cancel.gcode"
            source.touch()

            entered = threading.Event()

            def cancellable_load(_path: Path, *, cancel_check, **_kwargs: object):
                entered.set()
                while not cancel_check():
                    time.sleep(0.001)
                raise GCodeLoadCancelled("cancelled")

            coordinator = ResultLoadCoordinator()
            cancelled: list[object] = []
            completed: list[LoadResult] = []
            coordinator.cancelled.connect(cancelled.append)
            coordinator.completed.connect(completed.append)
            with patch.object(
                background_load, "load_gcode", side_effect=cancellable_load
            ):
                coordinator.start(LoadRequest("cancel", gcode_path=source))
                self._wait_until(entered.is_set)
                coordinator.cancel()
                self._wait_until(lambda: not coordinator.busy)
            self.assertEqual(cancelled, ["cancel"])
            self.assertEqual(completed, [])
            coordinator.deleteLater()

            failed_coordinator = ResultLoadCoordinator()
            failures: list[tuple[object, str]] = []
            failed_coordinator.failed.connect(
                lambda request_id, message: failures.append((request_id, message))
            )
            with patch.object(
                background_load, "load_gcode", side_effect=ValueError("damaged G-code")
            ):
                failed_coordinator.start(LoadRequest("failure", gcode_path=source))
                self._wait_until(lambda: not failed_coordinator.busy)
            self.assertEqual(failures, [("failure", "damaged G-code")])
            failed_coordinator.deleteLater()

    def test_step_loader_receives_the_coordinator_cancel_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cancel.step"
            source.touch()
            entered = threading.Event()

            def cancellable_step(_path: Path, *, cancel_check) -> object:
                entered.set()
                while not cancel_check():
                    time.sleep(0.001)
                raise StepLoadCancelled("cancelled")

            coordinator = ResultLoadCoordinator()
            cancelled: list[object] = []
            completed: list[LoadResult] = []
            coordinator.cancelled.connect(cancelled.append)
            coordinator.completed.connect(completed.append)
            with patch.object(
                background_load, "load_step", side_effect=cancellable_step
            ):
                coordinator.start(LoadRequest("step-cancel", model_path=source))
                self._wait_until(entered.is_set)
                coordinator.cancel()
                self._wait_until(lambda: not coordinator.busy)

            self.assertEqual(cancelled, ["step-cancel"])
            self.assertEqual(completed, [])
            coordinator.deleteLater()

    def test_gcode_audit_hash_receives_the_coordinator_cancel_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cancel.gcode"
            source.touch()
            entered = threading.Event()

            def cancellable_hash(_path: Path, *, cancel_check) -> str:
                entered.set()
                while not cancel_check():
                    time.sleep(0.001)
                raise StepLoadCancelled("cancelled")

            coordinator = ResultLoadCoordinator()
            cancelled: list[object] = []
            completed: list[LoadResult] = []
            coordinator.cancelled.connect(cancelled.append)
            coordinator.completed.connect(completed.append)
            with patch.object(
                background_load, "file_sha256", side_effect=cancellable_hash
            ):
                coordinator.start(LoadRequest("hash-cancel", gcode_path=source))
                self._wait_until(entered.is_set)
                coordinator.cancel()
                self._wait_until(lambda: not coordinator.busy)

            self.assertEqual(cancelled, ["hash-cancel"])
            self.assertEqual(completed, [])
            coordinator.deleteLater()

    def test_cancel_drops_a_pending_replacement_before_it_starts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_source = root / "old.gcode"
            new_source = root / "new.gcode"
            old_source.touch()
            new_source.touch()
            entered = threading.Event()
            load_calls: list[Path] = []

            def cancellable_load(path: Path, *, cancel_check, **_kwargs: object):
                load_calls.append(path)
                entered.set()
                while not cancel_check():
                    time.sleep(0.001)
                raise GCodeLoadCancelled("cancelled")

            coordinator = ResultLoadCoordinator()
            cancelled: list[object] = []
            completed: list[LoadResult] = []
            coordinator.cancelled.connect(cancelled.append)
            coordinator.completed.connect(completed.append)
            with patch.object(
                background_load, "load_gcode", side_effect=cancellable_load
            ):
                coordinator.start(LoadRequest("old", gcode_path=old_source))
                self._wait_until(entered.is_set)
                coordinator.start(LoadRequest("new", gcode_path=new_source))
                coordinator.cancel()
                self._wait_until(lambda: not coordinator.busy)

            self.assertEqual(cancelled, ["new"])
            self.assertEqual(completed, [])
            self.assertEqual(load_calls, [old_source.resolve()])
            coordinator.deleteLater()

    def test_superseded_completion_is_closed_and_only_latest_result_is_emitted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_source = root / "old.gcode"
            new_source = root / "new.gcode"
            old_source.touch()
            new_source.touch()
            constructing_old = threading.Event()
            release_old = threading.Event()
            indexes: list[_ClosableIndex] = []
            real_result_type = LoadResult

            def make_index(*_args: object, **_kwargs: object) -> _ClosableIndex:
                index = _ClosableIndex()
                indexes.append(index)
                return index

            def gated_result(*args: object, **kwargs: object) -> LoadResult:
                request_id = kwargs.get("request_id", args[0] if args else None)
                if request_id == "old":
                    constructing_old.set()
                    if not release_old.wait(2.0):
                        raise TimeoutError("test gate timed out")
                return real_result_type(*args, **kwargs)

            coordinator = ResultLoadCoordinator()
            completed: list[LoadResult] = []
            busy_states: list[bool] = []
            coordinator.completed.connect(completed.append)
            coordinator.busy_changed.connect(busy_states.append)
            with (
                patch.object(
                    background_load,
                    "load_gcode",
                    side_effect=lambda *_a, **_kw: object(),
                ),
                patch.object(
                    background_load, "GCodeSourceIndex", side_effect=make_index
                ),
                patch.object(background_load, "LoadResult", side_effect=gated_result),
            ):
                coordinator.start(LoadRequest("old", gcode_path=old_source))
                self._wait_until(constructing_old.is_set)
                coordinator.start(LoadRequest("new", gcode_path=new_source))
                self.assertEqual(coordinator.active_request_id, "new")
                release_old.set()
                self._wait_until(lambda: not coordinator.busy)

            self.assertEqual([result.request_id for result in completed], ["new"])
            self.assertEqual(busy_states, [True, False])
            self.assertEqual(len(indexes), 2)
            self.assertTrue(indexes[0].closed)
            self.assertFalse(indexes[1].closed)
            completed[0].close()
            self.assertTrue(indexes[1].closed)
            coordinator.deleteLater()

    def test_shutdown_timeout_keeps_uncooperative_step_worker_alive_for_repeated_wait(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "blocking.step"
            source.touch()
            entered = threading.Event()
            release = threading.Event()

            def blocking_step(_path: Path, *, cancel_check) -> object:
                entered.set()
                if not release.wait(3.0):
                    raise TimeoutError("test STEP gate timed out")
                return object()

            coordinator = ResultLoadCoordinator()
            busy_states: list[bool] = []
            coordinator.busy_changed.connect(busy_states.append)
            try:
                with patch.object(
                    background_load, "load_step", side_effect=blocking_step
                ):
                    coordinator.start(LoadRequest("step", model_path=source))
                    self._wait_until(entered.is_set)

                    self.assertFalse(coordinator.shutdown(timeout_ms=5))
                    self.assertTrue(coordinator.busy)
                    self.assertFalse(coordinator.wait_for_shutdown(timeout_ms=0))

                    release.set()
                    self.assertTrue(coordinator.wait_for_shutdown(timeout_ms=2000))
                    self.assertFalse(coordinator.busy)
            finally:
                release.set()
                coordinator.shutdown(timeout_ms=2000)

            self.assertEqual(busy_states, [True, False])
            coordinator.deleteLater()

    def test_timed_out_worker_outlives_coordinator_qobject_until_native_thread_stops(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "detached.step"
            source.touch()
            entered = threading.Event()
            release = threading.Event()

            def blocking_step(_path: Path, *, cancel_check) -> object:
                entered.set()
                if not release.wait(3.0):
                    raise TimeoutError("test STEP gate timed out")
                return object()

            coordinator = ResultLoadCoordinator()
            with patch.object(background_load, "load_step", side_effect=blocking_step):
                coordinator.start(LoadRequest("detached", model_path=source))
                self._wait_until(entered.is_set)
                self.assertFalse(coordinator.shutdown(timeout_ms=0))
                thread = coordinator._thread
                self.assertIsNotNone(thread)
                self.assertIn(thread, background_load._LIVE_WORKERS)

                coordinator.deleteLater()
                self.app.processEvents()
                self.assertIn(thread, background_load._LIVE_WORKERS)

                release.set()
                self.assertTrue(thread.wait(2000))
                self.app.processEvents()

            self.assertNotIn(thread, background_load._LIVE_WORKERS)


if __name__ == "__main__":
    unittest.main()
