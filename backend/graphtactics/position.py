"""
Position represents a point in space in terms of the road network graph.
The corresponding geometric coordinates are lazily computed via network.to_point(position).
"""

from dataclasses import dataclass, field

from shapely.geometry import Point


@dataclass(frozen=True)
class Position:
    """
    A position on the road network graph.

    The corresponding geometric coordinates are lazily computed via network.to_point(position).

    Attributes:
        u: Source node ID of the edge
        v: Target node ID of the edge
        ec: Position along edge (0.0 = at u, 1.0 = at v)
        init_point: Original point provided at creation (if created from coordinates)
        _point: Cached snapped point (computed lazily by RoadNetwork.to_point())
    """

    u: int
    v: int
    ec: float
    init_point: Point | None = field(default=None, compare=False)
    _point: Point | None = field(default=None, compare=False, repr=False)

    def __str__(self):
        return f"Position(u={self.u}, v={self.v}, ec={self.ec})"

    def __post_init__(self):
        if self.ec < 0 or self.ec > 1:
            raise ValueError("Edge cursor must be between 0 and 1")

    @staticmethod
    def floats_equal(a: float, b: float, epsilon: float = 1e-9) -> bool:
        return abs(a - b) < epsilon
