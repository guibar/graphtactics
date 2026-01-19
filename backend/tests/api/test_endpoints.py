"""
Tests for FastAPI endpoints using TestClient.
"""

import os
from collections.abc import Generator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from graphtactics.app import app

# Set environment variable before importing app
os.environ["NEO_GRAPH_NAME"] = "60"


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Create a test client with lifespan context."""
    with TestClient(app) as c:
        yield c


class TestBasicEndpoints:
    """Test basic API endpoints."""

    def test_root(self, client: TestClient):
        """Test root endpoint returns welcome message."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "The GraphTactics back-end is alive!!"}

    def test_networks_list(self, client: TestClient):
        """Test listing available networks."""
        response = client.get("/networks")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert "available" in data
        assert "current" in data
        available = cast(list[Any], data["available"])
        assert isinstance(available, list)
        assert len(available) > 0
        assert data["current"] == "60"

    def test_init_data(self, client: TestClient):
        """Test initialization data endpoint."""
        response = client.get("/init")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert "boundaries" in data
        assert "origin_coords" in data
        assert "escape_points" in data
        assert "lat" in data["origin_coords"]
        assert "lng" in data["origin_coords"]


class TestNetworkSwitching:
    """Test network switching functionality."""

    def test_switch_to_valid_network(self, client: TestClient):
        """Test switching to a valid network."""
        response = client.get("/network/noailles")
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert "boundaries" in data
        assert "origin_coords" in data
        assert "escape_points" in data
        assert "lat" in data["origin_coords"]
        assert "lng" in data["origin_coords"]

        # Verify the network actually changed
        response = client.get("/networks")
        data_networks: dict[str, Any] = response.json()
        assert data_networks["current"] == "noailles"

        # Switch back to 60
        client.get("/network/60")

    def test_switch_to_invalid_network(self, client: TestClient):
        """Test switching to an invalid network returns 404."""
        response = client.post("/networks/invalid_network")
        assert response.status_code == 404
        data: dict[str, Any] = response.json()
        assert "not found" in data["detail"].lower()


class TestRandomVehicles:
    """Test random vehicle generation."""

    def test_random_vehicles_default(self, client: TestClient):
        """Test generating random vehicles with default count."""
        response = client.get("/random_vehicles")
        assert response.status_code == 200
        vehicles: list[dict[str, Any]] = response.json()
        assert isinstance(vehicles, list)
        assert len(vehicles) == 5  # Default

        # Check vehicle structure
        vehicle = vehicles[0]
        assert "id" in vehicle
        assert "position" in vehicle
        assert "lat" in vehicle["position"]
        assert "lng" in vehicle["position"]

    def test_random_vehicles_custom_count(self, client: TestClient):
        """Test generating random vehicles with custom count."""
        response = client.get("/random_vehicles?nb_vh=3")
        assert response.status_code == 200
        vehicles: list[dict[str, Any]] = response.json()
        assert len(vehicles) == 3


class TestGeneratePlan:
    """Test plan generation endpoint."""

    def test_generate_plan_valid_scenario(self, client: TestClient):
        """Test generating a plan with valid scenario data."""
        # First get some random vehicles
        vehicles_response = client.get("/random_vehicles?nb_vh=2")
        vehicles: list[dict[str, Any]] = vehicles_response.json()

        # Create scenario with adversary and vehicles
        scenario: dict[str, Any] = {
            "lkp": {"lat": 49.35, "lng": 2.08},
            "time_elapsed": 300,  # seconds
            "vehicles": [
                {"id": v["id"], "position": {"lat": v["position"]["lat"], "lng": v["position"]["lng"]}}
                for v in vehicles
            ],
        }

        response = client.post("/generate", json=scenario)
        assert response.status_code == 200
        plan: dict[str, Any] = response.json()
        assert "origin" in plan
        assert "vehicles" in plan
        assert "assignments" in plan
        assert "destinations" in plan
        assert "stats" in plan

    def test_generate_plan_invalid_scenario(self, client: TestClient):
        """Test generating a plan with invalid scenario data."""
        invalid_scenario: dict[str, Any] = {
            "origin_coords": {"lat": "invalid", "lng": 2.08},  # Invalid lat
            "time_delta": 300,
            "vehicles": [],
        }

        response = client.post("/generate", json=invalid_scenario)
        assert response.status_code == 422  # Validation error

    def test_generate_plan_missing_fields(self, client: TestClient):
        """Test generating a plan with missing required fields."""
        incomplete_scenario = {
            "origin_coords": {"lat": 49.35, "lng": 2.08},
            # Missing time_delta, vehicles
        }

        response = client.post("/generate", json=incomplete_scenario)
        assert response.status_code == 422  # Validation error


class TestOpenAPISchema:
    """Test OpenAPI documentation endpoints."""

    def test_docs_endpoint_exists(self, client: TestClient):
        """Test that /docs endpoint is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_json_endpoint(self, client: TestClient):
        """Test that OpenAPI JSON schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema: dict[str, Any] = response.json()
        assert "openapi" in schema
        assert "paths" in schema
        assert "/random_vehicles" in schema["paths"]
        assert "/generate" in schema["paths"]
