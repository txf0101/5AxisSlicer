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
e=ROOT/'docs/reviews/evidence/2026-09-26_v2_final_delivery'
w.set_language('zh');w.open_project(e/'curve_zh1366_current150/project.json');w.enter_workbench('curve');p=w.curve_page;p.viewer.fit_view();p.editor_scroll.ensureWidgetVisible(p.edge_ids_edit)
edges=[s.strip() for s in p.edge_ids_edit.text().split(',') if s.strip()]
faces=[p.normal_face_edit.text().strip()] if p.normal_face_edit.text().strip() else []
p.viewer.set_selection(edge_ids=edges,face_ids=faces);p.viewer.set_build_surface(None);p.viewer.set_coordinate_frames(());p.viewer.fit_view()
capture('curve_edges_zh');capture('curve_edges_normal_face_zh')
w.set_language('en');capture('curve_edges_en')
w.set_language('zh');w.open_project(e/'three_color_completed150_gui_project/project.json');w.enter_workbench('freeform');p=w.freeform_page;p.viewer.fit_view();p.editor_scroll.ensureWidgetVisible(p.solid_geometry_edit);pump();bar=p.editor_scroll.verticalScrollBar();bar.setValue(bar.value()+650);capture('freeform_three_leaf_roles_zh')
w.close();pump(.2)
