from pathlib import Path
import os,sys,json,time,hashlib
ROOT=Path(__file__).resolve().parents[1]
os.environ['QT_QPA_PLATFORM']='windows'
os.environ['QT_SCALE_FACTOR']='1'
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR']='0'
sys.path.insert(0,str(ROOT/'src'))
from PyQt5.QtCore import Qt,QSettings
from PyQt5.QtWidgets import QApplication
from five_axis_slicer import ui
OUT=ROOT/'docs/guides/assets/hd_v27'
OUT.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.AA_DisableHighDpiScaling,True)
app=QApplication([])
ui.QSettings=lambda *args: QSettings(str(ROOT/'tmp/guide_hd.ini'),QSettings.IniFormat)
w=ui.MainWindow(http_port=0)
w.resize(1920,1080);w.show()
def pump(t=.4):
 end=time.monotonic()+t
 while time.monotonic()<end:
  app.processEvents();time.sleep(.015)
records=[]
def capture(name):
 w.resize(1920,1080);w.statusBar().clearMessage();pump()
 pix=w.grab();assert pix.width()>=1920 and pix.height()>=1080,(pix.width(),pix.height())
 path=OUT/(name+'.png');assert pix.save(str(path),'PNG')
 records.append({'file':path.name,'size':[pix.width(),pix.height()],'method':'Live QWidget.grab, native pixels, no OS cursor or computer-use overlay','sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 print(name,flush=True)
from five_axis_slicer.material_plan_editor import MaterialPlanEditor
from five_axis_slicer.tool_change_station_editor import ToolChangeStationEditor
for lang in ['zh','en']:
 d=MaterialPlanEditor(language=lang,parent=w);d.add_channel();d.add_channel();d.resize(1920,1080);d.show();pump()
 shot=d.grab();assert shot.width()>=1920 and shot.height()>=1080
 shot.save(str(OUT/('material_'+lang+'_draft.png')),'PNG');d.close()
d=ToolChangeStationEditor(language='zh',parent=w);d.resize(1920,1080);d.show();pump();d.grab().save(str(OUT/'station_zh_empty.png'),'PNG');d.close()
e=ROOT/'docs/reviews/evidence/2026-09-26_v2_final_delivery'
w.set_language('zh')
w.open_project(e/'impeller_completed150_gui_project/project.json');w.enter_workbench('freeform');pump();w.freeform_page.viewer.fit_view();capture('freeform_existing_surface_solid_zh')
w.open_project(e/'three_color_completed150_gui_project/project.json');w.enter_workbench('freeform');pump();w.freeform_page.viewer.fit_view();w.freeform_page.editor_scroll.ensureWidgetVisible(w.freeform_page.solid_geometry_edit);capture('freeform_three_leaf_roles_zh')
w.open_project(e/'tube_v7_gui_project/project.json');w.enter_workbench('tube');pump();w.tube_page.tree.setCurrentItem(next(v for k,v in w.tube_page._tree_items.items() if k.startswith('operation:')));w.tube_page.activate_selected_editor();w.tube_page.viewer.fit_view();w.tube_page.editor_scroll.ensureWidgetVisible(w.tube_page._operation_geometry_combos['tube_body_id']);capture('tube_roles_zh')
(OUT/'extra_capture_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
w.close();pump(.2)
