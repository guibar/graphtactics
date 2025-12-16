import pytest
from shapely import Point

from graphtactics.road_network import EdgeRef, RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory, network_dir
from graphtactics.utils import highway_value_to_int


@pytest.fixture(scope="module")
def road_network_noailles() -> RoadNetwork:
    factory = RoadNetworkFactory()
    return factory.create("noailles")


@pytest.fixture(scope="module")
def road_network_60() -> RoadNetwork:
    factory = RoadNetworkFactory()
    return factory.create("60")


def test_path():
    assert "data/networks" == network_dir


def test_highway_value_to_int():
    assert highway_value_to_int(["residential", "unclassified"]) == 1  # residential > unclassified
    assert highway_value_to_int(["tertiary_link", "residential"]) == 2  # tertiary > residential
    assert highway_value_to_int(["secondary", "tertiary_link"]) == 3  # secondary > tertiary
    assert highway_value_to_int(["motorway_link", "motorway"]) == 6  # motorway = motorway_link
    assert highway_value_to_int(["abc_link", "abc"]) == -1  # unknown highway types


# There are 2 edges between these 2 points, one unclassified and one residential, the residential should be picked up
def test_get_edge_data_317717938_7055380499(road_network_noailles):
    dict_edge = road_network_noailles.get_edge_data((1637479141, 1637479136))
    assert "bearing" in dict_edge
    assert "highway" in dict_edge
    assert "oneway" in dict_edge

    assert road_network_noailles.get_edge_data((317717938, 7055380499), "highway") == "secondary"
    assert road_network_noailles.get_edge_data((317717938, 7055380499), "length") == 93.182
    assert road_network_noailles.get_edge_data((317717938, 7055380499), "ref") == "D 2"
    assert road_network_noailles.get_edge_data((317717938, 7055380499), "name") == "Rue Simonet"
    assert road_network_noailles.get_edge_data((317717938, 7055380499), "oneway")


# One tertiary and one residential -> should get tertiary
def test_get_edge_data_1785952350_2423986443(road_network_noailles):
    assert len(road_network_noailles.get_edge_data((2447852537, 661117435))) == 12
    assert road_network_noailles.get_edge_data((2447852537, 661117435), "highway") == "secondary"
    assert road_network_noailles.get_edge_data((2447852537, 661117435), "length") == pytest.approx(681.251, 0.001)
    dict_1 = road_network_noailles.get_edge_data((2447852537, 661117435))
    dict_2 = road_network_noailles.get_edge_data((661117435, 2447852537))
    # the data on those attribute comes differently depending on which way we ask which is good
    assert dict_1["length"] == pytest.approx(dict_2["length"], 0.001)
    del dict_1["bearing"]
    del dict_1["geometry"]
    del dict_1["length"]
    del dict_1["name"]
    del dict_2["bearing"]
    del dict_2["geometry"]
    del dict_2["length"]
    del dict_2["name"]

    assert dict_1 == dict_2


def test_are_on_same_roundabout(road_network_noailles):
    assert road_network_noailles.are_on_same_round_about(317717951, 317717947)
    assert road_network_noailles.are_on_same_round_about(317717947, 317717951)
    assert road_network_noailles.are_on_same_round_about(2425344949, 317717951)
    assert not road_network_noailles.are_on_same_round_about(317717924, 317717951)
    assert not road_network_noailles.are_on_same_round_about(317717951, 317717924)


def test_put_on_graph(road_network_60):
    pts = road_network_60.get_random_points_in_boundary(20)
    road_network_60.points_to_edge_refs(pts)


def test_get_random_points_on_graph(road_network_60):
    positions = road_network_60.get_random_positions(10, on_node=True, seed=100)

    assert len(positions) == 10
    for position in positions:
        assert position.u != position.v  # on node means u is the node, v is a valid end node
        assert position.ec == 0.0

    positions = road_network_60.get_random_positions(10, on_node=False, seed=100)
    for position in positions:
        assert position.u != position.v
        assert position.ec > 0.0


def test_coords_to_point(road_network_60):
    """Test that coords_to_point correctly interpolates points along an edge."""
    # Get a random edge to test with
    position = road_network_60.get_random_positions(1, on_node=False, seed=42)[0]
    u: int = position.u
    v: int = position.v

    # Get the actual node points
    point_u: Point = road_network_60.node_to_point(u)
    point_v: Point = road_network_60.node_to_point(v)

    # Test ec=0.0 should give us point u

    point_at_0: Point = road_network_60.edge_ref_to_point(EdgeRef(u, v, 0.0))
    assert point_at_0.equals(point_u), "ec=0.0 should return the start node point"

    # Test ec=1.0 should give us point v
    point_at_1: Point = road_network_60.edge_ref_to_point(EdgeRef(u, v, 1.0))
    assert point_at_1.equals(point_v), "ec=1.0 should return the end node point"

    # Test ec=0.5 should give us a point that is neither u nor v
    point_at_half: Point = road_network_60.edge_ref_to_point(EdgeRef(u, v, 0.5))
    assert not point_at_half.equals(point_u), "ec=0.5 should not equal the start node"
    assert not point_at_half.equals(point_v), "ec=0.5 should not equal the end node"
