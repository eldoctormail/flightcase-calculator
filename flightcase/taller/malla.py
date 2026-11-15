"""Piezas de la malla 3D que dibuja la vista del Taller (y que usan el instructivo y el STEP)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Point3D:
    """3D point coordinate in millimeters."""
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Segment3D:
    """3D line segment with styling tags."""
    p1: Point3D
    p2: Point3D
    style: str = "solid"  # "solid", "dashed", "axis", "profile", "wall"
    color_group: str = "case"  # "case", "lid", "profile", "wall", "dimension"
    label: str = ""
    wall_index: Optional[int] = None


class ComponentLayer(IntEnum):
    """
    Topological structural hierarchy layer for flightcase 3D rendering.
    Ordered from bottom-most interior upward to exterior and lid.
    """
    BASE_FLOOR = 10
    INTERNAL_DIVIDERS = 20
    OUTER_BASE_WALLS = 30
    BASE_ALU = 40
    LID_WALLS = 50
    LID_ROOF = 60


@dataclass(frozen=True)
class PolygonFace3D:
    """Planar 3D polygonal face for solid volumetric panel rendering without hidden lines."""
    vertices: Tuple[Point3D, ...]
    normal: Tuple[float, float, float]
    color_group: str = "base"  # "base", "lid", "wall", "profile", "endgrain"
    label: str = ""
    is_endgrain: bool = False
    layer_order: int = ComponentLayer.BASE_FLOOR
    wall_index: Optional[int] = None

    @property
    def centroid(self) -> Point3D:
        """Computes geometric centroid of the face."""
        n = len(self.vertices)
        if n == 0:
            return Point3D(0, 0, 0)
        return Point3D(
            sum(p.x for p in self.vertices) / n,
            sum(p.y for p in self.vertices) / n,
            sum(p.z for p in self.vertices) / n,
        )


@dataclass(frozen=True)
class DimensionCallout3D:
    """Dimension annotation in 3D space with text label and offset direction."""
    start: Point3D
    end: Point3D
    label: str
    value_mm: float
    offset_vector: Tuple[float, float, float]
    dimension_type: str = "linear"  # "length", "width", "height", "lid_height", "wall_pos"


@dataclass
class WireframeMesh3D:
    """Caras, segmentos y cotas de la vista 3D."""
    faces: List[PolygonFace3D] = field(default_factory=list)
    segments: List[Segment3D] = field(default_factory=list)
    dimensions: List[DimensionCallout3D] = field(default_factory=list)
    bounding_box: Tuple[Point3D, Point3D] = (Point3D(0, 0, 0), Point3D(0, 0, 0))
