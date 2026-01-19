from __future__ import annotations

import argparse
import json
import logging
import os
import re
from io import BytesIO
from pathlib import Path
from typing import cast
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile, is_zipfile

import osmnx
from geopandas import GeoDataFrame, GeoSeries, read_file  # pyright: ignore[reportUnknownVariableType]
from networkx import MultiDiGraph, edge_boundary  # pyright: ignore[reportUnknownVariableType]
from osmnx import (  # pyright: ignore[reportUnknownVariableType]
    add_edge_bearings,  # pyright: ignore[reportUnknownVariableType]
    add_edge_speeds,  # pyright: ignore[reportUnknownVariableType]
    add_edge_travel_times,  # pyright: ignore[reportUnknownVariableType]
    load_graphml,  # pyright: ignore[reportUnknownVariableType]
    projection,
)
from pandas import Series
from shapely import MultiPolygon, from_wkt, to_wkt  # pyright: ignore[reportUnknownVariableType]
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from .config import (
    BUFFER_IN_METERS,
    DEPARTEMENTS_DATA_DIR,
    DEPARTEMENTS_SHP_FILE_PATH,
    DEPARTEMENTS_SHP_ZIPPED_URL,
)
from .github_network_files import download_files
from .road_network import RoadNetwork
from .utils import (
    convert_bool_string,
    data_dir,
    stringify_nonnumeric_cols,
)

osmnx.settings.log_console = True
osmnx.settings.log_level = logging.WARNING
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
network_dir: str = os.path.join(data_dir, "networks")
osmnx.settings.cache_folder = os.path.join(data_dir, "osmnx_cache")
osmnx.settings.use_cache = True


def get_buffered_poly(polygon: Polygon, buffer_in_meters: float = BUFFER_IN_METERS) -> Polygon:
    """
    Create a buffered version of a polygon by expanding it by a specified distance.
    For instance, a rectangle will result in a larger rectangle with rounded corners.

    This function is used to extend geographic boundaries outward to avoid edge effects
    in network graphs. The polygon is projected to UTM (meters), buffered by the
    specified distance, then converted back to lat/long coordinates.

    Args:
        polygon: A Shapely Polygon in lat/long (EPSG:4326) coordinates
        buffer_in_meters: Distance in meters to expand the polygon in all directions.
                         Defaults to BUFFER_IN_METERS

    Returns:
        A new Polygon (in lat/long) expanded by the specified distance in all directions
    """
    polygon_proj, crs_utm = cast(tuple[Polygon, str], projection.project_geometry(polygon))
    polygon_proj_buff = polygon_proj.buffer(buffer_in_meters)
    polygon_buff, _ = projection.project_geometry(polygon_proj_buff, crs=crs_utm, to_latlong=True)

    return cast(Polygon, polygon_buff)


def boundary_from_name(name: str) -> Polygon:
    """
    Convert a name identifier into a geographic boundary polygon.

    This function resolves different naming conventions to geographic boundaries
    used for network extraction. It supports three types of identifiers:

    1. French department codes (e.g., '60', '67', '2A', '2B')
       - Returns the administrative boundary of that department

    2. Department codes with 'c' suffix (e.g., '60c', '67c')
       - Returns the department boundary plus all neighboring departments

    3. Predefined box names (e.g., 'st_quentin', 'vauvert', 'noailles', 'd2', 'oise')
       - Returns a rectangular bounding box from the boxes dictionary

    Args:
        name: A string identifier - either a box name, department code, or department code with 'c'

    Returns:
        A Shapely Polygon representing the geographic boundary

    Raises:
        Exception: If the name doesn't match any known pattern
    """
    # name is either 2 digits or 2A/2B
    if re.match("^(\\d\\d|2A|2B)$", name):
        return get_departement_polygon(departement_code=name, include_neighbours=False)
    # name is either 2 digits or 2A/2B followed by 'c'
    elif re.match("^(\\d\\d|2A|2B)c$", name):
        return get_departement_polygon(departement_code=name[0:2], include_neighbours=True)
    # try to find a named box in boxes.json
    else:
        with open(os.path.join(os.path.join(data_dir, "boxes.json"))) as f:
            boxes = json.load(f)
        if name in boxes:
            bbox = boxes.get(name)
            return Polygon(
                ((bbox[0], bbox[2]), (bbox[0], bbox[3]), (bbox[1], bbox[3]), (bbox[1], bbox[2]), (bbox[0], bbox[2]))
            )
        else:
            raise Exception(f"{name} cannot be mapped to a geographic boundary.")


def get_departement_polygon(departement_code: str, include_neighbours: bool) -> Polygon:
    """
    Retrieve the geographic boundary polygon for a French department.
    If include_neighbours is True, the returned polygon includes the department
    and all neighboring departments as a single dissolved geometry.

    Args:
        departement_code: The INSEE code of the department (e.g., '60', '2A', '2B').
        include_neighbours: whether to include neighboring departments in the boundary.

    Returns:
        A Shapely Polygon representing the department boundary, or the union of
        the department and its neighbors if include_neighbours is True.

    Raises:
        Exception: If the department code is invalid or not found.
    """

    departments_gdf = get_departments_gdf()
    try:
        shape: BaseGeometry = departments_gdf[departments_gdf["DDEP_C_COD"] == departement_code].iloc[0]["geometry"]
    except KeyError as e:
        raise Exception(f"No geometry is associated with {departement_code}") from e

    if include_neighbours:
        logger.info(f"Adding departements neighbours of {departement_code}")
        # get 'not disjoint' countries, make a copy() to avoid the annoying SettingWithCopyWarning
        departements_around: GeoDataFrame = cast(
            GeoDataFrame, departments_gdf[~departments_gdf.geometry.disjoint(shape)].copy()
        )
        logger.info(f"The following departements will be included in the area: {list(departements_around.DDEP_C_COD)}")
        shape = cast(BaseGeometry, departements_around.union_all())
    # make sure to return a Polygon, not a MultiPolygon
    if shape.geom_type == "Polygon":
        return cast(Polygon, shape)
    # If we have a MultiPolygon, return the largest Polygon
    elif shape.geom_type == "MultiPolygon":
        return max(cast(MultiPolygon, shape).geoms, key=lambda pg: pg.area)
    else:
        raise Exception(f"Geometry for departement {departement_code} is neither a Polygon nor a MultiPolygon.")


def analyze_boundary(
    graph: MultiDiGraph,  # pyright: ignore[reportUnknownParameterType]
    nodes_df: GeoDataFrame,
    polygon: Polygon,
) -> tuple[GeoDataFrame, GeoDataFrame, set[int]]:
    """
    Identifies the edges that cross the boundary of the given polygon,the intersection points
    of those edges with the polygon boundary, and the set of node IDs located inside the polygon.

    Args:
        graph (MultiDiGraph): The networkx graph representing the road network.
        nodes_df (GeoDataFrame): GeoDataFrame containing node information for the graph.
        polygon (Polygon): The geographic boundary to analyze.

    Returns:
        Tuple[GeoDataFrame, GeoDataFrame, Set[int]]:
            - GeoDataFrame of edges crossing the polygon boundary.
            - GeoDataFrame of intersection points between those edges and the polygon boundary.
            - Set of node IDs located inside the polygon.
    """
    # boolean Series indicating if each node is within the polygon
    is_within_polygon: Series = nodes_df.within(polygon)
    # Set of node IDs that are inside the polygon
    nodes_in_polygon: set[int] = set(cast(Series, is_within_polygon[is_within_polygon]).index)

    # Helper to get edge data using highway ranking logic
    def get_edge_data_dict(edge: tuple[int, int]) -> dict:  # pyright: ignore[reportUnknownParameterType]
        edge_data = max(graph.get_edge_data(edge[0], edge[1]).values(), key=RoadNetwork.edge_quantifier)  # pyright: ignore[reportUnknownMemberType]
        return dict(edge_data)

    # edge_boundary returns edges where edge[0] is inside and edge[1] is outside
    edges_as_dict = [  # pyright: ignore[reportUnknownVariableType]
        {"in": edge[0], "out": edge[1], **get_edge_data_dict(edge)}  # pyright: ignore[reportUnknownArgumentType]
        for edge in edge_boundary(graph, nodes_in_polygon)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    ]
    # Create a GeoDataFrame for these crossing edges
    x_edges = GeoDataFrame(edges_as_dict, crs="EPSG:4326")  # pyright: ignore[reportUnknownArgumentType]

    # Ensure all non-numeric columns are stringified for compatibility
    # not sure this is needed as tests pass without it
    x_edges = stringify_nonnumeric_cols(x_edges)

    # Compute intersection points of these edges with the polygon boundary
    intersection_points: GeoSeries = x_edges.intersection(polygon.exterior)

    # Drop from intersection_points anything that is not a Point or a MultiPoint, I have seen None values
    intersection_points = cast(
        GeoSeries, intersection_points[intersection_points.geom_type.isin(["Point", "MultiPoint"])]
    )

    # Replace MultiPoint geometries by the first point in the collection for consistency
    intersection_points = GeoSeries(
        intersection_points.apply(lambda g: g.geoms[0] if g.geom_type == "MultiPoint" else g)  # pyright: ignore[reportUnknownLambdaType, reportUnknownMemberType]
    )

    # Convert GeoSeries to GeoDataFrame to match return type
    intersection_points_gdf = GeoDataFrame(geometry=intersection_points, crs="EPSG:4326")
    return x_edges, intersection_points_gdf, nodes_in_polygon


def extract_zip_url(url: str, dest_folder: Path) -> None:
    """
    Download the zip file at the given URL and extract its contents into the destination folder.

    Args:
        url (str): URL of the zip file to download.
        dest_folder (str): Destination folder to extract the contents into.

    Raises:
        FileNotFoundError: If the file_name is not found in the zip archive.
        Exception: For download or extraction errors.
    """
    try:
        resp = urlopen(url)
        zip_bytes = BytesIO(resp.read())
        if not is_zipfile(zip_bytes):
            raise Exception(f"The file downloaded from {url} is not a valid zip archive.")
        with ZipFile(zip_bytes) as zip_file:
            zip_file.extractall(path=dest_folder)
    except BadZipFile as err:
        raise Exception(f"Failed to open zip file from {url}") from err
    except Exception as e:
        raise Exception(f"Error extracting from {url}: {e}") from e


def get_departments_gdf(dir: Path = DEPARTEMENTS_DATA_DIR) -> GeoDataFrame:
    """
    Load the GeoDataFrame containing French department boundaries.

    Checks for the presence of the department shapefile in the local data directory.
    If the file is not found, downloads the shapefile from the official data.gouv.fr source,
    extracts it, and caches it locally for future use.

    Returns:
        GeoDataFrame: A GeoPandas GeoDataFrame containing the boundaries and attributes
        of all French departments.

    Raises:
        FileNotFoundError: If the shapefile cannot be found in the downloaded archive.
        Exception: For any issues encountered during file download or extraction.
    """
    if not DEPARTEMENTS_SHP_FILE_PATH.exists():
        logger.info(
            f"File {DEPARTEMENTS_SHP_FILE_PATH} not cached, downloading it from {DEPARTEMENTS_SHP_ZIPPED_URL} ..."
        )

        extract_zip_url(DEPARTEMENTS_SHP_ZIPPED_URL, DEPARTEMENTS_DATA_DIR)
        if not DEPARTEMENTS_SHP_FILE_PATH.exists():
            raise FileNotFoundError(f"Shapefile not found after extraction: {DEPARTEMENTS_SHP_FILE_PATH}")
    else:
        logger.info(f"Loading {DEPARTEMENTS_SHP_FILE_PATH} from cache")
    return read_file(DEPARTEMENTS_SHP_FILE_PATH)


class RoadNetworkFactory:
    """Factory for creating RoadNetwork instances with automatic data acquisition.

    This factory orchestrates the acquisition of road network data through multiple
    strategies in order of preference:
    1. Local cache (data/networks/)
    2. GitHub releases
    3. Generate from département boundaries (for 2-digit codes or 2A/2B)
    4. Generate from bbox definitions (boxes.json)

    Attributes:
        cache_dir: Directory where network files are cached
        bbox_file: Path to JSON file containing bbox definitions
        github_repo: GitHub repository for releases (format: "owner/repo")
        github_release_tag: Release tag to download from (e.g., "v1.0.0", "latest")
    """

    def __init__(
        self,
        bbox_file: str = os.path.join(data_dir, "boxes.json"),
        cache_dir: str = os.path.join(data_dir, "networks"),
    ):
        self.bbox_file = bbox_file
        self.cache_dir = cache_dir

        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)

    def _is_departement_code(self) -> bool:
        return bool(re.match(r"^(\d{2}|2A|2B)c?$", self.name))

    def is_valid_bbox(self) -> bool:
        """Check if a valid bbox exists for the given name.

        Opens bbox_file, loads JSON, and validates the bbox entry for the name.

        Args:
            name: The key to look up in the bbox file

        Returns:
            True if name maps to a valid bbox, False if name not found

        Raises:
            FileNotFoundError: If bbox_file doesn't exist
            json.JSONDecodeError: If bbox_file contains invalid JSON
            ValueError: If bbox exists but has invalid format/values
        """
        # Will raise FileNotFoundError if file doesn't exist
        with open(self.bbox_file) as f:
            # Will raise json.JSONDecodeError if invalid JSON
            boxes: dict[str, list[float]] = json.load(f)

        # Name not found - return False (not an error)
        box: list[float] | None = boxes.get(self.name)
        if box is None:
            return False

        # Validate it's a list of 4 numbers
        if not isinstance(box, list) or len(box) != 4 or not all(isinstance(x, (int, float)) for x in box):
            raise ValueError(f"Invalid bbox for '{self.name}': there must be 4 numbers, got {box}")

        # Validate longitude values (west and east) are between -5 and 10 and in the correct order
        if not ((-5 <= box[0] <= 10) and (-5 <= box[1] <= 10) and (box[0] < box[1])):
            raise ValueError(f"Invalid east/west values for '{self.name}")
        # Validate latitude values (south and north) are between 41 and 51 and in the correct order
        if not ((41 <= box[2] <= 51) and (41 <= box[3] <= 51) and (box[2] < box[3])):
            raise ValueError(f"Invalid north/south values for '{self.name}")
        return True

    def create(self, name: str, create_from_scratch: bool = False) -> RoadNetwork:
        """Create a RoadNetwork instance for the given name.

        Attempts to load or generate the network through multiple strategies:
        1. Check local cache
        2. Download from GitHub releases

        Args:
            name: Network identifier (département code, bbox name, etc.)

        Returns:
            RoadNetwork instance

        Raises:
            ValueError: If network files cannot be found
        """

        # we set the values needed for all that follows as instance variables
        # so we don't have to pass them around
        self.name: str = name
        self.graphml_path: str = os.path.join(self.cache_dir, f"{name}.graphml")

        # we check that name makes sense before proceeding
        if not self._is_departement_code() and not self.is_valid_bbox():
            raise ValueError(
                f"Name must be a département code (e.g., '60', '2A'), "
                f"département code with 'c' suffix (e.g., '60c'), "
                f"or a named bbox from {self.bbox_file} with valid coordinates."
            )

        if create_from_scratch:
            boundary: Polygon = boundary_from_name(self.name)
            self.create_files_from_boundary(boundary)
            return self.instantiate_from_files()

        # else we try to load from cache or download from GitHub releases
        # 1. Check cache
        if os.path.isfile(self.graphml_path) or download_files(self.name, Path(self.cache_dir)):
            return self.instantiate_from_files()
        # 3. We recreate from boundaries, the early check ensures this should work
        else:
            raise ValueError(f"Network files for '{self.name}' not found in cache or GitHub releases. ")

    def instantiate_from_files(self) -> RoadNetwork:
        """Load network from graphml file. Assumes file is present.

        Returns:
            RoadNetwork instance
        """
        graph: MultiDiGraph = load_graphml(  # pyright: ignore[reportUnknownVariableType]
            self.graphml_path, node_dtypes={"inner": convert_bool_string}
        )

        # Parse escape_nodes from graph attribute (comma-separated node IDs)
        escape_nodes_str: str = graph.graph.get("escape_nodes", "")
        escape_nodes: set[int] = {int(n) for n in escape_nodes_str.split(",") if n}

        # Parse boundaries from WKT strings stored in graph attributes
        boundary: Polygon = cast(Polygon, from_wkt(graph.graph["boundary"]))
        boundary_buff: Polygon = cast(Polygon, from_wkt(graph.graph["boundary_buff"]))

        return RoadNetwork(
            name=self.name,
            graph=graph,  # pyright: ignore[reportUnknownArgumentType]
            escape_nodes=escape_nodes,
            boundary=boundary,
            boundary_buff=boundary_buff,
        )

    def create_files_from_boundary(self, boundary: Polygon) -> None:
        """
        Prepare network files for a given geographic zone.

        Args:
            name (str): Name of the geographic zone (department code, box name, etc.).
        """

        boundary_buff = get_buffered_poly(boundary)
        logger.info(f"Downloading OSM data within the polygon defined by {boundary.bounds}.")
        # custom filter to get only major highways suitable for motor vehicles
        main_roads_filter = (
            '["highway"~"tertiary|tertiary_link|secondary|secondary_link|primary|primary_link|'
            'trunk|trunk_link|motorway|motorway_link"]["motor_vehicle"!~"no"]'
            '["motorcar"!~"no"]["service"!~"alley|driveway|emergency_access|parking|'
            'parking_aisle|private"]'
        )
        graph: MultiDiGraph = osmnx.graph_from_polygon(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            boundary_buff,
            network_type="drive",
            simplify=True,
            retain_all=False,
            truncate_by_edge=True,
            custom_filter=main_roads_filter,
        )
        logger.info(f"Graph has {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges")  # pyright: ignore[reportUnknownMemberType]
        # keep only the largest connected component
        graph = osmnx.truncate.largest_component(graph, strongly=True)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        logger.info(
            f"Graph has {graph.number_of_nodes()} nodes and {graph.number_of_edges()}"  # pyright: ignore[reportUnknownMemberType]
            + " edges after removing disconnected components"
        )

        logger.info("OSM data downloaded, processing the graph ...")
        nodes_gdf: GeoDataFrame
        nodes_gdf, _edges_gdf = osmnx.graph_to_gdfs(graph)  # pyright: ignore[reportUnknownMemberType]
        out_edges_gdf, _out_intersections_gdf, nodes_in_boundary = analyze_boundary(graph, nodes_gdf, boundary)

        nodes_to_remove: list[int] = []
        # set the inner flag and mark nodes to delete
        logger.info("Adding the 'inner' field to nodes and removing dead-ends outside the boundary ...")
        for node in graph.nodes:  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            if node in nodes_in_boundary:
                graph.nodes[node]["inner"] = True  # pyright: ignore[reportUnknownMemberType]
                if graph.out_degree(node) == 0 or graph.in_degree(node) == 0:  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                    nodes_to_remove.append(node)  # pyright: ignore[reportUnknownArgumentType]
            else:
                graph.nodes[node]["inner"] = False  # pyright: ignore[reportUnknownMemberType]

        # remove the nodes_to_remove from the graph, nodes_gdf and edges_gdf
        for node in nodes_to_remove:
            graph.remove_node(node)  # pyright: ignore[reportUnknownMemberType]
        nodes_gdf = cast(GeoDataFrame, nodes_gdf.drop(nodes_to_remove))

        # add essential edge attributes for routing before saving to graphml
        add_edge_bearings(graph)  # pyright: ignore[reportUnknownArgumentType]
        add_edge_speeds(graph)  # pyright: ignore[reportUnknownArgumentType]
        add_edge_travel_times(graph)  # pyright: ignore[reportUnknownArgumentType]

        # Compute escape_nodes from out_edges (nodes just outside the boundary)
        escape_nodes: set[int] = set(out_edges_gdf["out"].astype(int))

        # Store escape_nodes and boundaries as graph-level attributes for graphml
        graph.graph["escape_nodes"] = ",".join(str(n) for n in escape_nodes)
        graph.graph["boundary"] = to_wkt(boundary)
        graph.graph["boundary_buff"] = to_wkt(boundary_buff)

        osmnx.save_graphml(graph, self.graphml_path, gephi=False, encoding="utf-8")  # pyright: ignore[reportUnknownMemberType]

        logger.info(f"File {self.graphml_path} has been successfully generated.")

    def graphml_to_gpkg(self, graphml_path: str, gpkg_path: str) -> None:
        """
        Convert a GraphML file to a GeoPackage file with specific layers.

        Layers included:
        - nodes
        - edges
        - boundary
        - boundary buffer

        Args:
            graphml_path: Path to the input GraphML file.
            gpkg_path: Path to the output GeoPackage file.
        """
        graph: MultiDiGraph = load_graphml(  # pyright: ignore[reportUnknownVariableType]
            graphml_path, node_dtypes={"inner": convert_bool_string}
        )

        # Get nodes and edges GeoDataFrames
        nodes_gdf, edges_gdf = osmnx.graph_to_gdfs(graph)  # pyright: ignore[reportUnknownMemberType]

        # Stringify non-numeric columns to ensure GeoPackage compatibility
        nodes_gdf = stringify_nonnumeric_cols(nodes_gdf)
        edges_gdf = stringify_nonnumeric_cols(edges_gdf)

        # Save nodes and edges
        nodes_gdf.to_file(gpkg_path, layer="nodes", driver="GPKG")  # pyright: ignore[reportUnknownMemberType]
        edges_gdf.to_file(gpkg_path, layer="edges", driver="GPKG", mode="a")  # pyright: ignore[reportUnknownMemberType]

        # Extract boundary and boundary_buff from graph attributes
        boundary_wkt = graph.graph.get("boundary")
        boundary_buff_wkt = graph.graph.get("boundary_buff")

        # Save boundary layer
        if boundary_wkt:
            boundary_polygon = cast(Polygon, from_wkt(boundary_wkt))
            boundary_gdf = GeoDataFrame(geometry=[boundary_polygon], crs=nodes_gdf.crs)
            boundary_gdf.to_file(gpkg_path, layer="boundary", driver="GPKG", mode="a")  # pyright: ignore[reportUnknownMemberType]

        # Save boundary buffer layer
        if boundary_buff_wkt:
            boundary_buff_polygon = cast(Polygon, from_wkt(boundary_buff_wkt))
            boundary_buff_gdf = GeoDataFrame(geometry=[boundary_buff_polygon], crs=nodes_gdf.crs)
            boundary_buff_gdf.to_file(gpkg_path, layer="boundary buffer", driver="GPKG", mode="a")  # pyright: ignore[reportUnknownMemberType]

        logger.info(f"Successfully converted {graphml_path} to {gpkg_path}")


def main():
    parser = argparse.ArgumentParser(description="Road Network Factory CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a road network from OSM")
    create_parser.add_argument("name", help="Name of the department or bbox")
    create_parser.add_argument("--scratch", action="store_true", help="Force creation from scratch")

    # Convert command
    convert_parser = subparsers.add_parser("convert", help="Convert GraphML to GeoPackage")
    convert_parser.add_argument("input", help="Path to input GraphML file")
    convert_parser.add_argument("output", help="Path to output GeoPackage file")

    args = parser.parse_args()

    factory = RoadNetworkFactory()

    if args.command == "create":
        factory.create(args.name, create_from_scratch=args.scratch)
    elif args.command == "convert":
        factory.graphml_to_gpkg(args.input, args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
