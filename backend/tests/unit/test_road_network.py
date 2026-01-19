from typing import Any, cast

import pytest
from shapely import Point

from graphtactics.position import Position
from graphtactics.road_network import HighwayRank, RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory

# approx is partially unknown in pytest, using Any to satisfy strict Pyright
approx: Any = pytest.approx  # type: ignore


@pytest.fixture(scope="module")
def road_network_noailles() -> RoadNetwork:
    factory = RoadNetworkFactory()
    return factory.create("noailles")


@pytest.fixture(scope="module")
def road_network_60() -> RoadNetwork:
    factory = RoadNetworkFactory()
    return factory.create("60")


def test_place_points(road_network_60: RoadNetwork) -> None:
    id1 = 1776288149
    id2 = 348994024
    id3 = 1791474374

    p1 = road_network_60.node_to_point(id1)
    p2 = road_network_60.node_to_point(id2)
    p3 = road_network_60.node_to_point(id3)

    position1 = road_network_60.create_position_from_point(p1, on_node=False)
    position2 = road_network_60.create_position_from_point(p2, on_node=False)
    position3 = road_network_60.create_position_from_point(p3, on_node=False)

    assert position1.u == id1 or position1.v == id1
    assert position2.u == id2 or position2.v == id2
    assert position3.u == id3 or position3.v == id3
    assert position1.ec == 0.0 or position1.ec == 1.0
    assert position2.ec == 0.0 or position2.ec == 1.0
    assert position3.ec == 0.0 or position3.ec == 1.0


def test_edge_quantifier():
    assert RoadNetwork.edge_quantifier({"highway": ["residential", "unclassified"]}) == HighwayRank.RESIDENTIAL.value
    assert RoadNetwork.edge_quantifier({"highway": ["tertiary_link", "residential"]}) == HighwayRank.TERTIARY.value
    assert RoadNetwork.edge_quantifier({"highway": ["secondary", "tertiary_link"]}) == HighwayRank.SECONDARY.value
    assert RoadNetwork.edge_quantifier({"highway": ["motorway_link", "motorway"]}) == HighwayRank.MOTORWAY.value
    assert RoadNetwork.edge_quantifier({"highway": ["abc_link", "abc"]}) == HighwayRank.UNCLASSIFIED.value


# There are 2 edges between these 2 points, one unclassified and one residential, the residential should be picked up
def test_get_edge_data_317717938_7055380499(road_network_noailles: RoadNetwork):
    dict_edge = road_network_noailles.graph.get_edge_data(1637479141, 1637479136, 0)
    assert "bearing" in dict_edge
    assert "highway" in dict_edge
    assert "oneway" in dict_edge

    assert road_network_noailles.graph.get_edge_data(317717938, 7055380498, 0)["highway"] == "secondary"
    assert road_network_noailles.graph.get_edge_data(317717938, 7055380498, 0)["length"] == approx(20.513, 0.001)
    assert road_network_noailles.graph.get_edge_data(317717938, 7055380498, 0)["ref"] == "D 2"
    assert road_network_noailles.graph.get_edge_data(317717938, 7055380498, 0)["name"] == "Rue Simonet"
    assert road_network_noailles.graph.get_edge_data(317717938, 7055380498, 0)["oneway"]


# One tertiary and one residential -> should get tertiary
def test_get_edge_data_1785952350_2423986443(road_network_noailles: RoadNetwork):
    assert len(road_network_noailles.graph.get_edge_data(2447852537, 661117435, 0)) == 13
    assert road_network_noailles.graph.get_edge_data(2447852537, 661117435, 0)["highway"] == "secondary"
    assert road_network_noailles.graph.get_edge_data(2447852537, 661117435, 0)["length"] == approx(681.251, 0.001)
    dict_1 = cast(dict[str, Any], road_network_noailles.graph.get_edge_data(2447852537, 661117435, 0))
    dict_2 = cast(dict[str, Any], road_network_noailles.graph.get_edge_data(661117435, 2447852537, 0))
    # the data on those attribute comes differently depending on which way we ask which is good
    assert dict_1["length"] == approx(dict_2["length"], 0.001)
    del dict_1["bearing"]
    del dict_1["geometry"]
    del dict_1["length"]
    del dict_1["name"]
    del dict_1["travel_time"]
    del dict_2["bearing"]
    del dict_2["geometry"]
    del dict_2["length"]
    del dict_2["name"]
    del dict_2["travel_time"]

    assert dict_1 == dict_2


def test_get_random_points_on_graph(road_network_60: RoadNetwork):
    positions = road_network_60.get_random_positions(10, on_node=True, seed=100)

    assert len(positions) == 10
    for position in positions:
        assert position.u != position.v  # on node means u is the node, v is a valid end node
        assert position.ec == 0.0

    positions = road_network_60.get_random_positions(10, on_node=False, seed=100)
    for position in positions:
        assert position.u != position.v
        assert position.ec > 0.0


def test_to_point(road_network_60: RoadNetwork):
    """Test that to_point correctly interpolates points along an edge."""
    # Get a random edge to test with
    position = road_network_60.get_random_positions(1, on_node=False, seed=42)[0]
    u: int = position.u
    v: int = position.v

    # Get the actual node points
    point_u: Point = road_network_60.node_to_point(u)
    point_v: Point = road_network_60.node_to_point(v)

    # Test ec=0.0 should give us point u
    pos_at_0 = Position(u=u, v=v, ec=0.0)
    point_at_0: Point = road_network_60.pos_to_point(pos_at_0)
    assert point_at_0.equals(point_u), "ec=0.0 should return the start node point"

    # Test ec=1.0 should give us point v
    pos_at_1 = Position(u=u, v=v, ec=1.0)
    point_at_1: Point = road_network_60.pos_to_point(pos_at_1)
    assert point_at_1.equals(point_v), "ec=1.0 should return the end node point"

    # Test ec=0.5 should give us a point that is neither u nor v
    pos_at_half = Position(u=u, v=v, ec=0.5)
    point_at_half: Point = road_network_60.pos_to_point(pos_at_half)
    assert not point_at_half.equals(point_u), "ec=0.5 should not equal the start node"
    assert not point_at_half.equals(point_v), "ec=0.5 should not equal the end node"


def test_to_point_caching(road_network_60: RoadNetwork):
    """Test that to_point caches the result in position._point."""
    position = road_network_60.get_random_positions(1, on_node=False, seed=42)[0]

    # First call - should compute and cache
    point1 = road_network_60.pos_to_point(position)
    assert position._point is not None
    assert position._point == point1

    # Second call - should return cached value
    point2 = road_network_60.pos_to_point(position)
    assert point1 is point2  # Same object due to caching
