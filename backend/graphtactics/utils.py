import logging
from math import atan2
from pathlib import Path
from typing import TypedDict, cast

import numpy as np
import numpy.typing as npt
import pandas
from geopandas import GeoDataFrame, GeoSeries
from pyproj import Geod
from shapely import LineString, Point, ops
from shapely.geometry import Polygon

data_dir = Path(__file__).resolve().parent.parent / "data"
plans_dir = data_dir / "plans"

logger = logging.getLogger(__name__)


def merge_lines(line_list: list[LineString]) -> LineString:
    if line_list and all(
        len(line.coords) == 2 and line.coords[0] == line.coords[1] == line_list[0].coords[0] for line in line_list
    ):
        return line_list[0]
    return cast(LineString, ops.linemerge(line_list))


# stolen from osmnx.io
def stringify_nonnumeric_cols(gdf: GeoDataFrame) -> GeoDataFrame:
    """
    Make every non-numeric GeoDataFrame column (besides geometry) a string.

    This allows proper serializing via Fiona of GeoDataFrames with mixed types
    such as strings and ints in the same column.

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        gdf to stringify non-numeric columns of

    Returns
    -------
    gdf : geopandas.GeoDataFrame
        gdf with non-numeric columns stringified
    """
    # stringify every non-numeric column other than geometry column
    for col in (c for c in gdf.columns if c != "geometry"):
        if not pandas.api.types.is_numeric_dtype(gdf[col]):
            gdf[col] = gdf[col].fillna("").astype(str)  # pyright: ignore[reportUnknownMemberType]

    return gdf


def convert_bool_string(value: str | bool) -> bool:
    """
    Convert a "True" or "False" string literal to corresponding boolean type.

    This is necessary because Python will otherwise parse the string "False"
    to the boolean value True, that is, `bool("False") == True`. This function
    raises a ValueError if a value other than "True" or "False" is passed.

    If the value is already a boolean, this function just returns it, to
    accommodate usage when the value was originally inside a stringified list.

    Parameters
    ----------
    value : string {"True", "False"}
        the value to convert

    Returns
    -------
    bool
    """
    if value in {"True", "False"}:
        return value == "True"
    elif isinstance(value, bool):
        return value
    else:  # pragma: no cover
        raise ValueError(f'invalid literal for boolean: "{value}"')


def split_lines_by_points(lines: list[LineString], points: list[Point]) -> tuple[list[LineString], list[LineString]]:
    """
    Split a list of LineStrings at point locations.
    Returns two lists of the same size as the input:
    - The first list contains the first part of each LineString (before the split point).
    - The second list contains the second part of each LineString (after the split point).

    Uses snap before split to handle floating-point precision issues.
    If a line doesn't contain any of the points (within tolerance), the entire line
    goes into the first list and an empty LineString goes into the second list.
    """
    from shapely import MultiPoint
    from shapely.ops import split

    TOLERANCE = 1e-9  # Tolerance for snap

    first_parts: list[LineString] = []
    second_parts: list[LineString] = []

    multipoint = MultiPoint(points)

    for line in lines:
        # Snapping the line to the points will create a vertex at the point if it is close enough
        # This is necessary to handle floating-point precision issues
        snapped_line = ops.snap(line, multipoint, tolerance=TOLERANCE)

        result = split(snapped_line, multipoint)
        geoms = list(result.geoms)

        if len(geoms) == 1:
            # No split occurred, we put the entire line in the first list
            first_parts.append(cast(LineString, geoms[0]))
            # and an empty line in the second list
            second_parts.append(LineString())
        elif len(geoms) == 2:
            # Split into 2 parts
            first_parts.append(cast(LineString, geoms[0]))
            second_parts.append(cast(LineString, geoms[1]))
        else:
            # Multiple splits - take first and merge the rest
            first_parts.append(cast(LineString, geoms[0]))
            second_parts.append(cast(LineString, ops.linemerge([cast(LineString, g) for g in geoms[1:]])))
    return first_parts, second_parts


class PrincipalAxes(TypedDict):
    centroid: tuple[float, float]
    major_vector: tuple[float, float]
    minor_vector: tuple[float, float]
    eigenvalues: tuple[float, float]
    major_span: float
    minor_span: float
    major_axis: float
    minor_axis: float


def get_points_principal_axes(points: list[Point]) -> PrincipalAxes:
    """
    Calculate the principal axes of a polygon using PCA.
    Returns a PrincipalAxes TypedDict containing centroid, vectors, eigenvalues and spans.
    """
    coords: npt.NDArray[np.float64] = np.array([(p.x, p.y) for p in points])

    # Use unique vertices for PCA (skip last point if it duplicates the first, like in closed polygons)
    if len(coords) > 1 and np.array_equal(coords[-1], coords[0]):
        coords = coords[:-1]
    centroid_arr: npt.NDArray[np.float64] = np.mean(coords, axis=0)
    centered_coords: npt.NDArray[np.float64] = coords - centroid_arr

    # Calculate covariance matrix
    cov: npt.NDArray[np.float64] = np.cov(centered_coords, rowvar=False)

    # Get eigenvalues and eigenvectors
    # eigh returns them sorted by eigenvalue (ascending)
    # eigenvalues[0] is smallest (minor), eigenvalues[1] is largest (major)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    minor_vector: npt.NDArray[np.float64] = eigenvectors[:, 0]
    major_vector: npt.NDArray[np.float64] = eigenvectors[:, 1]

    # Project points onto axes to find span (half-length and half-width)
    proj_major: npt.NDArray[np.float64] = np.dot(centered_coords, major_vector)
    proj_minor: npt.NDArray[np.float64] = np.dot(centered_coords, minor_vector)

    major_span = float(np.max(np.abs(proj_major)))
    minor_span = float(np.max(np.abs(proj_minor)))

    # Spread is proportional to the square root of eigenvalues
    major_axis = np.sqrt(max(0, eigenvalues[1]))
    minor_axis = np.sqrt(max(0, eigenvalues[0]))

    return {
        "centroid": (float(centroid_arr[0]), float(centroid_arr[1])),
        "major_vector": (float(major_vector[0]), float(major_vector[1])),
        "minor_vector": (float(minor_vector[0]), float(minor_vector[1])),
        "eigenvalues": (float(eigenvalues[0]), float(eigenvalues[1])),
        "major_span": major_span,
        "minor_span": minor_span,
        "major_axis": major_axis,
        "minor_axis": minor_axis,
    }


def get_balanced_polygon(lat_long_points: list[Point], k: float = 1.0, max_ratio: float = 1.8) -> Polygon:
    """
    "Balances" a polygon by expanding its minor axis to match its major axis span.
    This makes elongated polygons more compact (closer to a circle/diamond).
    """

    projected_points = project_points(lat_long_points)

    axes = get_points_principal_axes(projected_points)
    centroid = np.array(axes["centroid"])

    minor_vector = np.array(axes["minor_vector"])
    major_span = axes["major_span"]

    if axes["minor_axis"] > 0 and axes["major_axis"] / axes["minor_axis"] < max_ratio:
        lat_lng_coords = np.array([(p.x, p.y) for p in lat_long_points])
        center_lat_lng: Point = Point(np.mean(lat_lng_coords, axis=0))
        lat_long_points.sort(key=lambda p: atan2(p.y - center_lat_lng.y, p.x - center_lat_lng.x))
        logger.info(f"Ratio is {axes['major_axis'] / axes['minor_axis']} -> returning sorted but unchanged polygon")
        return Polygon(lat_long_points)
    else:
        # Calculate two points along the minor axis that match the major axis span
        p1 = centroid + minor_vector * major_span * k
        p2 = centroid - minor_vector * major_span * k

        # Create a new polygon as the convex hull of original points + these 2 points
        projected_points = [*projected_points, Point(p1), Point(p2)]
        projected_points.sort(key=lambda p: atan2(p.y - centroid[1], p.x - centroid[0]))
        unprojected_points = unproject_points(projected_points)

        return Polygon(unprojected_points)


def project_points(points: list[Point]) -> list[Point]:
    """Project a lat/long polygon to a metric CRS (UTM)."""
    gs = GeoSeries(points, crs="EPSG:4326")
    return cast(list[Point], list(gs.to_crs("EPSG:2154")))


def unproject_points(points: list[Point]) -> list[Point]:
    """Unproject points from a metric CRS back to lat/long (EPSG:4326)."""
    gs = GeoSeries(points, crs="EPSG:2154")
    return cast(list[Point], list(gs.to_crs("EPSG:4326")))


def distance(p1: Point, p2: Point) -> float:
    line_string = LineString([p1, p2])
    geod = Geod(ellps="WGS84")
    return cast(float, geod.geometry_length(line_string.coords))  # pyright: ignore[reportUnknownMemberType]
