from geopandas import GeoDataFrame
from shapely.geometry import Polygon

from graphtactics.road_network_factory import boundary_from_name

boundary: Polygon = boundary_from_name("90")
gdf: GeoDataFrame = GeoDataFrame(
    [{"geometry": boundary.exterior}],
    crs="EPSG:4326",
)


gdf.to_file("test.gpkg", layer="tt", geometry_type="LineString", driver="GPKG")
