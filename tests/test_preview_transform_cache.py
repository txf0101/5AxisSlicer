from five_axis_slicer.manufacturing import preview_kinematics as pk


def motion(cache=None, angle=30, words=None, length=18):
    values = {"A": angle, "C": 20} if words is None else words
    return pk.reconstruct_preview_motion((1, 2, 30), (4, 5, 31), values, values,
        controller_semantics=pk.OWN_AC_PREVIEW_SEMANTICS, tool_length_mm=length,
        transform_cache=cache)


def test_pose_reuse_keeps_tool_length_and_material_positions_independent(monkeypatch):
    expected = [motion(length=length) for length in (18, 7)]
    original = pk._machine_to_workpiece_transform
    calls = []
    def measured(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(pk, "_machine_to_workpiece_transform", measured)
    cache = pk.PreviewTransformCache()
    assert [motion(cache, length=length) for length in (18, 7)] == expected
    assert len(calls) == 1
    motion(pk.PreviewTransformCache())
    assert len(calls) == 2


def test_unknown_words_and_nonfinite_values_still_fail_to_machine_coordinates():
    cache = pk.PreviewTransformCache()
    motion(cache)
    for words in ({"A": 30, "U": 0}, {"A": float("nan")}):
        cached = motion(cache, words=words)
        assert cached == motion(words=words)
        assert not cached.reconstructed


def test_continuous_angles_do_not_grow_cache_without_bound():
    cache = pk.PreviewTransformCache()
    for angle in range(150):
        assert motion(cache, angle=angle) == motion(angle=angle)
    assert len(cache._entries) == 128
