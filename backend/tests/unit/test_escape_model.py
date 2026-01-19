"""Unit tests for EscapeModel components."""

from datetime import datetime
from typing import Any

import pytest

from graphtactics.escape_model import EscapeModel
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.tree_node import CoverStatus, TreeNode
from graphtactics.vehicle import Vehicle

# approx is partially unknown in pytest, using Any to satisfy strict Pyright
approx: Any = pytest.approx  # type: ignore


@pytest.fixture(scope="module")
def road_network_d2():
    """Medium test network for escape model tests."""
    factory = RoadNetworkFactory()
    return factory.create("d2")


@pytest.fixture
def sample_escape_model(road_network_d2: RoadNetwork):
    """Create an escape model for testing."""
    lk_point = road_network_d2.pos_to_point(road_network_d2.central_position)
    last_time_seen = datetime.fromisoformat("2020-12-01T09:00:00")
    vehicles = Vehicle.get_random_vehicles(road_network_d2, 3, seed=123)
    time_elapsed = 300

    scenario = Scenario(road_network_d2, lk_point, last_time_seen, vehicles, time_elapsed)
    return scenario.adversary.escape_model


class TestTreeNode:
    """Test TreeNode class."""

    def test_tree_node_creation(self):
        """Test creating a TreeNode."""
        node = TreeNode(osmid=123, parent=None, time_reached=100.0, score=50, is_njoi=True)

        assert node.osmid == 123
        assert node.parent is None
        assert node.time_reached == 100.0
        assert node.score == 50
        assert node.is_njoi is True
        assert node.cover == CoverStatus.UNCOVERED
        assert node.is_control_node is False

    def test_tree_node_with_parent(self):
        """Test creating a TreeNode with a parent."""
        parent = TreeNode(osmid=100, parent=None, time_reached=50.0, score=25, is_njoi=False)
        child = TreeNode(osmid=200, parent=parent, time_reached=100.0, score=50, is_njoi=True)

        assert child.parent == parent
        assert child in parent.children

    def test_tree_node_id_assignment(self):
        """Test that TreeNode assigns IDs when candidate_id is provided."""
        # Now IDs are passed explicitly by EscapeModel, not auto-incremented
        node1 = TreeNode(osmid=1, parent=None, time_reached=10.0, score=5, is_njoi=False, candidate_id=0)
        node2 = TreeNode(osmid=2, parent=None, time_reached=20.0, score=10, is_njoi=False, candidate_id=1)

        # Both should have IDs since candidate_id was provided
        assert node1.id == 0
        assert node2.id == 1

    def test_tree_node_no_id_without_candidate_id(self):
        """Test that TreeNode has None id when candidate_id is not provided."""
        node = TreeNode(osmid=1, parent=None, time_reached=10.0, score=5, is_njoi=False)
        assert node.id is None


class TestEscapeModelInitialization:
    """Test EscapeModel initialization."""

    def test_escape_model_creation(self, sample_escape_model: EscapeModel):
        """Test that escape model is created successfully."""
        assert sample_escape_model is not None
        assert hasattr(sample_escape_model, "network")
        assert hasattr(sample_escape_model, "lk_position")
        assert hasattr(sample_escape_model, "lk_point")
        assert hasattr(sample_escape_model, "time_elapsed")

    def test_escape_model_has_candidate_nodes(self, sample_escape_model: EscapeModel):
        """Test that escape model identifies candidate nodes."""
        assert hasattr(sample_escape_model, "candidate_nodes")
        assert isinstance(sample_escape_model.candidate_nodes, list)


class TestEscapeModelMethods:
    """Test EscapeModel methods."""

    def test_get_time_to_any_node(self, sample_escape_model: EscapeModel):
        """Test getting time to a specific node."""
        # Get a node from the times_to_nodes dict
        if sample_escape_model.times_to_nodes:
            # These values correspond to the "d2" network center (bbox centroid)
            assert sample_escape_model.lk_point.x == approx(2.06974, abs=1e-4)
            assert sample_escape_model.lk_point.y == approx(49.387, abs=1e-3)

            # Ensure lk_position is not None for type checking and verify snapped coordinates
            assert sample_escape_model.lk_position is not None
            assert sample_escape_model.lk_position.u == 5548769432
            assert sample_escape_model.lk_position.v == 5546329872
            assert sample_escape_model.lk_position.ec == approx(0.086, abs=1e-3)

            u = sample_escape_model.lk_position.u
            # add the time elapse to get the time it takes to go from LK to u
            time_u = sample_escape_model.times_to_nodes.get(u, float("inf")) + sample_escape_model.time_elapsed
            v = sample_escape_model.lk_position.v
            # add the time elapse to get the time it takes to go from LK to v
            time_v = sample_escape_model.times_to_nodes.get(v, float("inf")) + sample_escape_model.time_elapsed

            time_u_v = sample_escape_model.network.get_edge_travel_time(u, v)
            assert time_u + time_v == approx(time_u_v, abs=1e-5)

    def test_get_stats(self, sample_escape_model: EscapeModel):
        """Test getting escape model statistics."""
        stats = sample_escape_model.get_stats()

        assert isinstance(stats, dict)
        assert "nb_escape_nodes" in stats
        assert "nb_njois" in stats
        assert "nb_candidate_nodes" in stats
        assert "max_possible_score" in stats

        # All values should be non-negative
        assert stats["nb_escape_nodes"] >= 0
        assert stats["nb_njois"] >= 0
        assert stats["nb_candidate_nodes"] >= 0
        assert stats["max_possible_score"] >= 0

    def test_set_cover_status(self, sample_escape_model: EscapeModel):
        """Test the bottom-up propagation of cover status."""
        root = sample_escape_model.tree_dict[0]

        # Initially everything is UNCOVERED
        sample_escape_model.set_cover_status()
        assert root.cover == CoverStatus.UNCOVERED

        # Mark all leaves of one branch as COVERED
        some_leaf = root.leaves[0]
        for node in some_leaf.path:
            if node != root:
                node.cover = CoverStatus.COVERED

        sample_escape_model.set_cover_status()
        # If one leaf is covered, the ancestors must be either COVERED (if all children covered)
        # or MIXED (if some children are uncovered)
        assert root.cover in [CoverStatus.COVERED, CoverStatus.MIXED]
        assert root.cover != CoverStatus.UNCOVERED

    def test_get_njois(self, sample_escape_model: EscapeModel):
        """Test getting the nodes just outside the isochrone."""
        njois = sample_escape_model.get_njois()

        assert isinstance(njois, list)
        # All NJOIs should have is_njoi=True
        for njoi in njois:
            assert njoi.is_njoi is True
