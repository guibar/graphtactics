import json
import logging
import os
from collections import OrderedDict
from math import atan2
from pathlib import Path
from typing import cast

import pandas
from geopandas import GeoDataFrame

# osmnx 1.9.4: functions moved to _overpass module
from osmnx._overpass import _make_overpass_polygon_coord_strs
from osmnx._overpass import _overpass_request as overpass_request
from shapely.geometry import Point, Polygon

data_dir = Path(__file__).resolve().parent.parent / "data"
plans_dir = data_dir / "plans"

logger = logging.getLogger(__name__)


def convert_txt_to_gpkg(txt_file):
    # file_header = ['vid', 'timestamp', 'x', 'y']
    df = pandas.read_csv(txt_file, delimiter="\t", header=0, dtype={0: "int32", 1: "str", 2: "float64", 3: "float64"})

    gdf = GeoDataFrame(df.drop(["x", "y"], axis=1), crs="EPSG:4326", geometry=[Point(xy) for xy in zip(df.x, df.y)])

    gdf.to_file(os.path.splitext(txt_file)[0] + ".gpkg", driver="GPKG")


# stolen from osmnx.io
def stringify_nonnumeric_cols(gdf):
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
    for col in (c for c in gdf.columns if not c == "geometry"):
        if not pandas.api.types.is_numeric_dtype(gdf[col]):
            gdf[col] = gdf[col].fillna("").astype(str)

    return gdf


def convert_bool_string(value):
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


def get_star_polygon(points_gdf: GeoDataFrame) -> Polygon:
    if len(points_gdf) < 3:
        return Polygon()
    point_list: list[Point] = cast(list[Point], [p for p in points_gdf.geometry])
    cx, cy = sum(p.x for p in point_list) / len(point_list), sum(p.y for p in point_list) / len(point_list)
    point_list.sort(key=lambda p: atan2(p.y - cy, p.x - cx))
    return Polygon(point_list)


def convert_here_json_isochrone_to_gpkg(here_isochrone_json_file) -> None:
    if not here_isochrone_json_file.endswith(".json"):
        logger.warning(here_isochrone_json_file + " is not a json file")
        return

    gpkg_filepath = here_isochrone_json_file[:-4] + "gpkg"
    logger.info("Will save result to " + gpkg_filepath)

    with open(here_isochrone_json_file) as json_file:
        here_isochrone_json = json.load(json_file)

    coords_lat_lng_str: list[str] = here_isochrone_json["response"]["isoline"][0]["component"][0]["shape"]

    # convert "lat,long" into (long,lat), [::-1] inverts the tuple order
    def convert_coords(coords_as_str: str) -> tuple[float, ...]:
        return tuple(map(float, coords_as_str.split(",")))[::-1]

    polygon = Polygon(list(map(convert_coords, coords_lat_lng_str)))
    isochrone_as_gdf: GeoDataFrame = GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    isochrone_as_gdf.to_file(gpkg_filepath, driver="GPKG")


# TODO: Tolls are not included in the graph, at least not with current options. We would probably
# get them with simplify=False, but with other nodes we are not interested in. We should
# test to see what nodes 'simplify=False' adds. Maybe they are interesting nodes for us.
# If 'simplify=False' does not solve the problem, we will have to reintroduce toll nodes
# in the graph ourselves. Thus, we will have to modify this function to know between
# which graph nodes the toll is inserted.
# To be done at the same time as we put bridges on expressways as fictitious nodes.
def get_tolls(polygon: Polygon) -> dict[int, dict]:
    # this breaks down the polygon in pieces, wonder if it is necessary ...
    polygon_coord_strs = _make_overpass_polygon_coord_strs(polygon)
    response_jsons = []
    for polygon_coord_str in polygon_coord_strs:
        overpass_query = f"[out:json];(node['barrier'='toll_booth'](poly:'{polygon_coord_str}');>;);out;"
        response_json = overpass_request(data=OrderedDict([("data", overpass_query)]))
        response_jsons.append(response_json)

    return {node["id"]: node for response_json in response_jsons for node in response_json["elements"]}


def edge_quantifier(edge_dict: dict[str, str]) -> int:
    """
    Assign an integer ranking to an edge based on its highway type.

    Args:
        edge_dict (Dict[str, str]): Dictionary of edge attributes, must include 'highway'.

    Returns:
        int: Integer ranking of the highway type for the edge.
    """
    return highway_value_to_int(edge_dict["highway"])


def highway_value_to_int(hw_value: list[str] | str) -> int:
    """
    Convert the value of the highway tag from an edge to an integer ranking.
    The value can be a string or list of strings.
    Many OSM highway tags include a suffix after an underscore (e.g., 'tertiary_link', 'motorway_link').
    The base type (before the underscore) is used for ranking, so 'tertiary_link' is treated as 'tertiary'.
    If the value is a list, returns the highest-ranked base type.
    If the value is a string, returns the base type (before any underscore).

    Example:
        hw_value_to_int('tertiary_link') -> 2  (same as 'tertiary')
        hw_value_to_int(['secondary_link', 'tertiary'])  -> 3 (secondary > tertiary)
        cf highway_tag_as_int for the ranking dictionary.
    Args:
        hw_value (Union[List[str], str]): Highway type(s) as a string or list of strings.

    Returns:
        int: Integer ranking for the highway type, or -1 if not recognized.
    """
    highway_tag_as_int = dict(unclassified=0, residential=1, tertiary=2, secondary=3, primary=4, trunk=5, motorway=6)

    if isinstance(hw_value, list):
        base_type = max([elem.split("_")[0] for elem in hw_value], key=lambda tag: highway_tag_as_int.get(tag, 0))
    else:
        base_type = hw_value.split("_")[0]
    return highway_tag_as_int.get(base_type, -1)
