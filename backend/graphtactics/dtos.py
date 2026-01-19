"""
Data Transfer Objects (DTOs) for the API.
These Pydantic models handle validation and conversion to domain objects.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from shapely import Polygon
from shapely.geometry import Point, mapping
from shapely.geometry.base import BaseGeometry

from .escape_model import EscapeModel
from .plan_geometry import PlanGeometry
from .planner import Plan
from .road_network import RoadNetwork
from .scenario import Scenario
from .vehicle import Vehicle


def to_feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap a list of GeoJSON Features into a FeatureCollection.

    Args:
        features: A list of feature dictionaries.

    Returns:
        A dictionary with "type": "FeatureCollection" and the "features" list.
    """
    return {"type": "FeatureCollection", "features": features}


def to_feature(geometry: Any, properties: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a GeoJSON Feature from a Shapely geometry.

    Args:
        geometry: A Shapely geometry object (Point, LineString, Polygon, etc.)
        properties: Optional properties dict for the feature.

    Returns:
        GeoJSON Feature dict.
    """
    return {
        "type": "Feature",
        "geometry": mapping(geometry),
        "properties": properties or {},
    }


def geometries_to_collection(
    geometries: Sequence[BaseGeometry | tuple[int, BaseGeometry]],
) -> dict[str, Any]:
    """Convert a list of Shapely geometries or (osmid, geometry) tuples to a GeoJSON FeatureCollection.

    Args:
        geometries: List of Shapely geometry objects or (osmid, geometry) tuples.

    Returns:
        GeoJSON FeatureCollection with geometry features
    """
    features: list[dict[str, Any]] = []
    for item in geometries:
        if isinstance(item, tuple):
            osmid, geom = item
            features.append(to_feature(geom, {"osmid": osmid}))
        else:
            features.append(to_feature(item))
    return to_feature_collection(features)


class PointDTO(BaseModel):
    """Simple spatial point representation for API transfer.

    Attributes:
        lat: Latitude in decimal degrees.
        lng: Longitude in decimal degrees.
    """

    lat: float = Field(..., description="Latitude coordinate (World Geodetic System 1984)")
    lng: float = Field(..., description="Longitude coordinate (World Geodetic System 1984)")

    def to_domain(self) -> Point:
        """Convert the DTO to a Shapely Geometry Point.

        Returns:
            A Point object using (longitude, latitude) order for Shapely.
        """
        return Point(self.lng, self.lat)

    @classmethod
    def from_domain(cls, point: Point) -> PointDTO:
        """Create a PointDTO from a Shapely Point.

        Args:
            point: The domain point object.

        Returns:
            A PointDTO with lat/lng extracted from the point's y and x coordinates.
        """
        return cls(lat=point.y, lng=point.x)


class VehicleDTO(BaseModel):
    """Data Transfer Object for individual police vehicles.

    Handles both incoming vehicle lists in scenarios and outgoing vehicle
    status in planning results.

    Attributes:
        id: Unique numeric identifier for the vehicle.
        position: Current spatial location of the vehicle.
        visible: UI flag to control visibility on the map.
        tooltip: Descriptive text shown in UI on hover.
        status: Numeric representation of the vehicle's current state.
    """

    id: int = Field(..., description="Unique vehicle identifier")
    position: PointDTO = Field(..., description="Current coordinates of the vehicle")
    visible: bool | None = Field(None, description="UI flag to toggle map visibility")
    tooltip: str | None = Field(None, description="Text for map tooltips/information panels")
    status: int | None = Field(None, description="Current state (e.g., ASSIGNABLE, ASSIGNED, UNAVAILABLE)")

    def to_domain(self, network: RoadNetwork) -> Vehicle:
        """Convert from DTO to Vehicle domain object (for input)."""
        return Vehicle(network, self.id, self.position.to_domain())

    @classmethod
    def from_domain(cls, vehicle: Vehicle, network: RoadNetwork) -> VehicleDTO:
        """Convert from Vehicle domain object to DTO (for output)."""
        position_json = PointDTO.from_domain(vehicle.point)
        return cls(
            id=vehicle.id,
            position=position_json,
            visible=True,
            tooltip=f"VID : {vehicle.id}",
            status=vehicle.status.value,
        )


class ScenarioDTO(BaseModel):
    """Payload representing a target to intercept and the available resources.

    Attributes:
        lkp: Last Known Position of the adversary.
        time_elapsed: Seconds since the adversary was at the LKP.
        vehicles: List of police vehicles currently in the network.
    """

    lkp: PointDTO
    time_elapsed: int = Field(..., description="Time elapsed in seconds since the adversary was last seen")
    vehicles: list[VehicleDTO]

    def to_domain(self, network: RoadNetwork) -> Scenario:
        """Convert the scenario payload into a Scenario domain object.

        This involves calculating the absolute 'time_of_incident' from the 'time_elapsed'.

        Args:
            network: The road network to associate the scenario with.

        Returns:
            A fully initialized Scenario object.
        """
        time_of_incident: datetime = datetime.now() - timedelta(seconds=self.time_elapsed)
        vehicles = {v.id: v.to_domain(network) for v in self.vehicles}
        origin_point: Point = self.lkp.to_domain()
        return Scenario(network, origin_point, time_of_incident, vehicles, self.time_elapsed)


class NetworkDTO(BaseModel):
    """Initial configuration data for a selected road network.

    Attributes:
        boundaries: GeoJSON FeatureCollection containing the inner and outer boundary polygons.
        origin_coords: Suggested starting center for the map view.
        escape_points: GeoJSON FeatureCollection of all predefined exit points in the network.
    """

    boundaries: dict[str, Any] = Field(
        ..., description="GeoJSON FeatureCollection: Boundary polygons for the valid area"
    )
    origin_coords: PointDTO = Field(..., description="Initial map center coordinates")
    escape_points: dict[str, Any] = Field(..., description="GeoJSON FeatureCollection: Location of all escape nodes")

    @staticmethod
    def escape_nodes_to_geojson(network: RoadNetwork) -> dict[str, Any]:
        """Convert escape nodes directly to GeoJSON FeatureCollection without using GeoDataFrame.

        Args:
            network: RoadNetwork instance containing escape nodes

        Returns:
            GeoJSON FeatureCollection with Point features for each escape node
        """
        features: list[dict[str, Any]] = [
            to_feature(network.node_to_point(node_id), {"osmid": node_id}) for node_id in network.escape_nodes
        ]
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
        return to_feature_collection(
            [
                to_feature(boundary, {"id": "inner"}),
                to_feature(boundary_buff, {"id": "outer"}),
            ]
        )

    @classmethod
    def from_domain(cls, network: RoadNetwork) -> NetworkDTO:
        """Create response DTO from RoadNetwork domain object.

        Args:
            network: RoadNetwork instance

        Returns:
            NetworkDTO with all initialization data
        """
        boundaries_json = cls.boundaries_to_geojson(network.boundary, network.boundary_buff)
        origin_coords_json = PointDTO.from_domain(network.pos_to_point(network.central_position))
        escape_points_json = cls.escape_nodes_to_geojson(network)

        return cls(
            boundaries=boundaries_json,
            origin_coords=origin_coords_json,
            escape_points=escape_points_json,
        )


class PlanGeometryDTO(BaseModel):
    """Collection of spatial layers representing the adversary analysis.

    This DTO groups various GeoJSON FeatureCollections that represent different
    aspects of potential escape routes and current coverage.

    Attributes:
        past_paths: Routes from the LKP to the Isochrone edge.
        isochrone: The boundary line representing where the adversary might be now.
        uncontrolled_paths: Future routes currently not covered by any vehicle.
        before_control_paths: Paths leading to an interception point.
        after_control_paths: Paths beyond an interception point (assumed safe).
        uncontrolled_escape_nodes: Escape nodes still reachable by the adversary.
        controlled_escape_nodes: Escape nodes successfully protected by the plan.
    """

    past_paths: dict[str, Any] = Field(
        ..., description="GeoJSON FeatureCollection: Paths already traveled by adversary"
    )
    isochrone: dict[str, Any] = Field(
        ..., description="GeoJSON Feature: Current frontier of adversary potential positions"
    )
    uncontrolled_paths: dict[str, Any] = Field(..., description="GeoJSON FeatureCollection: Vulnerable escape paths")
    before_control_paths: dict[str, Any] = Field(
        ..., description="GeoJSON FeatureCollection: Paths from isochrone to interception"
    )
    after_control_paths: dict[str, Any] = Field(
        ..., description="GeoJSON FeatureCollection: Secured paths behind interception points"
    )
    uncontrolled_escape_nodes: dict[str, Any] = Field(
        ..., description="GeoJSON FeatureCollection: Vulnerable exit points"
    )
    controlled_escape_nodes: dict[str, Any] = Field(..., description="GeoJSON FeatureCollection: Secured exit points")

    @classmethod
    def from_domain(cls, geometry: PlanGeometry) -> PlanGeometryDTO:
        """Construct the analysis payload from the computed PlanGeometry.

        Args:
            geometry: The PlanGeometry containing all categorized path segments and nodes.

        Returns:
            A PlanGeometryDTO with all layers formatted as GeoJSON.
        """
        linestrings = geometry.get_linestrings()

        # Prepare GeoJSON snippets for each analysis layer
        past_paths_json = geometries_to_collection(linestrings.get("past", []))
        isochrone_json = to_feature(geometry.get_isochrone())
        uncontrolled_paths_json = geometries_to_collection(linestrings.get("uncontrolled", []))
        before_control_paths_json = geometries_to_collection(linestrings.get("before_control", []))
        after_control_paths_json = geometries_to_collection(linestrings.get("after_control", []))
        uncontrolled_escape_nodes_json = geometries_to_collection(geometry.escape_nodes_uncovered)
        controlled_escape_nodes_json = geometries_to_collection(geometry.escape_nodes_covered)

        return cls(
            past_paths=past_paths_json,
            isochrone=isochrone_json,
            uncontrolled_paths=uncontrolled_paths_json,
            before_control_paths=before_control_paths_json,
            after_control_paths=after_control_paths_json,
            uncontrolled_escape_nodes=uncontrolled_escape_nodes_json,
            controlled_escape_nodes=controlled_escape_nodes_json,
        )


class PlanDTO(BaseModel):
    """The final result of the interception optimization.

    Attributes:
        origin: [lat, lng] of the starting point.
        vehicles: Updated list of vehicles with their status.
        escape_model: Visual layers for the adversary analysis.
        assignments: GeoJSON of vehicle movements to their targets.
        destinations: GeoJSON points of the interception locations.
        stats: Performance metrics for the plan.
    """

    origin: list[float] = Field(..., description="[Latitude, Longitude] of the adversary LKP")
    vehicles: list[VehicleDTO] = Field(..., description="List of participant vehicles and their final status")
    plan_geometry: PlanGeometryDTO = Field(..., description="The comprehensive escape analysis visualization")
    assignments: dict[str, Any] = Field(
        ..., description="GeoJSON FeatureCollection: Vehicle trajectories to assigned nodes"
    )
    destinations: dict[str, Any] = Field(
        ..., description="GeoJSON FeatureCollection: Points where interceptions will occur"
    )
    stats: dict[str, Any] = Field(..., description="Consolidated metrics from the EscapeModel and the solver")

    @classmethod
    def from_domain(
        cls, scenario: Scenario, plan: Plan, escape_model: EscapeModel, geometry: PlanGeometry, network: RoadNetwork
    ) -> PlanDTO:
        """
        Serialize the interception plan to a JSON-compatible dictionary.

        Args:
            scenario: The scenario containing adversary and vehicle information.
            plan: The plan containing vehicle assignments.
            escape_model: The escape model containing computed analysis.
            geometry: The PlanGeometry for isochrone and linestring visualization.
            network: The road network for computing point coordinates.

        Returns:
            A dictionary containing the full state of the plan, including origin,
            vehicles, isochrone, paths, assignments, and statistics.
        """
        lkp_point: Point = network.pos_to_point(scenario.adversary.lkp_position)

        # Prepare JSON-ready representations of the various plan components
        vehicles_json = [VehicleDTO.from_domain(v, network) for v in scenario.vehicles.values()]
        plan_geom_dto_json = PlanGeometryDTO.from_domain(geometry)
        assignments_json = cls.plan_assignments_to_geojson(plan)
        destinations_json = cls.plan_destinations_to_geojson(plan)
        stats_json: dict[str, Any] = {**escape_model.get_stats(), **plan.get_stats()}

        return cls(
            origin=[lkp_point.y, lkp_point.x],
            vehicles=vehicles_json,
            plan_geometry=plan_geom_dto_json,
            assignments=assignments_json,
            destinations=destinations_json,
            stats=stats_json,
        )

    @staticmethod
    def plan_assignments_to_geojson(plan: Plan) -> dict[str, Any]:
        """Convert optimized assignments into a GeoJSON FeatureCollection of trajectories.

        Each feature contains properties like video ID, travel time, and interception score.

        Args:
            plan: The computed optimal plan.

        Returns:
            A GeoJSON FeatureCollection of trajectories.
        """
        features = [
            to_feature(
                va.trajectory_geom,
                {
                    "vid": va.vehicle.id,
                    "origin": va.vehicle.position.u,  # pyright: ignore[reportOptionalMemberAccess]
                    "destination": va.destination_node,
                    "travel_time": va.time_to_dest,
                    "exp_waiting_time": int(va.adv_time_to_dest - va.time_to_dest),
                    "score": va.score,
                },
            )
            for va in plan.assignments
        ]
        return to_feature_collection(features)

    @staticmethod
    def plan_destinations_to_geojson(plan: Plan) -> dict[str, Any]:
        """Convert interception points into a GeoJSON FeatureCollection of points.

        Args:
            plan: The computed optimal plan.

        Returns:
            A GeoJSON FeatureCollection of destination nodes with associated vehicle IDs.
        """
        features: list[dict[str, Any]] = [
            to_feature(va.destination_point, {"vid": va.vehicle.id}) for va in plan.assignments
        ]
        return to_feature_collection(features)
