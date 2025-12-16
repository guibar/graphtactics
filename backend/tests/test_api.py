import os

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from graphtactics.road_network import EdgeRef
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.vehicle import Vehicle

# Set environment before importing app
os.environ["NEO_GRAPH_NAME"] = "60"
from graphtactics.app import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """Create a test client with lifespan context."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def network():
    """Get the network instance for direct testing."""
    factory = RoadNetworkFactory()
    return factory.create("60")


def test_random_vehicles(client):
    response = client.get("/random_vehicles?nb_vh=5")
    assert response.status_code == 200
    json_data = response.json()
    assert len(json_data) == 5
    for jd in json_data:
        assert "id" in jd
        assert "position" in jd
        assert "lat" in jd["position"]
        assert "lng" in jd["position"]


def test_from_json_vehicles(network):
    from shapely.geometry import Point

    p1 = network.node_to_point(1776288149)
    p2 = network.node_to_point(348994024)
    d = [
        {"id": 2758, "point": {"lat": p1.y, "lng": p1.x}},
        {"id": 6945, "point": {"lat": p2.y, "lng": p2.x}},
    ]

    # Create vehicles from JSON data
    vehicles = {}
    for veh_data in d:
        point = Point(veh_data["point"]["lng"], veh_data["point"]["lat"])
        vehicle = Vehicle.from_point(network, veh_data["id"], point, on_node=True)
        vehicles[veh_data["id"]] = vehicle

    assert vehicles[2758].position.u == 1776288149
    assert vehicles[6945].position.u == 348994024
    assert vehicles[2758].position.ec == 0.0
    assert vehicles[6945].position.ec == 0.0


def test_place_2_skip_1(network):
    id1 = 1776288149
    id2 = 348994024
    id3 = 1791474374

    p1 = network.node_to_point(id1)
    p2 = network.node_to_point(id2)
    p3 = network.node_to_point(id3)
    d = [
        {
            "id": 2758,
            "point": {"lat": p1.y, "lng": p1.x},
            "draggable": True,
            "visible": True,
            "tooltip": "VID : 2758",
        },
        {
            "id": 1111,
            "point": {"lat": p3.y, "lng": p3.x},
            "u": id1,
            "v": id2,
            "edge_cursor": 0.5,
            "draggable": True,
            "visible": True,
            "tooltip": "VID : 1111",
        },
        {
            "id": 6945,
            "point": {"lat": p2.y, "lng": p2.x},
            "draggable": True,
            "visible": True,
            "tooltip": "VID : 6945",
        },
    ]

    vehicles = {}
    for veh_data in d:
        point = Point(veh_data["point"]["lng"], veh_data["point"]["lat"])
        if "u" in veh_data and "v" in veh_data and "edge_cursor" in veh_data:
            # Create position from edge reference
            edge_ref = EdgeRef(veh_data["u"], veh_data["v"], veh_data["edge_cursor"])
            position = network.create_position_from_edge_ref(edge_ref)
            vehicle = Vehicle(network, veh_data["id"], position)
        else:
            vehicle = Vehicle.from_point(network, veh_data["id"], point, on_node=True)
        vehicles[veh_data["id"]] = vehicle

    assert vehicles[2758].position.u == id1
    assert vehicles[2758].position.ec == 0.0
    assert vehicles[6945].position.u == id2
    assert vehicles[6945].position.ec == 0.0

    assert vehicles[1111].position.u == id1
    assert vehicles[1111].position.ec == 0.5


# same as above but missing the edge_cursor which should trigger the placement of p3
def test_place_3(network):
    from shapely.geometry import Point

    p1 = network.node_to_point(1776288149)
    p2 = network.node_to_point(348994024)
    p3 = network.node_to_point(1791474374)
    d = [
        {
            "id": 2758,
            "point": {"lat": p1.y, "lng": p1.x},
            "draggable": True,
            "visible": True,
            "tooltip": "VID : 2758",
        },
        {
            "id": 1111,
            "point": {"lat": p3.y, "lng": p3.x},
            "u": 123,
            "v": 124,
            "draggable": True,
            "visible": True,
            "tooltip": "VID : 1111",
        },
        {
            "id": 6945,
            "point": {"lat": p2.y, "lng": p2.x},
            "draggable": True,
            "visible": True,
            "tooltip": "VID : 6945",
        },
    ]

    vehicles = {}
    for veh_data in d:
        point = Point(veh_data["point"]["lng"], veh_data["point"]["lat"])
        if "u" in veh_data and "v" in veh_data and "edge_cursor" in veh_data:
            edge_ref = EdgeRef(veh_data["u"], veh_data["v"], veh_data["edge_cursor"])
            position = network.create_position_from_edge_ref(edge_ref)
            vehicle = Vehicle(network, veh_data["id"], position)
        else:
            vehicle = Vehicle.from_point(network, veh_data["id"], point, on_node=True)
        vehicles[veh_data["id"]] = vehicle

    assert vehicles[2758].position.u == 1776288149
    assert vehicles[2758].position.ec == 0.0
    assert vehicles[6945].position.u == 348994024
    assert vehicles[6945].position.ec == 0.0
    # p3 is now place because edge_cursor is missing
    assert vehicles[1111].position.u == 1791474374
    assert vehicles[1111].position.ec == 0.0


# same as above but missing the edge_cursor which should trigger the placement of p3
def test_place_middle(network):
    from shapely.geometry import Point

    p1 = network.node_to_point(1776288149)
    p2 = network.node_to_point(348994024)
    d = [
        {
            "id": 2758,
            "point": {"lat": p1.y + (p2.y - p1.y) / 3, "lng": p1.x + (p2.x - p1.x) / 3},
            "draggable": True,
            "visible": True,
            "tooltip": "VID : 2758",
        },
    ]

    vehicles = {}
    for veh_data in d:
        point = Point(veh_data["point"]["lng"], veh_data["point"]["lat"])
        vehicle = Vehicle.from_point(network, veh_data["id"], point, on_node=True)
        vehicles[veh_data["id"]] = vehicle

    assert vehicles[2758].position.u == 1776288149
    assert vehicles[2758].position.ec == 0.0

    d = [
        {
            "id": 2758,
            "point": {"lat": p1.y + 2 * (p2.y - p1.y) / 3, "lng": p1.x + 2 * (p2.x - p1.x) / 3},
            "draggable": True,
            "visible": True,
            "tooltip": "VID : 2758",
        },
    ]

    vehicles = {}
    for veh_data in d:
        point = Point(veh_data["point"]["lng"], veh_data["point"]["lat"])
        vehicle = Vehicle.from_point(network, veh_data["id"], point, on_node=True)
        vehicles[veh_data["id"]] = vehicle

    assert vehicles[2758].position.u == 348994024
    assert vehicles[2758].position.ec == 0.0
