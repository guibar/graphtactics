"""Unit tests for DTO serialization."""

from datetime import datetime
from typing import Any

import pytest

from graphtactics.dtos import PlanDTO, geometries_to_collection
from graphtactics.plan_geometry import PlanGeometry
from graphtactics.planner import Plan, Planner
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_d2():
    """Medium test network for DTO tests."""
    factory = RoadNetworkFactory()
    return factory.create("d2")


@pytest.fixture
def sample_plan_dto(road_network_d2: RoadNetwork) -> PlanDTO:
    """Create a PlanDTO for testing."""
    network = road_network_d2
    lk_point = network.pos_to_point(network.central_position)
    last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
    vehicles = Vehicle.get_random_vehicles(network, 3, seed=123)
    time_elapsed = 300

    scenario = Scenario(network, lk_point, last_time_seen, vehicles, time_elapsed)
    planner = Planner(network, scenario)
    plan: Plan = planner.plan_interception()

    plan_geometry = PlanGeometry(planner.escape_model, network)
    return PlanDTO.from_domain(scenario, plan, planner.escape_model, plan_geometry, network)


class TestPlanDTOCreation:
    """Test PlanDTO creation from domain objects."""

    def test_plan_dto_from_domain(self, sample_plan_dto: PlanDTO):
        """Test creating PlanDTO from domain objects."""
        assert sample_plan_dto is not None
        assert isinstance(sample_plan_dto, PlanDTO)

    def test_plan_dto_has_required_fields(self, sample_plan_dto: PlanDTO):
        """Test that PlanDTO has all required fields."""
        assert hasattr(sample_plan_dto, "origin")
        assert hasattr(sample_plan_dto, "vehicles")
        assert hasattr(sample_plan_dto, "assignments")
        assert hasattr(sample_plan_dto, "destinations")
        assert hasattr(sample_plan_dto, "stats")
        assert hasattr(sample_plan_dto, "plan_geometry")


class TestPlanDTOSerialization:
    """Test PlanDTO serialization to dict."""

    def test_plan_dto_model_dump(self, sample_plan_dto: PlanDTO):
        """Test serializing PlanDTO to dictionary."""
        payload = sample_plan_dto.model_dump()

        assert isinstance(payload, dict)
        assert "origin" in payload
        assert "vehicles" in payload
        assert "assignments" in payload
        assert "destinations" in payload
        assert "stats" in payload
        assert "plan_geometry" in payload

    def test_plan_dto_origin_structure(self, sample_plan_dto: PlanDTO):
        """Test that origin has correct structure."""
        payload = sample_plan_dto.model_dump()
        origin: list[Any] = payload["origin"]

        # Origin is a list [lat, lng]
        assert isinstance(origin, list)
        assert len(origin) == 2
        assert isinstance(origin[0], (int, float))  # latitude
        assert isinstance(origin[1], (int, float))  # longitude

    def test_plan_dto_vehicles_structure(self, sample_plan_dto: PlanDTO):
        """Test that vehicles has correct structure."""
        payload = sample_plan_dto.model_dump()
        vehicles: list[dict[str, Any]] = payload["vehicles"]

        # Vehicles is a list of vehicle DTOs
        assert isinstance(vehicles, list)
        # Each vehicle should have expected fields
        if len(vehicles) > 0:
            vehicle: dict[str, Any] = vehicles[0]
            assert "id" in vehicle
            assert "position" in vehicle

    def test_plan_dto_assignments_structure(self, sample_plan_dto: PlanDTO):
        """Test that assignments has correct GeoJSON structure."""
        payload = sample_plan_dto.model_dump()
        assignments = payload["assignments"]

        assert isinstance(assignments, dict)
        assert "type" in assignments
        assert assignments["type"] == "FeatureCollection"
        assert "features" in assignments
        assert isinstance(assignments["features"], list)

    def test_plan_dto_stats_structure(self, sample_plan_dto: PlanDTO):
        """Test that stats has correct structure."""
        payload = sample_plan_dto.model_dump()
        stats: dict[str, Any] = payload["stats"]

        assert isinstance(stats, dict)
        # Stats should contain various metrics
        assert len(stats) > 0


class TestLinestringToCollection:
    """Test linestrings_to_collection helper function."""

    def test_empty_linestrings_list(self):
        """Test converting empty list of linestrings."""
        result = geometries_to_collection([])

        assert isinstance(result, dict)
        assert result["type"] == "FeatureCollection"
        assert result["features"] == []

    def test_single_linestring(self, road_network_d2: RoadNetwork):
        """Test converting a single linestring."""
        # Create a simple linestring from two points
        from shapely.geometry import LineString

        p1 = road_network_d2.pos_to_point(road_network_d2.central_position)
        positions = road_network_d2.get_random_positions(1, on_node=False, seed=42)
        p2 = road_network_d2.pos_to_point(positions[0])

        linestring = LineString([p1, p2])
        result: dict[str, Any] = geometries_to_collection([linestring])

        assert isinstance(result, dict)
        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 1
        assert result["features"][0]["type"] == "Feature"
        assert result["features"][0]["geometry"]["type"] == "LineString"

    def test_multiple_linestrings(self, road_network_d2: RoadNetwork):
        """Test converting multiple linestrings."""
        from shapely.geometry import LineString

        positions = road_network_d2.get_random_positions(4, on_node=False, seed=42)
        ls1 = LineString([road_network_d2.pos_to_point(positions[0]), road_network_d2.pos_to_point(positions[1])])
        ls2 = LineString([road_network_d2.pos_to_point(positions[2]), road_network_d2.pos_to_point(positions[3])])

        result: dict[str, Any] = geometries_to_collection([ls1, ls2])

        assert isinstance(result, dict)
        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 2


class TestPlanGeometryDTO:
    """Test PlanGeometry DTO structure."""

    def test_escape_model_dto_structure(self, sample_plan_dto: PlanDTO) -> None:
        """Test that escape_model DTO has correct structure."""
        payload = sample_plan_dto.model_dump()
        plan_geometry = payload["plan_geometry"]

        assert isinstance(plan_geometry, dict)
        assert "isochrone" in plan_geometry
        assert "past_paths" in plan_geometry

    def test_escape_model_isochrone_structure(self, sample_plan_dto: PlanDTO) -> None:
        """Test that isochrone has correct structure."""
        payload = sample_plan_dto.model_dump()
        isochrone = payload["plan_geometry"]["isochrone"]

        assert isinstance(isochrone, dict)
        assert "type" in isochrone
        assert isochrone["type"] == "Feature"
        assert "geometry" in isochrone

    def test_escape_model_past_paths_structure(self, sample_plan_dto: PlanDTO) -> None:
        """Test that past_paths has correct structure."""
        payload = sample_plan_dto.model_dump()
        past_paths = payload["plan_geometry"]["past_paths"]

        assert isinstance(past_paths, dict)
        assert "type" in past_paths
        assert past_paths["type"] == "FeatureCollection"
        assert "features" in past_paths
        assert isinstance(past_paths["features"], list)
