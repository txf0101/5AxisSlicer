import math

import pytest

from five_axis_slicer.algorithms.tube.column_partition import partition_column


@pytest.mark.parametrize("length,count,last", [(0.5, 1, 0.5), (1.49, 1, 1.49),
                                                (1.5, 2, 0.5), (2.4, 2, 1.4), (3, 3, 1)])
def test_round_half_up_partition(length, count, last):
    result = partition_column(0, length, 1)
    assert result.supported
    assert result.count == count
    intervals = [result.interval(i) for i in range(count)]
    assert intervals[0][0] == 0
    assert intervals[-1][1] == length
    assert all(a[1] == b[0] for a, b in zip(intervals, intervals[1:]))
    assert intervals[-1][1] - intervals[-1][0] == pytest.approx(last)
    assert sum(b - a for a, b in intervals) == pytest.approx(length)
    assert result.interval(count) is None
    assert not result.ready_for_export


def test_sub_half_column_is_explicitly_unsupported():
    result = partition_column(0, 0.49, 1)
    assert not result.supported
    assert result.reason == "column_below_geometric_half_layer"
    assert result.count == 0
    assert result.interval(0) is None


def test_translation():
    a, b = partition_column(0, 2.4, 1), partition_column(-10, -7.6, 1)
    assert a.count == b.count
    for i in range(a.count):
        assert b.interval(i) == pytest.approx(tuple(x - 10 for x in a.interval(i)))


@pytest.mark.parametrize("args", [(0, 0, 1), (1, 0, 1), (0, 1, 0),
                                   (0, 1, -1), (0, math.inf, 1), (math.nan, 1, 1)])
def test_invalid_input(args):
    with pytest.raises(ValueError):
        partition_column(*args)


def test_negative_or_noninteger_index_rejected():
    result = partition_column(0, 1, 1)
    for index in (-1, 0.5, True):
        with pytest.raises((ValueError, TypeError)):
            result.interval(index)
