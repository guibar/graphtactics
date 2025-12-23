"""
Position represents a geographic location on the road network.
Can be initialized either from coordinates (point) or from graph position (u/v/edge_cursor).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from shapely.geometry import Point

if TYPE_CHECKING:
    from .road_network import EdgeRef


@dataclass
class Position:
    """
    A position on the road network graph represented by both the lat/long coordinates and
    the edge reference (u/v/edge_cursor).

    Can be initialized in three ways:
    1. From coordinates: Position.from_point(Point(2.1, 49.4)) - snaps to nearest node or edge depending on on_node
    2. From EdgeRef: Position.from_edge(EdgeRef(u=12, v=45, edge_cursor=0.5)) - point coordinates are inferred
    3. From node: Position.from_node(123) - finds a valid v value, set edge_cursor to 0.0 and infers point coordinates

    Attributes:
        init_point: Shapely Point object representing the position provided at initialization.
        If initialized from graph position, this is the same as point.
        point: Shapely Point object representing the snapped position on the graph.
        u: Source node ID of the edge (node_from)
        v: Target node ID of the edge (node_to)
        ec: Position along edge (0.0 = at u, 1.0 = at v)
    """

    init_point: Point
    point: Point
    u: int
    v: int
    ec: float

    def __post_init__(self):
        if self.ec < 0 or self.ec > 1:
            raise ValueError("Edge cursor must be between 0 and 1")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Position):
            return False
        return (
            self.u == other.u
            and self.v == other.v
            and self.floats_equal(self.ec, other.ec)
            and self.floats_equal(self.point.x, other.point.x)
            and self.floats_equal(self.point.y, other.point.y)
        )

    def to_edge_ref(self) -> "EdgeRef":
        from .road_network import EdgeRef

        return EdgeRef(self.u, self.v, self.ec)

    @staticmethod
    def floats_equal(a: float, b: float, epsilon: float = 1e-9) -> bool:
        return abs(a - b) < epsilon
