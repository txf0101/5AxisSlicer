"""Project-level bindings between the shared Setup and workbench-local copies."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .manufacturing.setup import ManufacturingSetup


LOCAL_WORKBENCHES = ("planar", "curve", "freeform", "rotary")


def local_copy(common: ManufacturingSetup, workbench: str) -> ManufacturingSetup:
    if workbench not in LOCAL_WORKBENCHES:
        raise ValueError(f"unsupported local Setup workbench: {workbench}")
    return replace(
        common,
        setup_id=f"{common.setup_id}-{workbench}",
        name=f"{common.name} ({workbench})",
    )


def publish_to_common(local: ManufacturingSetup, common: ManufacturingSetup) -> ManufacturingSetup:
    """Copy manufacturing values while retaining the shared Setup identity."""

    return replace(local, setup_id=common.setup_id, name=common.name)


def resolve_bindings(
    setups: tuple[ManufacturingSetup, ...], workbench_state: Mapping[str, Any]
) -> tuple[ManufacturingSetup, dict[str, ManufacturingSetup]]:
    """Reject ambiguous project bindings instead of assigning the wrong machine."""

    by_id = {item.setup_id: item for item in setups}
    if len(by_id) != len(setups):
        raise ValueError("project contains duplicate Manufacturing Setup IDs")
    raw = workbench_state.get("setup_bindings")
    if raw is None:
        if len(setups) > 1:
            raise ValueError("multiple Setups require explicit workbench setup_bindings")
        common = setups[0] if setups else ManufacturingSetup()
        return common, {key: common for key in LOCAL_WORKBENCHES}
    if not isinstance(raw, Mapping):
        raise ValueError("workbench setup_bindings must be an object")
    common_id = raw.get("common")
    if not isinstance(common_id, str) or common_id not in by_id:
        raise ValueError("workbench common Setup binding is missing or unknown")
    if setups and setups[0].setup_id != common_id:
        raise ValueError("common Manufacturing Setup must be first in project Setups")
    common = by_id[common_id]
    bindings: dict[str, ManufacturingSetup] = {}
    local_ids: set[str] = set()
    for key in LOCAL_WORKBENCHES:
        setup_id = raw.get(key, common_id)
        if not isinstance(setup_id, str) or setup_id not in by_id:
            raise ValueError(f"workbench {key} Setup binding is missing or unknown")
        if setup_id != common_id:
            if setup_id in local_ids:
                raise ValueError("two workbenches cannot share one local Setup ID")
            local_ids.add(setup_id)
        bindings[key] = by_id[setup_id]
    return common, bindings


def binding_ids(common: ManufacturingSetup, bindings: Mapping[str, ManufacturingSetup]) -> dict[str, str]:
    return {"common": common.setup_id, **{key: bindings[key].setup_id for key in LOCAL_WORKBENCHES}}
