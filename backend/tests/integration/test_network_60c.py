from datetime import datetime

import pytest

from graphtactics.dtos import PlanDTO
from graphtactics.plan_geometry import PlanGeometry
from graphtactics.planner import Plan, Planner
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_60c() -> RoadNetwork:
    factory = RoadNetworkFactory()
    return factory.create("60c")


def test_route(road_network_60c: RoadNetwork):
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    scenario: Scenario = Scenario(
        road_network_60c,
        road_network_60c.node_to_point(3035472381),
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60c, 1, seed=345, on_node=True),
        16 * 60,
    )
    planner = Planner(road_network_60c, scenario)
    plan: Plan = planner.plan_interception()
    geometry = PlanGeometry(planner.escape_model, road_network_60c)
    payload = PlanDTO.from_domain(scenario, plan, planner.escape_model, geometry, road_network_60c).model_dump()
    assert "origin" in payload
    assert "vehicles" in payload
    assert "assignments" in payload
    assert "destinations" in payload
    assert "stats" in payload
