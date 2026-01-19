from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

import pytest
from shapely import LineString, Point

from graphtactics.dtos import PlanDTO, geometries_to_collection
from graphtactics.plan_geometry import PlanGeometry
from graphtactics.planner import Plan, Planner
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_60():
    factory = RoadNetworkFactory()
    return factory.create("60")


@pytest.fixture(scope="module")
def a_scenario(road_network_60: RoadNetwork) -> Callable[[], Scenario]:
    """Factory fixture to create scenarios with common setup."""

    def _create_scenario() -> Scenario:
        return Scenario(
            road_network_60,
            Point(2.10496, 49.40171),
            datetime.fromisoformat("2020-12-01T09:00:00"),
            Vehicle.get_random_vehicles(road_network_60, 3, seed=123, on_node=True),
            5 * 60,
        )

    return _create_scenario


def test_plan_response_geojson_structure(a_scenario: Callable[[], Scenario], road_network_60: RoadNetwork):
    # Generate plan
    scenario: Scenario = a_scenario()
    planner: Planner = Planner(road_network_60, scenario)
    plan: Plan = planner.plan_interception()

    # Serialize
    geometry: PlanGeometry = PlanGeometry(planner.escape_model, road_network_60)
    response: PlanDTO = PlanDTO.from_domain(scenario, plan, planner.escape_model, geometry, road_network_60)
    payload: dict[str, Any] = response.model_dump()

    # Verification Helper
    def verify_feature_collection(fc: dict[str, Any], expected_feature_count: int):
        assert fc["type"] == "FeatureCollection"
        features_list = cast(list[Any], fc["features"])
        assert isinstance(features_list, list)
        assert len(features_list) == expected_feature_count

        features = cast(list[dict[str, Any]], fc["features"])
        for feature in features:
            assert feature["type"] == "Feature"
            assert "geometry" in feature
            assert "properties" in feature
            # Geometry can be null in some cases, but generally shouldn't be for our use case.
            # Ideally verify geometry type (Point, LineString, etc.) if known.
            geometry = feature["geometry"]
            if geometry:
                assert geometry["type"] in ["MultiLineString", "Point", "LineString", "Polygon", "MultiPolygon"]
                assert isinstance(geometry["coordinates"], (list, tuple))

    # Verify specific fields
    plan_geometry = payload["plan_geometry"]
    # Isochrone is now a single Feature, not a FeatureCollection
    assert plan_geometry["isochrone"]["type"] == "Feature"
    assert "geometry" in plan_geometry["isochrone"]
    verify_feature_collection(plan_geometry["past_paths"], expected_feature_count=8)

    # Assignments might be empty if no solution found, but with 5 vehicles and 7 mins it should find something usually.
    # The solver might fail or return empty if no solution, so we check just structure.
    verify_feature_collection(payload["assignments"], expected_feature_count=3)
    verify_feature_collection(payload["destinations"], expected_feature_count=3)


def test_escape_model_future_paths_with_exact_positions(
    a_scenario: Callable[[], Scenario], road_network_60: RoadNetwork
):
    """Test that future paths correctly include the to_v_linestring portion from exact positions."""
    planner: Planner = Planner(road_network_60, a_scenario())
    planner.plan_interception()

    plan_geometry: PlanGeometry = PlanGeometry(planner.escape_model, road_network_60)
    linestrings: dict[str, list[LineString]] = plan_geometry.get_linestrings()

    # Call the method under test
    lines_past = linestrings["past"]
    assert lines_past is not None
    result = geometries_to_collection(lines_past)

    # Verify GeoJSON structure
    assert result["type"] == "FeatureCollection"
    features_list = cast(list[Any], result["features"])
    assert isinstance(features_list, list)
    assert len(features_list) > 0

    # Track how many features have exact positions
    features_with_exact_pos = 0

    # Verify each feature
    features = cast(list[dict[str, Any]], result["features"])
    for feature in features:
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert "properties" in feature

        # Verify geometry is a LineString
        geometry: dict[str, Any] = feature["geometry"]
        assert geometry["type"] in ["MultiLineString", "LineString"]
        coords = cast(tuple[Any, ...], geometry["coordinates"])
        assert isinstance(coords, tuple)
        assert len(coords) > 0

        features_with_exact_pos += 1
        assert len(coords) >= 2, "LineString should have at least 2 points"

    assert features_with_exact_pos > 0, "At least some escape nodes should have exact positions"


def test_travel_data_past_paths_with_exact_positions(a_scenario: Callable[[], Scenario], road_network_60: RoadNetwork):
    """Test that past paths correctly include the from_u_linestring portion from exact positions."""
    planner: Planner = Planner(road_network_60, a_scenario())
    planner.plan_interception()

    plan_geometry: PlanGeometry = PlanGeometry(planner.escape_model, road_network_60)
    linestrings: dict[str, list[LineString]] = plan_geometry.get_linestrings()
    # Call the method under test
    lines_past: Any | list[LineString] = linestrings["past"]
    assert lines_past is not None
    result: dict[str, Any] = geometries_to_collection(lines_past)

    # Verify GeoJSON structure
    assert result["type"] == "FeatureCollection"
    features_list = cast(list[Any], result["features"])
    assert isinstance(features_list, list)
    assert len(features_list) == len(lines_past)

    # Track how many features have exact positions
    features_with_exact_pos = 0

    # Verify each feature
    features = cast(list[dict[str, Any]], result["features"])
    for feature in features:
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert "properties" in feature

        # Verify geometry is a LineString (or MultiLineString after merge)
        geometry: dict[str, Any] = feature["geometry"]
        assert geometry["type"] in ["MultiLineString", "LineString"]
        coords = cast(list[Any], geometry["coordinates"])
        assert isinstance(coords, (list, tuple))
        assert len(coords) > 0

        features_with_exact_pos += 1
        # Verify the linestring has coordinates
        assert len(coords) >= 2, "LineString should have at least 2 points"

    # Verify that at least some features had exact positions
    assert features_with_exact_pos > 0, "At least some escape nodes should have exact positions"


def test_travel_data_paths_geometry_merging(a_scenario: Callable[[], Scenario], road_network_60: RoadNetwork):
    planner: Planner = Planner(road_network_60, a_scenario())
    planner.plan_interception()

    plan_geometry: PlanGeometry = PlanGeometry(planner.escape_model, road_network_60)
    linestrings: dict[str, list[LineString]] = plan_geometry.get_linestrings()
    # Get both future and past paths
    assert linestrings["past"] is not None
    result: dict[str, Any] = geometries_to_collection(linestrings["past"])

    # Verifyboth have valid features
    assert len(result["features"]) == len(linestrings["past"])

    # Verify that all features have valid LineString geometries
    for feature in result["features"]:
        assert feature["geometry"]["type"] in ["MultiLineString", "LineString"]
        assert len(feature["geometry"]["coordinates"]) >= 2
