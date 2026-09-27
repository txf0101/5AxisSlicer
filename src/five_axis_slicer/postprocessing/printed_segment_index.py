"""Conservative spatial candidate index for previously deposited segments."""

from bisect import bisect_left
from itertools import product
import math


class _PrintedSegmentIndex:
    """Conservative spatial cache for deposited segments before a service move.

    Each segment occupies every grid cell intersecting its bead/nozzle-padded
    bounding box. Querying sample-centre cells can only add candidates; the
    existing exact section-to-segment check remains the collision criterion.
    """

    def __init__(self, toolpath, maximum_radius, *, checkpoint=None):
        self.cell_size = max(1.0, 4.0 * maximum_radius)
        self.planar_xy_size = max(1.0, 2.0 * maximum_radius)
        self.planar_z_size = 1.0
        self.nonplanar_cells: dict[tuple[int, ...], list[int]] = {}
        self.planar_cells: dict[tuple[int, ...], list[int]] = {}
        self.planar_broad_cells = None
        self._planar_bounds = []
        self.maximum_radius = maximum_radius
        points = toolpath.points
        for index in range(1, len(points)):
            if checkpoint is not None and index % 4096 == 0:
                checkpoint()
            right = points[index]
            if right.point_type != "deposition":
                continue
            start, end = points[index - 1].position, right.position
            bead_radius = max(right.bead_width_mm or 0.0, right.layer_height_mm or 0.0) / 2.0
            padding = bead_radius + maximum_radius + 0.5
            planar = (
                right.bead_width_mm is not None
                and right.layer_height_mm is not None
                and abs(start[2] - end[2]) <= 1.0e-6
                and math.dist(right.nozzle_axis, (0.0, 0.0, -1.0)) <= 1.0e-6
            )
            if planar:
                self._planar_bounds.append((index, start, end, padding))
                xy_ranges = tuple(
                    range(
                        math.floor((min(start[axis], end[axis]) - padding) / self.planar_xy_size),
                        math.floor((max(start[axis], end[axis]) + padding) / self.planar_xy_size) + 1,
                    )
                    for axis in (0, 1)
                )
                top_bucket = math.floor(end[2] / self.planar_z_size)
                for xy in product(*xy_ranges):
                    self.planar_cells.setdefault((*xy, top_bucket), []).append(index)
                continue
            ranges = tuple(
                range(
                    math.floor((min(start[axis], end[axis]) - padding) / self.cell_size),
                    math.floor((max(start[axis], end[axis]) + padding) / self.cell_size) + 1,
                )
                for axis in range(3)
            )
            for key in product(*ranges):
                self.nonplanar_cells.setdefault(key, []).append(index)

    def _build_planar_broad_cells(self, checkpoint=None):
        if self.planar_broad_cells is not None:
            return
        broad: dict[tuple[int, ...], list[int]] = {}
        for ordinal, (index, start, end, padding) in enumerate(self._planar_bounds):
            if checkpoint is not None and ordinal % 1024 == 0:
                checkpoint()
            ranges = tuple(
                range(
                    math.floor((min(start[axis], end[axis]) - padding) / self.cell_size),
                    math.floor((max(start[axis], end[axis]) + padding) / self.cell_size) + 1,
                )
                for axis in range(3)
            )
            for key in product(*ranges):
                broad.setdefault(key, []).append(index)
        self.planar_broad_cells = broad

    def candidates(
        self, service_samples, sequence, *, planar_exact=True, maximum_height=None,
        checkpoint=None,
    ):
        candidate_indices: set[int] = set()
        visited_cells = set()

        def collect(cells, key):
            identity = (id(cells), key)
            if identity in visited_cells:
                return
            visited_cells.add(identity)
            bucket = cells.get(key, ())
            # Construction appends increasing point indices. Exclude future
            # material before copying a bucket, not after every sample query.
            stop = bisect_left(bucket, sequence)
            for start in range(0, stop, 4096):
                if checkpoint is not None:
                    checkpoint()
                candidate_indices.update(bucket[start:min(start + 4096, stop)])

        vertical_tip_positions = set()
        need_planar_broad = False
        if maximum_height is None:
            maximum_height = max(sample[7] for sample in service_samples)
        for ordinal, sample in enumerate(service_samples):
            if checkpoint is not None and ordinal % 1024 == 0:
                checkpoint()
            center, _radius, axis, _lower, _upper, _label, _exempt, height, _remaining = sample
            key = tuple(math.floor(value / self.cell_size) for value in center)
            collect(self.nonplanar_cells, key)
            if planar_exact and math.dist(axis, (0.0, 0.0, 1.0)) <= 1.0e-6:
                if height <= 1.0e-9:
                    vertical_tip_positions.add(tuple(center))
            else:
                need_planar_broad = True
        for ordinal, tip in enumerate(vertical_tip_positions):
            if checkpoint is not None and ordinal % 1024 == 0:
                checkpoint()
            x_bucket = math.floor(tip[0] / self.planar_xy_size)
            y_bucket = math.floor(tip[1] / self.planar_xy_size)
            # A horizontal bead can meet the vertical nozzle only at or above
            # the tip.  Query its actual layer-top bin, not every lower layer
            # inside the nozzle's broad 3-D sphere.
            first_z = math.floor((tip[2] - 1.0e-9) / self.planar_z_size)
            last_z = math.floor((tip[2] + maximum_height + 1.0e-9) / self.planar_z_size)
            for z_bucket in range(first_z, last_z + 1):
                collect(self.planar_cells, (x_bucket, y_bucket, z_bucket))
        if need_planar_broad:
            self._collect_broad(service_samples, planar_exact, collect, checkpoint)
        return sorted(candidate_indices)

    def _collect_broad(self, service_samples, planar_exact, collect, checkpoint):
        self._build_planar_broad_cells(checkpoint)
        assert self.planar_broad_cells is not None
        for ordinal, sample in enumerate(service_samples):
            if checkpoint is not None and ordinal % 1024 == 0:
                checkpoint()
            center, _radius, axis, *_ = sample
            if planar_exact and math.dist(axis, (0.0, 0.0, 1.0)) <= 1.0e-6:
                continue
            key = tuple(math.floor(value / self.cell_size) for value in center)
            collect(self.planar_broad_cells, key)

