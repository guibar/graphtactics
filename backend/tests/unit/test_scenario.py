"""Unit tests for the Scenario class."""

from datetime import datetime, timedelta

import pytest

from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_st_quentin():
    """Small test network for scenario tests."""
    factory = RoadNetworkFactory()
    return factory.create("st_quentin")


class TestScenarioInitialization:
    """Test Scenario initialization."""

    def test_valid_scenario_creation(self, road_network_st_quentin: RoadNetwork):
        """Test creating a scenario with valid inputs."""
        lk_point = road_network_st_quentin.pos_to_point(road_network_st_quentin.central_position)
        last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
        vehicles = Vehicle.get_random_vehicles(road_network_st_quentin, 5, seed=123)
        time_elapsed = 300

        scenario = Scenario(road_network_st_quentin, lk_point, last_time_seen, vehicles, time_elapsed)

        assert scenario.graph_name == road_network_st_quentin.name
        assert scenario.time_elapsed == time_elapsed
        assert scenario.vehicles == vehicles
        assert scenario.adversary is not None

    def test_scenario_time_calculations(self, road_network_st_quentin: RoadNetwork):
        """Test that scenario correctly calculates time_now."""
        lk_point = road_network_st_quentin.pos_to_point(road_network_st_quentin.central_position)
        last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
        vehicles = Vehicle.get_random_vehicles(road_network_st_quentin, 3, seed=123)
        time_elapsed = 300  # 5 minutes

        scenario = Scenario(road_network_st_quentin, lk_point, last_time_seen, vehicles, time_elapsed)

        expected_time_now = last_time_seen + timedelta(seconds=time_elapsed)
        assert scenario.time_now == expected_time_now

    def test_scenario_with_empty_vehicles(self, road_network_st_quentin: RoadNetwork):
        """Test creating a scenario with no vehicles."""
        lk_point = road_network_st_quentin.pos_to_point(road_network_st_quentin.central_position)
        last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
        vehicles: dict[int, Vehicle] = {}  # Empty vehicles dictionary
        time_elapsed = 300

        scenario = Scenario(road_network_st_quentin, lk_point, last_time_seen, vehicles, time_elapsed)

        assert scenario.vehicles == {}
        assert len(scenario.vehicles) == 0
        assert scenario.adversary is not None  # Adversary should still be created

    def test_scenario_with_different_time_elapsed(self, road_network_st_quentin: RoadNetwork):
        """Test scenarios with different time_elapsed values."""
        lk_point = road_network_st_quentin.pos_to_point(road_network_st_quentin.central_position)
        last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
        vehicles = Vehicle.get_random_vehicles(road_network_st_quentin, 3, seed=123)

        for time_elapsed in [0, 60, 300, 600, 3600]:
            scenario = Scenario(road_network_st_quentin, lk_point, last_time_seen, vehicles, time_elapsed)
            assert scenario.time_elapsed == time_elapsed
            expected_time_now = last_time_seen + timedelta(seconds=time_elapsed)
            assert scenario.time_now == expected_time_now


class TestScenarioAdversary:
    """Test Scenario adversary creation."""

    def test_adversary_created_with_scenario(self, road_network_st_quentin: RoadNetwork):
        """Test that adversary is created when scenario is initialized."""
        lk_point = road_network_st_quentin.pos_to_point(road_network_st_quentin.central_position)
        last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
        vehicles = Vehicle.get_random_vehicles(road_network_st_quentin, 3, seed=123)
        time_elapsed = 300

        scenario = Scenario(road_network_st_quentin, lk_point, last_time_seen, vehicles, time_elapsed)

        assert scenario.adversary is not None
        assert scenario.adversary.network == road_network_st_quentin
        assert scenario.adversary.last_time_seen == last_time_seen
        assert scenario.adversary.time_elapsed == time_elapsed

    def test_adversary_position_in_boundary(self, road_network_st_quentin: RoadNetwork):
        """Test that adversary position is within network boundary."""
        lk_point = road_network_st_quentin.pos_to_point(road_network_st_quentin.central_position)
        last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
        vehicles = Vehicle.get_random_vehicles(road_network_st_quentin, 3, seed=123)
        time_elapsed = 300

        scenario = Scenario(road_network_st_quentin, lk_point, last_time_seen, vehicles, time_elapsed)

        assert road_network_st_quentin.has_in_boundary(scenario.adversary.lkp_position)


class TestScenarioAttributes:
    """Test Scenario attribute access."""

    def test_all_attributes_accessible(self, road_network_st_quentin: RoadNetwork):
        """Test that all scenario attributes are accessible."""
        lk_point = road_network_st_quentin.pos_to_point(road_network_st_quentin.central_position)
        last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
        vehicles = Vehicle.get_random_vehicles(road_network_st_quentin, 5, seed=123)
        time_elapsed = 300

        scenario = Scenario(road_network_st_quentin, lk_point, last_time_seen, vehicles, time_elapsed)

        # All attributes should be accessible
        assert hasattr(scenario, "graph_name")
        assert hasattr(scenario, "time_elapsed")
        assert hasattr(scenario, "time_now")
        assert hasattr(scenario, "adversary")
        assert hasattr(scenario, "vehicles")

        # Check types
        assert isinstance(scenario.graph_name, str)
        assert isinstance(scenario.time_elapsed, int)
        assert isinstance(scenario.time_now, datetime)
        assert isinstance(scenario.vehicles, dict)

    def test_graph_name_matches_network(self, road_network_st_quentin: RoadNetwork):
        """Test that graph_name matches the network name."""
        lk_point = road_network_st_quentin.pos_to_point(road_network_st_quentin.central_position)
        last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
        vehicles = Vehicle.get_random_vehicles(road_network_st_quentin, 3, seed=123)
        time_elapsed = 300

        scenario = Scenario(road_network_st_quentin, lk_point, last_time_seen, vehicles, time_elapsed)

        assert scenario.graph_name == "st_quentin"
        assert scenario.graph_name == road_network_st_quentin.name


class TestScenarioClassAttributes:
    """Test Scenario class-level attributes."""

    def test_min_reachable_nodes_ratio(self):
        """Test that min_reachable_nodes_ratio_for_assignable is defined."""
        assert hasattr(Scenario, "min_reachable_nodes_ratio_for_assignable")
        assert isinstance(Scenario.min_reachable_nodes_ratio_for_assignable, float)
        assert 0 <= Scenario.min_reachable_nodes_ratio_for_assignable <= 1

    def test_save_plans_attribute(self):
        """Test that save_plans attribute is defined."""
        assert hasattr(Scenario, "save_plans")
        assert isinstance(Scenario.save_plans, bool)
