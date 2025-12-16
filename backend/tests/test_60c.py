from datetime import datetime, timedelta

import pytest

from graphtactics.dtos import PlanResponse
from graphtactics.planner import Planner
from graphtactics.serializer import Serializer
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_60c():
    factory = RoadNetworkFactory()
    return factory.create("60c")


def test_route(road_network_60c):
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    scenario = Scenario(
        road_network_60c,
        road_network_60c.node_to_point(3035472381),
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60c, 1, seed=345, on_node=True),
        timedelta(minutes=16),
    )
    serializer = Serializer(road_network_60c, scenario, None, "60c_345")
    serializer.save()
    planner = Planner(road_network_60c, scenario.vehicles, scenario.adversary.candidate_nodes)
    plan = planner.plan_interception()
    payload = PlanResponse.from_domain(scenario, plan).model_dump()
    assert "origin" in payload
    assert "vehicles" in payload
    assert "affectations" in payload
    assert "stats" in payload
