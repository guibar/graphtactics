# GraphTactics

[GraphTactics](https://github.com/GraphTactics/backend) is a project which evolved out of [NeoTAC](https://www.eig.numerique.gouv.fr/defis/neotac/), a project started at the Gendarmerie Nationale under the program Entrepreneur d'Interet Général (EIG 4).

It is a decision tool for helping Operational Command deploy very quickly a strategy in emergency situations when a vehicle needs to be located and intercepted on the road network. The given:
    - the last known position of the suspect vehicle
    - the time elapsed since it was last seen at that position
    - the real-time position of the available vehicles (which here are just random locations),

GraphTactics will determine the destination each police vehicle should go to in order to maximize the probability of spotting the suspect vehicle.

Operationnal areas are defined in terms of french "départements" which are the unit of opération of gendarmerie commandement.

The project is organized around 3 main components:

- a backend written in Python and exposing a REST API
- a frontend written in Vue.js
- a terraform configuration to deploy the application on Google Cloud Run

The application is deployed on Google Cloud Run and can be accessed at:

- **Frontend:** [https://graphtactics-frontend-ovktfcw4mq-ew.a.run.app](https://graphtactics-frontend-ovktfcw4mq-ew.a.run.app)
- **Backend API:** [https://graphtactics-backend-ovktfcw4mq-ew.a.run.app](https://graphtactics-backend-ovktfcw4mq-ew.a.run.app)

Only a few departments are available because some pre-processing of OpenStreetMap data is required to generate the road network data files and this has only been done for a few departments.

The code is release under the [GNU General Public License v3.0](https://choosealicense.com/licenses/gpl-3.0/).

## Backend Installation

### Prerequisites

- Python 3.11 or higher
- Git

### Installation with pip (traditional method)

```bash
# Clone the repository
git clone git@github.com:GraphTactics/backend.git
cd backend

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts/activate

# Install the project in development mode
pip install -e .

# To install with development dependencies (tests, linting)
pip install -e .[dev]
```

### Installation with UV (faster)

[UV](https://github.com/astral-sh/uv) is an ultra-fast Python package manager (10-100x faster than pip).

```bash
# Install UV
pip install uv

# Create a virtual environment and install the project
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts/activate
uv pip install -e .

# To install with development dependencies
uv pip install -e .[dev]
```

### Configuration

```bash
# Configure environment variables
source ./vars.env
```

## Data Files Used by GraphTactics

To operate, the GraphTactics algorithm needs a representation of the road network for the operational area. The road network data is stored in 2 files:

1. A graphml file that contains a graph representation of the road network
2. A gpkg file that contains 2 geodataframes (nodes and edges) pinning the graph elements to their geographical location.

### Generating graphml and gpkg Files

Files are generated for a defined geographic area. A geographic area can be specified in 3 different ways:

1. By a department number (example 60 for Oise)
2. By a department number followed by 'c', in which case this is interpreted as the area comprising the department and all neighboring departments. For example, 30c corresponds to the area formed by the union of departments 30, 34, 12, 48, 07, 84 and 13
3. By a latitude/longitude rectangle that must have been previously defined in the `boxes` dictionary located in the osm_graph_factory.py file

To generate the file corresponding to an area:

1. Navigate to the backend project root
2. Ensure that the PYTHONAPP environment variable has the path to the project root as its value. The easiest way to do this is to run `source ./vars.env`
3. Execute the following command:

```bash
python3 interceptor/osm_graph_factory.py prepare {area_name}
```

Following this command, the files

- ./data/networks/{area_name}.graphml
- ./data/networks/{area_name}.gpkg

should have been created.

## GraphTactics Frontend

### Project setup

```bash
npm install
```

### Compiles and hot-reloads for development

```bash
npm run serve
```

### Compiles and minifies for production

```bash
npm run build
```

### Lints and fixes files

```bash
npm run lint
```

### Customize configuration

See [Configuration Reference](https://cli.vuejs.org/config/).
