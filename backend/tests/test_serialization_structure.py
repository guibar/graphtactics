from datetime import datetime, timedelta

import pytest

from graphtactics.dtos import PlanResponse
from graphtactics.planner import Planner
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_60():
    factory = RoadNetworkFactory()
    return factory.create("60")


def test_plan_response_geojson_structure(road_network_60):
    # Setup scenario
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    scenario = Scenario(
        road_network_60,
        road_network_60.node_to_point(7761323880),
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60, 5, seed=123, on_node=True),
        timedelta(minutes=7),
    )

    # Generate plan
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()

    # Serialize
    response = PlanResponse.from_domain(scenario, plan)
    payload = response.model_dump()

    # Verification Helper
    def verify_feature_collection(fc, expected_feature_count=None):
        assert fc["type"] == "FeatureCollection"
        assert isinstance(fc["features"], list)
        if expected_feature_count is not None:
            if expected_feature_count == -1:  # Just check if not empty
                assert len(fc["features"]) > 0
            else:
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
    verify_feature_collection(travel_data["paths_to_njois"], expected_feature_count=-1)
    verify_feature_collection(travel_data["isochrone"], expected_feature_count=1)
    verify_feature_collection(travel_data["paths_from_njois"], expected_feature_count=-1)

    # Affectations might be empty if no solution found, but with 5 vehicles and 7 mins it should find something usually.
    # The solver might fail or return empty if no solution, so we check just structure.
    verify_feature_collection(payload["affectations"])
    verify_feature_collection(payload["destinations"])
