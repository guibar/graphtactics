from __future__ import annotations

import random
from enum import Enum
from logging import getLogger

from shapely import LineString
from shapely.geometry import Point

from .position import Position
from .road_network import RoadNetwork

logger = getLogger(__name__)

MIN_REACHABLE_NODES_RATIO_FOR_ASSIGNABLE = 0.5  # Default value, adjust as needed


class VehicleStatus(Enum):
    """Current availability or assignment state of a vehicle within the planning process."""

    ASSIGNABLE = 0  # Vehicle is available and can be considered for an interception plan.
    TOO_CLOSE_TO_LKP = 1  # Vehicle is too near the adversary's Last Known Position to react.
    UNAVAILABLE = 2  # Vehicle exists but cannot be used (e.g., out of service).
    ASSIGNED = 3  # An ASSIGNABLE vehicle that has been designated for an interception mission.
    UNASSIGNED = 4  # An ASSIGNABLE vehicle that was not needed for the current plan.


# @dataclass
class Vehicle:
    """Represents an agent (police vehicle) capable of intercepting an adversary in the road network.

    Attributes:
        id: Unique identifier for the vehicle.
        network: Reference to the road network the vehicle is operating in.
        point: Current geometric position (Shapely Point) of the vehicle.
        position: Graph-snapped position (u, v, ec) on the road network.
        status: The current VehicleStatus.
        times_to_nodes: Dictionary mapping node OSMIDs to travel times from current position.
        paths_to_nodes: Dictionary mapping node OSMIDs to the sequence of nodes in the shortest path.
    """

    def __init__(self, network: RoadNetwork, id_vehicle: int, point: Point):
        """Initialize a Vehicle.

        Args:
            network: The road network instance.
            id_vehicle: Unique ID for the vehicle.
            point: Initial geographic location, this might be modified as it gets snapped to the network.
        """
        self.id: int = id_vehicle
        self.network: RoadNetwork = network
        self.point: Point = point
        self.position: Position | None = None
        self.status: VehicleStatus = VehicleStatus.ASSIGNABLE
        self.times_to_nodes: dict[int, float] = {}
        self.paths_to_nodes: dict[int, list[int]] = {}

    def __repr__(self):
        return f"Vehicle: id={self.id}, lat={self.point.y}, long={self.point.x}"

    def set_travel_times(self) -> None:
        """Calculate shortest paths and travel times from the vehicle's position to all reachable nodes.

        Updates `self.position` (a point on an edge), `self.times_to_nodes`, and `self.paths_to_nodes`.
        Updates `self.point` to the snapped location.
        """
        self.position, self.times_to_nodes, self.paths_to_nodes = self.network.get_times_and_paths_from_position(
            self.point, 0
        )
        self.point = self.network.pos_to_point(self.position)

    @classmethod
    def get_time_matrix(cls, vehicles: dict[int, Vehicle], candidate_nodes: list[int]) -> list[list[int]]:
        """Build a 2D matrix of travel times from multiple vehicles to all candidate nodes.

        Args:
            vehicles: Dictionary of vehicles.
            candidate_nodes: List of target node OSMIDs.

        Returns:
            A matrix where matrix[i][j] is the travel time for vehicle i to node j.
        """
        return [[int(vehicle.times_to_nodes[node]) for node in candidate_nodes] for vehicle in vehicles.values()]

    @classmethod
    def get_random_vehicles(
        cls, network: RoadNetwork, nb_vehicles: int, on_node=False, seed: int | None = None
    ) -> dict[int, Vehicle]:
        """Generate a number of vehicles randomly distributed on the road network.

        Args:
            network: The road network.
            nb_vehicles: Number of vehicles to generate.
            on_node: If True, vehicles are placed exactly on nodes, otherwise they can be along edges.
            seed: Random seed for reproducibility.

        Returns:
            Dictionary of randomly generated Vehicle instances.
        """
        rng = random.Random(seed)
        positions: list[Position] = network.get_random_positions(nb_vehicles, on_node=on_node, seed=seed)
        points: list[Point] = [network.pos_to_point(position) for position in positions]
        vehicle_ids: list[int] = [rng.randint(1000, 9999) for _ in range(nb_vehicles)]
        return {v_id: Vehicle(network, v_id, point) for v_id, point in zip(vehicle_ids, points, strict=True)}


class VehicleAssignment:
    """Represents an assignment of a vehicle to an interception node.

    Attributes:
        vehicle: The Vehicle instance assigned.
        destination_node: OSMID of the node the vehicle is assigned to.
        destination_point: Geographic location of the destination node.
        time_to_dest: Time it takes for the vehicle to reach the destination (seconds).
        adv_time_to_dest: Time it takes for the adversary to reach the same node (seconds).
        score: The score contribution of this interception.
        trajectory_geom: LineString representing the vehicle's path to the destination.
    """

    def __init__(
        self,
        network: RoadNetwork,
        vehicle: Vehicle,
        destination_node: int,
        time_to_dest: float,
        adv_time_to_dest: float,
        score: int,
    ):
        """Initialize a VehicleAssignment.

        Args:
            network: The road network.
            vehicle: The assigned vehicle.
            destination_node: Target node OSMID.
            time_to_dest: The time it will take the vehicle to reach the destination.
            adv_time_to_dest: The time it will take the adversary to reach the destination.
            score: The score contribution of this interception.
            trajectory_geom: The geometry of the vehicle's path to the destination.
        """
        self.vehicle: Vehicle = vehicle
        self.destination_node: int = destination_node
        self.destination_point: Point = network.node_to_point(destination_node)
        self.time_to_dest: float = time_to_dest
        self.adv_time_to_dest: float = adv_time_to_dest
        self.score: int = score
        self.trajectory_geom: LineString = network.to_linestring(
            self.vehicle.paths_to_nodes[destination_node],
            self.vehicle.position,  # type: ignore
        )

    def __repr__(self):
        return (
            f"Vehicle: id={self.vehicle.id} is assigned to node {self.destination_node} "
            f"and will get there in {self.time_to_dest} seconds"
        )
