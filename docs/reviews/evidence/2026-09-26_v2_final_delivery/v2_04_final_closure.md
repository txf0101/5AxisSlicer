# V2-04 教程图片收口建议

建议关闭教程图片与图注子任务。原始 83 处引用已逐项关联最终处置，见 v2_04_final_disposition.json；原始 15 个低对比度候选全部有实际视觉判断及替换/保留理由。29 个编号原图完成替换，涉及 66 处引用；16 个编号图和额外 3 个普通链接唯一图保留，合计覆盖 48 个唯一原图。另新增一张校徽局部图。

当前指南 218 个本地链接无缺失，git diff --check 通过。主 Agent 的 audit_guide_images.py 报告当前 84 处内嵌图片引用、missing=0；23 个低对比候选是统计提示，不能推翻逐图可辨性判断，也不增加重拍门槛。

首页、机床、材料已有语言匹配的中英图；其余英文页面复用中文图处已注明 Chinese-interface example 或中文界面说明，未把中文图冒称英文界面。保留图仅作参数、状态或路径类型教学；当前截图的草稿、生成、Warning、Error、Stale 均按真实状态描述。

8 个素材过程 JSON 已迁入 guide_capture_records，本轮逐文件 SHA256 核验通过。6 张已被替换且含内部捕获标记的旧图从用户 assets 移入 guide_capture_records/retired_images，内容原样保留，见 retired_image_relocation_manifest.json。教程 Markdown 未检出 Computer Use、paint harness、EvidenceViewer 或捕获失败过程表述；实际逐图审阅中的过程标记图均已退出教程与用户素材目录。没有使用生成图或改色遮蔽错误。

两处当前图仍有位于非关键撤销区/区域间的鼠标光晕，未覆盖教学控件、错误文字、角区字段或路径，已按计划 §8 记录保留理由。蓝色细线保持实际颜色，不因外观再次拍摄。该处属于明确的有限保留，并非声称全部截图绝无光晕。

最后 Around Part 图核对实际状态 JSON：区域 crosses_zero=true/false，R20/H20、轴步2mm、采样5°、进给900/1800、omega0.5；图中不显示空移。由此必需补拍清单为空。该结论只关闭教程内容检查，不代表真实打印机标定或制造放行；主台账由主 Agent 更新。
