"""Explicit Indexed layer identities, independent of geometric Z coordinates."""
from ..manufacturing.toolpath import GeneratedToolpath


def indexed_layer_comments(toolpath: GeneratedToolpath) -> list[str | None]:
    """Number actual layer IDs by first occurrence, including destination travel.

    Repeated tracks/fragments with the same ID retain their number. The source
    point's layer identity remains authoritative for non-deposition moves.
    """
    numbers: dict[str, int] = {}
    previous: int | None = None
    result: list[str | None] = []
    for point in toolpath.points:
        if not point.layer_id:
            raise ValueError("Indexed preview requires explicit layer identity")
        number = numbers.setdefault(point.layer_id, len(numbers))
        result.append(f"; Layer {number}" if number != previous else None)
        previous = number
    return result


def indexed_layer_preview_comments(toolpath: GeneratedToolpath) -> list[str]:
    """Pair dimensional metadata with optional standard parser layer comments."""
    from ..indexed_preview_metadata import indexed_preview_comments

    return [f"{layer}\n{point}" if layer is not None else point
            for layer, point in zip(indexed_layer_comments(toolpath),
                                    indexed_preview_comments(toolpath), strict=True)]
