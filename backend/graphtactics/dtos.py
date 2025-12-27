"""
Data Transfer Objects (DTOs) for the API.
These Pydantic models handle validation and conversion to domain objects.
"""

from datetime import datetime, timedelta
from typing import Any, cast

from pydantic import BaseModel, Field
from shapely import Polygon
from shapely.geometry import LineString, Point, mapping

from .adversary import TravelData
from .planner import Plan
from .position import Position
from .road_network import RoadNetwork
from .scenario import Scenario
from .vehicle import Vehicle


def to_feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


class PointDTO(BaseModel):
    """DTO for Position input - expects lat/lng coordinates from frontend."""

    lat: float = Field(..., description="Latitude coordinate")
    lng: float = Field(..., description="Longitude coordinate")

    def to_domain(self) -> Point:
        """Convert to Position domain object."""
        return Point(self.lng, self.lat)  # Shapely uses (x, y) = (lng, lat)

    @classmethod
    def from_domain(cls, point: Point) -> "PointDTO":
        """Convert to PointDTO from Position domain object."""
        return cls(lat=point.y, lng=point.x)


class VehicleDTO(BaseModel):
    """DTO for Vehicle - handles both input and output serialization."""

    id: int = Field(..., description="Unique vehicle identifier")
    coordinates: PointDTO
    visible: bool | None = None
    tooltip: str | None = None
    status: int | None = None

    def to_domain(self, network: RoadNetwork) -> Vehicle:
        """Convert from DTO to Vehicle domain object (for input)."""
        return Vehicle.from_point(network, self.id, self.coordinates.to_domain(), on_node=False)

    @classmethod
    def from_domain(cls, vehicle: Vehicle) -> "VehicleDTO":
        """Convert from Vehicle domain object to DTO (for output)."""
        return cls(
            id=vehicle.id,
            coordinates=PointDTO(lat=vehicle.position.point.y, lng=vehicle.position.point.x),
            visible=True,
            tooltip=f"VID : {vehicle.id}",
            status=vehicle.status.value,
        )


class ScenarioDTO(BaseModel):
    """DTO for Scenario input."""

    origin_coords: PointDTO
    time_delta: int = Field(..., description="Time elapsed in seconds since observation")
    vehicles: list[VehicleDTO]

    def to_domain(self, network: RoadNetwork) -> Scenario:
        """Convert to Scenario domain object."""
        td: timedelta = timedelta(seconds=self.time_delta)
        vehicles = {v.id: v.to_domain(network) for v in self.vehicles}
        return Scenario(network, self.origin_coords.to_domain(), datetime.now() - td, vehicles, td)


class NetworkDTO(BaseModel):
    """DTO for network initialization data."""

    boundaries: dict[str, Any] = Field(..., description="GeoJSON FeatureCollection of boundary polygons")
    origin_coords: PointDTO
    escape_points: dict[str, Any] = Field(..., description="GeoJSON FeatureCollection of escape node points")

    @staticmethod
    def escape_nodes_to_geojson(network: RoadNetwork) -> dict[str, Any]:
        """Convert escape nodes directly to GeoJSON FeatureCollection without using GeoDataFrame.

        Args:
            network: RoadNetwork instance containing escape nodes

        Returns:
            GeoJSON FeatureCollection with Point features for each escape node
        """
        escape_nodes = network.get_escape_nodes()
        features = []
        for node_id in escape_nodes:
            point = network.node_to_point(node_id)
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(point),
                    "properties": {},
                }
            )
        return to_feature_collection(features)

    @staticmethod
    def boundaries_to_geojson(boundary: Polygon, boundary_buff: Polygon) -> dict[str, Any]:
        """Convert boundary polygons to GeoJSON FeatureCollection.

        Args:
            boundary: Inner boundary polygon
            boundary_buff: Outer buffered boundary polygon

        Returns:
            GeoJSON FeatureCollection with boundary features
        """
        features = [
            {
                "type": "Feature",
                "geometry": mapping(boundary),
                "properties": {"id": "inner"},
            },
            {
                "type": "Feature",
                "geometry": mapping(boundary_buff),
                "properties": {"id": "outer"},
            },
        ]
        return to_feature_collection(features)

    @classmethod
    def from_domain(cls, network: RoadNetwork) -> "NetworkDTO":
        """Create response DTO from RoadNetwork domain object.

        Args:
            network: RoadNetwork instance

        Returns:
            NetworkResponse with all initialization data
        """
        central_point = network.central_position.point

        return cls(
            boundaries=cls.boundaries_to_geojson(network.boundary, network.boundary_buff),
            origin_coords=PointDTO.from_domain(central_point),
            escape_points=cls.escape_nodes_to_geojson(network),
        )


class TravelDataDTO(BaseModel):
    """Response DTO for TravelData - serializes graph analysis to JSON."""

    past_paths: dict
    isochrone: dict
    future_paths: dict

    @classmethod
    def from_domain(cls, travel_data: TravelData) -> "TravelDataDTO":
        past_linestrings, future_linestrings = cls.past_and_future_paths_as_line_strings(travel_data)

        # Use past paths to create the isochrone polygon
        isochrone_polygon = travel_data.get_isochrone()

        return cls(
            past_paths=cls.linestrings_to_collection(past_linestrings),
            isochrone={"type": "Feature", "geometry": mapping(isochrone_polygon), "properties": {}},
            future_paths=cls.linestrings_to_collection(future_linestrings),
        )

    @staticmethod
    def past_and_future_paths_as_line_strings(travel_data: TravelData) -> tuple[list[LineString], list[LineString]]:
        """Helper method to get linestrings without converting to GeoJSON."""
        lines_past: list[LineString] = []
        lines_future: list[LineString] = []
        for en, nodes in travel_data.e_node_to_past_path.items():
            # the exact position is a Position object
            if isinstance(travel_data.exact_positions[en], Position):
                line_past = travel_data.network.to_linestring(
                    nodes,
                    pos_before=travel_data.lkp_position,
                    pos_after=cast(Position, travel_data.exact_positions[en]),
                )
            # the exact position is a Point object probably not on the network,
            # we just plot a straight line from the escape_node to the point
            else:
                point: Point = cast(Point, travel_data.exact_positions[en])
                line_past = LineString(list(travel_data.network.to_linestring(nodes).coords) + [(point.x, point.y)])
            lines_past.append(line_past)

        for en, nodes in travel_data.e_node_to_future_path.items():
            if isinstance(travel_data.exact_positions[en], Position):
                line_future = travel_data.network.to_linestring(
                    nodes, pos_before=cast(Position, travel_data.exact_positions[en])
                )
                lines_future.append(line_future)
            else:  # in this case, there is no future line
                assert not nodes
        return lines_past, lines_future

    @staticmethod
    def linestrings_to_collection(linestrings: list[LineString]) -> dict[str, Any]:
        features = []
        for line_string in linestrings:
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(line_string),
                    "properties": {},
                }
            )
        return to_feature_collection(features)


class PlanDTO(BaseModel):
    origin: list[float]
    vehicles: list[VehicleDTO]
    travel_data: TravelDataDTO
    affectations: dict
    destinations: dict
    stats: dict

    @classmethod
    def from_domain(cls, scenario: Scenario, plan: Plan) -> "PlanDTO":
        """
        Serialize the interception plan to a JSON-compatible dictionary.

        Returns:
            A dictionary containing the full state of the plan, including origin,
            vehicles, isochrone, paths, assignments, and statistics.
        """

        return cls(
            origin=[
                scenario.adversary.lkp_position.point.y,
                scenario.adversary.lkp_position.point.x,
            ],
            vehicles=[VehicleDTO.from_domain(v) for v in scenario.vehicles.values()],
            travel_data=TravelDataDTO.from_domain(scenario.adversary.travel_data),
            affectations=cls._plan_assignments_to_geojson(plan),
            destinations=cls._plan_destinations_to_geojson(plan),
            stats={**scenario.adversary.get_stats(), **plan.get_stats()},  # merge stats
        )

    @staticmethod
    def _plan_assignments_to_geojson(plan: Plan) -> dict[str, Any]:
        features = []
        for va in plan.assignments:
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(va.trajectory_geom),
                    "properties": {
                        "vid": va.vehicle.id,
                        "origin": va.vehicle.position.u,
                        "destination": va.destination_node,
                        "travel_time": va.time_to_dest,
                        "time_margin": va.adv_time_to_dest,
                        "score": va.score,
                    },
                }
            )
        return to_feature_collection(features)

    @staticmethod
    def _plan_destinations_to_geojson(plan: Plan) -> dict[str, Any]:
        features = []
        for va in plan.assignments:
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(va.destination_point),
                    "properties": {"vid": va.vehicle.id},
                }
            )
        return to_feature_collection(features)
