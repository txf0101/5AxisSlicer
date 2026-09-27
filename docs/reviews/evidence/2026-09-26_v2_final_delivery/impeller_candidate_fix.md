# 居中叶轮候选索引热点修复

2026-09-27，V2-03局部修复。主线程两次只读py-spy栈定位 `_PrintedSegmentIndex.candidates` 重复桶合并。当时工序序号682，桶却包含未来全部沉积段，每个喷嘴截面样本重复合并整个桶，最终才过滤序号。该循环没有取消/事件检查点。

修复保留原桶几何及全部精确碰撞判定：每类索引中的同一网格只查询一次，升序桶用 `bisect_left(sequence)` 取严格已打印前缀，扫描/复制加入现有取消回调。索引类提取到 `postprocessing/printed_segment_index.py`，原入口导入兼容；未放宽容差、删检查或调整质量基线。

官方依据：https://docs.python.org/3/library/bisect.html#bisect.bisect_left ，其左侧严格小于查找值，符合既有 `index < sequence` 判据。

验证：`impeller_candidate_index_final.xml`，25 passed / 3.06s，覆盖既有有碰撞/无碰撞精确检查、平面与倾斜姿态、严格前缀边界、重复桶、查询取消。Ruff与context预算通过。`impeller_candidate_benchmark.json`：10万索引、2000重复样本，结果681个候选完全一致，旧1.129792s，新0.001925s；这是合成热点基准，不是完整叶轮耗时/GUI通过证据。当前进程重新载入后，仍需真实GUI生成与取消复验。

使用Skills：five-axis-workbench-development、five-axis-slicer-validation。主线程统一更新唯一台账与任务复盘。
