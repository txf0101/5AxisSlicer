# 2026-07-09 G-code 查看入口复盘

## 本轮对象

本轮调整首页右上角原演示入口。用户要求该按钮改为“示意gcode查看”，点击后进入选择 G-code 文件流程，让软件可直接作为 G-code 查看器使用。

动手前已核对项目依据：`README.md` 说明当前主线是 `Imported NC Review`；`docs/project_structure.md` 记录 G-code 解析、缓存、OpenGL/VTK 预览和 HTTP 自动化链路；`docs/reviews/2026-07-06_workbench_nc_preview_review.md` 说明该阶段主打导入已有 G-code 后检查路径；`圭臬/开发目标文档.docx` 时间戳为 2026-07-06 13:45:16，文档内容要求软件以 Workbench 为入口，并提供 NC 路径预览和检查能力。

## 修改内容

- 首页右上角按钮文案改为“示意gcode查看”，英文界面对应为 `Open G-code Viewer`。
- 按钮行为从 `load_demo()` 改为 `open_gcode_dialog()`，点击后直接打开 NC/G-code 文件选择框。
- `open_gcode()` 载入成功后统一切换到 Operation Session 的 Preview 页。菜单、左侧按钮、HTTP 入口和首页按钮共用同一条载入后显示逻辑。
- 保留 `load_demo()`、`--demo` 和 `/demo/load`，不影响旧截图脚本和演示自动化。
- 新增 UI 回归测试：点击首页按钮时模拟文件选择，验证 G-code 被载入、主界面进入 Session、右侧页签切到 Preview，并检查中英文按钮文案。

## 验证记录

- `python -m compileall src tests`：通过。
- `python -m unittest discover -s tests`：26 个测试通过。
- 真实应用链路冒烟：启动 GUI HTTP 服务后调用 `/gcode/open` 打开临时小 G-code，返回 `segment_count = 4`、`layer_count = 1`，当前工作台为 `curve`，操作为 `imported_nc_review`。

第一次 HTTP 冒烟把测试 G-code 放在工作区路径下，Windows PowerShell 发送 JSON 时把中文路径编码成问号，服务端返回文件不存在。改用系统临时目录的 ASCII 路径后应用链路通过。按钮文件选择由 Qt 返回本机路径，不走这条 PowerShell JSON 编码路径；后续若要强化 HTTP 自动化，可补一个中文路径 payload 编码用例。

## 方法沉淀

这次改动的价值在于把“演示样例入口”收敛成“真实文件查看入口”，同时保留原有 demo 自动化。成熟桌面工程软件通常会让导入入口、预览状态和自动化接口共享业务函数，本轮沿用 `open_gcode()` 作为唯一载入主线，避免首页按钮形成一套额外流程。

可复用做法有三点：入口按钮只负责触发文件选择；成功载入后的界面跳转放在业务函数内；回归测试用模拟文件选择覆盖按钮连接和状态切换。后续若增加 STEP 快速查看、项目打开或最近文件入口，也可沿这个结构扩展。
