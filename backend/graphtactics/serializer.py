from __future__ import annotations

import os
from datetime import datetime
from logging import getLogger

from geopandas import GeoDataFrame, read_file  # pyright: ignore[reportUnknownVariableType]
from pandas import Index
from shapely.geometry import Point
from shapely.geometry.linestring import LineString

from graphtactics.adversary import Adversary
from graphtactics.plan_geometry import PlanGeometry
from graphtactics.position import Position
from graphtactics.scenario import Scenario

from .planner import Plan
from .road_network import RoadNetwork
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
        geometry: PlanGeometry | None = None,
        filepath: str | None = None,
    ) -> None:
        if filepath:
            if not filepath.endswith(".gpkg"):
                filepath = filepath + ".gpkg"
        elif scenario:
            filepath = datetime.now().isoformat() + ".gpkg"
        else:
            filepath = "default.gpkg"

        self.filepath: str = os.path.join(plans_dir, filepath)
        self.network: RoadNetwork = network
        self.scenario: Scenario | None = scenario
        self.plan: Plan | None = plan
        self.geometry: PlanGeometry | None = geometry

        logger.info(f"Data will be saved in {filepath}")

    def save(self) -> None:
        if not self.scenario:
            logger.warning("No scenario provided to save.")
            return

        self.save_scenario()
        self.save_adversary()
        self.save_vehicles()
        self.save_plan_geometries()
        self.save_plan()

    def save_scenario(self) -> None:
        if not self.scenario:
            return
        lkp_position = self.scenario.adversary.lkp_position
        GeoDataFrame(
            [
                {
                    "time_elapsed_seconds": self.scenario.time_elapsed,
                    "geometry": lkp_position.init_point,
                },
                {
                    "graph_name": self.scenario.graph_name,
                    "geometry": self.network.pos_to_point(lkp_position),
                },
            ],
            crs="EPSG:4326",
        ).to_file(self.filepath, layer="scenario", driver="GPKG")  # pyright: ignore[reportUnknownMemberType]

    def save_adversary(self) -> None:
        if not self.scenario:
            return
        adversary: Adversary = self.scenario.adversary
        lkp_position: Position = adversary.lkp_position
        GeoDataFrame(
            [
                {
                    "time_lkp": adversary.last_time_seen.isoformat(),
                    "geometry": lkp_position.init_point,
                },
                {
                    "time_lkp": adversary.last_time_seen.isoformat(),
                    "geometry": self.network.pos_to_point(lkp_position),
                },
            ],
            crs="EPSG:4326",
        ).to_file(self.filepath, layer="adversary", driver="GPKG")  # pyright: ignore[reportUnknownMemberType]

    def save_vehicles(self) -> None:
        if not self.scenario:
            return
        vehicles = self.scenario.vehicles
        gdf: GeoDataFrame = GeoDataFrame(
            data=[[veh.id, veh.point] for veh in vehicles.values()],
            columns=Index(["id", "geometry"]),
            crs="EPSG:4326",
        )
        gdf.set_index("id", inplace=True)
        gdf.to_file(self.filepath, layer="vehicles", driver="GPKG")  # pyright: ignore[reportUnknownMemberType]

    @staticmethod
    def points_to_gdf(points: list[tuple[int, Point]]) -> GeoDataFrame:
        """Create a GeoDataFrame from a list of Point geometries.

        Returns an empty GeoDataFrame with the correct schema if the list is empty.
        """
        if not points:
            return GeoDataFrame({"geometry": []}, crs="EPSG:4326")
        return GeoDataFrame(
            {"osmid": [id_pt[0] for id_pt in points], "geometry": [id_pt[1] for id_pt in points]}, crs="EPSG:4326"
        )

    def save_plan_geometries(self) -> None:
        if self.geometry is None:
            return
        paths_sets: dict[str, list[LineString]] = self.geometry.get_linestrings()

        GeoDataFrame(
            [{"geometry": self.geometry.get_isochrone()}],
            crs="EPSG:4326",
        ).to_file(self.filepath, layer="em_isochrone", driver="GPKG")  # pyright: ignore[reportUnknownMemberType]

        self.points_to_gdf(self.geometry.njois).to_file(  # pyright: ignore[reportUnknownMemberType]
            self.filepath, layer="em_njois", driver="GPKG"
        )

        self.points_to_gdf(self.geometry.escape_nodes_covered).to_file(  # pyright: ignore[reportUnknownMemberType]
            self.filepath, layer="em_ens_covered", driver="GPKG"
        )

        self.points_to_gdf(self.geometry.escape_nodes_uncovered).to_file(  # pyright: ignore[reportUnknownMemberType]
            self.filepath, layer="em_ens_uncovered", driver="GPKG"
        )

        GeoDataFrame(
            paths_sets["past"],
            columns=Index(["geometry"]),
            crs="EPSG:4326",
        ).to_file(self.filepath, layer="em_past_paths", driver="GPKG")  # pyright: ignore[reportUnknownMemberType]

        GeoDataFrame(
            paths_sets["uncontrolled"],
            columns=Index(["geometry"]),
            crs="EPSG:4326",
        ).to_file(self.filepath, layer="em_uncontrolled_paths", driver="GPKG")  # pyright: ignore[reportUnknownMemberType]

        GeoDataFrame(
            paths_sets["before_control"],
            columns=Index(["geometry"]),
            crs="EPSG:4326",
        ).to_file(self.filepath, layer="em_before_control_paths", driver="GPKG")  # pyright: ignore[reportUnknownMemberType]
        GeoDataFrame(
            paths_sets["after_control"],
            columns=Index(["geometry"]),
            crs="EPSG:4326",
        ).to_file(self.filepath, layer="em_after_control_paths", driver="GPKG")  # pyright: ignore[reportUnknownMemberType]

    def save_plan(self) -> None:
        if self.plan is None:
            return

        move_list = [  # pyright: ignore[reportUnknownVariableType]
            [
                va.vehicle.id,
                va.trajectory_geom,
                va.vehicle.position.u,  # pyright: ignore[reportOptionalMemberAccess]
                va.destination_node,
                va.time_to_dest,
                va.adv_time_to_dest,
                va.score,
            ]
            for va in self.plan.assignments
        ]
        GeoDataFrame(  # pyright: ignore[reportUnknownMemberType]
            move_list,  # pyright: ignore[reportUnknownArgumentType]
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
    def load_scenario(network: RoadNetwork, filepath: str) -> Scenario:
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

        scenario_gdf: GeoDataFrame = read_file(filepath, layer="scenario")  # pyright: ignore[reportUnknownVariableType]
        adversary_gdf: GeoDataFrame = read_file(filepath, layer="adversary")  # pyright: ignore[reportUnknownVariableType]
        all_vehicles_gdf: GeoDataFrame = read_file(filepath, layer="vehicles")  # pyright: ignore[reportUnknownVariableType]
        veh = {  # pyright: ignore[reportUnknownVariableType]
            row.id: Vehicle(network, row.id, row.geometry)
            for index, row in all_vehicles_gdf.iterrows()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        }
        return Scenario(
            network,
            Point(scenario_gdf.at[1, "geometry"]),  # type: ignore # pyright: ignore[reportUnknownMemberType]
            datetime.fromisoformat(str(adversary_gdf.at[0, "time_lkp"])),  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
            veh,  # pyright: ignore[reportUnknownArgumentType]
            int(scenario_gdf.at[0, "time_elapsed_seconds"]),  # pyright: ignore[reportArgumentType, reportUnknownArgumentType, reportUnknownMemberType]
        )
