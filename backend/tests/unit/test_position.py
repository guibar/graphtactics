"""Unit tests for the Position dataclass."""

import pytest

from graphtactics.position import Position
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory


@pytest.fixture(scope="module")
def road_network_st_quentin():
    """Small test network for position tests."""
    factory = RoadNetworkFactory()
    return factory.create("st_quentin")


class TestPositionValidation:
    """Test Position validation logic."""

    def test_edge_cursor_must_be_between_0_and_1(self, road_network_st_quentin: RoadNetwork):
        """Test that edge cursor must be in valid range [0, 1]."""
        # Valid edge cursors should work
        pos = Position(u=123, v=456, ec=0.0)
        assert pos.ec == 0.0

        pos = Position(u=123, v=456, ec=1.0)
        assert pos.ec == 1.0

        # Invalid edge cursors should raise ValueError
        with pytest.raises(ValueError, match="Edge cursor must be between 0 and 1"):
            Position(u=123, v=456, ec=-0.1)

        with pytest.raises(ValueError, match="Edge cursor must be between 0 and 1"):
            Position(u=123, v=456, ec=1.1)


class TestPositionCreation:
    """Test Position creation from network methods."""

    def test_position_from_point(self, road_network_st_quentin: RoadNetwork):
        """Test creating Position from a geographic point."""
        point = road_network_st_quentin.pos_to_point(road_network_st_quentin.central_position)
        pos = road_network_st_quentin.create_position_from_point(point)

        # Check that init_point is preserved
        assert pos.init_point == point
        # Check that u, v, ec are valid
        assert pos.u is not None
        assert pos.v is not None
        assert 0 <= pos.ec <= 1


class TestFloatsEqual:
    """Test the floats_equal static method."""

    def test_identical_floats_are_equal(self):
        """Test that identical floats are considered equal."""
        assert Position.floats_equal(1.0, 1.0)
        assert Position.floats_equal(0.0, 0.0)
        assert Position.floats_equal(-1.5, -1.5)

    def test_floats_within_epsilon_are_equal(self):
        """Test that floats within epsilon are considered equal."""
        assert Position.floats_equal(1.0, 1.0 + 1e-10)
        assert Position.floats_equal(1.0, 1.0 - 1e-10)
        assert Position.floats_equal(0.0, 1e-10)

    def test_floats_outside_epsilon_are_not_equal(self):
        """Test that floats outside epsilon are not considered equal."""
        assert not Position.floats_equal(1.0, 1.0 + 1e-8)
        assert not Position.floats_equal(1.0, 1.0 - 1e-8)
        assert not Position.floats_equal(0.0, 1e-8)

    def test_custom_epsilon(self):
        """Test using a custom epsilon value."""
        assert Position.floats_equal(1.0, 1.1, epsilon=0.2)
        assert not Position.floats_equal(1.0, 1.3, epsilon=0.2)
