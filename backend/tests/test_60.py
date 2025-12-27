from datetime import datetime, timedelta

import pytest
from shapely.geometry import Point

from graphtactics.dtos import PlanDTO
from graphtactics.planner import Planner
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.serializer import Serializer
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_60():
    factory = RoadNetworkFactory()
    return factory.create("60")


def test_oise_complet_a(road_network_60):
    lkp = Point(2.10496, 49.40171)
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    scenario = Scenario(
        road_network_60,
        lkp,
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60, 12, seed=345),
        timedelta(minutes=16),
    )
    serializer = Serializer(road_network_60, scenario, None, "60_345a")
    serializer.save()
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    PlanDTO.from_domain(scenario, plan)


def test_oise_complet_b(road_network_60):
    lkp = Point(2.384, 49.388)
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    scenario = Scenario(
        road_network_60,
        lkp,
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60, 40, seed=345),
        timedelta(minutes=16),
    )
    serializer = Serializer(road_network_60, scenario, None, "60_345b")
    serializer.save()
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    PlanDTO.from_domain(scenario, plan)


# This was used for debugging the case where some of the escape routes found in the 2nd phase were going
# through the isochrone. This was throwing an exception at the EscapeRoute creation
def test_new_dispo(road_network_60):
    network = road_network_60
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    scenario = Scenario(
        network,
        network.node_to_point(9281562110),
        time_lkp,
        Vehicle.get_random_vehicles(network, 7, seed=123, on_node=True),
        timedelta(minutes=7),
    )
    serializer = Serializer(network, scenario, None, "new_dispo_60")
    serializer.save()
    assert len(scenario.adversary.travel_data.get_njois()) == 4
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    PlanDTO.from_domain(scenario, plan)


def test_debug_dispo(road_network_60):
    network = road_network_60
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    scenario = Scenario(
        network,
        network.node_to_point(9281562110),
        time_lkp,
        Vehicle.get_random_vehicles(network, 7, seed=123, on_node=True),
        timedelta(minutes=7),
    )
    serializer = Serializer(network, scenario, None, "new_dispo_60")
    serializer.save()
    assert len(scenario.adversary.travel_data.get_njois()) == 4
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    PlanDTO.from_domain(scenario, plan)


def test_debug(road_network_60):
    scenario = Serializer.load_scenario(road_network_60, "debug_60")
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    assert len(scenario.vehicles) == 10
    assert len(plan.assignments) == 6
    for va in plan.assignments:
        if va.vehicle.id == 4470:
            assert va.destination_node == 683781249
