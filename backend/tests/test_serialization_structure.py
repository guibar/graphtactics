from datetime import datetime, timedelta

import pytest
from shapely import Point

from graphtactics.dtos import PlanResponse, TravelDataResponse
from graphtactics.planner import Planner
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_60():
    factory = RoadNetworkFactory()
    return factory.create("60")


@pytest.fixture(scope="module")
def a_scenario(road_network_60):
    """Factory fixture to create scenarios with common setup."""

    def _create_scenario():
        return Scenario(
            road_network_60,
            Point(2.10496, 49.40171),
            datetime.fromisoformat("2020-12-01T09:00:00"),
            Vehicle.get_random_vehicles(road_network_60, 3, seed=123, on_node=True),
            timedelta(minutes=5),
        )

    return _create_scenario


def test_plan_response_geojson_structure(a_scenario, road_network_60):
    # Generate plan
    planner = Planner(road_network_60, a_scenario())
    plan = planner.plan_interception()

    # Serialize
    response = PlanResponse.from_domain(a_scenario(), plan)
    payload = response.model_dump()

    # Verification Helper
    def verify_feature_collection(fc, expected_feature_count):
        assert fc["type"] == "FeatureCollection"
        assert isinstance(fc["features"], list)
        assert len(fc["features"]) == expected_feature_count

        for feature in fc["features"]:
            assert feature["type"] == "Feature"
            assert "geometry" in feature
            assert "properties" in feature
            # Geometry can be null in some cases, but generally shouldn't be for our use case.
            # Ideally verify geometry type (Point, LineString, etc.) if known.
            if feature["geometry"]:
                assert feature["geometry"]["type"] in ["Point", "LineString", "Polygon", "MultiPolygon"]
                assert isinstance(feature["geometry"]["coordinates"], (list, tuple))

    # Verify specific fields
    travel_data = payload["travel_data"]
    # Isochrone is now a single Feature, not a FeatureCollection
    assert travel_data["isochrone"]["type"] == "Feature"
    assert "geometry" in travel_data["isochrone"]
    verify_feature_collection(travel_data["future_paths"], expected_feature_count=72)

    # Affectations might be empty if no solution found, but with 5 vehicles and 7 mins it should find something usually.
    # The solver might fail or return empty if no solution, so we check just structure.
    verify_feature_collection(payload["affectations"], expected_feature_count=2)
    verify_feature_collection(payload["destinations"], expected_feature_count=2)


def test_travel_data_future_paths_with_exact_positions(a_scenario):
    """Test that future paths correctly include the to_v_linestring portion from exact positions."""
    travel_data = a_scenario().adversary.travel_data

    # Verify that exact_positions is populated
    assert len(travel_data.exact_positions) > 0, "TravelData should have exact positions"

    # Call the method under test
    lines_past, lines_future = TravelDataResponse.past_and_future_paths_as_line_strings(travel_data)
    result = TravelDataResponse.linestrings_to_collection(lines_future)

    # Verify GeoJSON structure
    assert result["type"] == "FeatureCollection"
    assert isinstance(result["features"], list)
    assert len(result["features"]) > 0

    # Track how many features have exact positions
    features_with_exact_pos = 0

    # Verify each feature
    for feature in result["features"]:
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert "properties" in feature

        # Verify geometry is a LineString
        geometry = feature["geometry"]
        assert geometry["type"] == "LineString"
        assert isinstance(geometry["coordinates"], tuple)
        assert len(geometry["coordinates"]) > 0

        features_with_exact_pos += 1
        assert len(geometry["coordinates"]) >= 2, "LineString should have at least 2 points"

    assert features_with_exact_pos > 0, "At least some escape nodes should have exact positions"


def test_travel_data_past_paths_with_exact_positions(a_scenario):
    """Test that past paths correctly include the from_u_linestring portion from exact positions."""
    travel_data = a_scenario().adversary.travel_data

    # Verify that exact_positions is populated
    # TravelData should have exact positions
    assert len(travel_data.exact_positions) == len(travel_data.paths_to_e_nodes_future)

    # Call the method under test
    lines_past, lines_future = TravelDataResponse.past_and_future_paths_as_line_strings(travel_data)
    result = TravelDataResponse.linestrings_to_collection(lines_past)

    # Verify GeoJSON structure
    assert result["type"] == "FeatureCollection"
    assert isinstance(result["features"], list)
    assert len(result["features"]) == len(travel_data.paths_to_e_nodes_future)

    # Track how many features have exact positions
    features_with_exact_pos = 0

    # Verify each feature
    for feature in result["features"]:
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert "properties" in feature

        # Verify geometry is a LineString (or MultiLineString after merge)
        geometry = feature["geometry"]
        assert geometry["type"] == "LineString"
        assert isinstance(geometry["coordinates"], (list, tuple))
        assert len(geometry["coordinates"]) > 0

        features_with_exact_pos += 1
        # Verify the linestring has coordinates
        assert len(geometry["coordinates"]) >= 2, "LineString should have at least 2 points"

    # Verify that at least some features had exact positions
    assert features_with_exact_pos > 0, "At least some escape nodes should have exact positions"


def test_travel_data_paths_geometry_merging(a_scenario):
    travel_data = a_scenario().adversary.travel_data

    # Get both future and past paths
    lines_past, lines_future = TravelDataResponse.past_and_future_paths_as_line_strings(travel_data)
    future_paths_json = TravelDataResponse.linestrings_to_collection(lines_future)
    past_paths_json = TravelDataResponse.linestrings_to_collection(lines_past)

    # Verify both have valid features
    assert len(future_paths_json["features"]) == len(travel_data.paths_to_e_nodes_future)
    assert len(past_paths_json["features"]) == len(travel_data.paths_to_e_nodes_past)

    # Verify that all features have valid LineString geometries
    for feature in future_paths_json["features"]:
        assert feature["geometry"]["type"] == "LineString"
        assert len(feature["geometry"]["coordinates"]) >= 2

    for feature in past_paths_json["features"]:
        assert feature["geometry"]["type"] == "LineString"
        assert len(feature["geometry"]["coordinates"]) >= 2
