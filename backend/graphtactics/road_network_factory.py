import json
import logging
import os
import re
from io import BytesIO
from typing import cast
from urllib.error import HTTPError
from urllib.request import urlopen, urlretrieve
from zipfile import BadZipFile, ZipFile, is_zipfile

import osmnx
from geopandas import GeoDataFrame, GeoSeries, read_file
from networkx import MultiDiGraph, edge_boundary
from osmnx import (
    add_edge_bearings,
    add_edge_speeds,
    add_edge_travel_times,
    load_graphml,
    projection,
)
from pandas import Series
from pandas.core.base import IndexLabel
from shapely import MultiPolygon
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from .road_network import RoadNetwork
from .utils import (
    convert_bool_string,
    data_dir,
    edge_quantifier,
    stringify_nonnumeric_cols,
)

osmnx.settings.cache_folder = "cache/osmnx"
osmnx.settings.log_console = True
osmnx.settings.log_level = logging.INFO
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
network_dir: str = os.path.join(data_dir, "networks")
# departments_shp_zipped_url = "https://www.data.gouv.fr/en/datasets/r/eb36371a-761d-44a8-93ec-3d728bec17ce"
departments_shp_zipped_url = "https://data-interne.ademe.fr/data-fair/api/v1/datasets/geo-contours-departements/data-files/GEO_Contours_Departements.zip"
departments_data_dir = os.path.join(data_dir, "departements")
departments_file_name = "Departements.shp"


def get_buffered_poly(polygon: Polygon, buffer_in_meters: float = 2000) -> Polygon:
    """
    Create a buffered version of a polygon by expanding it by a specified distance.
    For instance, a rectangle will result in a larger rectangle with rounded corners.

    This function is used to extend geographic boundaries outward to avoid edge effects
    in network graphs. The polygon is projected to UTM (meters), buffered by the
    specified distance, then converted back to lat/long coordinates.

    Args:
        polygon: A Shapely Polygon in lat/long (EPSG:4326) coordinates
        buffer_in_meters: Distance in meters to expand the polygon in all directions.
                         Defaults to 2000 meters (2 km)

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
        with open(os.path.join(os.path.join(data_dir, "boxes.json")), "r") as f:
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
    except KeyError:
        raise Exception(f"No geometry is associated with {departement_code}")

    if include_neighbours:
        logger.info(f"Adding departements neighbours of {departement_code}")
        # get 'not disjoint' countries, make a copy() to avoid the annoying SettingWithCopyWarning
        departements_around: GeoDataFrame = cast(
            GeoDataFrame, departments_gdf[~departments_gdf.geometry.disjoint(shape)].copy()
        )
        logger.info(f"The following departements will be included in the area: {list(departements_around.code_insee)}")
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
    graph: MultiDiGraph, nodes_df: GeoDataFrame, polygon: Polygon
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
    def get_edge_data_dict(edge: tuple[int, int]) -> dict:
        edge_data = max(graph.get_edge_data(edge[0], edge[1]).values(), key=edge_quantifier)
        return dict(edge_data)

    # edge_boundary returns edges where edge[0] is inside and edge[1] is outside
    edges_as_dict = [
        {"in": edge[0], "out": edge[1], **get_edge_data_dict(edge)} for edge in edge_boundary(graph, nodes_in_polygon)
    ]
    # Create a GeoDataFrame for these crossing edges
    x_edges = GeoDataFrame(edges_as_dict, crs="EPSG:4326")

    # Ensure all non-numeric columns are stringified for compatibility
    # not sure this is needed as tests pass without it
    x_edges = stringify_nonnumeric_cols(x_edges)

    # Compute intersection points of these edges with the polygon boundary
    intersection_points: GeoSeries = x_edges.intersection(polygon.exterior)
    # Replace MultiPoint geometries by the first point in the collection for consistency
    intersection_points = GeoSeries(intersection_points.apply(lambda g: g[0] if g.geom_type == "MultiPoint" else g))
    # Convert GeoSeries to GeoDataFrame to match return type
    intersection_points_gdf = GeoDataFrame(geometry=intersection_points, crs="EPSG:4326")
    return x_edges, intersection_points_gdf, nodes_in_polygon


def extract_zip_url(url: str, dest_folder: str) -> None:
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
    except BadZipFile:
        raise Exception(f"Failed to open zip file from {url}")
    except Exception as e:
        raise Exception(f"Error extracting from {url}: {e}")


def get_departments_gdf(dir: str = departments_data_dir) -> GeoDataFrame:
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
    shp_file_path = os.path.join(departments_data_dir, departments_file_name)
    if not os.path.exists(shp_file_path):
        logger.info(f"File {shp_file_path} not cached, downloading it from {departments_shp_zipped_url} ...")

        extract_zip_url(departments_shp_zipped_url, departments_data_dir)
        if not os.path.exists(shp_file_path):
            raise FileNotFoundError(f"Shapefile not found after extraction: {shp_file_path}")
    else:
        logger.info(f"Loading {shp_file_path} from cache")
    return read_file(shp_file_path)


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
        github_repo: str = "guibar/graphtactics",
        github_release_tag: str = "osm-networks-v1.0",
    ):
        self.cache_dir = network_dir
        self.bbox_file = bbox_file
        self.github_repo = github_repo
        self.github_release_tag = github_release_tag

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
        with open(self.bbox_file, "r") as f:
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

    def create(self, name: str) -> RoadNetwork:
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
        self.gpkg_path: str = os.path.join(self.cache_dir, f"{name}.gpkg")

        # we check that name makes sense before proceeding
        if not self._is_departement_code() and not self.is_valid_bbox():
            raise ValueError(
                f"Name must be a département code (e.g., '60', '2A'), "
                f"département code with 'c' suffix (e.g., '60c'), "
                f"or a named bbox from {self.bbox_file} with valid coordinates."
            )

        # 1. Check cache
        if os.path.isfile(self.graphml_path) and os.path.isfile(self.gpkg_path):
            return self.instantiate_from_files()
        # 2. Try to download from GitHub releases
        elif self.download_files_from_github():
            return self.instantiate_from_files()
        # 3. We recreate from boundaries, the early check ensures this should work
        else:
            raise ValueError(f"Network files for '{self.name}' not found in cache or GitHub releases. ")
            # boundary: Polygon = boundary_from_name(self.name)
            # self.create_files_from_boundary(boundary)
            # return self.instantiate_from_files()

    def instantiate_from_files(self) -> RoadNetwork:
        """Load network from files. Assumes files are present.

        Returns:
            RoadNetwork instance
        """
        graph: MultiDiGraph = load_graphml(self.graphml_path, node_dtypes={"inner": convert_bool_string})

        nodes_gdf: GeoDataFrame = read_file(self.gpkg_path, layer="nodes")
        nodes_gdf.set_index("osmid", inplace=True, verify_integrity=True)
        edges_gdf: GeoDataFrame = read_file(self.gpkg_path, layer="edges")
        out_edges_gdf: GeoDataFrame = read_file(self.gpkg_path, layer="out_edges")
        out_intersections_gdf: GeoDataFrame = read_file(self.gpkg_path, layer="out_edges_intersections")
        boundaries_gdf: GeoDataFrame = read_file(self.gpkg_path, layer="boundaries")
        boundary: Polygon = boundaries_gdf.iloc[0].geometry
        boundary_buff: Polygon = boundaries_gdf.iloc[1].geometry

        return RoadNetwork(
            name=self.name,
            graph=graph,
            nodes_df=nodes_gdf,
            edges_df=edges_gdf,
            out_edges_df=out_edges_gdf,
            out_intersections_df=out_intersections_gdf,
            boundary=boundary,
            boundary_buff=boundary_buff,
        )

    def download_files_from_github(self) -> bool:
        """Download network files from GitHub releases if available.
        Args:
            name: Network identifier
        Returns:
            True if files were successfully downloaded, False otherwise
        """

        # Determine the release URL
        if self.github_release_tag == "latest":
            base_url = f"https://github.com/{self.github_repo}/releases/latest/download"
        else:
            base_url = f"https://github.com/{self.github_repo}/releases/download/{self.github_release_tag}"

        graphml_url = f"{base_url}/{self.name}.graphml"
        gpkg_url = f"{base_url}/{self.name}.gpkg"

        try:
            logger.info(f"Attempting to download graphml from {graphml_url}")
            urlretrieve(graphml_url, self.graphml_path)
            logger.info(f"Attempting to download gpkg from {gpkg_url}")
            urlretrieve(gpkg_url, self.gpkg_path)
            logger.info(f"Successfully downloaded graphml and gpkg for '{self.name}' from GitHub")
            return True
        except HTTPError as e:
            logger.debug(f"GitHub release files not found for '{self.name}': {e}")
        except Exception as e:
            logger.warning(f"Failed to download from GitHub for '{self.name}': {e}")

        # Clean up partial downloads (only reached if exception occurred)
        if os.path.exists(self.graphml_path):
            os.remove(self.graphml_path)
        if os.path.exists(self.gpkg_path):
            os.remove(self.gpkg_path)
        return False

    def create_files_from_boundary(self, boundary: Polygon) -> None:
        """
        Prepare network files for a given geographic zone.

        Args:
            name (str): Name of the geographic zone (department code, box name, etc.).
        """

        osmnx.settings.cache_folder = "cache/osmnx"
        boundary_buff = get_buffered_poly(boundary)
        logger.info(f"Downloading OSM data within the polygon defined by {boundary}.")
        # custom filter to get only major highways suitable for motor vehicles
        major_highways = (
            '["highway"~"tertiary|tertiary_link|secondary|secondary_link|primary|primary_link|'
            'trunk|trunk_link|motorway|motorway_link"]["motor_vehicle"!~"no"]'
            '["motorcar"!~"no"]["service"!~"alley|driveway|emergency_access|parking|'
            'parking_aisle|private"]'
        )
        graph: MultiDiGraph = osmnx.graph_from_polygon(
            boundary_buff,
            network_type="drive",
            simplify=True,
            retain_all=False,
            truncate_by_edge=True,
            custom_filter=major_highways,
        )
        logger.info("OSM data downloaded, processing the graph ...")
        nodes_gdf: GeoDataFrame
        edges_gdf: GeoDataFrame
        nodes_gdf, edges_gdf = osmnx.graph_to_gdfs(graph)
        out_edges_gdf, out_intersections_gdf, nodes_in_boundary = analyze_boundary(graph, nodes_gdf, boundary)

        nodes_to_remove: list[int] = []
        # set the inner flag and mark nodes to delete
        logger.info("Adding the 'inner' field to nodes and removing dead-ends outside the boundary ...")
        for node in graph.nodes:
            if node in nodes_in_boundary:
                graph.nodes[node]["inner"] = True
                if graph.out_degree(node) == 0 or graph.in_degree(node) == 0:
                    nodes_to_remove.append(node)
            else:
                graph.nodes[node]["inner"] = False

        # remove the nodes_to_remove from the graph, nodes_gdf and edges_gdf
        for node in nodes_to_remove:
            graph.remove_node(node)
        nodes_gdf = cast(GeoDataFrame, nodes_gdf.drop(nodes_to_remove))

        # Remove edges where either the source (level 0) or target (level 1) node is in nodes_to_remove
        mask = edges_gdf.index.get_level_values(0).isin(nodes_to_remove) | edges_gdf.index.get_level_values(1).isin(
            nodes_to_remove
        )
        edges_gdf = cast(GeoDataFrame, edges_gdf.drop(cast(IndexLabel, edges_gdf[mask].index)))

        # without this, lists cause errors when saving to file
        nodes_gdf = stringify_nonnumeric_cols(nodes_gdf)
        edges_gdf = stringify_nonnumeric_cols(edges_gdf)

        nodes_gdf.to_file(self.gpkg_path, layer="nodes", driver="GPKG")
        edges_gdf.to_file(self.gpkg_path, layer="edges", driver="GPKG")
        boundaries_gdf: GeoDataFrame = GeoDataFrame(
            [{"geometry": boundary, "id": "inner"}, {"geometry": boundary_buff, "id": "outer"}], crs=graph.graph["crs"]
        )  # crs is "EPSG:4326"
        boundaries_gdf.to_file(self.gpkg_path, layer="boundaries", driver="GPKG")
        out_edges_gdf.to_file(self.gpkg_path, layer="out_edges", driver="GPKG")
        out_intersections_gdf.to_file(self.gpkg_path, layer="out_edges_intersections", driver="GPKG")

        # add essential edge attributes for routing before saving to graphml
        add_edge_bearings(graph)
        add_edge_speeds(graph)
        add_edge_travel_times(graph)

        osmnx.save_graphml(graph, self.graphml_path, gephi=False, encoding="utf-8")

        logger.info(f"Files {self.graphml_path} and {self.gpkg_path} have been successfully generated.")
