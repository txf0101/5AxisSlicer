"""Describe the coordinates actually shown by a result preview."""

from .manufacturing.preview_kinematics import AC_INVERSE_TRANSFORM, MACHINE_COORDINATE_TRANSFORM


def coordinate_text(preview, language: str) -> str:
    english = language == "en"
    if preview is None:
        return "Coordinates: no path loaded" if english else "坐标：尚未加载路径"
    frame = preview.coordinate_transform
    if frame == MACHINE_COORDINATE_TRANSFORM:
        return (
            "Machine XYZ: workpiece shape has not been reconstructed"
            if english
            else "机床 XYZ：尚未还原工件形状"
        )
    if frame == AC_INVERSE_TRANSFORM:
        label = "Workpiece coordinates" if english else "工件坐标"
        return f"{label} · P = Rz(-C) × Rx(-A) × (XYZ − (0, 0, {preview.tool_length_mm:g} mm))"
    label = "Path coordinate frame" if english else "路径坐标系"
    return f"{label}: {frame}"
