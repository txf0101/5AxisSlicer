"""Bundled paper-backed printer and defaults for new desktop projects."""

from __future__ import annotations

from importlib.resources import files
import json

from .machine import MachineProfile
from .resources import ResourceSnapshot
from .setup import ManufacturingSetup

OWN_AC_ID = "builtin.machine.own_ac_fdm.v1"


def own_ac_document() -> dict:
    return json.loads(
        files(__package__).joinpath("profiles/own_ac_fdm.json").read_text(encoding="utf-8")
    )


def own_ac_profile() -> MachineProfile:
    return MachineProfile.from_json(own_ac_document()["profile"])


def default_printer_setup() -> ManufacturingSetup:
    return ManufacturingSetup().with_machine(ResourceSnapshot.capture("machine", own_ac_profile()))
