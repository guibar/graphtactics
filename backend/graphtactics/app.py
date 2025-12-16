"""
FastAPI application for NeoTAC interception planning.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from geopandas import GeoDataFrame
from shapely.geometry import Point

from .dtos import PlanResponse, ScenarioDTO, VehicleResponse
from .planner import Planner
from .road_network_factory import RoadNetworkFactory
from .serializer import Serializer
from .vehicle import Vehicle

logger = logging.getLogger(__name__)

# Available networks (from github_network_files.py)
AVAILABLE_NETWORKS = ["30", "60", "60c", "67", "67c", "74", "74c", "82", "d2", "noailles", "st_quentin", "vauvert"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the network on startup and cleanup on shutdown."""
    network_name = os.environ.get("NEO_GRAPH_NAME", "60")  # Default to 60
    logger.info(f"Initializing network: {network_name}")
    factory = RoadNetworkFactory()
    app.state.network = factory.create(network_name)
    app.state.factory = factory
    yield
    # Cleanup would go here if needed


app = FastAPI(
    title="GraphTactics Interception API",
    description="API for generating vehicle interception plans",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Welcome message."""
    return {"message": "The GraphTactics back-end is alive!!"}


@app.get("/networks")
async def list_networks():
    """
    List available networks.

    Returns:
        Dictionary with available networks and current network
    """
    return {"available": AVAILABLE_NETWORKS, "current": app.state.network.name}


@app.post("/networks/{network_name}")
async def switch_network(network_name: str):
    """
    Switch to a different network.

    Args:
        network_name: Name of the network to load

    Returns:
        Same payload as GET /init for the newly loaded network.
    """
    if network_name not in AVAILABLE_NETWORKS:
        raise HTTPException(
            status_code=404, detail=f"Network '{network_name}' not found. Available: {AVAILABLE_NETWORKS}"
        )

    try:
        logger.info(f"Switching to network: {network_name}")
        app.state.network = app.state.factory.create(network_name)
        return await get_init_data()
    except Exception as e:
        logger.error(f"Error switching network: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/init")
async def get_init_data():
    """
    Get initial data for the map (boundaries, origin, escape points).

    Returns:
        Dictionary with boundaries, origin coordinates, and escape points
    """
    network = app.state.network
    d_orig_pt: Point = network.central_point
    boundaries_gdf = GeoDataFrame(
        [{"geometry": network.boundary, "id": "inner"}, {"geometry": network.boundary_buff, "id": "outer"}],
        crs="EPSG:4326",
    )

    return {
        "boundaries": boundaries_gdf.__geo_interface__,
        "origin_coords": {"lat": d_orig_pt.y, "lng": d_orig_pt.x},
        "escape_points": network.out_intersections_df.__geo_interface__,
    }


@app.get("/random_vehicles", response_model=list[VehicleResponse])
async def get_random_vehicles(nb_vh: int = 5):
    """
    Generate random vehicles on the network.

    Args:
        nb_vh: Number of vehicles to generate (default: 5)

    Returns:
        List of vehicle response DTOs
    """
    network = app.state.network
    vehicles = Vehicle.get_random_vehicles(network, nb_vh)
    return [VehicleResponse.from_domain(v) for v in vehicles.values()]


@app.post("/generate")
async def generate_plan(scenario_dto: ScenarioDTO):
    """
    Generate an interception plan from the scenario.

    Args:
        scenario_input: Scenario DTO with adversary and vehicles

    Returns:
        Complete interception plan with assignments and analysis
    """
    try:
        # Convert DTO to domain object (pass network)
        scenario = scenario_dto.to_domain(app.state.network)

        # Generate plan
        planner = Planner(app.state.network, scenario.vehicles, scenario.adversary.candidate_nodes)
        plan = planner.plan_interception()

        # Save plan if enabled
        if os.environ.get("NEO_SAVE_PLANS", default="True") == "True":
            serializer = Serializer(app.state.network, scenario, plan)
            serializer.save()

        return PlanResponse.from_domain(scenario, plan)

    except Exception as e:
        logger.error(f"Error generating plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
