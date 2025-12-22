"""
Tests for FastAPI endpoints using TestClient.
"""

import os

import pytest
from fastapi.testclient import TestClient

# Set environment variable before importing app
os.environ["NEO_GRAPH_NAME"] = "60"

from graphtactics.app import app


@pytest.fixture(scope="module")
def client():
    """Create a test client with lifespan context."""
    with TestClient(app) as c:
        yield c


class TestBasicEndpoints:
    """Test basic API endpoints."""

    def test_root(self, client):
        """Test root endpoint returns welcome message."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "The GraphTactics back-end is alive!!"}

    def test_networks_list(self, client):
        """Test listing available networks."""
        response = client.get("/networks")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert "current" in data
        assert isinstance(data["available"], list)
        assert len(data["available"]) > 0
        assert data["current"] == "60"

    def test_init_data(self, client):
        """Test initialization data endpoint."""
        response = client.get("/init")
        assert response.status_code == 200
        data = response.json()
        assert "boundaries" in data
        assert "origin_coords" in data
        assert "escape_points" in data
        assert "lat" in data["origin_coords"]
        assert "lng" in data["origin_coords"]


class TestNetworkSwitching:
    """Test network switching functionality."""

    def test_switch_to_valid_network(self, client):
        """Test switching to a valid network."""
        response = client.get("/network/noailles")
        assert response.status_code == 200
        data = response.json()
        assert "boundaries" in data
        assert "origin_coords" in data
        assert "escape_points" in data
        assert "lat" in data["origin_coords"]
        assert "lng" in data["origin_coords"]

        # Verify the network actually changed
        response = client.get("/networks")
        assert response.json()["current"] == "noailles"

        # Switch back to 60
        client.get("/network/60")

    def test_switch_to_invalid_network(self, client):
        """Test switching to an invalid network returns 404."""
        response = client.post("/networks/invalid_network")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestRandomVehicles:
    """Test random vehicle generation."""

    def test_random_vehicles_default(self, client):
        """Test generating random vehicles with default count."""
        response = client.get("/random_vehicles")
        assert response.status_code == 200
        vehicles = response.json()
        assert isinstance(vehicles, list)
        assert len(vehicles) == 5  # Default

        # Check vehicle structure
        vehicle = vehicles[0]
        assert "id" in vehicle
        assert "position" in vehicle
        assert "lat" in vehicle["position"]
        assert "lng" in vehicle["position"]

    def test_random_vehicles_custom_count(self, client):
        """Test generating random vehicles with custom count."""
        response = client.get("/random_vehicles?nb_vh=3")
        assert response.status_code == 200
        vehicles = response.json()
        assert len(vehicles) == 3


class TestGeneratePlan:
    """Test plan generation endpoint."""

    def test_generate_plan_valid_scenario(self, client):
        """Test generating a plan with valid scenario data."""
        # First get some random vehicles
        vehicles_response = client.get("/random_vehicles?nb_vh=2")
        vehicles = vehicles_response.json()

        # Create scenario with adversary and vehicles
        scenario = {
            "origin_coords": {"lat": 49.35, "lng": 2.08},
            "time_delta": 300,  # seconds
            "vehicles": [
                {"id": v["id"], "lat_lng": {"lat": v["position"]["lat"], "lng": v["position"]["lng"]}} for v in vehicles
            ],
        }

        response = client.post("/generate", json=scenario)
        assert response.status_code == 200
        plan = response.json()
        assert "origin" in plan
        assert "vehicles" in plan
        assert "affectations" in plan
        assert "stats" in plan

    def test_generate_plan_invalid_scenario(self, client):
        """Test generating a plan with invalid scenario data."""
        invalid_scenario = {
            "origin_coords": {"lat": "invalid", "lng": 2.08},  # Invalid lat
            "time_delta": 300,
            "vehicles": [],
        }

        response = client.post("/generate", json=invalid_scenario)
        assert response.status_code == 422  # Validation error

    def test_generate_plan_missing_fields(self, client):
        """Test generating a plan with missing required fields."""
        incomplete_scenario = {
            "origin_coords": {"lat": 49.35, "lng": 2.08},
            # Missing time_delta, vehicles
        }

        response = client.post("/generate", json=incomplete_scenario)
        assert response.status_code == 422  # Validation error


class TestOpenAPISchema:
    """Test OpenAPI documentation endpoints."""

    def test_docs_endpoint_exists(self, client):
        """Test that /docs endpoint is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_json_endpoint(self, client):
        """Test that OpenAPI JSON schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
        assert "/random_vehicles" in schema["paths"]
        assert "/generate" in schema["paths"]
