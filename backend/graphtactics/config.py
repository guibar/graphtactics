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

# Configuration - modify these variables
GITHUB_TOKEN: str | None = os.environ.get("GITHUB_TOKEN")
REPO_NAME: str = "guibar/graphtactics"
RELEASE_TAG: str = "osm-networks-v1.1"
RELEASE_NAME: str = "Network Files v1.1"
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
