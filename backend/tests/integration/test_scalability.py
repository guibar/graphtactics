from datetime import datetime
from typing import Any

import pytest
from shapely import Point

from graphtactics.dtos import PlanDTO
from graphtactics.plan_geometry import PlanGeometry
from graphtactics.planner import Plan, Planner
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.serializer import Serializer
from graphtactics.vehicle import Vehicle

# Ca n'est pas le solver qui est le facteur limitant en temps, mais la recherche des trajets à partir
# de la position des véhicules. C'est surtout ća qui augmente le temps d'execution avec le nombre
# de véhicules.


@pytest.fixture(scope="module")
def road_network_60() -> RoadNetwork:
    factory = RoadNetworkFactory()
    return factory.create("60")


@pytest.mark.parametrize(
    "num_vehicles",
    [
        (10),
        (50),
    ],
    ids=["10_vehicles", "50_vehicles"],
)
@pytest.mark.timeout(90)
def test_n_vehicles(road_network_60: RoadNetwork, num_vehicles: int) -> None:
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    lkp: Point = Point(2.10496, 49.40171)
    scenario: Scenario = Scenario(
        road_network_60,
        lkp,
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60, num_vehicles, seed=123, on_node=True),
        7 * 60,
    )
    planner = Planner(road_network_60, scenario)
    plan: Plan = planner.plan_interception()
    geometry = PlanGeometry(planner.escape_model, road_network_60)
    payload: dict[str, Any] = PlanDTO.from_domain(
        scenario, plan, planner.escape_model, geometry, road_network_60
    ).model_dump()
    assert "stats" in payload
    serializer = Serializer(road_network_60, scenario, plan, geometry, f"60_{num_vehicles}v.gpkg")
    serializer.save()
