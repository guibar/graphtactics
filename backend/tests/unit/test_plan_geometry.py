"""Unit tests for PlanGeometry class."""

from datetime import datetime

import pytest

from graphtactics.escape_model import EscapeModel
from graphtactics.plan_geometry import PlanGeometry
from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory
from graphtactics.scenario import Scenario
from graphtactics.vehicle import Vehicle


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


@pytest.fixture
def plan_geometry(sample_escape_model: EscapeModel, road_network_d2: RoadNetwork) -> PlanGeometry:
    """Create a PlanGeometry for testing."""
    return PlanGeometry(sample_escape_model, road_network_d2)


class TestPlanGeometryIsochrone:
    """Test PlanGeometry isochrone methods."""

    def test_get_isochrone(self, plan_geometry: PlanGeometry):
        """Test getting the isochrone polygon."""
        isochrone = plan_geometry.get_isochrone()

        # Should return a Polygon or MultiPolygon
        assert isochrone is not None
        assert hasattr(isochrone, "geom_type")

    def test_isochrone_caching(self, plan_geometry: PlanGeometry):
        """Test that isochrone is computed once and cached."""
        isochrone1 = plan_geometry.get_isochrone()
        isochrone2 = plan_geometry.get_isochrone()

        # Should be the same object (cached)
        assert isochrone1 is isochrone2


class TestPlanGeometryLinestrings:
    """Test PlanGeometry linestring generation methods."""

    def test_get_linestrings(self, plan_geometry: PlanGeometry):
        """Test getting categorized linestrings."""
        linestrings = plan_geometry.get_linestrings()

        assert isinstance(linestrings, dict)
        assert "past" in linestrings
        assert "uncontrolled" in linestrings
        assert "before_control" in linestrings
        assert "after_control" in linestrings

        # Each category should be a list
        for _key, value in linestrings.items():
            assert isinstance(value, list)

    def test_linestrings_caching(self, plan_geometry: PlanGeometry):
        """Test that linestrings are computed once and cached."""
        linestrings1 = plan_geometry.get_linestrings()
        linestrings2 = plan_geometry.get_linestrings()

        # Should be the same object (cached)
        assert linestrings1 is linestrings2

    def test_to_linestring_basic(self, plan_geometry: PlanGeometry, sample_escape_model: EscapeModel):
        """Test internal _to_linestring with no position arguments (basic case)."""
        root = sample_escape_model.tree_dict[0]
        # Get a path with at least 2 nodes
        some_leaf = root.leaves[0]
        path = list(some_leaf.path)

        if len(path) >= 2:
            linestring = plan_geometry._to_linestring(path)
            assert linestring is not None
            assert hasattr(linestring, "coords")
            assert len(linestring.coords) >= 2

    def test_to_linestring_single_node(self, plan_geometry: PlanGeometry, sample_escape_model: EscapeModel):
        """Test _to_linestring with a single node - returns point-to-point."""
        root = sample_escape_model.tree_dict[0]
        some_leaf = root.leaves[0]  # Use a real node, not the virtual root (osmid=0)
        path = [some_leaf]

        linestring = plan_geometry._to_linestring(path)
        assert linestring is not None
        # Point-to-point linestring should have 2 identical coordinates
        assert len(linestring.coords) == 2


class TestPlanGeometryEscapeNodes:
    """Test PlanGeometry escape node methods."""

    def test_get_escape_nodes(self, plan_geometry: PlanGeometry):
        """Test getting escape node lists."""
        covered, uncovered = plan_geometry.get_escape_nodes()

        assert isinstance(covered, list)
        assert isinstance(uncovered, list)

    def test_escape_nodes_properties(self, plan_geometry: PlanGeometry):
        """Test escape node property accessors."""
        covered = plan_geometry.escape_nodes_covered
        uncovered = plan_geometry.escape_nodes_uncovered

        assert isinstance(covered, list)
        assert isinstance(uncovered, list)


class TestPlanGeometryWithPositions:
    """Test PlanGeometry methods that use present positions."""

    def test_linestring_with_pos_after(self, plan_geometry: PlanGeometry, sample_escape_model: EscapeModel):
        """Test _to_linestring with pos_after argument."""
        # First compute isochrone to populate present_positions
        plan_geometry.get_isochrone()

        njois = sample_escape_model.get_njois()

        if njois:
            njoi = njois[0]
            if njoi.osmid in plan_geometry._present_positions:
                pos = plan_geometry._present_positions[njoi.osmid]
                njoi_path = list(njoi.path)

                linestring = plan_geometry._to_linestring(njoi_path, pos_after=pos)
                assert linestring is not None
                assert hasattr(linestring, "coords")

    def test_linestring_with_pos_before(self, plan_geometry: PlanGeometry, sample_escape_model: EscapeModel):
        """Test _to_linestring with pos_before argument."""
        # First compute isochrone to populate present_positions
        plan_geometry.get_isochrone()

        njois = sample_escape_model.get_njois()
        if njois:
            njoi = njois[0]
            if njoi.osmid in plan_geometry._present_positions:
                pos = plan_geometry._present_positions[njoi.osmid]
                for leaf in njoi.leaves:
                    path = list(leaf.path)
                    njoi_idx = next((i for i, n in enumerate(path) if n == njoi), None)
                    if njoi_idx is not None:
                        future_path = path[njoi_idx:]
                        if len(future_path) >= 1:
                            linestring = plan_geometry._to_linestring(future_path, pos_before=pos)
                            assert linestring is not None
                            assert hasattr(linestring, "coords")
                            break
