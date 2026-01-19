"""
Road Network management and spatial utility module.

This module provides the `RoadNetwork` class, which serves as a high-level
wrapper around an OSM-derived NetworkX graph. It handles geographic-to-graph
conversions, shortest-path routing (Dijkstra), and spatial operations like
snapping points to edges and generating random distributions.

Key Features:
- Lazy coordinate computation for network positions.
- Bidirectional Dijkstra routing from arbitrary points on edges.
- Integration with OSMNX for nearest-node/edge lookups.
- Highway ranking for interception scoring logic.
"""

from __future__ import annotations

import itertools
import logging
import random
from enum import Enum
from typing import cast

from networkx import MultiDiGraph, single_source_dijkstra, subgraph_view
from osmnx import settings
from osmnx.distance import (
    nearest_edges,  # pyright: ignore[reportUnknownVariableType]
    nearest_nodes,  # pyright: ignore[reportUnknownVariableType]
)
from shapely import ops
from shapely.geometry import LineString, Point, Polygon

from .position import Position
from .utils import merge_lines

# OSMNX settings for internal logging Control
settings.log_console = True
settings.log_level = logging.WARNING
logger = logging.getLogger(__name__)


class RoadNetwork:
    """A wrapper for the road network graph providing tactical and spatial utilities.

    This class manages a NetworkX `MultiDiGraph` where nodes represent junctions
    (with 'x', 'y' and 'inner' attributes) and edges represent road segments
    (with 'travel_time', 'highway', and 'geometry' attributes).

    Attributes:
        name: A unique identifier for the network (e.g., '60' or 'd2').
        graph: The NetworkX MultiDiGraph representing the road topology.
        boundary: A Shapely Polygon defining the operational area.
        boundary_buff: A larger safety buffer surrounding the operational boundary.
        escape_nodes: A set of OSM nodes IDs that lie outside 'boundary' but which are at
            the end of an edge whose other end is inside the 'boundary'.
        central_position: A `Position` object representing the centroid of
            the operational boundary, used for setting an arbitrary initial position for the adversary.
    """

    def __init__(
        self,
        name: str,
        graph: MultiDiGraph[int],
        escape_nodes: set[int],
        boundary: Polygon,
        boundary_buff: Polygon,
    ):
        """Initialize RoadNetwork with pre-loaded data.

        Use RoadNetworkFactory.create(name) to construct instances with automatic
        data acquisition from cache, GitHub releases, or OSM extraction.

        Args:
            name: Network identifier
            graph: NetworkX MultiDiGraph representing the road network
            escape_nodes: Set of nodes outside the boundary (escape destinations)
            boundary: Polygon of the operational zone
            boundary_buff: Buffered polygon around the boundary
        """
        self.name: str = name
        self.graph: MultiDiGraph[int] = graph
        self.escape_nodes: set[int] = escape_nodes
        self.boundary: Polygon = boundary
        self.boundary_buff: Polygon = boundary_buff
        self.central_position: Position = self.create_position_from_point(self.boundary.centroid)

    def has_in_boundary(self, position: Position) -> bool:
        """Check if a position's edge is within the inner operational boundary.

        Args:
            position: The road network position to check.

        Returns:
            True if either the source or destination node of the position's
            edge is marked as 'inner'.
        """
        return self.graph.nodes[position.u]["inner"] or self.graph.nodes[position.v]["inner"]

    # ============================================================
    # Position factory methods
    # ============================================================

    def create_position_from_point(self, point: Point, on_node: bool = False) -> Position:
        """Find a coordinate on the road network closest to the given point.

        If `on_node` is True, it snaps to the single closest node.
        If `on_node` is False (default), it snaps to the closest position on an edge.

        Args:
            point: The Shapely Point (lng, lat) to project.
            on_node: If True, snap exactly to a node. Otherwise, snap to an edge.

        Returns:
            A new `Position` object with snapped graph coordinates.

        Raises:
            ValueError: If the nearest node has no outgoing edges.
        """
        if on_node:
            # Snap to single closest node
            u = nearest_nodes(
                self.graph,
                [point.x],
                [point.y],
                return_dist=False,
            ).tolist()[0]

            try:
                # We pick an arbitrary successor to define an edge, as Position
                # requires an (u,v) pair even for node-snapped locations.
                return Position(u=u, v=next(self.graph.successors(u)), ec=0.0, init_point=point)
            except StopIteration as err:
                raise ValueError(f"Node {u} has no outgoing edges.") from err
        else:
            # Snap to the closest directed edge
            edges = nearest_edges(
                self.graph,
                [point.x],
                [point.y],
                return_dist=False,
            )
            u, v, _ = edges[0]
            edge_geom = self.get_edge_as_linestring(u, v)

            # Project the point onto the edge to find the closest position on the edge
            ec = edge_geom.project(point, normalized=True)
            return Position(u, v, ec, init_point=point)

    def get_random_positions(self, qty: int, on_node: bool = False, seed: int | None = None) -> list[Position]:
        """
        Generate random positions directly on the road network graph.
        When on_node=True, positions are placed at randomly selected nodes with edge_cursor=0.0.
        When on_node=False, positions are placed at random locations along randomly selected edges.

        Args:
            qty: Number of random positions to generate
            on_node: If True, generate positions at nodes; if False, generate positions
                    along edges (default: False)
            seed: Random seed for reproducibility (default: None)

        Returns:
            List of Position objects
        """
        if seed is not None:
            random.seed(seed)
        # Get all edges as a list and randomly sample from them
        all_edges: list[tuple[int, int]] = list(self.graph.edges())
        random_edges: list[tuple[int, int]] = random.sample(all_edges, qty)
        if on_node:
            edge_cursors: list[float] = [0.0] * qty
        else:
            edge_cursors = [random.random() for _ in range(qty)]
        return [
            Position(u=u, v=v, ec=edge_cursor) for (u, v), edge_cursor in zip(random_edges, edge_cursors, strict=True)
        ]

    # ============================================================
    # Conversion to point methods
    # ============================================================

    def node_to_point(self, node_id: int) -> Point:
        """Find the geographic coordinates of a graph node.

        Args:
            node_id: The OSM ID of the junction.

        Returns:
            A Shapely Point (lng, lat).
        """
        return Point(self.graph.nodes[node_id]["x"], self.graph.nodes[node_id]["y"])

    def pos_to_point(self, position: Position) -> Point:
        """Calculate the geographic Point for a given Position.

        This method performs linear interpolation along the edge using the
        `edge_cursor` (percentage). The result is cached within the `position`
        object to avoid redundant calculations.

        Args:
            position: The Position object containing edge (u, v) and cursor.

        Returns:
            A Shapely Point interpolated along the edge's geometry.

        Raises:
            ValueError: If the edge (u, v) does not exist in the graph.
        """
        # Return cached value if already computed
        if position._point is not None:
            return position._point

        if not self.graph.has_edge(position.u, position.v):
            raise ValueError(f"No edge exists from {position.u} to {position.v}")

        # Interpolate the point along the LineString geometry of the edge
        line = self.get_edge_as_linestring(position.u, position.v)
        point = line.interpolate(position.ec, normalized=True)

        # Cache in the frozen dataclass using object.__setattr__
        object.__setattr__(position, "_point", point)
        return point

    # ============================================================
    # Routing Method
    # ============================================================

    def get_times_and_paths_from_position(
        self, point: Point, time_elapsed: float, ens_as_sink: bool = False
    ) -> tuple[Position, dict[int, float], dict[int, list[int]]]:
        """Compute shortest travel times and paths from any point in the zone to all osm nodes.

        This method is the core routing engine for both vehicles and the adversary.
        Since the starting point is usually on an edge (not at a junction), we must
        calculate the time from both endpoints of the edge (u or v) and keep the best
        result for each node. We first need to place the point somewhere on the network.
        The resulting Position object is returned with the computed times and paths.

        Logic:
        1. If the edge is one-way (u -> v), we only compute paths via node 'v'.
        2. If bidirectional, we compute paths via both 'u' and 'v' and return
           the best route for each node.
        3. Because we don't want to deal with routes that exit the zone and then re-enter it,
           we use subgraphs to eliminate any further path that goes through an escape node.
           This is only used if `ens_as_sink` is True

        Args:
            point: The starting geographic Point.
            time_elapsed: Seconds already passed (subtracted from final results).
            ens_as_sink: If True, treat escape nodes as dead-ends (no outgoing edges).

        Returns:
            A tuple containing:
            - The created Position object (snapped point).
            - A dict mapping node OSMID to travel time (seconds, adjusted by time_elapsed).
            - A dict mapping node OSMID to the list of nodes forming the path.
        """
        # Determine the graph to use based on the 'sink' requirement
        if ens_as_sink:
            # Create a view that 'cuts off' any path attempting to leave an escape node.
            def filter_edge_out_of_escape_nodes(u: int, v: int, key: int) -> bool:
                return u not in self.escape_nodes

            _graph: MultiDiGraph = cast(  # type: ignore
                MultiDiGraph,
                subgraph_view(self.graph, filter_edge=filter_edge_out_of_escape_nodes),
            )
        else:
            _graph = self.graph

        # Snap the input point to the closest edge in the selected graph. We had to wait until this
        # point to do the snapping to avoid snapping the adversary to an edge that would be
        # eliminated by the subgraph view.
        position: Position = self.create_position_from_point(point, on_node=False)

        if _graph.get_edge_data(position.u, position.v, 0) is None:  # type: ignore
            raise ValueError(f"Edge {position.u} -> {position.v} not found in graph view")

        # Calculate time needed to reach the immediate endpoint 'v'
        time_to_v = self.get_time_from_position_to_v(position)

        # CASE 1: ONE-WAY EDGE
        if _graph.get_edge_data(position.u, position.v, 0)["oneway"] == "yes":  # type: ignore
            times, paths = cast(
                tuple[dict[int, float], dict[int, list[int]]],
                single_source_dijkstra(_graph, position.v, weight="travel_time", target=None),  # type: ignore
            )
            # Offset all times by the time it took to reach node 'v' from the start point
            times = {node: time + time_to_v - time_elapsed for node, time in times.items()}
            return position, times, paths

        # CASE 2: BIDIRECTIONAL EDGE
        else:
            # We must consider two starting directions: towards 'u' and towards 'v'
            time_to_u = self.get_time_from_position_to_u(position)

            # --- Routing via 'u' ---
            # When leaving towards u, we are not interested in routes that would go via v
            # as they would necessarily be worse than the route via v.
            # This only makes sense from an efficiency perspective.
            avoid_v_graph: MultiDiGraph = cast(  # type: ignore
                MultiDiGraph,
                subgraph_view(_graph, filter_edge=lambda u, v, k: (u, v) != (position.u, position.v)),  # type: ignore
            )

            times_from_u, paths_from_u = cast(
                tuple[dict[int, float], dict[int, list[int]]],
                single_source_dijkstra(avoid_v_graph, position.u, weight="travel_time", target=None),  # type: ignore
            )

            # --- Routing via 'v' ---
            # Similarly, when leaving towards v, exclude the immediate reverse edge (v -> u).
            avoid_u_graph: MultiDiGraph = cast(  # type: ignore
                MultiDiGraph,
                subgraph_view(_graph, filter_edge=lambda u, v, k: (u, v) != (position.v, position.u)),  # type: ignore
            )
            times_from_v, paths_from_v = cast(
                tuple[dict[int, float], dict[int, list[int]]],
                single_source_dijkstra(avoid_u_graph, position.v, weight="travel_time", target=None),  # type: ignore
            )

            # Merge the results from the two search directions
            all_reachable = set(times_from_u.keys()) | set(times_from_v.keys())
            times: dict[int, float] = {}
            paths: dict[int, list[int]] = {}

            for node in all_reachable:
                # Compare the travel time via node 'u' vs the travel time via node 'v'
                time_via_u = times_from_u.get(node, float("inf")) + time_to_u
                time_via_v = times_from_v.get(node, float("inf")) + time_to_v

                # Store the most efficient path for this node
                times[node] = min(time_via_u, time_via_v) - time_elapsed
                paths[node] = paths_from_u[node] if time_via_u < time_via_v else paths_from_v[node]

            return position, times, paths

    # ============================================================
    # Edge data Methods
    # ============================================================

    @staticmethod
    def edge_quantifier(edge_dict: dict[str, list[str] | str]) -> int:
        """
        Convert the value of the highway tag from an edge to an integer ranking.
        The value can be a string or list of strings.
        Many OSM highway tags include a suffix after an underscore (e.g., 'tertiary_link', 'motorway_link').
        The base type (before the underscore) is used for ranking, so 'tertiary_link' is treated as 'tertiary'.
        If the value is a list, returns the highest-ranked base type.
        If the value is a string, returns the base type (before any underscore).

        Example:
            edge_quantifier('tertiary_link') -> 2  (same as 'tertiary')
            edge_quantifier(['secondary_link', 'tertiary'])  -> 3 (secondary > tertiary)
            cf HighwayRank for the ranking dictionary.
        Args:
            edge_dict (Dict[str, str]): Dictionary of edge attributes, must include 'highway'.

        Returns:
            int: Integer ranking for the highway type, or -1 if not recognized.
        """
        hw_value: list[str] | str = edge_dict["highway"]

        if isinstance(hw_value, list):
            base_type = max(
                [elem.split("_")[0] for elem in hw_value],
                key=lambda tag: getattr(HighwayRank, tag.upper(), HighwayRank.UNCLASSIFIED).value,
            )
        else:
            base_type = hw_value.split("_")[0]
        return getattr(HighwayRank, base_type.upper(), HighwayRank.UNCLASSIFIED).value

    def get_edge_hw_as_int(self, u: int, v: int) -> int:
        """Get the numeric rank of an edge based on its OSM highway tag.

        Args:
            u: Source node ID.
            v: Destination node ID.

        Returns:
            The integer rank (0-6) from `HighwayRank`.
        """
        hw_value: list[str] | str = self.graph.get_edge_data(u, v, 0)["highway"]
        if isinstance(hw_value, list):
            base_type = max(
                [elem.split("_")[0] for elem in hw_value],
                key=lambda tag: getattr(HighwayRank, tag.upper(), HighwayRank.UNCLASSIFIED).value,
            )
        else:
            base_type = hw_value.split("_")[0]
        return getattr(HighwayRank, base_type.upper(), HighwayRank.UNCLASSIFIED).value

    def get_edge_travel_time(self, u: int, v: int) -> float:
        """Get the travel time for an edge in seconds.

        Args:
            u: Source node ID.
            v: Destination node ID.

        Returns:
            The 'travel_time' attribute from the edge data.
        """
        return self.graph.get_edge_data(u, v, 0)["travel_time"]

    # ============================================================
    # Edge geometry Methods
    # ============================================================

    def get_edge_as_linestring(self, u: int, v: int) -> LineString:
        """Retrieve the geometry LineString for a specific graph edge.

        If the edge is missing geometry (common for straight-line edges in some
        OSM extracts), a simple LineString between the two nodes is created
        and cached.

        Args:
            u: Source node ID.
            v: Destination node ID.

        Returns:
            Shapely LineString representing the road segment.
        """
        edge_data = self.graph.get_edge_data(u, v, 0)

        if "geometry" not in edge_data:
            linestring = LineString(
                [
                    Point(self.graph.nodes[u]["x"], self.graph.nodes[u]["y"]),
                    Point(self.graph.nodes[v]["x"], self.graph.nodes[v]["y"]),
                ]
            )
            logger.debug(f"Geometry synthesized for edge {u, v}")
            edge_data["geometry"] = linestring
        else:
            linestring = cast(LineString, edge_data["geometry"])
        return linestring

    def get_partial_linestring(self, position: Position, u_or_v: int, reverse: bool = False) -> LineString:
        """Find the linstring corresponding to the portion of an edge between position and either u or v.

        Args:
            position: The starting graph position (u, v, ec).
            u_or_v: The target endpoint node (must be position.u or position.v).
            reverse: If True, the resulting LineString will be oriented from
                the node towards the position. If False (default), from
                position towards the node.

        Returns:
            A clipped Shapely LineString.

        Raises:
            ValueError: If `u_or_v` is not one of the edge's endpoints.
        """
        if u_or_v == position.v:
            if position.ec == 1.0:
                v_point = self.node_to_point(position.v)
                return LineString([v_point, v_point])
            # v is at the end of the edge (1.0)
            start, end = (1.0, position.ec) if reverse else (position.ec, 1.0)
        elif u_or_v == position.u:
            if position.ec == 0.0:
                u_point = self.node_to_point(position.u)
                return LineString([u_point, u_point])
            # u is at the start of the edge (0.0)
            start, end = (0.0, position.ec) if reverse else (position.ec, 0.0)
        else:
            raise ValueError("u_or_v must be either position.u or position.v")

        return cast(
            LineString,
            ops.substring(self.get_edge_as_linestring(position.u, position.v), start, end, normalized=True),
        )

    # ======================================================================
    # Path geometry Methods (EscapeModel has its own version of this method)
    # ======================================================================

    def to_linestring(self, path: list[int], pos_before: Position) -> LineString:
        """Combine multiple graph segments into a single continuous LineString.

        This is used for visualizing vehicle trajectories. The path is prefixed with the segment
        from the current vehicle position to the first node in the path.

        Args:
            path: Sequential list of node IDs.
            pos_before: The position of the vehicle somewhere on an edge leading to the first node in path

        Returns:
            A merged Shapely LineString.

        Raises:
            ValueError: If `pos_before` is not located on an edge connected to the first node in the path.
        """
        line_pieces: list[LineString] = []

        # Add fractional segment if starting from a mid-edge position
        if pos_before:
            if pos_before.u == path[0] or pos_before.v == path[0]:
                line_pieces.append(self.get_partial_linestring(pos_before, u_or_v=path[0]))
            else:
                raise ValueError(f"Position {pos_before} incompatible with path start {path[0]}")

        # Stitch together all edges in the path
        line_pieces.extend([self.get_edge_as_linestring(u, v) for u, v in itertools.pairwise(path)])
        return merge_lines(line_pieces)

    # ============================================================
    # Time Methods
    # ============================================================

    def get_time_from_position_to_u(self, position: Position) -> float:
        """Calculate the travel time from a along-the-edge position back to the 'u' node.

        Args:
            position: Current graph position.

        Returns:
            Seconds to reach node 'u'.
        """
        edge_travel_time = self.get_edge_travel_time(position.u, position.v)
        return edge_travel_time * position.ec

    def get_time_from_position_to_v(self, position: Position) -> float:
        """Calculate the travel time from a along-the-edge position forward to the 'v' node.

        Args:
            position: Current graph position.

        Returns:
            Seconds to reach node 'v'.
        """
        edge_travel_time = self.get_edge_travel_time(position.u, position.v)
        return edge_travel_time * (1 - position.ec)

    def update_position_after_duration(self, position: Position, duration: float, towards_v: bool) -> Position:
        """Move a position along its current edge for a specific duration.

        Note: This does not support crossing junctions. It will raise an error
        if the duration would push the position beyond the current edge.

        Args:
            position: Starting graph position.
            duration: Time in seconds of movement.
            towards_v: If True, moves towards node 'v' (increasing cursor).
                If False, moves towards node 'u' (decreasing cursor).

        Returns:
            A new Position object with the updated edge cursor.

        Raises:
            ValueError: If the movement would overshoot the edge boundaries [0, 1].
        """
        if towards_v:
            new_ec = position.ec + duration / self.get_edge_travel_time(position.u, position.v)
        else:
            new_ec = position.ec - duration / self.get_edge_travel_time(position.u, position.v)

        if new_ec > 1 or new_ec < 0:
            raise ValueError(f"Movement overshoot: Duration {duration}s pushes position {position} beyond its edge.")
        return Position(u=position.u, v=position.v, ec=new_ec)


class HighwayRank(Enum):
    """Categorization of OSM highway tags for tactical scoring.

    Higher values represent higher-speed, more significant arterial roads.
    """

    UNCLASSIFIED = 0
    RESIDENTIAL = 1
    TERTIARY = 2
    SECONDARY = 3
    PRIMARY = 4
    TRUNK = 5
    MOTORWAY = 6
