"""Native full-HD Rotary guide recapture. Run only in main desktop sequence."""
from __future__ import annotations
import os
os.environ['QT_QPA_PLATFORM'] = 'windows'
os.environ['QT_SCALE_FACTOR'] = '1'
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '0'
import sys, json, math, hashlib
from pathlib import Path
from dataclasses import replace
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from test_rotary_integration import _controller
from test_curve_workbench import _machine
from five_axis_slicer.rotary_ui import RotaryPage
from five_axis_slicer.styles import APP_STYLE
from five_axis_slicer.rotary_controller import RotaryController
from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.manufacturing.resources import ResourceSnapshot
from five_axis_slicer.models import SelectionState
from five_axis_slicer.project_io import save_project, load_project

OUT = ROOT / 'docs/guides/assets/hd_v27'
WORK = ROOT / 'tmp/guide_hd_rotary_work'
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)
app = QApplication.instance() or QApplication([])
app.setStyle('Fusion')
records = []
page = None
controller = None
operation = None
model = axis = surface = None
scenes = ['around', 'selection', 'flat_rejected', 'coordinates', 'error', 'recovered', 'stale', 'reopened']
if len(sys.argv) > 1:
    scenes = sys.argv[1:]

def setup(scene):
    global page, controller, operation, model, axis, surface
    kind = 'rotary_around_part' if scene in {'around', 'selection', 'flat_rejected', 'coordinates'} else 'rotary_spiral'
    controller, operation, model, axis, surface = _controller(WORK / scene, kind)
    machine = _machine()
    machine = replace(machine, build_surfaces=tuple(replace(s, shape='circle', width_mm=None, depth_mm=None, diameter_mm=150) for s in machine.build_surfaces))
    controller.mark_setup_changed(setup=replace(controller.setup,
        machine=ResourceSnapshot.capture('machine', machine),
        T_mount_from_build=RigidTransform.from_translation((0,0,0), source_frame='build', target_frame='build_plate_mount')))
    if kind == 'rotary_around_part':
        operation = controller.configure_operation(operation_id=operation.operation_id,
            geometry=replace(operation.geometry, profile=replace(operation.geometry.profile, axial_start_mm=0, axial_end_mm=20)),
            parameters=replace(operation.parameters, axial_step_mm=2, angular_velocity_rad_s=0.1, feedrate_mm_min=600, travel_feedrate_mm_min=300))
    else:
        operation = controller.configure_operation(operation_id=operation.operation_id,
            parameters=replace(operation.parameters, angular_velocity_rad_s=0.5 if scene == 'error' else 0.1,
                feedrate_mm_min=600, travel_feedrate_mm_min=1800 if scene == 'error' else 300))
    result = controller.generate_operation(operation.operation_id)
    if scene == 'error':
        assert not result.exportable, 'Expected actual acceleration error'
        assert 'acceleration_limit_exceeded' in json.dumps(result.to_json()), 'Expected acceleration diagnostic'
    else:
        assert result.exportable, f'{scene}: expected exportable generated result'
    if scene == 'stale':
        controller.configure_operation(operation_id=operation.operation_id, parameters=replace(operation.parameters, bead_width_mm=0.7))
    if scene == 'reopened':
        saved = save_project(WORK / 'saved_project', model, SelectionState(edge_ids={axis.edge_id}, face_ids={surface.face_id}),
            {'workbench':'rotary'}, setup=controller.setup, operations=(operation,), original_source_path=model.source_path)
        loaded = load_project(saved)
        controller = RotaryController.reopened_without_generated_products(loaded.model, setup=loaded.setup, operations=loaded.operations)
        assert controller.product_state(operation.operation_id).status == 'stale'
    page = RotaryPage(controller=controller)
    page.set_language('zh')
    page.setStyleSheet(APP_STYLE)
    page.setWindowTitle('5AxisSlicer V2.7 — Rotary')
    page.setFixedSize(1920,1080)
    page.show()
    QTimer.singleShot(1800, lambda: prepare(scene))

def prepare(scene):
    try:
        if scene == 'recovered':
            # Generate after the page has applied its initial controls.
            result = controller.generate_operation(operation.operation_id)
            assert result.exportable
            page.refresh()
        page.viewer.set_build_surface(None)
        page.viewer.home_view()
        if scene == 'around':
            page.show_model_checkbox.setChecked(False)
            page.editor_scroll.verticalScrollBar().setValue(530)
        elif scene == 'selection':
            page.viewer.set_selection(edge_ids=[axis.edge_id], face_ids=[surface.face_id])
        elif scene == 'flat_rejected':
            flat = next(f for f in model.faces if f.surface_type == 'plane')
            page.viewer.set_selection(edge_ids=[axis.edge_id], face_ids=[flat.face_id])
            page._use_selected_surfaces()
            page._apply()
            assert page._apply_failed
            assert 'rotary.surface_reference_invalid' in str(page._last_error)
            page.editor_scroll.verticalScrollBar().setValue(page.editor_scroll.verticalScrollBar().maximum())
        elif scene == 'coordinates':
            page.editor_scroll.verticalScrollBar().setValue(310)
        else:
            page.editor_scroll.verticalScrollBar().setValue(page.editor_scroll.verticalScrollBar().maximum())
        QTimer.singleShot(1000, lambda: capture(scene))
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(1)

def capture(scene):
    try:
        if scene == 'recovered':
            product_state = controller.product_state(operation.operation_id)
            assert product_state.status in {'ready', 'warning'}, product_state.status
            assert controller.product_result(operation.operation_id).exportable
            assert page.export_button.isEnabled(), page.status_label.text()
            assert page.state_json()['ui']['export_enabled']
        path = OUT / f'rotary_{scene}_zh.png'
        pix = page.grab()
        assert pix.width() >= 1920 and pix.height() >= 1080
        assert pix.save(str(path), 'PNG')
        state = page.state_json()
        (WORK / f'{scene}_state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        records.append({'scene':scene, 'path':str(path.relative_to(ROOT)), 'width':pix.width(), 'height':pix.height(),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'capture':'QWidget.grab native pixels; real ModelViewer; no cursor composition',
            'operation':operation.to_json(), 'state_file':str((WORK/f'{scene}_state.json').relative_to(ROOT))})
        (OUT / 'rotary_manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'CAPTURED {scene} {pix.width()}x{pix.height()}', flush=True)
        page.close()
        page.deleteLater()
        if scenes:
            QTimer.singleShot(300, lambda: setup(scenes.pop(0)))
        else:
            app.quit()
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(1)
app.setQuitOnLastWindowClosed(False)
QTimer.singleShot(0, lambda: setup(scenes.pop(0)))
raise SystemExit(app.exec_())


