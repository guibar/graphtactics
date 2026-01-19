"""
FastAPI application for the GraphTactics interception planning system.

This module provides the web API for:
- Initializing and switching between different road networks.
- Generating random vehicle distributions for simulations.
- Running the interception planner to generate optimal pursuit strategies.
- Handling GeoJSON serialization for frontend visualization.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from graphtactics.plan_geometry import PlanGeometry
from graphtactics.planner import Planner
from graphtactics.scenario import Scenario
from graphtactics.serializer import Serializer

from .config import AVAILABLE_NETWORKS
from .dtos import NetworkDTO, PlanDTO, ScenarioDTO, VehicleDTO
from .planner import Plan
from .road_network import RoadNetwork
from .road_network_factory import RoadNetworkFactory
from .vehicle import Vehicle

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI application.

    Pre-loads the road network on startup to avoid latency on the first request.
    The network is stored in `app.state.network` for access across all routes.
    """
    network_name = os.environ.get("NEO_GRAPH_NAME", "60")  # Default to network "60"
    logger.info(f"Initializing network: {network_name}")

    factory: RoadNetworkFactory = RoadNetworkFactory()
    # The factory handles loading and caching of network data (OSM, edges, etc.)
    app.state.network = factory.create(network_name)
    app.state.factory = factory
    yield
    # Cleanup resources (if any) on shutdown


app = FastAPI(
    title="GraphTactics Interception API",
    description="API for generating vehicle interception plans",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS to allow interaction from the frontend (usually running on a different port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Broad CORS policy for development/flexibility
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for consistent error responses."""
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "path": request.url.path},
    )


@app.get("/")
async def root():
    """Health check endpoint to verify the API is running."""
    return {"message": "The GraphTactics back-end is alive!!"}


@app.get("/networks")
async def list_networks() -> dict[str, list[str] | str]:
    """Retrieve the names of all supported road networks and the one currently in use.

    Returns:
        A dictionary containing "available" (list of names) and "current" (active name).
    """
    network: RoadNetwork = cast(RoadNetwork, app.state.network)
    return {"available": AVAILABLE_NETWORKS, "current": network.name}


@app.get("/network/{network_name}", response_model=NetworkDTO)
async def switch_network(network_name: str) -> NetworkDTO:
    """Switch to another road network.

    This triggers a reload of the network data (graph, escape points, etc.) via the factory.

    Args:
        network_name: The identifier of the network to load.

    Returns:
        The initialization data (boundaries, etc.) for the new network.

    Raises:
        HTTPException: 404 if the network name is invalid.
    """
    if network_name not in AVAILABLE_NETWORKS:
        raise HTTPException(
            status_code=404, detail=f"Network '{network_name}' not found. Available: {AVAILABLE_NETWORKS}"
        )

    logger.info(f"Switching to network: {network_name}")
    factory = cast(RoadNetworkFactory, app.state.factory)
    app.state.network = factory.create(network_name)
    network_json = await get_init_data()
    return network_json


@app.get("/init", response_model=NetworkDTO)
async def get_init_data() -> NetworkDTO:
    """Get the core metadata for the current network.

    Includes map boundaries (bbox), the centroid for initial center-viewing,
    and the list of predefined escape points.

    Returns:
        NetworkDTO detailing the current network configuration.
    """
    network: RoadNetwork = app.state.network
    network_json = NetworkDTO.from_domain(network)
    return network_json


@app.get("/random_vehicles", response_model=list[VehicleDTO])
async def get_random_vehicles(nb_vh: int = 5) -> list[VehicleDTO]:
    """Generate a pseudo-random distribution of vehicles across the network.

    Useful for initializing simulations or testing the planner.

    Args:
        nb_vh: How many vehicles to spawn.

    Returns:
        A list of Vehicle DTOs with their assigned positions and a unique ID.
    """
    network = cast(RoadNetwork, app.state.network)
    vehicles = Vehicle.get_random_vehicles(network, nb_vh)
    vehicles_json = [VehicleDTO.from_domain(v, network) for v in vehicles.values()]
    return vehicles_json


@app.post("/generate")
async def generate_plan(scenario_dto: ScenarioDTO):
    """The central orchestration point for generating an interception plan.

    This endpoint:
    1. Converts the incoming request (DTO) into rich domain objects (Scenario).
    2. Runs the OR-Tools based `Planner` to find optimal vehicle-to-node assignments.
    3. Computes the `PlanGeometry` for visual display (e.g., path lines, coverage areas).
    4. Optionally serializes the result to disk for historical analysis or reproduction.

    Args:
        scenario_dto: Data containing vehicle locations and the adversary's LKP.

    Returns:
        PlanDTO containing assignments, trajectories, and coverage status for visualization.
    """
    # Map the web format to the internal domain model
    scenario: Scenario = scenario_dto.to_domain(app.state.network)

    # Execute the optimization engine
    planner: Planner = Planner(app.state.network, scenario)
    plan: Plan = planner.plan_interception()

    # Post-process results into geometries (GeoJSON friendly) for the frontend
    geometry: PlanGeometry = PlanGeometry(planner.escape_model, app.state.network)

    # Persistence in gpkg format (easy to open with QGIS) for debugging or logging purposes
    if os.environ.get("NEO_SAVE_PLANS", default="True") == "True":
        serializer: Serializer = Serializer(app.state.network, scenario, plan, geometry)
        serializer.save()

    plan_json = PlanDTO.from_domain(scenario, plan, planner.escape_model, geometry, app.state.network)
    return plan_json


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
