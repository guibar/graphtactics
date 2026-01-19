"""Unit tests for Plan class methods."""

from datetime import datetime

import pytest

from graphtactics.planner import Plan, Planner
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_d2():
    """Medium test network for plan tests."""
    factory = RoadNetworkFactory()
    return factory.create("d2")


@pytest.fixture
def sample_plan_with_assignments(road_network_d2: RoadNetwork):
    """Create a plan with actual assignments for testing."""
    lk_point = road_network_d2.pos_to_point(road_network_d2.central_position)
    last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
    vehicles = Vehicle.get_random_vehicles(road_network_d2, 5, seed=123)
    time_elapsed = 300

    scenario = Scenario(road_network_d2, lk_point, last_time_seen, vehicles, time_elapsed)
    planner = Planner(road_network_d2, scenario)
    planner.plan_interception()

    return planner.plan


class TestPlanInitialization:
    """Test Plan initialization."""

    def test_empty_plan_creation(self):
        """Test creating an empty plan."""
        plan = Plan(nb_assignable_vehicles=10)

        assert plan.nb_assignable_vehicles == 10
        assert plan.assignments == []
        assert plan.solution_score == 0

    def test_plan_with_different_vehicle_counts(self):
        """Test creating plans with different vehicle counts."""
        for count in [0, 5, 10, 50]:
            plan = Plan(nb_assignable_vehicles=count)
            assert plan.nb_assignable_vehicles == count


class TestPlanStats:
    """Test Plan.get_stats() method."""

    def test_empty_plan_stats(self):
        """Test stats for an empty plan."""
        plan = Plan(nb_assignable_vehicles=10)
        stats = plan.get_stats()

        assert isinstance(stats, dict)
        assert "nb_vehicles" in stats
        assert stats["nb_vehicles"] == 10
        assert "nb_assignments" in stats
        assert stats["nb_assignments"] == 0

    def test_plan_with_assignments_stats(self, sample_plan_with_assignments: Plan):
        """Test stats for a plan with assignments."""
        stats = sample_plan_with_assignments.get_stats()

        assert isinstance(stats, dict)
        assert "nb_vehicles" in stats
        assert "nb_assignments" in stats
        assert stats["nb_assignments"] >= 0
        assert stats["nb_assignments"] <= stats["nb_vehicles"]


class TestPlanAssignments:
    """Test Plan assignments handling."""

    def test_plan_assignments_list(self, sample_plan_with_assignments: Plan):
        """Test that plan has a list of assignments."""
        assert isinstance(sample_plan_with_assignments.assignments, list)
        assert len(sample_plan_with_assignments.assignments) >= 0

    def test_plan_solution_score(self, sample_plan_with_assignments: Plan):
        """Test that plan has a solution score."""
        assert isinstance(sample_plan_with_assignments.solution_score, (int, float))
        assert sample_plan_with_assignments.solution_score >= 0
