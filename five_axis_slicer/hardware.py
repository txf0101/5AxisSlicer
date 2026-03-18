"""Machine presets for the slicer.

The current preset follows the hardware concept from Freddie Hong's Open5x
paper: a converted Cartesian printer with a two-axis rotary bed labelled U/V.
"""

from __future__ import annotations

from .core import MachineParameters

# The default Open5x-style machine profile lives here so the GUI, CLI, and
# exporter all start from the same calibration baseline.
# 默认的 Open5x 风格机床预设集中放在这里，GUI、CLI、导出器就能共用同一套
# 标定基线。

OPEN5X_PROFILE_NAME = "Open5x / Prusa i3 MK3s (Freddi Hong style)"
OPEN5X_PROFILE_DESCRIPTION = (
    "Converted Cartesian printer with a rotary bed. U is the bed tilt around the machine Y axis. "
    "V is the spin of the already tilted bed around its local rotary axis."
)
OPEN5X_PROFILE_DESCRIPTION_ZH = (
    "笛卡尔三轴打印机加装双旋转打印床。U 轴让床面绕机器 Y 轴倾斜，"
    "V 轴让已经倾斜的床面继续绕局部旋转轴转动。"
)


def open5x_freddi_hong_machine() -> MachineParameters:
    """Return the default machine preset used by this project.

    返回本项目默认使用的机床预设。

    The numeric offsets are still conservative because every converted printer
    needs a last round of measurements on the real machine. What matters here
    is that the axis meaning, signs, homes, and template structure already
    match the Open5x workflow.
    数值偏移先收得比较保守，因为每台改装机器最后都得回到实机再量一遍。
    更重要的是，轴的含义、方向、回零角和模板结构已经先对齐了 Open5x 的
    工作流。
    """

    return MachineParameters(
        profile_name=OPEN5X_PROFILE_NAME,
        profile_description=OPEN5X_PROFILE_DESCRIPTION,
        x_offset_mm=0.0,
        y_offset_mm=0.0,
        z_offset_mm=0.0,
        rotary_center_x_mm=0.0,
        rotary_center_y_mm=0.0,
        rotary_center_z_mm=0.0,
        bed_diameter_mm=90.0,
        rotary_scale_radius_mm=35.0,
        phase_change_lift_mm=8.0,
        u_axis_sign=1,
        v_axis_sign=1,
        u_zero_offset_deg=0.0,
        v_zero_offset_deg=0.0,
        home_u_deg=0.0,
        home_v_deg=0.0,
        min_u_deg=-95.0,
        max_u_deg=95.0,
        min_v_deg=-540.0,
        max_v_deg=540.0,
        max_feed_mm_min=9000.0,
        linear_axis_names=("X", "Y", "Z"),
        rotary_axis_names=("U", "V"),
    )


def machine_profile_summary(machine: MachineParameters, language: str = "en") -> str:
    """Build the short machine summary shown in the GUI and README examples.

    生成 GUI 和 README 示例里那段简短的机床摘要。
    """

    if language == "zh":
        return (
            f"{machine.profile_name}：U={machine.u_axis_name} 绕机器 Y 轴倾斜，"
            f"V={machine.v_axis_name} 绕倾斜后的局部轴转动，"
            f"旋转中心=({machine.rotary_center_x_mm:.1f}, {machine.rotary_center_y_mm:.1f}, {machine.rotary_center_z_mm:.1f}) mm，"
            f"回零角度=({machine.home_u_deg:.1f}, {machine.home_v_deg:.1f}) deg"
        )
    return (
        f"{machine.profile_name}: U={machine.u_axis_name} tilt around machine Y, "
        f"V={machine.v_axis_name} spin around the local tilted axis, "
        f"rotary centre=({machine.rotary_center_x_mm:.1f}, {machine.rotary_center_y_mm:.1f}, {machine.rotary_center_z_mm:.1f}) mm, "
        f"home=({machine.home_u_deg:.1f}, {machine.home_v_deg:.1f}) deg"
    )
