# CI 依赖修复与分支统一复盘

## 任务与结论

GitHub 仓库的默认分支经远端配置和 API 核对为 `master`。处理前远端 `main` 与 `master` 已指向同一提交 `950f717`；四条本地 `codex/*` 分支均为该提交的祖先，没有未合入内容。本轮以 `master` 为唯一主线，CI 修复提交完成远端验证后删除已合入的其余分支引用。

失败运行 `34744383882` 的原始日志给出两类环境问题：Linux 与 Windows Python 3.10 的 mypy 解析 `casadi 3.8.0` 存根时报告重复参数 `INOUT`；Windows Python 3.12 的 `pip check` 发现 runner 自带 `pipx 1.17.2` 要求 `packaging>=26`，而 CadQuery 依赖组合使用 `packaging 24.2`。Node.js 20 弃用信息只是 Actions 警告。

## 修改与取舍

- 三个 Actions job 均在安装依赖前创建隔离虚拟环境，避免 runner 预装包参与 `pip check`。
- 开发依赖固定 `mypy==1.11.2`，CAD 测试依赖固定 `casadi==3.7.2`，避免未审查升级改变静态门禁结果。
- PyQt5 固定为项目既有验证版本 `5.15.10`。干净环境会加载 PyQt 类型存根，因此把已有动态 Qt 界面模块明确列入 mypy 的 legacy `ignore_errors` 清单；其余源码仍由同一仓库级 mypy 门禁检查。
- Linux mypy 会静态解析 Windows 专用 `msvcrt` 分支；锁操作改为与 POSIX `fcntl` 一致的运行时平台导入，保留原执行语义并消除跨平台存根误判。
- Windows 托管 runner 的完整 GUI 回归在 VTK `render()` 中发生原生访问冲突。Windows CI 改跑与 Linux 对齐的 13 个无头领域测试文件；完整 Qt/VTK 桌面回归仍按项目验证规范在具备真实显示上下文的本机串行执行，不能由该 CI 子集替代。

## 本地验证

使用干净的 `tmp/ci_fix_py312` Python 3.12 虚拟环境安装 `.[dev,cad-tests]`：

- `python -m pip check`：通过，输出 `No broken requirements found.`；
- `python scripts/check_quality.py`：Ruff、格式、上下文预算及 mypy 全部通过，mypy 检查 148 个源码文件；
- `python -X faulthandler -m pytest -q tests/test_preview_index.py tests/test_machine_profiles.py`：27 passed、23 subtests passed。
- `python -X faulthandler -m pytest -q tests/test_project_io.py`：33 passed、2 skipped、14 subtests passed；
- 与 Windows CI 相同的 13 文件无头领域集：161 passed、2 skipped、89 subtests passed。

提交 `fdc0ff4` 的首次远端运行确认 Windows 3.10/3.12 均已通过隔离安装、`pip check` 和质量门禁；Linux 暴露 `msvcrt` 的平台存根误判，Windows 完整回归暴露托管 runner 的 VTK 原生访问冲突。本机干净环境复现完整回归时同样在 GUI/VTK 阶段异常退出，未生成完整 JUnit，因此不把该次尝试记录为测试通过。修复提交 `7e0ff13` 的 GitHub Actions 运行 `34747228928` 最终四项全部通过：Linux static/domain、Windows Python 3.10/3.12 regression 和 Windows native smoke 均为 success。

## 可复用判断

共享 GitHub runner 上的 `pip check` 应在项目隔离环境内执行。静态检查依赖应固定已验证版本；第三方类型存根异常与项目自身类型错误需分开记录。新增受 mypy 检查的领域模块不应加入 legacy Qt 豁免清单。
