"""Shared test fixtures for GraphTactics test suite."""

import logging
from pathlib import Path

import pytest

from graphtactics.road_network_factory import RoadNetworkFactory

logging.getLogger("pyogrio").setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def plans_fixtures_dir() -> Path:
    """Return the path to the plans fixtures directory."""
    return Path(__file__).parent / "fixtures" / "plans"


@pytest.fixture(scope="session")
def road_network_60():
    """Shared fixture for network '60' - largest test network."""
    factory = RoadNetworkFactory()
    return factory.create("60")


@pytest.fixture(scope="session")
def road_network_d2():
    """Shared fixture for network 'd2' - medium test network."""
    factory = RoadNetworkFactory()
    return factory.create("d2")


@pytest.fixture(scope="session")
def road_network_noailles():
    """Shared fixture for network 'noailles' - small test network."""
    factory = RoadNetworkFactory()
    return factory.create("noailles")


@pytest.fixture(scope="session")
def road_network_st_quentin():
    """Shared fixture for network 'st_quentin' - smallest test network."""
    factory = RoadNetworkFactory()
    return factory.create("st_quentin")
