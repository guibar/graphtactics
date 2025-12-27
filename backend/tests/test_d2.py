from datetime import datetime, timedelta

import pytest
from shapely.geometry import Point

from graphtactics.dtos import PlanDTO
from graphtactics.planner import Planner
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.serializer import Serializer
from graphtactics.vehicle import Vehicle


class TestD2:
    @pytest.fixture(scope="class")
    def road_network_d2(self) -> RoadNetwork:
        return RoadNetworkFactory().create("d2")

    def test_run_d2_1(self, road_network_d2):
        lkp = Point(2.10496, 49.40171)
        time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
        scenario = Scenario(
            road_network_d2,
            lkp,
            time_lkp,
            Vehicle.get_random_vehicles(road_network_d2, 10, seed=123),
            timedelta(minutes=8),
        )
        repo = Serializer(road_network_d2, scenario, filepath="d2_123")
        repo.save()
        planner = Planner(road_network_d2, scenario)
        plan = planner.plan_interception()
        payload = PlanDTO.from_domain(scenario, plan).model_dump()
        assert "affectations" in payload

    def test_run_d2_2(self, road_network_d2):
        lkp = Point(2.10496, 49.40171)
        time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
        scenario = Scenario(
            road_network_d2,
            lkp,
            time_lkp,
            Vehicle.get_random_vehicles(road_network_d2, 10, seed=234),
            timedelta(minutes=8),
        )
        repo = Serializer(road_network_d2, scenario, filepath="d2_234")
        repo.save()
        planner = Planner(road_network_d2, scenario)
        plan = planner.plan_interception()
        payload = PlanDTO.from_domain(scenario, plan).model_dump()
        assert "affectations" in payload

    def test_point(self, road_network_d2):
        point = Point(2.11215, 49.40795)
        position = road_network_d2.create_position_from_point(point, on_node=True)
        assert position.u == 5546401948

    def test_run_d2_3(self, road_network_d2):
        lkp = Point(2.11215, 49.40795)
        time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
        scenario = Scenario(
            road_network_d2,
            lkp,
            time_lkp,
            Vehicle.get_random_vehicles(road_network_d2, 40, seed=234),
            timedelta(minutes=8),
        )
        repo = Serializer(road_network_d2, scenario, filepath="d2_234")
        repo.save()
        planner = Planner(road_network_d2, scenario)
        plan = planner.plan_interception()
        payload = PlanDTO.from_domain(scenario, plan).model_dump()
        assert "affectations" in payload

    def test_from_gpkg(self, road_network_d2):
        scenario = Serializer.load_scenario(road_network_d2, "d2_123")
        planner = Planner(road_network_d2, scenario)
        plan = planner.plan_interception()
        payload = PlanDTO.from_domain(scenario, plan).model_dump()
        assert "affectations" in payload


class TestNoailles:
    @pytest.fixture(scope="class")
    def road_network_noailles(self) -> RoadNetwork:
        return RoadNetworkFactory().create("noailles")

    def test_from_gpkg(self, road_network_noailles):
        pass
