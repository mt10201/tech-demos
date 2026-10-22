"""Small forward-compat shims for build123d features merged to ``dev`` but not yet released.

* ``filter_by_value`` mirrors ``ShapeList.filter_by_value`` from build123d PR #1524 (merged to dev
  2026-10-18, not in 0.13.0). When the installed build123d has the method, it is used directly.
* ``fillet_or_explain`` / ``faulty_fillet_edges`` report which edges make a fillet fail. build123d
  PR #1525 (dev) puts that in the fillet error itself; on 0.13 we find them by trying edges.

Once a release contains both (expected build123d 0.14): bump ``build123d>=0.14`` in requirements.txt,
replace ``filter_by_value(shapes, ...)`` with ``shapes.filter_by_value(...)`` and drop this module.
"""
from __future__ import annotations

import numbers
import re
from typing import Any, Callable, Iterable

from build123d import ShapeList

try:  # build123d keeps TOLERANCE in build123d.geometry
    from build123d.geometry import TOLERANCE
except ImportError:  # pragma: no cover
    TOLERANCE = 1e-6

NATIVE_FILTER_BY_VALUE = hasattr(ShapeList, "filter_by_value")


def _measure(measure: Any, shape) -> Any:
    if isinstance(measure, property):
        return measure.__get__(shape)
    if callable(measure):
        return measure(shape)
    raise TypeError("measure must be a property (e.g. Edge.length) or a callable of one shape")


def filter_by_value(shapes: Iterable, measure: Any, value: Any, tolerance: float = TOLERANCE,
                    reverse: bool = False) -> ShapeList:
    """Shapes whose ``measure`` equals ``value`` (numbers: within ``tolerance``), like PR #1524."""
    shapes = ShapeList(shapes)
    if NATIVE_FILTER_BY_VALUE:
        return shapes.filter_by_value(measure, value, tolerance=tolerance, reverse=reverse)
    if type(measure).__name__ == "SortBy":
        raise TypeError("filter_by_value takes a property or callable, not SortBy")

    def keep(s) -> bool:
        v = _measure(measure, s)
        if v is None:
            return False
        if isinstance(v, numbers.Real) and isinstance(value, numbers.Real):
            return abs(v - value) <= tolerance
        return v == value

    return ShapeList(s for s in shapes if keep(s) != reverse)


def _fillet_ok(solid, radius: float, edges) -> bool:
    try:
        r = solid.fillet(radius, list(edges))
        return r is not None and r.is_valid
    except Exception:
        return False


def faulty_fillet_edges(solid, radius: float, edges) -> list[int]:
    """Indices (into ``edges``) of edges to drop so the rest fillets at ``radius``.

    First every edge that fails alone, then (greedy, in order) every edge whose addition breaks
    the fillet of the edges accepted so far. Costs at most 2 x len(edges) fillet attempts.
    """
    edges = list(edges)
    bad = [i for i, e in enumerate(edges) if not _fillet_ok(solid, radius, [e])]
    if _fillet_ok(solid, radius, [e for i, e in enumerate(edges) if i not in bad]):
        return bad
    kept: list = []
    for i, e in enumerate(edges):
        if i in bad:
            continue
        if _fillet_ok(solid, radius, kept + [e]):
            kept.append(e)
        else:
            bad.append(i)
    return sorted(bad)


def fillet_or_explain(solid, radius: float, edges: list):
    """``solid.fillet(radius, edges)``, re-raising with the failing edge indices and points."""
    edges = list(edges)
    try:
        return solid.fillet(radius, edges)
    except Exception as exc:
        msg = str(exc)
        if re.search(r"on \d+ of \d+ edges", msg):
            raise  # build123d >= PR #1525 already names the edges
        bad = faulty_fillet_edges(solid, radius, edges)
        where = "; ".join(f"#{i} at ({p.X:.2f}, {p.Y:.2f}, {p.Z:.2f}) len {edges[i].length:.2f}"
                          for i in bad for p in [edges[i].center()])
        raise ValueError(f"fillet r={radius} failed; edges to drop: {where or 'none (combination only)'}"
                         ) from exc
