import logging
from collections import namedtuple
from typing import cast

from geopandas import GeoDataFrame
from networkx import MultiDiGraph, single_source_dijkstra
from numpy.random import default_rng
from osmnx import settings, shortest_path
from osmnx.distance import nearest_edges, nearest_nodes
from pandas import DataFrame, Index
from shapely import ops
from shapely.geometry import LineString, Point, Polygon

from .position import Position
from .utils import edge_quantifier, highway_value_to_int

settings.log_console = True
settings.log_level = logging.INFO
logger = logging.getLogger(__name__)


EdgeRef = namedtuple("EdgeRef", ["u", "v", "ec"])


class RoadNetwork:
    """
    A class that wraps around the osmnx graph objects and allows me to manipulate it the graph the way I want
    This class is a singleton because we always want to have a unique underlying graph

    Attributes
    ----------
    name : str
        the 2 digits of a departement or 2 digits + c
    graph : MultiDiGraph
        the osmnx object of this type that is wrapped
    nodes_df : GeoDataFrame
        the nodes of the graph as a gdf
    edges_df : GeoDataFrame
        the edges of the graph as a gdf
    self.boundary: Polygon
        the polygon representing the geographic boundary of the
        zone in which we operate. if the opponent leaves this zone
        it is game over for us.
    self.boundary_buff: Polygon
        a buffer around the boundary to make sure that there are no border
        effects due to the graph ending abruptly.
    out_edges_df: GeoDataFrame
        the subset of edges_df which go from inside the boundary
        to outside
    self.out_intersections_df: GeoDataFrame
        the points (or multipoints) of intersection between out_edges_df
        and the boundary.

    Methods
    -------
    node_to_point(self, node_id: int)
        converts an osmid into a geographic point
    """

    def __init__(
        self,
        name: str,
        graph: MultiDiGraph,
        nodes_df: GeoDataFrame,
        edges_df: GeoDataFrame,
        out_edges_df: GeoDataFrame,
        out_intersections_df: GeoDataFrame,
        boundary: Polygon,
        boundary_buff: Polygon,
    ):
        """Initialize RoadNetwork with pre-loaded data.

        Use RoadNetworkFactory.create(name) to construct instances with automatic
        data acquisition from cache, GitHub releases, or OSM extraction.

        Args:
            name: Network identifier
            graph: NetworkX MultiDiGraph representing the road network
            nodes_df: GeoDataFrame of network nodes
            edges_df: GeoDataFrame of network edges
            out_edges_df: GeoDataFrame of edges crossing the boundary
            out_intersections_df: GeoDataFrame of boundary intersection points
            boundary: Polygon of the operational zone
            boundary_buff: Buffered polygon around the boundary
        """
        self.name: str = name
        self.graph: MultiDiGraph = graph
        self.nodes_df: GeoDataFrame = nodes_df
        self.edges_df: GeoDataFrame = edges_df
        self.out_edges_df: GeoDataFrame = out_edges_df
        self.out_intersections_df: GeoDataFrame = out_intersections_df
        self.boundary: Polygon = boundary
        self.boundary_buff: Polygon = boundary_buff
        self.central_position: Position = self.create_position_from_point(self.boundary.centroid)

    # when the geometry is a simple line between 2 points, it doesn't seem to be stored e.g. (1390672272, 1390672213)
    def get_edge_geometry(self, edge: tuple[int, int]) -> LineString:
        # get_edge_data creates a LineString if geometry is missing, so this cast is safe
        result = self.get_edge_data(edge, key="geometry")
        assert isinstance(result, LineString), f"Expected LineString but got {type(result)}"
        return result

    # this one is special because it sometimes returns a single value and sometimes a list
    def get_edge_hw_as_int(self, edge: tuple[int, int]) -> int:
        hw_value = self.get_edge_data(edge, key="highway")
        # highway value should be str or list of str, not a dict
        assert not isinstance(hw_value, dict), "Expected str or list[str] but got dict"
        return highway_value_to_int(hw_value)  # type: ignore[arg-type]

    def get_route_edge_junctions(self, route):
        """
        Get junction attribute values for edges along a route.

        This is used to detect if nodes are on the same roundabout.
        The get_route_edge_attributes function was removed from osmnx 2.0,
        so we implement this simplified version specific to junction attributes.

        Args:
            route: List of nodes representing the route

        Returns:
            List of junction attribute values for each edge in the route
            (None if edge doesn't have a junction attribute)
        """
        junctions = []
        for u, v in zip(route[:-1], route[1:]):
            # For MultiDiGraph, get the first edge's data
            edge_data = self.graph.get_edge_data(u, v)
            if edge_data:
                # Get first key (edge could have multiple edges between same nodes)
                first_edge = edge_data[min(edge_data.keys())]  # type: ignore[type-var]
                junctions.append(first_edge.get("junction"))
            else:
                junctions.append(None)
        return junctions

    def are_on_same_round_about(self, node1: int, node2: int) -> bool:
        sh_path_n1_n2 = shortest_path(self.graph, node1, node2)
        return set(self.get_route_edge_junctions(sh_path_n1_n2)) == {"roundabout"}

    def node_to_edge_ref(self, node: int) -> EdgeRef:
        v_list = list(self.graph.successors(node))
        if not v_list:
            raise Exception(f"Node {node} has no outgoing edges to create an EdgeRef.")
        v = v_list[0]
        return EdgeRef(node, v, 0.0)

    def points_to_edge_refs(self, points: list[Point], on_node=False) -> list[EdgeRef]:
        if on_node:
            u_list = nearest_nodes(
                self.graph,
                [point.x for point in points],
                [point.y for point in points],
                return_dist=False,
            ).tolist()
            return [self.node_to_edge_ref(u) for u in u_list]
        else:
            # nearest_edges returns a list of (u, v, key) tuples for multiple points
            edges = nearest_edges(
                self.graph,
                [point.x for point in points],
                [point.y for point in points],
                return_dist=False,
            )
            u_list, v_list, key_list = zip(*edges)  # Transpose list of tuples into separate lists

            edges_geometries: list[LineString] = [self.get_edge_geometry((u, v)) for u, v in zip(u_list, v_list)]
            ec_list: list[float] = [
                edge_geom.project(point, normalized=True) for edge_geom, point in zip(edges_geometries, points)
            ]
            return [EdgeRef(u, v, ec) for u, v, ec in zip(u_list, v_list, ec_list)]

    def node_to_point(self, node_id: int) -> Point:
        return Point(self.graph.nodes[node_id]["x"], self.graph.nodes[node_id]["y"])

    def edge_ref_to_point(self, edge_ref: EdgeRef) -> Point:
        if edge_ref.ec < 0.0 or edge_ref.ec > 1.0:
            raise Exception("Edge cursor must be between 0.0 and 1.0")
        if not self.graph.has_edge(edge_ref.u, edge_ref.v):
            raise Exception("No edge exists from {} to {}".format(edge_ref.u, edge_ref.v))
        line_of_edge: LineString = self.get_edge_geometry((edge_ref.u, edge_ref.v))
        return line_of_edge.interpolate(edge_ref.ec, normalized=True)

    def get_random_points_in_boundary(self, nb, seed=None) -> list[Point]:
        """
        Generate random geographic points within the graph's boundary polygon.
        Points are generated within the bounding box and rejected
        if they fall outside the boundary polygon.

        Args:
            nb: Number of random points to generate
            seed: Optional random seed for reproducibility (default: None)

        Returns:
            List of Point objects guaranteed to be within the boundary polygon
        Raises:
            Exception: If unable to generate enough points after 10 times the number of points requested
        """
        rng = default_rng(seed)
        points: list[Point] = []
        nb_loops: int = 0
        while len(points) < nb:
            point: Point = Point(
                rng.uniform(self.boundary.bounds[0], self.boundary.bounds[2]),
                rng.uniform(self.boundary.bounds[1], self.boundary.bounds[3]),
            )
            if self.boundary.contains(point):
                points.append(point)
            # just in case we get no points inside the boundary
            nb_loops += 1
            if nb_loops > 10 * nb:
                raise Exception("We have been inside the while loop {} times.".format(nb_loops))
        return points

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
            List of EdgeRef namedtuples (u,v,ec)
        """
        rng = default_rng(seed)
        edge_cursors: list[float]
        random_edges: DataFrame = self.edges_df.iloc[rng.choice(len(self.edges_df), qty, replace=False)]
        if on_node:
            edge_cursors = [0.0] * qty
        else:
            edge_cursors = cast(list[float], rng.random(qty))
        return [
            self.create_position_from_edge_ref(EdgeRef(int(random_edge["u"]), int(random_edge["v"]), edge_cursor))
            for (_, random_edge), edge_cursor in zip(random_edges.iterrows(), edge_cursors)
        ]

    def has_in_boundary(self, position: Position) -> bool:
        return self.graph.nodes[position.u]["inner"]

    def get_escape_nodes(self) -> list[int]:
        return self.out_edges_df["out"].unique().tolist()

    def get_times_and_paths_from(self, source: int) -> tuple[dict[int, int], dict[int, list[int]]]:
        # the return types of single_source_dijkstra are a union to cater for the case where the
        # target is specified or not, so we need to cast here
        times_float, paths = cast(
            tuple[dict[int, float], dict[int, list[int]]],
            single_source_dijkstra(self.graph, source, weight="travel_time", target=None),
        )
        times_int = {node: int(time) for node, time in times_float.items()}
        return times_int, paths

    # Position factory methods
    def create_position_from_point(self, point: Point, on_node: bool = False) -> "Position":
        """
        Create a Position by snapping a geographic point to the road network.

        Args:
            point: Geographic point to snap to network
            on_node: If True, snap to nearest node; if False, snap to nearest point on edge

        Returns:
            Position object with snapped coordinates and edge reference
        """

        init_point = point
        u, v, e = self.points_to_edge_refs([point], on_node=on_node)[0]
        snapped_point = self.edge_ref_to_point(EdgeRef(u, v, e))
        return Position(init_point=init_point, point=snapped_point, u=u, v=v, ec=e)

    def create_position_from_edge_ref(self, edge_ref: EdgeRef) -> "Position":
        """
        Create a Position from an edge reference.

        Args:
            edge_ref: EdgeRef with u, v, and edge_cursor

        Returns:
            Position object with coordinates calculated from edge reference
        """

        point = self.edge_ref_to_point(edge_ref)
        return Position(
            init_point=point,
            point=point,
            u=edge_ref.u,
            v=edge_ref.v,
            ec=edge_ref.ec,
        )

    def create_position_from_node(self, u: int) -> "Position":
        """
        Create a Position from a graph node.

        Args:
            u: Node ID

        Returns:
            Position at the node with edge_cursor=0.0
        """

        edge_ref = self.node_to_edge_ref(u)
        point = self.node_to_point(u)
        return Position(init_point=point, point=point, u=edge_ref.u, v=edge_ref.v, ec=edge_ref.ec)

    def to_linestring(self, nodes: list[int]) -> LineString:
        """
        Get a single LineString representing the path between a list of nodes.

        Args:
            nodes: List of node IDs representing the path. Successive nodes should be connected by edges.
        Returns:
            LineString representing the path
        """
        if not nodes:
            raise ValueError("Empty list of nodes cannot be converted to a LineString")
        if len(nodes) == 1:
            point = self.node_to_point(nodes[0])
            return LineString([point, point])
        else:
            return cast(
                LineString,
                ops.linemerge([self.get_edge_geometry(edge) for edge in zip(nodes, nodes[1:])]),
            )

    def u_to_position_as_ls(self, edge_ref: EdgeRef) -> LineString:
        if edge_ref.ec == 0.0:
            u_point = self.node_to_point(edge_ref.u)
            return LineString([u_point, u_point])
        return cast(
            LineString,
            ops.substring(self.get_edge_geometry((edge_ref.u, edge_ref.v)), 0.0, edge_ref.ec, normalized=True),
        )

    def v_to_position_as_ls(self, edge_ref: EdgeRef) -> LineString:
        if edge_ref.ec == 1.0:
            v_point = self.node_to_point(edge_ref.v)
            return LineString([v_point, v_point])
        return cast(
            LineString,
            ops.substring(self.get_edge_geometry((edge_ref.u, edge_ref.v)), edge_ref.ec, 1.0, normalized=True),
        )

    # return the geometry only but as a dataframe, not a series
    def get_node_list_as_gdf(self, the_lst: list[int]):
        return self.nodes_df.loc[the_lst, ["geometry"]]

    def get_paths_as_small_gdf(self, path_list: list[list[int]]) -> GeoDataFrame:
        tuple_set: set[tuple[int, int]] = {tup for path in path_list for tup in zip(path, path[1:])}
        return GeoDataFrame(
            [[self.to_linestring(list(tup))] for tup in tuple_set],
            crs="EPSG:4326",
            columns=Index(["geometry"]),
        )

    # this allows us to treat the MultiDiGraph as a Digraph. Instead of having to put a [0] after everything
    def get_edge_data(self, edge: tuple[int, int], key=None, default=None) -> str | dict[str, object]:
        """
        Retrieve data associated with an edge in a MultiDiGraph.
        We treat the MultiDiGraph as a Digraph by using only the edge with the highest
        highway ranking if there are multiple edges.

        If the geometry attribute is missing, it is constructed as a LineString between the two nodes.
        Optionally, a specific attribute can be retrieved using the 'key' argument.

        Args:
            edge (Tuple[int, int]): The edge specified as a tuple of node IDs (u, v).
            key (str, optional): Specific attribute to retrieve from the edge data. If None, returns the full edge data.
            default (any, optional): Default value to return if the specified key is not found.

        Returns:
            Union[str, Dict[str, object]]: Either the requested edge attribute (str)
            or the full edge data dictionary (Dict[str, object]).
        """
        # Validate edge exists
        raw_edge_data = self.graph.get_edge_data(edge[0], edge[1])
        if raw_edge_data is None:
            raise ValueError(f"Edge {edge} does not exist in the graph")

        edge_data: dict[str, object] = max(raw_edge_data.values(), key=edge_quantifier)

        # if you are going to need the geometry, check if it is missing
        if (key is None or key == "geometry") and "geometry" not in edge_data.keys():
            edge_data["geometry"] = LineString(
                [
                    Point(self.graph.nodes[edge[0]]["x"], self.graph.nodes[edge[0]]["y"]),
                    Point(self.graph.nodes[edge[1]]["x"], self.graph.nodes[edge[1]]["y"]),
                ]
            )
        if key is None:
            return edge_data
        # Cast to expected return type - caller is responsible for ensuring type safety
        return cast(str | dict[str, object], edge_data.get(key, default))

    def get_edge_position_after_time(self, u: int, v: int, time_elapsed: int) -> Position:
        # find the edge between the nodes with the minimum travel time
        edge_data: dict[str, object] = min(self.graph.get_edge_data(u, v).values(), key=lambda x: x["travel_time"])
        edge_travel_time: float = cast(float, edge_data["travel_time"])
        if not (0 <= time_elapsed <= edge_travel_time):
            raise ValueError(f"Time elapsed {time_elapsed} is out of bounds for edge {u}-{v}")
        return self.create_position_from_edge_ref(EdgeRef(u, v, time_elapsed / edge_travel_time))
