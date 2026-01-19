from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch
from shapely import Point, Polygon

from graphtactics.road_network_factory import extract_zip_url, get_departments_gdf
from graphtactics.utils import (
    PrincipalAxes,
    get_balanced_polygon,
    get_points_principal_axes,
    project_points,
    unproject_points,
)


@pytest.fixture
def fixtures_dir():
    """Return the path to the fixtures directory."""
    # tests/unit/test_utils.py -> tests/fixtures/
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def test_departements_zip(fixtures_dir: Path):
    """Return path to test departements zip file."""
    return fixtures_dir / "test_departements.zip"


@pytest.fixture
def extracted_departements(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_departements_zip: Path):
    """
    Extract the test departements zip file and return the extraction directory.
    """

    def mock_urlopen(url: str):
        class MockResponse:
            def read(self):
                return test_departements_zip.read_bytes()

        return MockResponse()

    monkeypatch.setattr("graphtactics.road_network_factory.urlopen", mock_urlopen)

    dest_folder: Path = tmp_path / "extracted"
    dest_folder.mkdir()

    extract_zip_url("http://fake-url.com", dest_folder)

    return dest_folder


def test_extract_zip_url(tmp_path: Path, monkeypatch: MonkeyPatch, test_departements_zip: Path):
    """Test that extract_zip_url properly extracts files from a zip."""

    def mock_urlopen(url: str):
        class MockResponse:
            def read(self):
                return test_departements_zip.read_bytes()

        return MockResponse()

    monkeypatch.setattr("graphtactics.road_network_factory.urlopen", mock_urlopen)

    dest_folder = tmp_path / "test_extract"
    dest_folder.mkdir()

    # Actually test extract_zip_url
    extract_zip_url("http://fake-url.com", dest_folder)

    # Verify extraction worked
    assert len(list(dest_folder.iterdir())) > 0
    assert (dest_folder / "departements-20180101.shp").exists()
    assert (dest_folder / "departements-20180101.shx").exists()
    assert (dest_folder / "departements-20180101.dbf").exists()


def test_get_departements_gdf(extracted_departements: Path):
    """Test loading departements GeoDataFrame using extracted test files."""

    # Point get_departments_gdf to use the extracted test files
    gdf = get_departments_gdf(dir=extracted_departements)
    assert len(gdf) == 109


def test_project_unproject():
    # Long narrow rectangle in Marseille (lat 43.3)
    lat_long_unbalanced: list[Point] = [Point(5.3, 43.3), Point(5.301, 43.3), Point(5.301, 43.4), Point(5.3, 43.4)]

    proj_unbalanced = project_points(lat_long_unbalanced)
    unproj_balance: list[Point] = unproject_points(proj_unbalanced)

    for i in range(len(unproj_balance)):
        assert unproj_balance[i].x == pytest.approx(lat_long_unbalanced[i].x)  # type: ignore[reportUnknownMemberType]
        assert unproj_balance[i].y == pytest.approx(lat_long_unbalanced[i].y)  # type: ignore[reportUnknownMemberType]


def test_balanced():
    # Square (approximate 0.001 degree lon is 80m, let's use 0.001 lat too which is 111m)
    lat_long_balanced: list[Point] = [Point(5.3, 43.3), Point(5.301, 43.3), Point(5.301, 43.301), Point(5.3, 43.301)]
    projected_balanced = project_points(lat_long_balanced)

    axes: PrincipalAxes = get_points_principal_axes(projected_balanced)
    assert axes["major_span"] == pytest.approx(55.58232, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["minor_span"] == pytest.approx(40.59571, abs=1e-5)  # type: ignore[reportUnknownMemberType]

    assert axes["major_axis"] == pytest.approx(64.18093, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["minor_axis"] == pytest.approx(46.87548, abs=1e-5)  # type: ignore[reportUnknownMemberType]

    assert axes["major_vector"][0] == pytest.approx(-0.02913, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["major_vector"][1] == pytest.approx(0.99957, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["minor_vector"][0] == pytest.approx(-0.99957, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["minor_vector"][1] == pytest.approx(-0.02913, abs=1e-5)  # type: ignore[reportUnknownMemberType]

    assert axes["eigenvalues"][0] == pytest.approx(2197.31, abs=1e-2)  # type: ignore[reportUnknownMemberType]
    assert axes["eigenvalues"][1] == pytest.approx(4119.19, abs=1e-2)  # type: ignore[reportUnknownMemberType]

    assert axes["centroid"][0] == pytest.approx(886752.8222, abs=1e-4)  # type: ignore[reportUnknownMemberType]
    assert axes["centroid"][1] == pytest.approx(6247313.3477, abs=1e-4)  # type: ignore[reportUnknownMemberType]


def test_polygon_balanced():
    lat_long_balanced: list[Point] = [Point(5.3, 43.3), Point(5.301, 43.3), Point(5.301, 43.301), Point(5.3, 43.301)]
    polygon1 = Polygon(lat_long_balanced)
    polygon2 = get_balanced_polygon(lat_long_balanced)
    assert polygon1.equals(polygon2)


def test_unbalanced():
    # Square (approximate 0.001 degree lon is 80m, let's use 0.1 lat too which is 11100m)
    lat_long_unbalanced: list[Point] = [Point(5.3, 43.3), Point(5.301, 43.3), Point(5.301, 43.4), Point(5.3, 43.4)]
    projected_unbalanced = project_points(lat_long_unbalanced)

    axes: PrincipalAxes = get_points_principal_axes(projected_unbalanced)
    assert axes["major_span"] == pytest.approx(5558.02157, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["minor_span"] == pytest.approx(40.59571, abs=1e-5)  # type: ignore[reportUnknownMemberType]

    assert axes["major_axis"] == pytest.approx(6417.85049, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["minor_axis"] == pytest.approx(46.83526, abs=1e-5)  # type: ignore[reportUnknownMemberType]

    assert axes["major_vector"][0] == pytest.approx(-0.02913, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["major_vector"][1] == pytest.approx(0.99957, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["minor_vector"][0] == pytest.approx(-0.99957, abs=1e-5)  # type: ignore[reportUnknownMemberType]
    assert axes["minor_vector"][1] == pytest.approx(-0.02913, abs=1e-5)  # type: ignore[reportUnknownMemberType]

    assert axes["eigenvalues"][0] == pytest.approx(2193.54, abs=1e-2)  # type: ignore[reportUnknownMemberType]
    assert axes["eigenvalues"][1] == pytest.approx(41188805.00, abs=1e-2)  # type: ignore[reportUnknownMemberType]

    assert axes["centroid"][0] == pytest.approx(886592.53634, abs=1e-4)  # type: ignore[reportUnknownMemberType]
    assert axes["centroid"][1] == pytest.approx(6252813.45192, abs=1e-4)  # type: ignore[reportUnknownMemberType]


def test_polygon_unbalanced():
    lat_long_unbalanced: list[Point] = [Point(5.3, 43.3), Point(5.301, 43.3), Point(5.301, 43.4), Point(5.3, 43.4)]
    polygon1 = Polygon(lat_long_unbalanced)
    polygon2 = get_balanced_polygon(lat_long_unbalanced)
    assert not polygon1.equals(polygon2)

    assert polygon2.area > polygon1.area * 1.5
