"""HD recapture adapter; uses production Qt/OpenGL and existing real scene recipes.
Run only serially with other GUI work. Does not replace tutorial references.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ['FIVE_AXIS_RENDER_BACKEND'] = 'opengl'
os.environ.setdefault('QT_QPA_PLATFORM', 'windows')
os.environ['QT_SCALE_FACTOR'] = '1'
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '0'
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts'), str(ROOT / 'tests')]
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from five_axis_slicer.opengl_viewer import OpenGLModelViewer
from five_axis_slicer.styles import APP_STYLE

OUT = ROOT / 'docs/guides/assets/hd_v27'
RECORDS = []
SIZE = (1920, 1080)
SCENE = 'pending'

def capture(page, filename, language='zh', model_visible=True, view='isometric', bottom=True):
    if not isinstance(page.viewer, OpenGLModelViewer):
        raise RuntimeError('Production OpenGL viewer required')
    page.set_language(language)
    page.resize(*SIZE)
    page.show()
    QApplication.processEvents()
    if not hasattr(page, '_hd_original_overlays'):
        page._hd_original_overlays = (
            page.viewer._build_surface,
            page.viewer._coordinate_frames,
        )
    surface, frames = page._hd_original_overlays
    page.viewer.set_build_surface(None)
    page.viewer.set_coordinate_frames(())
    page.viewer.set_model_visible(model_visible)
    page.viewer.set_standard_view(view)
    page.viewer.fit_view()
    bar = page.editor_scroll.verticalScrollBar()
    bar.setValue(bar.maximum() if bottom else 0)
    QApplication.processEvents()
    # The production QOpenGLWidget participates in QWidget.grab directly.
    # No desktop cursor, viewport replacement, image scaling, or path edits.
    pixmap = page.grab()
    filename = re.sub(r'\d{3,4}x\d{3,4}', f'{SIZE[0]}x{SIZE[1]}', filename)
    target = OUT / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    if pixmap.width() < 1920 or pixmap.height() < 1080:
        raise RuntimeError(f'Insufficient native size: {pixmap.width()} x {pixmap.height()}')
    if not pixmap.save(str(target), 'PNG'):
        raise RuntimeError(f'Failed capture {target}')
    record = dict(file=target.relative_to(ROOT).as_posix(), width=pixmap.width(),
        height=pixmap.height(), language=language, backend='production OpenGL',
        capture_method='QWidget.grab of current styled OpenGL page; no cursor, scaling or compositing',
        status=page.status_label.text(), export_enabled=page.export_button.isEnabled(),
        sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    RECORDS.append(record)
    (OUT / f'{SCENE}_capture_manifest.json').write_text(json.dumps(RECORDS, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return record

def main():
    global SIZE, SCENE
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', choices=['curve', 'planar-support', 'planar-spiral'], required=True)
    parser.add_argument('--size', choices=['1920x1080', '2560x1440'], default='1920x1080')
    args = parser.parse_args()
    SCENE = args.scene
    SIZE = tuple(map(int, args.size.split('x')))
    QApplication.setAttribute(Qt.AA_DisableHighDpiScaling)
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    app.setStyleSheet(APP_STYLE)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.scene == 'curve':
        import curve_c05_evidence as recipe
        def curve_capture(page, path, *, language, size, model_visible=True, scroll_to_bottom=True):
            return capture(page, 'curve_' + path.name, language, model_visible, bottom=scroll_to_bottom)
        recipe._capture = curve_capture
        recipe.generate(ROOT / 'tmp/guide_hd_curve_products', OUT)
    elif args.scene == 'planar-support':
        import planar_p07_ui_evidence as recipe
        def planar_capture(page, output, filename, case):
            return capture(page, 'planar_support_' + filename, case['language'], case['model_visible'], case['view'], case.get('editor_scroll_position', 'bottom') != 'top')
        recipe._capture = planar_capture
        model_path = recipe._write_floating_beam(ROOT / 'tmp/guide_hd_support/analytic_floating_beam.step')
        model = recipe.load_step(model_path)
        body = model.bodies[0].body_id
        recipe._ready_cases(app, model, body, OUT)
        recipe._error_recovery(app, model, body, OUT)
        recipe._stale_recovery(app, model, body, OUT)
    else:
        import planar_p06_ui_evidence as recipe
        def spiral_capture(page, output, filename, case):
            return capture(page, 'planar_spiral_' + filename, case['language'], case['model_visible'], case['view'])
        recipe._capture = spiral_capture
        model = recipe.load_step(ROOT / 'example/三叶扇/Supportless_sample.stp')
        recipe._error_recovery(app, model, 'body_002', OUT)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

