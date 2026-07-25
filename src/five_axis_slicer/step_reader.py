"""STEP/XCAF file reading, unit normalization, and product-name extraction."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Pnt, gp_Trsf
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPConstruct import STEPConstruct_UnitContext
from OCP.StepData import StepData_Factors, StepData_StepModel
from OCP.StepGeom import (
    StepGeom_GeometricRepresentationContextAndGlobalUnitAssignedContext,
    StepGeom_GeomRepContextAndGlobUnitAssCtxAndGlobUncertaintyAssCtx,
)
from OCP.TCollection import TCollection_ExtendedString
from OCP.TColStd import TColStd_SequenceOfAsciiString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_AttributeIterator, TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

from .models import CadUnitInfo
from .step_topology import body_shapes

CancelCheck = Callable[[], bool]
FirstAscii = Callable[[TColStd_SequenceOfAsciiString], str | None]

_UNIT_TO_MM = {
    "millimetre": 1.0,
    "millimeter": 1.0,
    "mm": 1.0,
    "centimetre": 10.0,
    "centimeter": 10.0,
    "cm": 10.0,
    "metre": 1000.0,
    "meter": 1000.0,
    "m": 1000.0,
    "inch": 25.4,
    "in": 25.4,
    "foot": 304.8,
    "feet": 304.8,
    "ft": 304.8,
    "micrometre": 0.001,
    "micrometer": 0.001,
    "um": 0.001,
}


@dataclass(frozen=True, slots=True)
class ProductBodyMetadata:
    shape: object
    kind: str
    name: str
    assembly_path: str


@dataclass(frozen=True, slots=True)
class _UnitResolution:
    source_unit: str
    declared_unit: str | None
    override_applied: bool
    conversion_source: str


class StepReaderError(RuntimeError):
    pass


class StepReaderCancelled(StepReaderError):
    pass


def read_root_shape(
    source_path: Path,
    *,
    length_unit_override: str | None,
    cancel_check: CancelCheck | None,
    first_ascii: FirstAscii,
) -> tuple[object, CadUnitInfo, tuple[ProductBodyMetadata, ...]]:
    """Read one STEP into millimetres and retain optional XCAF names."""

    _raise_if_cancelled(cancel_check)
    caf_reader, reader = _open_step(source_path)
    length_units, angle_units, solid_angle_units = _file_units(reader)
    resolution = _resolve_length_unit(length_units, length_unit_override, first_ascii)
    declared_factor_mm = _step_length_factor_mm(reader.StepModel(), cancel_check=cancel_check)
    reader.SetSystemLengthUnit(1.0)
    metadata, transferred = _transfer_xcaf(caf_reader, cancel_check)
    root_shape = _root_shape(reader, transferred, source_path)
    root_shape, metadata = _apply_override_scale(
        root_shape, metadata, resolution, declared_factor_mm
    )
    _raise_if_cancelled(cancel_check)
    return (
        root_shape,
        _unit_info(resolution, angle_units, solid_angle_units, first_ascii),
        metadata,
    )


def _open_step(source_path: Path) -> tuple[Any, Any]:
    caf_reader = STEPCAFControl_Reader()
    caf_reader.SetNameMode(True)
    if caf_reader.ReadFile(str(source_path)) != IFSelect_RetDone:
        raise StepReaderError(f"OpenCascade failed to read STEP: {source_path}")
    return caf_reader, caf_reader.ChangeReader()


def _file_units(
    reader: Any,
) -> tuple[
    TColStd_SequenceOfAsciiString,
    TColStd_SequenceOfAsciiString,
    TColStd_SequenceOfAsciiString,
]:
    length_units = TColStd_SequenceOfAsciiString()
    angle_units = TColStd_SequenceOfAsciiString()
    solid_angle_units = TColStd_SequenceOfAsciiString()
    reader.FileUnits(length_units, angle_units, solid_angle_units)
    return length_units, angle_units, solid_angle_units


def _resolve_length_unit(
    length_units: TColStd_SequenceOfAsciiString,
    override_value: str | None,
    first_ascii: FirstAscii,
) -> _UnitResolution:
    declared = first_ascii(length_units)
    normalized = _normalize_unit(declared)
    override = _normalize_unit(override_value)
    if normalized in _UNIT_TO_MM:
        assert normalized is not None
        return _UnitResolution(normalized, declared, False, "step_declaration")
    if override in _UNIT_TO_MM:
        assert override is not None
        source = (
            "override_missing_declaration"
            if normalized is None
            else "override_unsupported_declaration"
        )
        return _UnitResolution(override, declared, True, source)
    raise StepReaderError(
        "STEP length unit is missing or unsupported; provide length_unit_override "
        f"(declared={declared!r})"
    )


def _unit_info(
    resolution: _UnitResolution,
    angle_units: TColStd_SequenceOfAsciiString,
    solid_angle_units: TColStd_SequenceOfAsciiString,
    first_ascii: FirstAscii,
) -> CadUnitInfo:
    return CadUnitInfo(
        source_length_unit=resolution.source_unit,
        scale_to_mm=_UNIT_TO_MM[resolution.source_unit],
        angle_unit=first_ascii(angle_units),
        solid_angle_unit=first_ascii(solid_angle_units),
        override_applied=resolution.override_applied,
        declared_length_unit=resolution.declared_unit,
        conversion_source=resolution.conversion_source,
    )


def _step_length_factor_mm(
    model: StepData_StepModel,
    *,
    cancel_check: CancelCheck | None,
) -> float | None:
    """Read numeric context factors so an override cannot double-scale geometry."""

    factors: list[float] = []
    context_types = (
        StepGeom_GeomRepContextAndGlobUnitAssCtxAndGlobUncertaintyAssCtx,
        StepGeom_GeometricRepresentationContextAndGlobalUnitAssignedContext,
    )
    for index in range(1, model.NbEntities() + 1):
        if index == 1 or index % 256 == 0:
            _raise_if_cancelled(cancel_check)
        entity = model.Value(index)
        if not isinstance(entity, context_types):
            continue
        factor = _context_length_factor(entity.GlobalUnitAssignedContext())
        if factor is not None:
            factors.append(factor)
    unique = _unique_factors(factors)
    if len(unique) > 1:
        raise StepReaderError("STEP contains multiple incompatible length-unit contexts")
    _raise_if_cancelled(cancel_check)
    return None if not unique else unique[0]


def _context_length_factor(context: object) -> float | None:
    factors = StepData_Factors()
    factors.InitializeFactors(1.0, 1.0, 1.0)
    factors.SetCascadeUnit(1.0)
    unit_context = STEPConstruct_UnitContext()
    status = unit_context.ComputeFactors(context, factors)
    if status != 0 or not unit_context.LengthDone():
        return None
    value = float(unit_context.LengthFactor())
    return value if math.isfinite(value) and value > 0.0 else None


def _unique_factors(values: list[float]) -> list[float]:
    result: list[float] = []
    for value in values:
        if not any(
            math.isclose(value, known, rel_tol=1.0e-12, abs_tol=1.0e-12) for known in result
        ):
            result.append(value)
    return result


def _transfer_xcaf(
    caf_reader: Any,
    cancel_check: CancelCheck | None,
) -> tuple[tuple[ProductBodyMetadata, ...], bool]:
    application = XCAFApp_Application.GetApplication_s()
    document_format = TCollection_ExtendedString("MDTV-XCAF")
    document = TDocStd_Document(document_format)
    application.NewDocument(document_format, document)
    metadata: tuple[ProductBodyMetadata, ...] = ()
    transferred = False
    try:
        transferred = bool(caf_reader.Transfer(document))
        _raise_if_cancelled(cancel_check)
        if transferred:
            metadata = _collect_product_metadata(document, cancel_check)
    except StepReaderCancelled:
        raise
    except Exception:
        # Product names are optional; exact geometry remains authoritative.
        transferred = False
        metadata = ()
    finally:
        try:
            application.Close(document)
        except Exception:
            pass
    return metadata, transferred


def _root_shape(reader: Any, transferred: bool, source_path: Path) -> object:
    root_shape = reader.OneShape()
    if root_shape.IsNull():
        transferred_roots = reader.TransferRoots()
        root_shape = reader.OneShape()
    else:
        transferred_roots = 1 if transferred else reader.NbShapes()
    if transferred_roots <= 0 or root_shape.IsNull():
        raise StepReaderError(f"STEP file contains no transferable roots: {source_path}")
    return root_shape


def _apply_override_scale(
    root_shape: object,
    metadata: tuple[ProductBodyMetadata, ...],
    resolution: _UnitResolution,
    declared_factor_mm: float | None,
) -> tuple[object, tuple[ProductBodyMetadata, ...]]:
    if not resolution.override_applied:
        return root_shape, metadata
    reader_factor = declared_factor_mm if declared_factor_mm and declared_factor_mm > 0.0 else 1.0
    correction = _UNIT_TO_MM[resolution.source_unit] / reader_factor
    if math.isclose(correction, 1.0, rel_tol=1.0e-12, abs_tol=1.0e-12):
        return root_shape, metadata
    return _scaled_shape(root_shape, correction), tuple(
        ProductBodyMetadata(
            _scaled_shape(item.shape, correction), item.kind, item.name, item.assembly_path
        )
        for item in metadata
    )


def _collect_product_metadata(
    document: TDocStd_Document,
    cancel_check: CancelCheck | None,
) -> tuple[ProductBodyMetadata, ...]:
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    free_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free_labels)
    result: list[ProductBodyMetadata] = []
    for index in range(1, free_labels.Length() + 1):
        _visit_product_label(free_labels.Value(index), (), result, cancel_check)
    return tuple(result)


def _visit_product_label(
    label: TDF_Label,
    parent_path: tuple[str, ...],
    result: list[ProductBodyMetadata],
    cancel_check: CancelCheck | None,
) -> None:
    _raise_if_cancelled(cancel_check)
    effective_name, current_path = _label_identity(label, parent_path)
    components = TDF_LabelSequence()
    has_components = XCAFDoc_ShapeTool.GetComponents_s(label, components, False)
    if has_components and components.Length() > 0:
        for index in range(1, components.Length() + 1):
            _visit_product_label(components.Value(index), current_path, result, cancel_check)
        return
    shape = XCAFDoc_ShapeTool.GetShape_s(label)
    display_name = effective_name or (current_path[-1] if current_path else "")
    if shape.IsNull() or not display_name:
        return
    assembly_path = "/".join(current_path)
    for kind, body_shape in body_shapes(shape):
        _raise_if_cancelled(cancel_check)
        result.append(ProductBodyMetadata(body_shape, kind, display_name, assembly_path))


def _label_identity(
    label: TDF_Label,
    parent_path: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    label_name = _meaningful_xcaf_name(_xcaf_label_name(label))
    referred_name = ""
    referred = TDF_Label()
    if XCAFDoc_ShapeTool.GetReferredShape_s(label, referred):
        referred_name = _meaningful_xcaf_name(_xcaf_label_name(referred))
    effective_name = label_name or referred_name
    path = parent_path if not effective_name else (*parent_path, effective_name)
    return effective_name, path


def _xcaf_label_name(label: TDF_Label) -> str:
    iterator = TDF_AttributeIterator(label)
    name_attribute: TDataStd_Name | None = None
    while iterator.More():
        attribute = iterator.Value()
        if isinstance(attribute, TDataStd_Name):
            name_attribute = attribute
            break
        iterator.Next()
    if name_attribute is None:
        return ""
    value = name_attribute.Get()
    text = "".join(value.Value(index) for index in range(1, value.Length() + 1))
    return " ".join(text.replace("\x00", "").strip().split())


def _meaningful_xcaf_name(value: str) -> str:
    if not value or value.startswith("=>["):
        return ""
    if value.upper() in {"COMPOUND", "SOLID", "SHELL", "SHAPE"}:
        return ""
    return value


def _scaled_shape(shape: object, factor: float) -> object:
    transform = gp_Trsf()
    transform.SetScale(gp_Pnt(0.0, 0.0, 0.0), factor)
    return BRepBuilderAPI_Transform(shape, transform, True).Shape()


def _normalize_unit(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("碌", "u")
    aliases = {
        "millimeters": "millimetre",
        "millimeter": "millimetre",
        "millimetres": "millimetre",
        "centimeters": "centimetre",
        "centimeter": "centimetre",
        "centimetres": "centimetre",
        "meters": "metre",
        "meter": "metre",
        "metres": "metre",
        "inches": "inch",
        "micrometers": "micrometre",
        "micrometer": "micrometre",
        "micrometres": "micrometre",
    }
    return aliases.get(normalized, normalized)


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise StepReaderCancelled("STEP loading cancelled")
