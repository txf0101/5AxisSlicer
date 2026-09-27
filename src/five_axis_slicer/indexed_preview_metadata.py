"""Explicit Indexed TCP-to-material preview metadata; legacy NC stays untouched."""

import json
import math

from .manufacturing.tube_tcp import indexed_centerline_to_tcp


def indexed_preview_comments(toolpath):
    tcp = indexed_centerline_to_tcp(toolpath)
    widths = _point_widths(toolpath.points)
    result = []
    for center, tip, width in zip(toolpath.points, tcp.points, widths, strict=True):
        offset = math.dist(center.position, tip.position)
        result.append(
            "; INDEXED_TUBE_POINT "
            + json.dumps(
                {
                    "center_offset_mm": offset,
                    "height_mm": offset * 2,
                    "width_mm": width,
                },
                separators=(",", ":"),
            )
        )
    return result


def _point_widths(points):
    """Keep local widths; a layer may contain several tracks or vary along one."""
    following = []
    width = None
    for point in reversed(points):
        if point.point_type == "deposition":
            width = point.bead_width_mm
        following.append(width)
    result = []
    previous = None
    for point, after in zip(points, reversed(following), strict=True):
        width = point.bead_width_mm
        if width is None:
            width = previous if point.point_type == "depart" else after
        if width is None or not math.isfinite(width) or width <= 0:
            raise ValueError("Indexed point requires positive associated bead width")
        result.append(width)
        if point.point_type == "deposition":
            previous = width
    return result


class IndexedPreviewMetadata:
    def __init__(self):
        self.enabled = False
        self.pending = None
        self.offset = 0.0

    def comment(self, comment):
        if comment.startswith("INDEXED_TUBE_POSITION "):
            if comment != "INDEXED_TUBE_POSITION tip_from_center_v1":
                raise ValueError("Unsupported Indexed Tube position semantics")
            self.enabled = True
        elif comment.startswith("INDEXED_TUBE_POINT "):
            if not self.enabled:
                raise ValueError("Indexed point metadata requires position declaration")
            values = json.loads(comment.split(" ", 1)[1])
            for key in ("center_offset_mm", "height_mm", "width_mm"):
                value = values.get(key)
                if isinstance(value, bool) or not isinstance(value, (float, int)):
                    raise ValueError("Indexed point dimensions must be numeric")
                if not math.isfinite(value) or value <= 0:
                    raise ValueError("Indexed point dimensions must be finite and positive")
            if not math.isclose(values["height_mm"], 2 * values["center_offset_mm"], abs_tol=1e-8):
                raise ValueError("Indexed center offset must equal half layer height")
            if self.pending is not None:
                raise ValueError("Unconsumed Indexed point metadata")
            self.pending = values

    def motion(self, spatial):
        start = self.offset
        dimensions = None
        if self.enabled and spatial:
            if self.pending is None:
                raise ValueError("Indexed spatial motion is missing point metadata")
            dimensions = self.pending
            self.offset = dimensions["center_offset_mm"]
            self.pending = None
        return self.enabled, start, self.offset, dimensions


def material_preview_positions(reconstruction, values):
    start, end = reconstruction.start, reconstruction.end
    if not values.indexed_material:
        return start, end
    if not reconstruction.reconstructed:
        raise ValueError("Indexed material preview requires known controller kinematics")
    start = tuple(
        v + n * values.center_offset_start
        for v, n in zip(start, reconstruction.start_nozzle_axis, strict=True)
    )
    end = tuple(
        v + n * values.center_offset_end
        for v, n in zip(end, reconstruction.end_nozzle_axis, strict=True)
    )
    return start, end
