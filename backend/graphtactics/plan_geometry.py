"""
PlanGeometry - Generates geometric representations for visualization.

This class is responsible for creating the visual/geometric output of an interception plan:
- Isochrone polygon (boundary of where adversary could be now)
- Categorized path LineStrings (past, future, controlled, uncontrolled)
- Escape node classifications
"""

from __future__ import annotations

import itertools

from anytree import findall
from shapely import LineString, Polygon
from shapely.geometry import Point

from graphtactics.tree_node import TreeNode

from .escape_model import EscapeModel
from .position import Position
from .road_network import RoadNetwork
from .tree_node import CoverStatus
from .utils import get_balanced_polygon, merge_lines


class PlanGeometry:
    """Generates geometric data for plan visualization.

    This class computes and caches the geometric representations needed
    for visualizing an interception plan, including isochrones, paths,
    and escape node classifications.

    Attributes:
        escape_model: The underlying escape model with tree structure.
        network: The road network for coordinate lookups.
    """

    def __init__(self, escape_model: EscapeModel, network: RoadNetwork):
        """Initialize PlanGeometry.

        Args:
            escape_model: The escape model containing the tree structure and candidate nodes.
            network: The road network for geometry operations.
        """
        self._model = escape_model
        self._network = network

        # Cached computed values
        self._isochrone: Polygon | None = None
        self._linestrings: dict[str, list[LineString]] | None = None
        self._present_positions: dict[int, Position] = {}
        self._njois: list[tuple[int, Point]] | None = None
        self._escape_nodes_covered: list[tuple[int, Point]] | None = None
        self._escape_nodes_uncovered: list[tuple[int, Point]] | None = None

    # =========================================================================
    # Public API
    # =========================================================================

    def get_isochrone(self) -> Polygon:
        """Get the isochrone polygon representing where the adversary could be now.

        The isochrone is computed lazily and cached.

        Returns:
            A Polygon representing the boundary of possible adversary positions.
        """
        if self._isochrone is not None:
            return self._isochrone

        lk_position = self._model.lk_position
        assert lk_position is not None

        point_list: list[Point] = []

        for njoi in self._model.get_njois():
            path: tuple[TreeNode, ...] = njoi.path

            # This will always work because the njoi is at least the second node in the path
            # the first one being the root (0)
            edge_travel_time = path[-1].time_reached - path[-2].time_reached
            assert edge_travel_time > 0

            # ec at time 0 is the fraction of edge_travel_time that corresponds to |time_to_prev_osmid|
            ec: float = -path[-2].time_reached / edge_travel_time

            # in this case we don't have a proper edge between prev_osmid and curr_osmid
            # the present_position is somewhere on the same edge as the lkp_position
            if path[-2].osmid == 0:
                # if the time elapsed is less than 10 seconds, use 10 seconds to have a visible isochrone
                min10 = max(10, self._model.time_elapsed)
                pos = self._network.update_position_after_duration(
                    lk_position, min10, (path[-1].osmid == lk_position.v)
                )
            else:
                pos = Position(u=path[-2].osmid, v=path[-1].osmid, ec=ec)

            self._present_positions[path[-1].osmid] = pos
            point_list.append(self._network.pos_to_point(pos))

        for escape_node in findall(
            self._model.tree_dict[0],
            lambda node: node.is_leaf and node.time_reached <= 0,  # type: ignore[attr-defined]
        ):
            # the escape node is behind the adversary
            p0: Point = self._network.pos_to_point(lk_position)
            p1: Point = self._network.node_to_point(escape_node.osmid)
            r: float = self._model.time_elapsed / (
                self._model.times_to_nodes[escape_node.osmid] + self._model.time_elapsed
            )
            assert r >= 0
            # don't add this to the present positions as it won't intercept any paths
            pos = self._network.create_position_from_point(Point(p0.x + r * (p1.x - p0.x), p0.y + r * (p1.y - p0.y)))
            point_list.append(self._network.pos_to_point(pos))

        self._isochrone = get_balanced_polygon(point_list)
        return self._isochrone

    def get_linestrings(self) -> dict[str, list[LineString]]:
        """Get categorized LineStrings for path visualization.

        Returns a dictionary with keys:
        - "past": Paths the adversary has already traveled
        - "uncontrolled": Future paths with no interception
        - "before_control": Future paths leading to control points
        - "after_control": Future paths after control points (covered)

        Returns:
            Dictionary mapping category names to lists of LineStrings.
        """
        if self._linestrings is not None:
            return self._linestrings

        # Ensure present_positions is populated (computed in get_isochrone)
        self.get_isochrone()

        segment_per_category: dict[str, list[list[TreeNode]]] = self._model.tree_dict[0].categorize_segments()

        # Convert to linestrings and split by present positions (isochrone)
        pst_uncontrolled_ls, fut_uncontrolled_ls = self._split_past_present(segment_per_category["uncovered"])
        pst_before_control_ls, fut_before_control_ls = self._split_past_present(segment_per_category["before_control"])

        self._linestrings = {
            "past": pst_uncontrolled_ls + pst_before_control_ls,
            "uncontrolled": fut_uncontrolled_ls,
            "before_control": fut_before_control_ls,
            "after_control": [self._to_linestring(seg) for seg in segment_per_category["after_control"]],
        }
        return self._linestrings

    def get_escape_nodes(self) -> tuple[list[tuple[int, Point]], list[tuple[int, Point]]]:
        """Get lists of covered and uncovered escape node geometries.

        Returns:
            Tuple of (covered_escape_node_points, uncovered_escape_node_points).
        """
        if self._escape_nodes_covered is None:
            self._escape_nodes_covered = [
                (escape_node.osmid, self._network.node_to_point(escape_node.osmid))
                for escape_node in findall(
                    self._model.tree_dict[0],
                    lambda node: node.is_leaf and node.cover == CoverStatus.COVERED,  # type: ignore[attr-defined]
                )
            ]
        if self._escape_nodes_uncovered is None:
            self._escape_nodes_uncovered = [
                (escape_node.osmid, self._network.node_to_point(escape_node.osmid))
                for escape_node in findall(
                    self._model.tree_dict[0],
                    lambda node: node.is_leaf and node.cover == CoverStatus.UNCOVERED,  # type: ignore[attr-defined]
                )
            ]
        return self._escape_nodes_covered, self._escape_nodes_uncovered

    @property
    def escape_nodes_covered(self) -> list[tuple[int, Point]]:
        """List of Point geometries for escape nodes covered by the plan."""
        covered, _ = self.get_escape_nodes()
        return covered

    @property
    def escape_nodes_uncovered(self) -> list[tuple[int, Point]]:
        """List of Point geometries for escape nodes not covered by the plan."""
        _, uncovered = self.get_escape_nodes()
        return uncovered

    @property
    def njois(self) -> list[tuple[int, Point]]:
        """List of Point geometries for nodes just outside the isochrone (NJOIs)."""
        if self._njois is None:
            self._njois = [(njoi.osmid, self._network.node_to_point(njoi.osmid)) for njoi in self._model.get_njois()]
        return self._njois

    # =========================================================================
    # Private helper methods
    # =========================================================================

    def _split_past_present(self, segments: list[list[TreeNode]]) -> tuple[list[LineString], list[LineString]]:
        """Split path segments into past and future portions at the isochrone.

        Args:
            segments: List of path segments (each segment is a list of TreeNodes).

        Returns:
            Tuple of (past_linestrings, future_linestrings).
        """
        past_linestrings: list[LineString] = []
        future_linestrings: list[LineString] = []

        for seg in segments:
            idx_njoi: tuple[int, TreeNode] | None = next(
                ((i, node) for i, node in enumerate(seg) if node.is_njoi), None
            )
            if idx_njoi:
                idx, njoi = idx_njoi
                pos: Position = self._present_positions[njoi.osmid]

                past_path: list[TreeNode] = list[TreeNode](seg[: idx + 1])
                past_linestring: LineString = self._to_linestring_pos_after(past_path, pos)
                if past_linestring:
                    past_linestrings.append(past_linestring)

                future_path: list[TreeNode] = list[TreeNode](seg[idx:])
                future_linestring: LineString = self._to_linestring_pos_before(future_path, pos)
                if future_linestring:
                    future_linestrings.append(future_linestring)
            else:
                if seg[0].time_reached > 0:
                    future_linestrings.append(self._to_linestring(seg))
                else:
                    past_linestrings.append(self._to_linestring(seg))

        return (past_linestrings, future_linestrings)

    def _to_linestring(
        self, path: list[TreeNode], pos_before: Position | None = None, pos_after: Position | None = None
    ) -> LineString:
        """Convert a path of TreeNodes to a LineString.

        Args:
            path: List of TreeNodes representing the path.
            pos_before: Optional position to prepend to the path.
            pos_after: Optional position to append to the path.

        Returns:
            A LineString representing the path.
        """
        lk_position = self._model.lk_position
        assert lk_position is not None

        lines: list[LineString] = []
        if len(path) > 1:
            for n1, n2 in itertools.pairwise(path):
                # we need a special case for this, as (0,u) and (0,v) are not real edges in the graph
                if n1.osmid == 0:
                    assert n2.osmid == lk_position.u or n2.osmid == lk_position.v
                    lines.append(self._network.get_partial_linestring(lk_position, u_or_v=n2.osmid))
                else:
                    lines.append(self._network.get_edge_as_linestring(n1.osmid, n2.osmid))
        elif len(path) == 1:
            p: Point = self._network.node_to_point(path[0].osmid)
            lines.append(LineString([p, p]))
        else:
            raise ValueError("Path must contain at least one node")

        if pos_before:
            lines.insert(0, self._network.get_partial_linestring(pos_before, u_or_v=path[0].osmid))
        if pos_after:
            lines.append(self._network.get_partial_linestring(pos_after, u_or_v=path[-1].osmid, reverse=True))

        line = merge_lines(lines)
        if not isinstance(line, LineString):
            raise ValueError(
                f"Conversion of ({path},{pos_before},{pos_after}) did not produce a LineString as expected."
            )
        return line

    def _to_linestring_pos_after(self, path: list[TreeNode], position: Position) -> LineString:
        """Convert path to LineString, ending at the given position."""
        assert path is not None
        assert len(path) > 0
        assert position is not None

        lk_position = self._model.lk_position
        assert lk_position is not None
        assert position.u == path[-1].osmid or position.v == path[-1].osmid

        if len(path) == 1:
            return self._network.get_partial_linestring(position, u_or_v=path[-1].osmid, reverse=True)

        lines: list[LineString] = []

        for n1, n2 in itertools.pairwise(path):
            # we need a special case for this, as (0,u) and (0,v) are not real edges in the graph
            if n1.osmid == 0:
                lines.append(self._network.get_partial_linestring(lk_position, u_or_v=n2.osmid))
            else:
                lines.append(self._network.get_edge_as_linestring(n1.osmid, n2.osmid))
        lines.append(self._network.get_partial_linestring(position, u_or_v=path[-1].osmid, reverse=True))
        return merge_lines(lines)

    def _to_linestring_pos_before(self, path: list[TreeNode], position: Position) -> LineString:
        """Convert path to LineString, starting from the given position."""
        assert path is not None
        assert len(path) > 0
        assert position is not None
        assert position.v == path[0].osmid or position.u == path[0].osmid

        lk_position = self._model.lk_position
        assert lk_position is not None

        lines: list[LineString] = []
        lines.append(self._network.get_partial_linestring(position, u_or_v=path[0].osmid))

        if len(path) > 1:
            for n1, n2 in itertools.pairwise(path):
                # we need a special case for this, as (0,u) and (0,v) are not real edges in the graph
                if n1.osmid == 0:
                    lines.append(self._network.get_partial_linestring(lk_position, u_or_v=n2.osmid))
                else:
                    lines.append(self._network.get_edge_as_linestring(n1.osmid, n2.osmid))
        return merge_lines(lines)
