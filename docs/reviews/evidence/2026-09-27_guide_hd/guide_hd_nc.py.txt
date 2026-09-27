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
w.set_language('zh')
e=ROOT/'docs/reviews/evidence/2026-09-26_v2_final_delivery'
for name,folder in [('gcode_logo_file_preview_zh','logo_current150_gui_export'),('tube_indexed_export_zh','tube_v7_gui_export')]:
 w.start_result_load(gcode_path=e/folder/'main.gcode')
 deadline=time.monotonic()+600
 while w.result_page.state.status=='loading' and time.monotonic()<deadline:pump(.1)
 assert w.result_page.state.status in {'ready','warning'},w.result_page.state.status
 page=w.result_page;page.set_visibility(show_model=False,show_travel=False,show_pose_samples=False)
 if 'logo' in name and page.stage_combo.count()>2:page.stage_combo.setCurrentIndex(2)
 page.viewer.fit_view();pump();capture(name)
 if 'logo' in name:
  page.viewer.camera_command('zoom',1.5);capture('logo_nc_stage2_detail')
(OUT/'nc_capture_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
w.close();pump(.2)
