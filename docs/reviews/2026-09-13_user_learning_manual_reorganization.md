# DOC-01 学习手册与教程矩阵重组复盘

日期：2026-09-13

## 本轮目标

把既有按模块平铺、容易被理解为“照着某个案例切片”的文档，整理为面向新使用者的学习体系。随附 pipe2、平面件、叶轮、扇叶和半球继续作为练手材料，但课程完成条件改为理解通用规则、自检并迁移到一个同类新零件。

## 实际调整

- 新增 `docs/guides/user_learning_manual_zh.md` 作为总册。正文开头写明 IDE 运行根目录 `run_app.py`，PowerShell 运行 `scripts/run_app.ps1`，并给出普通、Demo 和成果页启动方式。
- 总册按 L01—L09 公共主线和 W01—W05 工作台支线组织，覆盖界面、对象、Setup、坐标、工作台选择、操作、状态恢复、Viewer、NC 回读、六件套、项目重开和独立迁移。
- 重写 `docs/guides/README.md`，形成学习路线、工作台课程、公共参考和教程编写矩阵。每节课程需具备学习目标、通用概念、引导练习、判断、错误恢复、迁移任务和能力边界。
- Tube、Planar、Curve、Rotary 和 Freeform 参考手册增加学习总册入口及案例使用限制；根 README 和项目文档索引改为优先指向总册。

## 图片处理与判断

总册引用 10 张仓库内稳定图片，覆盖导入总览、Part、Model CS、机型、Curve、Rotary、Planar、Stale、Error 和可审查 Warning 路径。图片尺寸从 1366×768 到 2582×1550，全部可读取。错误态和 Stale 图在相邻正文中明确标注；参考机型 Warning 没有被写成生产资格。

用户指定了 `computer-use`。本轮完整读取其 Skill、运行指导、确认规则和 API 后，首次调用、轻量重试及会话重置后的重试均返回 `nodeRepl.fetch request failed`，且 `apps=[]`，无法选出唯一 Windows 窗口。因此没有新增或冒充 Computer Use 截图。总册复用的是当前版本既有 Qt/VTK 或证据绘制图片，并保留其原有证据边界。

## 内容验收

- `tmp/pytest9/Scripts/python.exe run_app.py --help` 退出码 0，确认 `--demo`、`--results`、模型、G-code、host 和 port 参数仍存在。
- PowerShell AST 解析 `scripts/run_app.ps1` 无语法错误；脚本实际调用根目录 `run_app.py`。
- 对本轮 11 个相关 Markdown 文件检查相对链接，全部目标存在。
- 总册 10 张图片均可由图像解码器读取并取得有效尺寸。
- `git diff --check` 通过；禁用句式扫描无命中。
- 本轮没有修改应用源码、UI 或制造算法。按验证 Skill 的文档改动规则，没有重复运行 856 项全仓回归。

## 取舍和后续边界

总册采用 Markdown 作为项目内唯一可维护源，模块文档继续作为参考手册，避免把同一参数表复制到多本文件。当前没有另制 PDF 或 DOCX，以免形成与源码手册不同步的第二版本；需要外发印刷版时可从总册单向生成并做独立版式验收。

Research、通用 Freeform F01—F06、完整第二机型和实机资格仍未完成。总册不为这些范围编写虚构操作。自有 AC 输出继续标明 `machine_executable=false`。

## 使用的 Skills

- `five-axis-workbench-development`：采用 UI、手册、错误恢复、能力边界和台账闭环要求。
- `five-axis-slicer-validation`：复用已验证解释器，按文档改动选择入口、链接和图片检查，不重复全仓回归。
- `computer-use`：按用户要求尝试 Windows 窗口操作；连接失败后按恢复规则停止并如实记录。
