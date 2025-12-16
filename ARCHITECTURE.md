# Architecture Documentation

## Overview

GraphTactics is a decision support system designed to assist Operational Command in intercepting vehicles on a road network. It calculates optimal interception points based on the suspect's last known position and elapsed time.

## System Context

The system consists of three main components:

1. **Frontend**: A Vue.js web application for the user interface.
2. **Backend**: A Python FastAPI application providing proper interception logic and data management.
3. **Data Persistence**:  Uses GeoPackages (`.gpkg`) and GraphML (`.graphml`) files to store road network graphs and spatial data. There is currently no traditional relational database; state is transient or derived from these files.

## Component View

### Backend (`/backend`)

The backend is built with Python 3.11+ and FastAPI.

#### Key Modules

* **`graphtactics/app.py`**: The entry point for the FastAPI application. Defines routes and initializes the application.
* **`graphtactics/road_network_factory.py`**:  Responsible for generating road network data.
  * Downloads data from OpenStreetMap (via OSMnx) and data.gouv.fr (department boundaries).
  * Processes raw data into a graph representation suitable for routing.
  * Outputs `.graphml` (graph structure) and `.gpkg` (spatial layers) files.
* **`graphtactics/road_network.py`**: Defines the `RoadNetwork` class, which holds the in-memory representation of the graph and associated GeoDataFrames (nodes, edges).
* **`graphtactics/planner.py`**:  Contains the core core logic for strategy calculation. It uses the road network to determine optimal vehicle placements.
* **`graphtactics/adversary.py`**:  Models the suspect vehicle's potential movements.
* **`graphtactics/vehicle.py`**:  Models potential interception vehicles.

### Frontend (`/frontend`)

The frontend is a Vue.js application.

* **Map Visualization**: Uses Leaflet (via `vue2-leaflet` or similar) to display the road network, vehicle positions, and interception strategy on a map.
* **Integration**: Communicates with the backend REST API to fetch network data and request strategy calculations.

## Data Flow

1. **Network Generation**:
    * Admin/Dev runs `RoadNetworkFactory`.
    * Downloads OSM data => Processes Graph => Saves to `data/networks/{zone}.(graphml|gpkg)`.

2. **Application Startup**:
    * Backend loads pre-generated network files into memory.

3. **Interception Request**:
    * User inputs last known position and time in Frontend.
    * Frontend sends request to Backend API.
    * Backend (`Planner`) calculates reachable nodes and optimal intercept points.
    * Backend returns strategy to Frontend.
    * Frontend renders the strategy.

## Deployment

* **Infrastructure**: Deployed on Google Cloud Run using Terraform (`/terraform`).
* **Containerization**: Dockerfile in `/backend` for containerizing the API.
