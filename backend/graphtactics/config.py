"""
Configuration constants for GraphTactics.
"""

# Available network identifiers
import os
from pathlib import Path

from dotenv import load_dotenv

AVAILABLE_NETWORKS = ["30", "60", "60c", "67", "74", "82", "d2", "noailles", "st_quentin", "vauvert"]

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# Domain Constants
# =============================================================================

# Planner: Maximum speed threshold for filtering vehicles (80 km/h in m/s)
MAX_SPEED_M_PER_SECOND: float = 80000 / 3600

# Scenario: Default time margin in seconds for vehicle arrival before adversary
DEFAULT_TIME_MARGIN: int = 30

# Road Network Factory: Buffer distance around boundary polygons in meters
BUFFER_IN_METERS: int = 6000

# Escape Model: Scoring constants
SCORE_LAST_EDGE_FACTOR: int = 80  # Weight for the highway type of the last edge
SCORE_TIME_FACTOR: int = 480  # Weight for time-based score component
SCORE_TIME_CONSTANT: int = 900  # Time constant for exponential decay (10 min = neutral)

# =============================================================================
# GitHub / Release Configuration
# =============================================================================

GITHUB_TOKEN: str | None = os.environ.get("GITHUB_TOKEN")
REPO_NAME: str = "guibar/graphtactics"
RELEASE_TAG: str = "osm-networks-v1.2"
RELEASE_NAME: str = "Network Files v1.2"
RELEASE_DESCRIPTION: str = "Pre-generated network files some areas"

# Directory containing network files
DATA_DIR: Path = Path(__file__).parent.parent / "data"
NETWORK_DIR: Path = DATA_DIR / "networks"
DEPARTEMENTS_DATA_DIR: Path = DATA_DIR / "departements"

# Files to upload (modify this list)
ALL_NETWORK_FILES: list[str] = [f"{name}.graphml" for name in AVAILABLE_NETWORKS] + [
    f"{name}.gpkg" for name in AVAILABLE_NETWORKS
]

# departments_shp_zipped_url = "https://www.data.gouv.fr/en/datasets/r/eb36371a-761d-44a8-93ec-3d728bec17ce"
DEPARTEMENTS_SHP_ZIPPED_URL: str = "https://data-interne.ademe.fr/data-fair/api/v1/datasets/geo-contours-departements/data-files/GEO_Contours_Departements.zip"
DEPARTEMENTS_SHP_FILE_NAME: str = "Departements.shp"
DEPARTEMENTS_SHP_FILE_PATH: Path = DEPARTEMENTS_DATA_DIR / DEPARTEMENTS_SHP_FILE_NAME
