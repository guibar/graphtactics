import os
from datetime import datetime, timedelta
from logging import getLogger

from geopandas import GeoDataFrame, read_file
from pandas import Index
from shapely import LineString, unary_union
from shapely.geometry import Point

from .adversary import TravelData
from .planner import Plan
from .road_network import RoadNetwork
from .scenario import Scenario
from .utils import plans_dir
from .vehicle import Vehicle

logger = getLogger(__name__)


class Serializer:
    """
    Repository for persisting and loading Scenario objects.
    """

    def __init__(
        self,
        network: RoadNetwork,
        scenario: Scenario | None = None,
        plan: Plan | None = None,
        filepath: str | None = None,
    ):
        if filepath:
            if not filepath.endswith(".gpkg"):
                filepath = filepath + ".gpkg"
        elif scenario:
            filepath = datetime.now().isoformat() + ".gpkg"
        else:
            filepath = "default.gpkg"

        self.filepath: str = os.path.join(plans_dir, filepath)
        self.network: RoadNetwork = network
        self.scenario = scenario
        self.plan = plan

        logger.info("Data will be saved in {}".format(filepath))

    def save(self) -> None:
        if not self.scenario:
            logger.warning("No scenario provided to save.")
            return

        self.save_scenario()
        self.save_adversary()
        self.save_vehicles()
        self.save_travel_data()
        self.save_candidate_nodes()
        if self.plan:
            self.save_plan()

    def save_scenario(self) -> None:
        if not self.scenario:
            return
        GeoDataFrame(
            [
                {
                    "time_elapsed_seconds": self.scenario.time_elapsed.total_seconds(),
                    "geometry": self.scenario.adversary.lkp_position.init_point,
                },
                {
                    "graph_name": self.scenario.graph_name,
                    "geometry": self.scenario.adversary.lkp_position.point,
                },
            ],
            crs="EPSG:4326",
        ).to_file(self.filepath, layer="scenario", driver="GPKG")

    def save_adversary(self) -> None:
        if not self.scenario:
            return
        adversary = self.scenario.adversary
        GeoDataFrame(
            [
                {
                    "time_lkp": adversary.last_time_seen.isoformat(),
                    "geometry": adversary.lkp_position.init_point,
                },
                {
                    "time_lkp": adversary.last_time_seen.isoformat(),
                    "geometry": adversary.lkp_position.point,
                },
            ],
            crs="EPSG:4326",
        ).to_file(self.filepath, layer="adversary", driver="GPKG")

    def save_vehicles(self) -> None:
        if not self.scenario:
            return
        vehicles = self.scenario.vehicles
        gdf = GeoDataFrame(
            [
                [veh.id, veh.position.u, veh.position.v, veh.position.ec, veh.position.point]
                for veh in vehicles.values()
            ],
            columns=Index(["id", "u", "v", "edge_cursor", "geometry"]),
            crs="EPSG:4326",
        )
        gdf.set_index("id", inplace=True)
        gdf.to_file(self.filepath, layer="vehicles", driver="GPKG")

    def save_travel_data(self) -> None:
        if not self.scenario:
            return
        travel_data = self.scenario.adversary.travel_data
        self.travel_data_to_isochrone_gdf(travel_data).to_file(self.filepath, layer="td_isochrone", driver="GPKG")
        self.travel_data_to_past_paths_gdf(travel_data).to_file(self.filepath, layer="td_past_paths", driver="GPKG")
        self.travel_data_to_future_paths_gdf(travel_data).to_file(self.filepath, layer="td_future_paths", driver="GPKG")
        self.travel_data_to_full_paths_gdf(travel_data).to_file(self.filepath, layer="td_full_paths", driver="GPKG")

    def travel_data_to_isochrone_gdf(self, travel_data: TravelData) -> GeoDataFrame:
        point_list: list[Point] = [p if isinstance(p, Point) else p.point for p in travel_data.exact_positions.values()]
        return GeoDataFrame(
            [{"geometry": unary_union(point_list).convex_hull}],
            crs="EPSG:4326",
        )

    def travel_data_to_future_paths_gdf(self, travel_data: TravelData) -> GeoDataFrame:
        return GeoDataFrame(
            [
                [
                    en,
                    self.network.to_linestring(travel_data.e_node_to_future_path[en])
                    if travel_data.e_node_to_future_path[en]
                    else LineString(),
                ]
                for en in travel_data.e_node_to_future_path.keys()
            ],
            columns=Index(["en", "geometry"]),
            crs="EPSG:4326",
        )

    def travel_data_to_past_paths_gdf(self, travel_data: TravelData) -> GeoDataFrame:
        return GeoDataFrame(
            [
                [
                    en,
                    self.network.to_linestring(travel_data.e_node_to_past_path[en]),
                ]
                for en in travel_data.e_node_to_past_path.keys()
            ],
            columns=Index(["en", "geometry"]),
            crs="EPSG:4326",
        )

    def travel_data_to_full_paths_gdf(self, travel_data: TravelData) -> GeoDataFrame:
        return GeoDataFrame(
            [
                [
                    en,
                    self.network.to_linestring(
                        travel_data.e_node_to_past_path[en] + travel_data.e_node_to_future_path[en]
                    ),
                ]
                for en in travel_data.e_node_to_past_path.keys()
            ],
            columns=Index(["en", "geometry"]),
            crs="EPSG:4326",
        )

    def save_candidate_nodes(self) -> None:
        if not self.scenario:
            return
        node_ids = list(self.scenario.adversary.candidate_nodes.node_scores.keys())
        scores = list(self.scenario.adversary.candidate_nodes.node_scores.values())
        nodes_gdf = self.network.get_node_list_as_gdf(node_ids)
        nodes_gdf["score"] = scores
        nodes_gdf.to_file(self.filepath, layer="candidate_nodes", driver="GPKG")

    def save_plan(self) -> None:
        if not self.plan:
            return
        move_list = [
            [
                va.vehicle.id,
                va.trajectory_geom,
                va.vehicle.position.u,
                va.destination_node,
                va.time_to_dest,
                va.adv_time_to_dest,
                va.score,
            ]
            for va in self.plan.assignments
        ]
        GeoDataFrame(
            move_list,
            crs="EPSG:4326",
            columns=Index(
                [
                    "vid",
                    "geometry",
                    "origin",
                    "destination",
                    "travel_time",
                    "time_margin",
                    "score",
                ]
            ),
        ).to_file(self.filepath, layer="plan", driver="GPKG")

    @staticmethod
    def load_scenario(network: RoadNetwork, filepath: str) -> "Scenario":
        """
        Load a Scenario from a GeoPackage file.

        Args:
            network: RoadNetwork instance used to reconstruct objects.
            filepath: Path to the GeoPackage file.

        Returns:
            An instance of Scenario initialized with data from the file.
        """
        if not filepath.endswith(".gpkg"):
            filepath = filepath + ".gpkg"

        # Check if filepath exists directly or inside plans_dir
        if not os.path.exists(filepath):
            filepath = os.path.join(plans_dir, filepath)

        scenario_gdf: GeoDataFrame = read_file(filepath, layer="scenario")
        adversary_gdf: GeoDataFrame = read_file(filepath, layer="adversary")
        all_vehicles_gdf: GeoDataFrame = read_file(filepath, layer="vehicles")
        veh = {
            row.id: Vehicle(network, row.id, network.create_position_from_point(row.geometry, on_node=True))
            for index, row in all_vehicles_gdf.iterrows()
        }
        return Scenario(
            network,
            Point(scenario_gdf.at[1, "geometry"]),  # type: ignore
            datetime.fromisoformat(str(adversary_gdf.at[0, "time_lkp"])),
            veh,
            timedelta(seconds=float(str(scenario_gdf.at[0, "time_elapsed_seconds"]))),
        )
