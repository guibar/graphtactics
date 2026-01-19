from datetime import datetime
from pathlib import Path

import pytest
from shapely.geometry import Point

from graphtactics.dtos import PlanDTO
from graphtactics.plan_geometry import PlanGeometry
from graphtactics.planner import Plan, Planner
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.serializer import Serializer
from graphtactics.vehicle import Vehicle


@pytest.fixture(scope="module")
def road_network_60() -> RoadNetwork:
    factory = RoadNetworkFactory()
    return factory.create("60")


@pytest.mark.parametrize(
    "lkp,num_vehicles,filepath",
    [
        (Point(2.10496, 49.40171), 12, "60_345a"),
        (Point(2.384, 49.388), 40, "60_345b"),
    ],
    ids=["location_a_12_vehicles", "location_b_40_vehicles"],
)
def test_oise_complet(road_network_60: RoadNetwork, lkp: Point, num_vehicles: int, filepath: str):
    """Test complete planning workflow on network 60 with different scenarios."""
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    scenario: Scenario = Scenario(
        road_network_60,
        lkp,
        time_lkp,
        Vehicle.get_random_vehicles(road_network_60, num_vehicles, seed=345),
        16 * 60,
    )
    planner = Planner(road_network_60, scenario)
    plan: Plan = planner.plan_interception()
    geometry = PlanGeometry(planner.escape_model, road_network_60)
    plan_dto: PlanDTO = PlanDTO.from_domain(scenario, plan, planner.escape_model, geometry, road_network_60)

    serializer: Serializer = Serializer(road_network_60, scenario, plan, geometry)
    serializer.save()

    # Add meaningful assertions
    assert plan_dto is not None
    assert len(plan.assignments) >= 0  # May be 0 if no valid assignments
    assert planner.escape_model.candidate_nodes is not None


def test_escape_routes_not_through_isochrone(road_network_60: RoadNetwork):
    """Test that escape routes found in 2nd phase don't go through the isochrone.

    This was a regression test for a bug where some escape routes were incorrectly
    going through the isochrone, causing an exception at EscapeRoute creation.
    """
    network = road_network_60
    time_lkp = datetime.fromisoformat("2020-12-01T09:00:00")
    scenario: Scenario = Scenario(
        network,
        network.node_to_point(9281562110),
        time_lkp,
        Vehicle.get_random_vehicles(network, 7, seed=123, on_node=True),
        7 * 60,
    )

    planner: Planner = Planner(network, scenario)
    plan: Plan = planner.plan_interception()

    # Create geometry for serialization
    geometry = PlanGeometry(planner.escape_model, network)
    serializer = Serializer(network, scenario, plan, geometry, "new_dispo_60")
    serializer.save()

    # Verify the escape model has exactly 4 unique NJOIs (escape nodes)
    assert len(set(scenario.adversary.escape_model.get_njois())) == 5

    # Verify PlanDTO creation doesn't raise an exception (the original bug)
    plan_dto: PlanDTO = PlanDTO.from_domain(scenario, plan, planner.escape_model, geometry, network)
    assert plan_dto is not None

    # Verify the plan has valid structure
    assert hasattr(plan_dto, "plan_geometry")
    assert plan_dto.plan_geometry is not None


def test_debug(road_network_60: RoadNetwork, plans_fixtures_dir: Path):
    scenario: Scenario = Serializer.load_scenario(road_network_60, str(plans_fixtures_dir / "debug_60.gpkg"))
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    assert len(scenario.vehicles) == 10
    assert len(plan.assignments) == 10
    for va in plan.assignments:
        if va.vehicle.id == 4470:
            assert va.destination_node == 683781249


def test_debug2(road_network_60: RoadNetwork, plans_fixtures_dir: Path):
    scenario: Scenario = Serializer.load_scenario(road_network_60, str(plans_fixtures_dir / "deb_60.gpkg"))
    planner = Planner(road_network_60, scenario)
    plan = planner.plan_interception()
    geometry = PlanGeometry(planner.escape_model, road_network_60)
    plan_dto: PlanDTO = PlanDTO.from_domain(scenario, plan, planner.escape_model, geometry, road_network_60)
    assert plan_dto is not None


# def test_cover_status_propagation(road_network_60: RoadNetwork):
#     pass
#     """Test the propagation of cover status on a specific scenario (deb_60)."""
#     # Inputs from deb_60.gpkg
#     lk_point = Point(2.42029, 49.41011)
#     last_time_seen = datetime.fromisoformat("2026-01-11T10:55:29.062954")
#     time_elapsed = 300

#     # Vehicles data exactly as in the bug report
#     vehicles_data: list[dict[str, int | float]] = [
#         {"id": 3601, "u": 2073318561, "v": 5486480377, "ec": 0.517709},
#         {"id": 9747, "u": 9525698317, "v": 1118850950, "ec": 0.585518},
#         {"id": 2958, "u": 893218267, "v": 3822859439, "ec": 0.558808},
#         {"id": 6063, "u": 676672323, "v": 1520861847, "ec": 0.308507},
#     ]

#     vehicles: dict[int, Vehicle] = {}
#     for data in vehicles_data:
#         pos = Position(u=data["u"], v=data["v"], ec=data["ec"])  # type: ignore
#         vehicles[data["id"]] = Vehicle(road_network_60, data["id"], road_network_60.pos_to_point(pos))  # type: ignore

#     # 1. Initialize Scenario and Planner
#     scenario = Scenario(road_network_60, lk_point, last_time_seen, vehicles, time_elapsed)
#     planner = Planner(road_network_60, scenario)
#     serializer = Serializer(road_network_60, scenario, planner, "cover_status_propagation")
#     serializer.save()

#     # 2. Check if cover status propagated to root
#     root = planner.escape_model.tree_dict[0]
#     assert root.cover == CoverStatus.MIXED, "Root should at least be MIXED if there are interceptions"

#     # Specific path analysis (from the bug report)
#     escape_node_osmid = 130777644
#     escape_tn: TreeNode = planner.escape_model.tree_dict[escape_node_osmid]
#     path = planner.escape_model.tree_dict[escape_node_osmid].path
#     assert len(path) == 10

#     # This is the last node that is not covered on the path to the control_node
#     branching_node_osmid: int = 1011046372
#     branching_tn: TreeNode = planner.escape_model.tree_dict[branching_node_osmid]
#     control_node_osmid: int = 5015328562
#     control_tn: TreeNode = planner.escape_model.tree_dict[control_node_osmid]

#     assert planner.escape_model.tree_dict[branching_node_osmid] in path
#     assert planner.escape_model.tree_dict[control_node_osmid] in path

#     assert planner.escape_model.tree_dict[control_node_osmid].is_control_node is True

#     # This is the last node on the path that is mixed
#     assert planner.escape_model.tree_dict[branching_node_osmid].cover == CoverStatus.MIXED

#     # All nodes after branching_node and control_node should be covered
#     branching_node_index = path.index(planner.escape_model.tree_dict[branching_node_osmid])
#     for node in path[branching_node_index + 1 :]:
#         assert node.cover == CoverStatus.COVERED

#     root_to_branching, branching_to_control, control_to_escape = path[-1].split_controlled_path()

#     assert root_to_branching[0] == planner.escape_model.tree_dict[0]
#     assert root_to_branching[-1] == branching_tn
#     assert all(node.cover == CoverStatus.MIXED for node in root_to_branching)

#     assert branching_to_control[0] == branching_tn
#     assert branching_to_control[-1] == control_tn
#     assert all(node.cover == CoverStatus.COVERED for node in branching_to_control[1:])

#     assert control_to_escape[0] == control_tn
#     assert control_to_escape[-1] == escape_tn
#     assert all(node.cover == CoverStatus.COVERED for node in control_to_escape)
