from __future__ import annotations


TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": {
        "app_title": "5AxisSclicer V2.0 前置选择器",
        "open": "打开 STEP",
        "save": "保存项目",
        "clear": "清空选择",
        "fit": "适配视图",
        "home": "初始视角",
        "language": "English",
        "left_title": "输入与选择",
        "right_title": "当前选择",
        "body_list": "块体列表",
        "edge_list": "边线列表",
        "status_ready": "就绪",
        "status_loaded": "已载入：{body_count} 个 body，{edge_count} 条 edge",
        "status_single_body": "已载入单实体 STEP；首版不做区域自动识别",
        "status_saved": "已保存项目：{path}",
        "status_error": "错误：{message}",
        "no_model": "尚未载入模型",
        "http": "HTTP 自动化：{url}",
    },
    "en": {
        "app_title": "5AxisSclicer V2.0 Preprocessor",
        "open": "Open STEP",
        "save": "Save Project",
        "clear": "Clear",
        "fit": "Fit",
        "home": "Home",
        "language": "中文",
        "left_title": "Input and Selection",
        "right_title": "Selection",
        "body_list": "Bodies",
        "edge_list": "Edges",
        "status_ready": "Ready",
        "status_loaded": "Loaded {body_count} bodies and {edge_count} edges",
        "status_single_body": "Single-solid STEP loaded; automatic region detection is out of scope",
        "status_saved": "Project saved: {path}",
        "status_error": "Error: {message}",
        "no_model": "No model loaded",
        "http": "HTTP automation: {url}",
    },
}


def tr(language: str, key: str, **kwargs: object) -> str:
    text = TRANSLATIONS.get(language, TRANSLATIONS["zh"]).get(key, key)
    return text.format(**kwargs)
