"""Unit tests for the Adversary class."""

from datetime import datetime

import pytest
from shapely.geometry import Point

from graphtactics.adversary import Adversary
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory


@pytest.fixture(scope="module")
def road_network_st_quentin() -> RoadNetwork:
    """Small test network for adversary tests."""
    factory = RoadNetworkFactory()
    return factory.create("st_quentin")


class TestAdversaryInitialization:
    """Test Adversary initialization."""

    def test_valid_adversary_creation(self, road_network_st_quentin: RoadNetwork):
        """Test creating an adversary with a valid position."""
        network: RoadNetwork = road_network_st_quentin
        lk_point: Point = network.pos_to_point(network.central_position)
        last_time_seen: datetime = datetime.fromisoformat("2020-12-01T09:00:00")
        time_elapsed: int = 300

        adversary: Adversary = Adversary(network, lk_point, last_time_seen, time_elapsed)

        assert adversary.network == network
        assert adversary.last_time_seen == last_time_seen
        assert adversary.time_elapsed == time_elapsed
        assert adversary.lkp_position is not None
        assert network.has_in_boundary(adversary.lkp_position)

    def test_adversary_position_snapped_to_network(self, road_network_st_quentin: RoadNetwork):
        """Test that adversary position is snapped to the network."""
        network: RoadNetwork = road_network_st_quentin
        # Use the central position which is guaranteed to be in the boundary
        lk_point: Point = network.pos_to_point(network.central_position)
        last_time_seen: datetime = datetime.fromisoformat("2020-12-01T09:00:00")
        time_elapsed: int = 300

        adversary: Adversary = Adversary(network, lk_point, last_time_seen, time_elapsed)

        # The position should be snapped to the network
        assert adversary.lkp_position.u is not None
        assert adversary.lkp_position.v is not None
        # For on_node=False, ec should be between 0 and 1
        assert 0 <= adversary.lkp_position.ec <= 1

    def test_adversary_outside_boundary_raises_error(self, road_network_st_quentin: RoadNetwork):
        """Test that creating an adversary outside the network boundary raises ValueError."""
        network: RoadNetwork = road_network_st_quentin
        # Use a point far outside the network boundary
        lk_point: Point = Point(0.0, 0.0)  # This should be outside st_quentin
        last_time_seen: datetime = datetime.fromisoformat("2020-12-01T09:00:00")
        time_elapsed: int = 300

        with pytest.raises(ValueError, match="is not a valid position"):
            Adversary(network, lk_point, last_time_seen, time_elapsed)


class TestAdversaryRepresentation:
    """Test Adversary string representation."""

    def test_repr_contains_position_and_time(self, road_network_st_quentin: RoadNetwork):
        """Test that __repr__ includes position and time information."""
        network: RoadNetwork = road_network_st_quentin
        lk_point: Point = network.pos_to_point(network.central_position)
        last_time_seen: datetime = datetime.fromisoformat("2020-12-01T09:00:00")
        time_elapsed: int = 300

        adversary: Adversary = Adversary(network, lk_point, last_time_seen, time_elapsed)
        repr_str: str = repr(adversary)

        assert "Adversary" in repr_str
        assert "lkp=" in repr_str
        assert "last_time_seen=" in repr_str
        assert "2020-12-01" in repr_str


class TestAdversaryAttributes:
    """Test Adversary attribute access and properties."""

    def test_adversary_attributes_accessible(self, road_network_st_quentin: RoadNetwork):
        """Test that all adversary attributes are accessible."""
        network: RoadNetwork = road_network_st_quentin
        lk_point: Point = network.pos_to_point(network.central_position)
        last_time_seen: datetime = datetime.fromisoformat("2020-12-01T09:00:00")
        time_elapsed: int = 300

        adversary: Adversary = Adversary(network, lk_point, last_time_seen, time_elapsed)

        # All attributes should be accessible
        assert hasattr(adversary, "network")
        assert hasattr(adversary, "lkp_position")
        assert hasattr(adversary, "last_time_seen")
        assert hasattr(adversary, "time_elapsed")

        # Check types
        assert isinstance(adversary.time_elapsed, int)
        assert isinstance(adversary.last_time_seen, datetime)

    def test_different_time_elapsed_values(self, road_network_st_quentin: RoadNetwork):
        """Test adversary with different time_elapsed values."""
        network: RoadNetwork = road_network_st_quentin
        lk_point: Point = network.pos_to_point(network.central_position)
        last_time_seen: datetime = datetime.fromisoformat("2020-12-01T09:00:00")

        # Test with various time_elapsed values
        for time_elapsed in [0, 60, 300, 600, 3600]:
            adversary: Adversary = Adversary(network, lk_point, last_time_seen, time_elapsed)
            assert adversary.time_elapsed == time_elapsed
