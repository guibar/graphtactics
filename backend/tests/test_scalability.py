from datetime import datetime, timedelta

import pytest
from shapely import Point

from graphtactics.dtos import PlanDTO
from graphtactics.planner import Planner
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.serializer import Serializer
from graphtactics.vehicle import Vehicle

# Ca n'est pas le solver qui est le facteur limitant en temps, mais la recherche des trajets à partir
# de la position des véhicules. C'est surtout ća qui augmente le temps d'execution avec le nombre
# de véhicules.


@pytest.fixture(scope="module")
def road_network_60():
    factory = RoadNetworkFactory()
    return factory.create("60")


@pytest.mark.timeout(30)
def test_dispositif_10_vehicles(road_network_60):
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    lkp = Point(2.10496, 49.40171)
    scenario = Scenario(
        road_network_60,
        lkp,
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60, 50, seed=123, on_node=True),
        timedelta(minutes=7),
    )
    serializer = Serializer(road_network_60, scenario, None, "60_10v.gpkg")
    serializer.save()
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    payload = PlanDTO.from_domain(scenario, plan).model_dump()
    assert "stats" in payload


@pytest.mark.timeout(30)
def test_dispositif_50_vehicles(road_network_60):
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    lkp = Point(2.10496, 49.40171)
    scenario = Scenario(
        road_network_60,
        lkp,
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60, 50, seed=123, on_node=True),
        timedelta(minutes=7),
    )
    serializer = Serializer(road_network_60, scenario, None, "60_50v.gpkg")
    serializer.save()
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    payload = PlanDTO.from_domain(scenario, plan).model_dump()
    assert "stats" in payload


@pytest.mark.timeout(30)
def test_dispositif_100_vehicles(road_network_60):
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    lkp = Point(2.10496, 49.40171)
    scenario = Scenario(
        road_network_60,
        lkp,
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60, 100, seed=123, on_node=True),
        timedelta(minutes=7),
    )
    serializer = Serializer(road_network_60, scenario, None, "60_100v.gpkg")
    serializer.save()
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    payload = PlanDTO.from_domain(scenario, plan).model_dump()
    assert "stats" in payload
