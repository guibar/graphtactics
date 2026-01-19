from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from shapely.geometry import Point

from graphtactics.dtos import PlanDTO
from graphtactics.plan_geometry import PlanGeometry
from graphtactics.planner import Plan, Planner
from graphtactics.position import Position
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.serializer import Serializer
from graphtactics.vehicle import Vehicle

# approx is partially unknown in pytest, using Any to satisfy strict Pyright
approx: Any = pytest.approx  # type: ignore


class TestD2:
    @pytest.fixture(scope="class")
    def road_network_d2(self) -> RoadNetwork:
        return RoadNetworkFactory().create("d2")

    def test_run_d2_1(self, road_network_d2: RoadNetwork):
        lkp: Point = Point(2.10496, 49.40171)
        time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
        scenario: Scenario = Scenario(
            road_network_d2,
            lkp,
            time_lkp,
            Vehicle.get_random_vehicles(road_network_d2, 10, seed=123),
            8 * 60,
        )
        planner: Planner = Planner(road_network_d2, scenario)
        plan: Plan = planner.plan_interception()
        geometry = PlanGeometry(planner.escape_model, road_network_d2)
        payload: dict[str, Any] = PlanDTO.from_domain(
            scenario, plan, planner.escape_model, geometry, road_network_d2
        ).model_dump()
        assert "assignments" in payload

    def test_run_d2_2(self, road_network_d2: RoadNetwork):
        lkp: Point = Point(2.10496, 49.40171)
        time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
        scenario: Scenario = Scenario(
            road_network_d2,
            lkp,
            time_lkp,
            Vehicle.get_random_vehicles(road_network_d2, 10, seed=234),
            8 * 60,
        )
        repo: Serializer = Serializer(road_network_d2, scenario, None, filepath="d2_234")
        repo.save()
        planner: Planner = Planner(road_network_d2, scenario)
        plan: Plan = planner.plan_interception()
        geometry = PlanGeometry(planner.escape_model, road_network_d2)
        payload: dict[str, Any] = PlanDTO.from_domain(
            scenario, plan, planner.escape_model, geometry, road_network_d2
        ).model_dump()
        assert "assignments" in payload
        assert "destinations" in payload

    def test_point(self, road_network_d2: RoadNetwork):
        point: Point = Point(2.11215, 49.40795)
        position = road_network_d2.create_position_from_point(point, on_node=True)
        assert position.u == 5546401948

    def test_run_d2_3(self, road_network_d2: RoadNetwork):
        lkp: Point = Point(2.11215, 49.40795)
        time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
        scenario: Scenario = Scenario(
            road_network_d2,
            lkp,
            time_lkp,
            Vehicle.get_random_vehicles(road_network_d2, 40, seed=234),
            8 * 60,
        )
        repo: Serializer = Serializer(road_network_d2, scenario, None, filepath="d2_234")
        repo.save()
        planner: Planner = Planner(road_network_d2, scenario)
        plan: Plan = planner.plan_interception()
        geometry = PlanGeometry(planner.escape_model, road_network_d2)
        payload: dict[str, Any] = PlanDTO.from_domain(
            scenario, plan, planner.escape_model, geometry, road_network_d2
        ).model_dump()
        assert "assignments" in payload

    def test_from_gpkg(self, road_network_d2: RoadNetwork, plans_fixtures_dir: Path):
        scenario: Scenario = Serializer.load_scenario(road_network_d2, str(plans_fixtures_dir / "d2_123.gpkg"))
        planner: Planner = Planner(road_network_d2, scenario)
        plan: Plan = planner.plan_interception()
        geometry = PlanGeometry(planner.escape_model, road_network_d2)
        payload: dict[str, Any] = PlanDTO.from_domain(
            scenario, plan, planner.escape_model, geometry, road_network_d2
        ).model_dump()
        assert "assignments" in payload


class TestNoailles:
    @pytest.fixture(scope="class")
    def road_network_noailles(self) -> RoadNetwork:
        return RoadNetworkFactory().create("noailles")

    def create_scenario(
        self, road_network_noailles: RoadNetwork, time_elapsed: int, time_margin: int
    ) -> tuple[Scenario, Plan]:
        vehicles_data: list[list[Any]] = [
            [8646, 9492259465, 2453116957, 0.7140],
            [1748, 1604750621, 1614109486, 0.122],
            [5093, 663847596, 1604751413, 0.4508],
            [7211, 1614109854, 7157438017, 0.1402],
        ]
        vehicles: dict[int, Vehicle] = {
            int(v_data[0]): Vehicle(
                road_network_noailles,
                int(v_data[0]),
                road_network_noailles.pos_to_point(Position(u=int(v_data[1]), v=int(v_data[2]), ec=float(v_data[3]))),
            )
            for v_data in vehicles_data
        }
        scenario: Scenario = Scenario(
            road_network_noailles,
            road_network_noailles.pos_to_point(road_network_noailles.central_position),
            datetime.fromisoformat("2020-12-01T09:00:00"),
            vehicles,
            time_elapsed,
            time_margin,
        )
        planner: Planner = Planner(road_network_noailles, scenario)
        plan: Plan = planner.plan_interception()
        return scenario, plan

    def test_verified_scenario_5_min(self, road_network_noailles: RoadNetwork):
        scenario, plan = self.create_scenario(road_network_noailles, 5 * 60, 0)

        assert plan.assignments[0].vehicle.id == 8646
        assert plan.assignments[0].destination_node == 2594302252
        assert len(plan.assignments) == 1

        # Use network.to_point() to get coordinates from positions
        assert scenario.vehicles[8646].position is not None
        point_8646 = road_network_noailles.pos_to_point(scenario.vehicles[8646].position)

        assert point_8646.x == approx(2.326, abs=0.001)
        assert point_8646.y == approx(49.318, abs=0.001)

        assert plan.assignments[0].vehicle.id == 8646
        assert plan.assignments[0].destination_node == 2594302252

    def test_boundary_case(self, road_network_noailles: RoadNetwork):
        lkp: Point = road_network_noailles.pos_to_point(road_network_noailles.central_position)
        time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
        scenario: Scenario = Scenario(
            road_network_noailles,
            lkp,
            time_lkp,
            Vehicle.get_random_vehicles(road_network_noailles, 3, seed=234),
            30 * 60,
        )
        planner: Planner = Planner(road_network_noailles, scenario)
        plan: Plan = planner.plan_interception()
        geometry = PlanGeometry(planner.escape_model, road_network_noailles)
        repo: Serializer = Serializer(road_network_noailles, scenario, plan, geometry, filepath="noailles_234")
        repo.save()

    def test_limit_short_time(self, road_network_noailles: RoadNetwork):
        # This point is chosen to be roughly the middle of the edge (2014919181, 10203356564)
        lkp: Point = Point(2.175, 49.320)

        time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
        # In a minute, you cannot reach either end of the edge
        scenario: Scenario = Scenario(
            road_network_noailles,
            lkp,
            time_lkp,
            Vehicle.get_random_vehicles(road_network_noailles, 1, seed=234),
            60,
        )
        lkp_point = road_network_noailles.pos_to_point(scenario.adversary.lkp_position)
        assert lkp_point.x == approx(2.175, abs=0.001)
        assert lkp_point.y == approx(49.320, abs=0.001)

        expected_u = 2014919181
        expected_v = 10203356564
        expected_ec = 0.4628

        assert road_network_noailles.get_edge_travel_time(expected_u, expected_v) == approx(178.233, abs=0.001)

        assert scenario.adversary.lkp_position.u == expected_u
        assert scenario.adversary.lkp_position.v == expected_v
        assert scenario.adversary.lkp_position.ec == approx(expected_ec, abs=0.001)

        planner: Planner = Planner(road_network_noailles, scenario)
        plan: Plan = planner.plan_interception()

        assert planner.escape_model.tree_dict[expected_u].is_njoi
        assert planner.escape_model.tree_dict[expected_v].is_njoi

        # This one is on the north and the exist is via v, so the ec of the present position should increase.
        expected_escape_node = 5690815937
        assert planner.escape_model.tree_dict[expected_escape_node].is_leaf

        assert planner.escape_model.tree_dict[expected_escape_node].is_leaf

        geometry = PlanGeometry(planner.escape_model, road_network_noailles)
        plan_dto: PlanDTO = PlanDTO.from_domain(scenario, plan, planner.escape_model, geometry, road_network_noailles)
        assert plan_dto is not None
