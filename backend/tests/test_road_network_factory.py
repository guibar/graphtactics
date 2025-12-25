import json
import os
import tempfile

import pytest
from networkx import MultiDiGraph

from graphtactics.road_network import RoadNetwork
from graphtactics.road_network_factory import RoadNetworkFactory


class TestIsDepartementCode:
    """Tests for RoadNetworkFactory._is_departement_code method."""

    def test_is_departement_code(self):
        """Test valid 2-digit département codes."""
        factory = RoadNetworkFactory()

        # Standard metropolitan departments
        for code in ["01", "60", "75", "99", "2A", "2B", "60c"]:
            factory.name = code
            assert factory._is_departement_code(), f"{code} should be valid"

        invalid_codes = ["1", "100", "2C", "60cc", "abc", "60x", "noailles", " "]

        for code in invalid_codes:
            factory.name = code
            assert not factory._is_departement_code(), f"{code} should be invalid"


class TestIsValidBbox:
    """Tests for RoadNetworkFactory.is_valid_bbox method."""

    @pytest.fixture(scope="class")
    def temp_bbox_file(self):
        """Create a temporary bbox file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "valid_box": [2.0, 3.0, 45.0, 46.0],
                    "st_quentin": [2.07, 2.11, 49.32404, 49.35212],
                    "edges": [-5.0, 10.0, 41.0, 51.0],
                    "invalid_west_low": [-6.0, 3.0, 45.0, 46.0],
                    "invalid_west_high": [11.0, 12.0, 45.0, 46.0],
                    "invalid_east_low": [-6.0, -5.5, 45.0, 46.0],
                    "invalid_east_high": [5.0, 11.0, 45.0, 46.0],
                    "invalid_south_low": [2.0, 3.0, 40.0, 45.0],
                    "invalid_south_high": [2.0, 3.0, 52.0, 53.0],
                    "invalid_north_low": [2.0, 3.0, 40.0, 40.5],
                    "invalid_north_high": [2.0, 3.0, 45.0, 52.0],
                    "invalid_order": [3.0, 2.0, 45.0, 46.0],
                    "not_a_list": "invalid",
                    "wrong_length": [2.0, 3.0, 45.0],
                    "has_string": [2.0, "three", 45.0, 46.0],
                },
                f,
            )
            temp_path = f.name

        yield temp_path

        # Cleanup
        os.unlink(temp_path)

    def test_valid_bbox_exists(self, temp_bbox_file):
        """Test that valid bbox returns True."""
        factory = RoadNetworkFactory(bbox_file=temp_bbox_file)
        factory.name = "valid_box"
        assert factory.is_valid_bbox()

    def test_valid_bbox_with_real_data(self, temp_bbox_file):
        """Test with actual st_quentin data."""
        factory = RoadNetworkFactory(bbox_file=temp_bbox_file)
        factory.name = "st_quentin"
        assert factory.is_valid_bbox()

    def test_bbox_not_found_returns_false(self, temp_bbox_file):
        """Test that non-existent bbox name returns False (not an exception)."""
        factory = RoadNetworkFactory(bbox_file=temp_bbox_file)
        factory.name = "nonexistent"
        assert not factory.is_valid_bbox()

    def test_bbox_edge_values_west(self, temp_bbox_file):
        """Test edge values for west longitude."""
        factory = RoadNetworkFactory(bbox_file=temp_bbox_file)

        factory.name = "edges"
        assert factory.is_valid_bbox()

    def test_invalid_box_values(self, temp_bbox_file):
        """Test that west longitude out of range raises ValueError."""
        factory = RoadNetworkFactory(bbox_file=temp_bbox_file)

        factory.name = "invalid_west_low"
        with pytest.raises(ValueError, match="Invalid east/west values"):
            factory.is_valid_bbox()

        factory.name = "invalid_west_high"
        with pytest.raises(ValueError, match="Invalid east/west values"):
            factory.is_valid_bbox()

        factory.name = "invalid_east_low"
        with pytest.raises(ValueError, match="Invalid east/west values"):
            factory.is_valid_bbox()

        factory.name = "invalid_east_high"
        with pytest.raises(ValueError, match="Invalid east/west values"):
            factory.is_valid_bbox()

        factory.name = "invalid_south_low"
        with pytest.raises(ValueError, match="Invalid north/south values"):
            factory.is_valid_bbox()

        factory.name = "invalid_south_high"
        with pytest.raises(ValueError, match="Invalid north/south values"):
            factory.is_valid_bbox()

        factory.name = "invalid_north_low"
        with pytest.raises(ValueError, match="Invalid north/south values"):
            factory.is_valid_bbox()

        factory.name = "invalid_north_high"
        with pytest.raises(ValueError, match="Invalid north/south values"):
            factory.is_valid_bbox()

        factory.name = "invalid_order"
        with pytest.raises(ValueError, match="Invalid east/west values"):
            factory.is_valid_bbox()

        factory.name = "not_a_list"
        with pytest.raises(ValueError, match="there must be 4 numbers"):
            factory.is_valid_bbox()

        factory.name = "wrong_length"
        with pytest.raises(ValueError, match="there must be 4 numbers"):
            factory.is_valid_bbox()

        factory.name = "has_string"
        with pytest.raises(ValueError, match="there must be 4 numbers"):
            factory.is_valid_bbox()

    def test_bbox_file_not_found(self):
        """Test that FileNotFoundError is raised if bbox file doesn't exist."""
        factory = RoadNetworkFactory(bbox_file="/nonexistent/path/boxes.json")
        factory.name = "test"
        with pytest.raises(FileNotFoundError):
            factory.is_valid_bbox()

    def test_bbox_invalid_json(self):
        """Test that JSONDecodeError is raised for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ this is not valid json }")
            temp_path = f.name

        try:
            factory = RoadNetworkFactory(bbox_file=temp_path)
            factory.name = "test"
            with pytest.raises(json.JSONDecodeError):
                factory.is_valid_bbox()
        finally:
            os.unlink(temp_path)

    def test_bbox_with_actual_file(self):
        """Test with the actual data/boxes.json file."""
        factory = RoadNetworkFactory()

        # Test valid entries from the actual file
        for name in ["st_quentin", "vauvert", "noailles", "d2", "oise"]:
            factory.name = name
            assert factory.is_valid_bbox(), f"{name} should be valid in boxes.json"

        # Test non-existent entry
        factory.name = "nonexistent_box"
        assert not factory.is_valid_bbox()


class TestCreate:
    """Tests for RoadNetworkFactory.create method."""

    def test_create_from_cache_when_files_exist(self, monkeypatch):
        """Test that create() returns network from cache if files exist."""
        # Setup: Create a factory
        factory = RoadNetworkFactory()

        # Mock the file existence check to return True (simulating cache hit)
        monkeypatch.setattr("os.path.isfile", lambda path: True)

        # Create a mock RoadNetwork to return
        from unittest.mock import MagicMock

        mock_network = MagicMock(spec=RoadNetwork)
        mock_network.name = "60"

        # Track calls
        instantiate_called = []
        download_called = []
        create_files_called = []

        # Mock the instantiate_from_files method
        def mock_instantiate():
            instantiate_called.append(True)
            return mock_network

        monkeypatch.setattr(factory, "instantiate_from_files", mock_instantiate)

        # Mock download_files to track if it's called
        def mock_download(name):
            download_called.append(True)
            return False  # Return False so it doesn't proceed

        monkeypatch.setattr("graphtactics.github_network_files.download_files", mock_download)

        # Mock create_files_from_boundary to track if it's called
        def mock_create(boundary):
            create_files_called.append(True)

        monkeypatch.setattr(factory, "create_files_from_boundary", mock_create)

        # Call create
        result = factory.create("60")

        # Assert: Network was returned
        assert result == mock_network
        assert result.name == "60"

        # Assert: instantiate_from_files was called once
        assert len(instantiate_called) == 1

        # Assert: Download and generation were NOT called (cache hit)
        assert len(download_called) == 0, "download_files_from_github should not be called when files exist in cache"
        assert len(create_files_called) == 0, (
            "create_files_from_boundary should not be called when files exist in cache"
        )

        # Assert: Factory attributes were set correctly
        assert factory.name == "60"
        assert factory.graphml_path.endswith("60.graphml")
        assert factory.gpkg_path.endswith("60.gpkg")

    def test_download_and_instantiate_from_github(self, tmp_path):
        """Test downloading files from GitHub and instantiating network (integration test)."""

        network_name = "noailles"
        # Create factory with default GitHub settings
        factory = RoadNetworkFactory()

        # Use tmp_path as cache_dir to avoid polluting actual cache
        factory.cache_dir = tmp_path

        # Verify cache is empty initially
        graphml_path = tmp_path / f"{network_name}.graphml"
        gpkg_path = tmp_path / f"{network_name}.gpkg"
        assert not graphml_path.exists()
        assert not gpkg_path.exists()

        # Download and create network
        network = factory.create(network_name)

        # Assert: Network was created successfully
        assert network is not None
        assert isinstance(network, RoadNetwork)
        assert network.name == network_name

        # Assert: Files were downloaded to cache
        assert graphml_path.exists()
        assert gpkg_path.exists()

        # Assert: Network has expected attributes
        assert network.graph is not None
        assert isinstance(network.graph, MultiDiGraph)
        assert len(network.graph.nodes()) == 202
        assert len(network.graph.edges()) == 432
        assert network.nodes_df is not None
        assert len(network.nodes_df) == 202
        assert network.edges_df is not None
        assert len(network.edges_df) == 432

    def test_create_network_from_scratch(self, tmp_path):
        """Test creating files from boundary (integration test)."""
        # Create factory with default GitHub settings
        # Use tmp_path as cache_dir to avoid polluting actual cache

        factory = RoadNetworkFactory(cache_dir=tmp_path)
        # name: str = "st_quentin"
        # factory.create(name, create_from_scratch=True)

        # # Assert: Files were created successfully
        # graphml_path = tmp_path / f"{name}.graphml"
        # gpkg_path = tmp_path / f"{name}.gpkg"
        # assert graphml_path.exists()
        # assert gpkg_path.exists()

        name = "90"
        factory.create(name, create_from_scratch=True)

        # Assert: Files were created successfully
        graphml_path = tmp_path / f"{name}.graphml"
        gpkg_path = tmp_path / f"{name}.gpkg"
        assert graphml_path.exists()
        assert gpkg_path.exists()
