# V2-03 / V2-05 当前收口核查

2026-09-27，三叶扇当前 GUI 生成期间完成只读复核。依据第二代收尾计划第3、4、7、8节、最新进度台账和下列现存证据。沿用 five-axis-slicer-validation Skill。未重启应用、运行测试或修改主台账；仅新增本报告。

## V2-03：现有证据足以关闭限定的体验验收

建议主任务将 V2-03 记为通过，并保留首次大 NC 加载缓慢的限制。计划未规定必须低于某一秒数，也未要求对每个模型重复全部取消测试，不再新增同类大模型复验。

| 实际判据 | 当前证据及判断 |
| --- | --- |
| 高点数任务生成期间有明确状态，记录机器和输入 | `v2_03_machine_environment.json`：i7-12700H，14核20线程，31.8GB，Windows11，隔离Python环境。`v2_03_impeller_fixed_start.txt`、`v2_03_impeller_fixed_generating.json`、`v2_02_impeller_fixed_completed_state.json`与摘要记录居中叶轮生成；起始观察16:09:53、完成16:33:54.992，约24分02秒，属于观察区间而非精确点击计时。 |
| 取消检查点结束，不产生伪成功，不破坏有效旧结果 | `v2_03_tube_generating.png`、`v2_03_tube_cancelled.png`及generation_state证明空结果取消后导出未误启用；`v2_03_logo_cancel_state.json`、`v2_03_logo_cancel_preserved.png`证明有效校徽结果取消后保留，导出重新可用，台账记录产品JSON前后相等。旧GUI证据先于索引性能改动；新增索引取消检查点由 `impeller_candidate_index_final.xml` 中查询可取消测试补验，未更改发布/保留旧结果语义。不能声称所有阶段或所有模型都具相同取消延迟。 |
| 复现的生成卡顿得到处理，界面可操作 | 原未响应截图/栈保留；`impeller_candidate_fix.md`、`impeller_candidate_benchmark.json`和25项相关回归记录根因及修复。修复后的 `v2_03_impeller_fixed_hide_responsive.png`、运行观察和材料/语言对话框真实操作证明生成期间响应，完整叶轮最终生成成功。没有把HTTP超时当自然结束。 |
| 模型显隐、全线、过滤、方向和放大可用 | Tube429层范围切换、校徽工序1/2及细节图、叶轮810990点全部沉积与空移、操作2旋转放大、操作3切换有当前真实GUI记录。主要证据为 `v2_02_v7_gui_nc_travel_rotated.png`、`v2_02_logo_nc_stage1.png`、`v2_02_logo_nc_stage2.png`、`v2_02_impeller_nc_travel.png`、`v2_02_impeller_nc_stage2_rotated.png`、`v2_02_impeller_nc_stage3.png`以及台账对应点击记录。 |
| 高点数可查看全部路线，完成后交互可用 | `v2_02_impeller_nc_preview_summary.json`记录810990空间段、780606挤出段、30384空移/非挤出段，加载complete、当前op03及全部显示开关；实际操作证据见上项。首次无缓存worker403.273939秒、端到端407.922299秒，必须保留“首次加载慢”，不宣传快速。现有记录支持载入后交互响应，不是全程逐毫秒响应测量。 |

本判断区分“耗时较长的首次解析”与“绘制后长期不能交互”。现有证据未显示修复后的绘制交互再次长期失去响应。计划没有要求新增性能目标，故不因缺少逐阶段精确秒表、全模型统一延迟或首次解析优化而继续开放此包。三叶当前生成结果仍属于 V2-02，不需因此重新打开已覆盖的 V2-03 判据。

## V2-05：仍未满足的事项与最短顺序

已满足的局部判据：隔离环境依赖安装/Qt启动及Tube实际六件套导出；依赖缺漏与中文路径Qt修复已验证。`quality_impeller_candidate_final.log`包含完整质量门禁成功、Mypy220文件；最新build与Twine成功。`v2_05_final_wheel_source_check.json`记录220源码一致，本报告再次只读比较wheel内Python文件与当前src，差异仍为空。安装包SHA256为 `6402ac8d6b08bdffa36bebfb52f33a9a2f0e0fd301ae8985697fe7f06ba400a9`。

仍需完成：

1. 教程收口后的双语链接、图片和操作描述一致性确认。当前尚有教程代理工作，不能把早先218链接通过扩展到未完成修改。
2. 本轮最终串行全仓回归。当前代码涉及多个共享模块，已有专项不能替代这一最终检查。等主GUI操作完成再运行，避免Qt/QSettings冲突；不要为等待而启动第二套测试。
3. 最终wheel安装与启动核对。已有新环境GUI导出满足原计划短流程条款，无需再跑大叶轮。关闭应用后在既有隔离环境安装最终wheel，清除PYTHONPATH，验证导入来自site-packages、pip check、真实启动并打开小示例；若想补一次短流程，仅用已有小例。不得在三叶生成期间改其运行环境。
4. 显式选定提交内容并取得该提交四项CI成功。此前edacd49的CI不代表当前源码。依照 `v2_05_commit_scope_review.md`，不整仓暂存历史产物或巨型证据。

建议命令，执行前确认输出名未使用及GUI已退出：

```powershell
$env:PYTHONPATH='src'
$env:QT_QPA_PLATFORM='offscreen'
& tmp/pytest9/Scripts/python.exe -X utf8 -X faulthandler -m pytest -q -ra --basetemp=tmp/v2_final_pytest_20260927 --junitxml=docs/reviews/evidence/2026-09-26_v2_final_delivery/v2_05_final_pytest.xml
```

若basetemp已存在则换唯一新名；保留既定180秒测试超时。失败只诊断最小失败集，按新增修复影响复验，不无条件重跑完整集。

```powershell
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
& tmp/v2_clean_install/Scripts/python.exe -m pip install --force-reinstall --no-deps 'tmp/v2_release_final/five_axis_slicer-2.6.3.dev3+gedacd49.d20260927-py3-none-any.whl'
& tmp/v2_clean_install/Scripts/python.exe -m pip check
& tmp/v2_clean_install/Scripts/python.exe -c "import five_axis_slicer; print(five_axis_slicer.__file__)"
$env:QT_QPA_PLATFORM='windows'
& tmp/v2_clean_install/Scripts/python.exe -X utf8 -m five_axis_slicer
```

现有wheel是工作区候选版本。若源码变化必须重新build/Twine/源码匹配；仅指南文字改动不重跑整件NC。最终提交后，依据版本策略更新包与提交映射，不能把候选包名称中的旧HEAD当最终提交证明。

当前唯一工作流 `.github/workflows/quality.yml` 要求Windows3.10、Windows3.12、Linux static-domain、Windows native-smoke四项成功。没有必要为CI发布GitHub Release或创建空提交；先核对本地/远端差异及明确暂存内容，再运行该提交对应CI。V2-05在这些证据齐全前保持进行中。
