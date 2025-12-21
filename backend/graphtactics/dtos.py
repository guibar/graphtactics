"""
Data Transfer Objects (DTOs) for the API.
These Pydantic models handle validation and conversion to domain objects.
"""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from shapely.geometry import Point, mapping

from .adversary import TravelData
from .planner import Plan
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

    paths_to_njois: dict
    isochrone: dict
    paths_from_njois: dict

    @classmethod
    def from_domain(cls, travel_data: TravelData) -> "TravelDataResponse":
        return cls(
            paths_to_njois=cls._travel_data_to_past_paths_geojson(travel_data),
            isochrone=cls._travel_data_to_isochrone_geojson(travel_data),
            paths_from_njois=cls._travel_data_to_future_paths_geojson(travel_data),
        )

    @staticmethod
    def _travel_data_to_isochrone_geojson(travel_data: TravelData) -> dict[str, Any]:
        return to_feature_collection(
            [{"type": "Feature", "geometry": mapping(travel_data.get_isochrone()), "properties": {}}]
        )

    @staticmethod
    def _travel_data_to_future_paths_geojson(travel_data: TravelData) -> dict[str, Any]:
        features = []
        for en, nodes in travel_data.paths_to_e_nodes_future.items():
            line_string = travel_data.network.to_linestring(nodes)
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(line_string),
                    "properties": {"en": en},
                }
            )
        return to_feature_collection(features)

    @staticmethod
    def _travel_data_to_past_paths_geojson(travel_data: TravelData) -> dict[str, Any]:
        features = []
        for en, nodes in travel_data.paths_to_e_nodes_past.items():
            line_string = travel_data.network.to_linestring(nodes)
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(line_string),
                    "properties": {"en": en},
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
