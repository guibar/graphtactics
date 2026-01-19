import os

import pytest
from fastapi.testclient import TestClient

from graphtactics.road_network_factory import RoadNetworkFactory

# Set environment before importing app
os.environ["NEO_GRAPH_NAME"] = "60"
from graphtactics.app import app


@pytest.fixture(scope="module")
def client():
    """Create a test client with lifespan context."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def network():
    """Get the network instance for direct testing."""
    factory = RoadNetworkFactory()
    return factory.create("60")


def test_random_vehicles(client: TestClient) -> None:
    response = client.get("/random_vehicles?nb_vh=5")
    assert response.status_code == 200
    json_data = response.json()
    assert len(json_data) == 5
    for jd in json_data:
        assert "id" in jd
        assert "position" in jd
        assert "lat" in jd["position"]
        assert "lng" in jd["position"]
