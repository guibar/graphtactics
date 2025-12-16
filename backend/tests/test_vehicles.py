import pytest
from shapely import Point

from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.vehicle import Vehicle, VehicleAssignment


@pytest.fixture(scope="module")
def road_network_st_quentin():
    factory = RoadNetworkFactory()
    return factory.create("st_quentin")


@pytest.fixture(scope="module")
def road_network_d2():
    factory = RoadNetworkFactory()
    return factory.create("d2")


def test_get_random_vehicles(road_network_st_quentin):
    network = road_network_st_quentin
    vehicles = Vehicle.get_random_vehicles(network, 3, on_node=False, seed=123)
    for veh in vehicles.values():
        geometry = network.get_edge_geometry((veh.position.u, veh.position.v))
        assert geometry.distance(veh.position.point) < 1e-6

    vehicles = Vehicle.get_random_vehicles(network, 3, on_node=True, seed=123)
    for veh in vehicles.values():
        assert veh.position.u != veh.position.v
        assert network.node_to_point(veh.position.u) == veh.position.point


def test_get_empty_dict(road_network_st_quentin):
    vehicles = Vehicle.get_random_vehicles(road_network_st_quentin, 0)
    assert len(vehicles) == 0


def test_set_assignment(road_network_d2):
    origin = 5546330058
    destination = 5546329912

    origin_pt = road_network_d2.node_to_point(origin)
    destination_pt = road_network_d2.node_to_point(destination)

    vehicle = Vehicle.from_point(road_network_d2, 1, origin_pt, on_node=True)
    vehicle.set_travel_times()
    va = VehicleAssignment(road_network_d2, vehicle, destination, 10, 10, 10)

    assert Point(va.trajectory_geom.coords[0]) == origin_pt
    assert Point(va.trajectory_geom.coords[-1]) == destination_pt
