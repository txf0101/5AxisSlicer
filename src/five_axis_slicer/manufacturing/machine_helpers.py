"""Small implementation helpers for immutable MachineProfile values."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import Any

Vector3 = tuple[float, float, float]
Matrix4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]

RESERVED_POST_WORDS = frozenset({"E", "F", "G", "M", "N", "P", "S", "T"})


def rotary_axis_words(profile: Any, error_type: type[ValueError]) -> Mapping[str, str]:
    """Return a read-only, complete rotary joint-to-controller address map."""

    profile.validate()
    result: dict[str, str] = {}
    for joint in profile.joints:
        if joint.joint_type != "rotary":
            continue
        if joint.post_axis_map is None:
            raise error_type((f"joint:{joint.joint_id}.post_axis.missing",))
        result[joint.joint_id] = joint.post_axis_map.word
    return MappingProxyType(result)


def with_rotary_axis_words(profile: Any, words: Mapping[str, str]) -> Any:
    """Atomically update controller words while preserving all kinematic fields."""

    if not isinstance(words, Mapping):
        raise TypeError("rotary axis words must be a mapping")
    if not words:
        raise ValueError("rotary axis words must not be empty")
    updates: dict[str, str] = {}
    for raw_joint_id, word in words.items():
        joint_id = str(raw_joint_id).strip()
        if joint_id in updates:
            raise ValueError(f"duplicate rotary joint mapping: {joint_id}")
        joint = profile.joint_map.get(joint_id)
        if joint is None:
            raise KeyError(f"unknown machine joint: {joint_id}")
        if joint.joint_type != "rotary":
            raise ValueError(f"joint is not rotary: {joint_id}")
        if joint.post_axis_map is None:
            raise ValueError(f"rotary joint has no post-axis mapping: {joint_id}")
        updates[joint_id] = str(word)
    candidate = replace(
        profile,
        joints=tuple(
            replace(
                joint,
                post_axis_map=replace(joint.post_axis_map, word=updates[joint.joint_id]),
            )
            if joint.joint_id in updates
            else joint
            for joint in profile.joints
        ),
    )
    return candidate.validate()


def chain_errors(root_link_id: str, joints: Iterable[Any]) -> list[str]:
    child_to_parent = {
        joint.child_link_id: joint.parent_link_id for joint in joints if joint.child_link_id
    }
    errors: list[str] = []
    for child in sorted(child_to_parent):
        path: set[str] = set()
        current = child
        while current != root_link_id:
            if current in path:
                errors.append(f"joint.cycle:{current}")
                break
            path.add(current)
            parent = child_to_parent.get(current)
            if parent is None:
                break
            current = parent
    return errors


def translation_matrix(axis: Vector3, distance: float) -> Matrix4:
    return (
        (1.0, 0.0, 0.0, axis[0] * distance),
        (0.0, 1.0, 0.0, axis[1] * distance),
        (0.0, 0.0, 1.0, axis[2] * distance),
        (0.0, 0.0, 0.0, 1.0),
    )


def rotation_about_axis_matrix(axis: Vector3, center: Vector3, angle_rad: float) -> Matrix4:
    x, y, z = axis
    cosine = math.cos(angle_rad)
    sine = math.sin(angle_rad)
    one_minus_cosine = 1.0 - cosine
    rotation = (
        (
            cosine + x * x * one_minus_cosine,
            x * y * one_minus_cosine - z * sine,
            x * z * one_minus_cosine + y * sine,
        ),
        (
            y * x * one_minus_cosine + z * sine,
            cosine + y * y * one_minus_cosine,
            y * z * one_minus_cosine - x * sine,
        ),
        (
            z * x * one_minus_cosine - y * sine,
            z * y * one_minus_cosine + x * sine,
            cosine + z * z * one_minus_cosine,
        ),
    )
    cx, cy, cz = center
    translation = (
        cx - (rotation[0][0] * cx + rotation[0][1] * cy + rotation[0][2] * cz),
        cy - (rotation[1][0] * cx + rotation[1][1] * cy + rotation[1][2] * cz),
        cz - (rotation[2][0] * cx + rotation[2][1] * cy + rotation[2][2] * cz),
    )
    return (
        (*rotation[0], translation[0]),
        (*rotation[1], translation[1]),
        (*rotation[2], translation[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


__all__ = [
    "RESERVED_POST_WORDS",
    "chain_errors",
    "rotary_axis_words",
    "rotation_about_axis_matrix",
    "translation_matrix",
    "with_rotary_axis_words",
]
