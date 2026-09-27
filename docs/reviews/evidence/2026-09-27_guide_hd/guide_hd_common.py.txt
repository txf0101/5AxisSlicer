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
for lang in ['zh','en']:
 w.set_language(lang);w.stack.setCurrentWidget(w.home_page);capture('home_'+lang)
w.set_language('zh')
project=ROOT/'docs/reviews/evidence/2026-09-26_v2_final_delivery/impeller_completed150_gui_project/project.json'
w.open_project(project)
w.open_manufacturing_setup();pump()
p=w.tube_page
for name,node in [('part_impeller_roles_zh','part'),('machine150_zh','machine'),('material_zh_draft','material'),('modelcs_draft_zh','model_cs'),('buildcs_draft_zh','build_cs'),('placement_draft_controls_zh','placement')]:
 p.tree.setCurrentItem(p._tree_items[node]);p.activate_selected_editor();p.viewer.fit_view();capture(name)
 if p.controller.has_drafts:
  p.controller.discard_all_drafts();p.refresh()
w.set_language('en')
for name,node in [('machine150_en','machine'),('material_en_draft','material')]:
 p.tree.setCurrentItem(p._tree_items[node]);p.activate_selected_editor();p.viewer.fit_view();capture(name)
(OUT/'common_capture_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
w.close();pump(.2)
