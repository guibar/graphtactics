from pathlib import Path

import pytest
from geopandas import GeoDataFrame
from pandas import Index
from shapely.geometry import Point

from graphtactics.road_network_factory import boundary_from_name, extract_zip_url, get_departments_gdf
from graphtactics.utils import get_star_polygon, get_tolls


@pytest.fixture
def fixtures_dir():
    """Return the path to the fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def test_departements_zip(fixtures_dir):
    """Return path to test departements zip file."""
    return fixtures_dir / "test_departements.zip"


@pytest.fixture
def extracted_departements(tmp_path, monkeypatch, test_departements_zip):
    """
    Extract the test departements zip file and return the extraction directory.
    """

    def mock_urlopen(url):
        class MockResponse:
            def read(self):
                return test_departements_zip.read_bytes()

        return MockResponse()

    monkeypatch.setattr("graphtactics.road_network_factory.urlopen", mock_urlopen)

    dest_folder = tmp_path / "extracted"
    dest_folder.mkdir()

    extract_zip_url("http://fake-url.com", str(dest_folder))

    return dest_folder


def test_get_polygon():
    gdf = GeoDataFrame(
        [Point(-1, -1), Point(1, 1), Point(-1, 1), Point(1, -1)],
        crs="EPSG:4326",
        columns=Index(["geometry"]),
    )
    polygon = get_star_polygon(gdf)
    assert list(polygon.exterior.coords) == [
        (-1.0, -1.0),
        (1.0, -1.0),
        (1.0, 1.0),
        (-1.0, 1.0),
        (-1.0, -1.0),
    ]


def test_get_tolls():
    assert len(get_tolls(boundary_from_name("60"))) == 33


def test_extract_zip_url(tmp_path, monkeypatch, test_departements_zip):
    """Test that extract_zip_url properly extracts files from a zip."""

    def mock_urlopen(url):
        class MockResponse:
            def read(self):
                return test_departements_zip.read_bytes()

        return MockResponse()

    monkeypatch.setattr("graphtactics.road_network_factory.urlopen", mock_urlopen)

    dest_folder = tmp_path / "test_extract"
    dest_folder.mkdir()

    # Actually test extract_zip_url
    extract_zip_url("http://fake-url.com", str(dest_folder))

    # Verify extraction worked
    assert len(list(dest_folder.iterdir())) > 0
    assert (dest_folder / "departements-20180101.shp").exists()
    assert (dest_folder / "departements-20180101.shx").exists()
    assert (dest_folder / "departements-20180101.dbf").exists()


def test_get_departements_gdf(extracted_departements):
    """Test loading departements GeoDataFrame using extracted test files."""

    # Point get_departments_gdf to use the extracted test files
    gdf = get_departments_gdf(dir=str(extracted_departements))
    assert len(gdf) == 5
