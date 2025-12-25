"""
Data Transfer Objects (DTOs) for the API.
These Pydantic models handle validation and conversion to domain objects.
"""

from datetime import datetime, timedelta
from typing import Any, cast

from pydantic import BaseModel, Field
from shapely import Polygon, ops, unary_union
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


class VehicleDTO(BaseModel):
    """DTO for Vehicle input."""

    id: int = Field(..., description="Unique vehicle identifier")
    lat_lng: PointDTO

    def to_domain(self, network: RoadNetwork) -> Vehicle:
        """Convert to Vehicle domain object."""
        return Vehicle.from_point(network, self.id, self.lat_lng.to_domain(), on_node=True)


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


# Response DTOs (for serializing domain objects to JSON)


class NetworkResponse(BaseModel):
    """Response DTO for network initialization data."""

    boundaries: dict[str, Any] = Field(..., description="GeoJSON FeatureCollection of boundary polygons")
    origin_coords: dict[str, float] = Field(..., description="Central point coordinates (lat/lng)")
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
    def from_domain(cls, network: RoadNetwork) -> "NetworkResponse":
        """Create response DTO from RoadNetwork domain object.

        Args:
            network: RoadNetwork instance

        Returns:
            NetworkResponse with all initialization data
        """
        central_point = network.central_position.point

        return cls(
            boundaries=cls.boundaries_to_geojson(network.boundary, network.boundary_buff),
            origin_coords={"lat": central_point.y, "lng": central_point.x},
            escape_points=cls.escape_nodes_to_geojson(network),
        )


class VehicleResponse(BaseModel):
    """Response DTO for Vehicle - serializes domain Vehicle to JSON."""

    id: int
    position: PointDTO
    visible: bool
    tooltip: str
    status: int

    @classmethod
    def from_domain(cls, vehicle: Vehicle) -> "VehicleResponse":
        """Create response DTO from domain Vehicle."""
        return cls(
            id=vehicle.id,
            position=PointDTO(lat=vehicle.position.point.y, lng=vehicle.position.point.x),
            visible=True,
            tooltip=f"VID : {vehicle.id}",
            status=vehicle.status.value,
        )


class TravelDataResponse(BaseModel):
    """Response DTO for TravelData - serializes graph analysis to JSON."""

    past_paths: dict
    isochrone: dict
    future_paths: dict

    @classmethod
    def from_domain(cls, travel_data: TravelData) -> "TravelDataResponse":
        past_linestrings, future_linestrings = cls.past_and_future_paths_as_line_strings(travel_data)

        # Use past paths to create the isochrone polygon
        isochrone_polygon = cast(Polygon, unary_union(past_linestrings).convex_hull)

        return cls(
            past_paths=cls.linestrings_to_collection(past_linestrings),
            isochrone={"type": "Feature", "geometry": mapping(isochrone_polygon), "properties": {}},
            future_paths=cls.linestrings_to_collection(future_linestrings),
        )

    @staticmethod
    def past_and_future_paths_as_line_strings(travel_data: TravelData) -> tuple[list[LineString], list[LineString]]:
        lines_past: list[LineString] = []
        lines_future: list[LineString] = []
        """Helper method to get linestrings without converting to GeoJSON."""
        for en, nodes in travel_data.e_node_to_past_path.items():
            line_past: LineString = travel_data.network.to_linestring(nodes)
            if isinstance(travel_data.exact_positions[en], Position):
                position: Position = cast(Position, travel_data.exact_positions[en])
                from_u_geom = travel_data.network.u_to_position_as_ls(position.to_edge_ref())
                line_past = cast(LineString, ops.linemerge([line_past, from_u_geom]))
            else:
                point: Point = cast(Point, travel_data.exact_positions[en])
                line_past = LineString(list(line_past.coords) + [(point.x, point.y)])
            lines_past.append(line_past)

        for en, nodes in travel_data.e_node_to_future_path.items():
            if isinstance(travel_data.exact_positions[en], Position):
                line_future: LineString = travel_data.network.to_linestring(nodes)
                position = cast(Position, travel_data.exact_positions[en])
                to_v_geom = travel_data.network.v_to_position_as_ls(position.to_edge_ref())
                line_future = cast(LineString, ops.linemerge([to_v_geom, line_future]))
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


class PlanResponse(BaseModel):
    origin: list[float]
    vehicles: list[VehicleResponse]
    travel_data: TravelDataResponse
    affectations: dict
    destinations: dict
    stats: dict

    @classmethod
    def from_domain(cls, scenario: Scenario, plan: Plan) -> "PlanResponse":
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
            vehicles=[VehicleResponse.from_domain(v) for v in scenario.vehicles.values()],
            travel_data=TravelDataResponse.from_domain(scenario.adversary.travel_data),
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
