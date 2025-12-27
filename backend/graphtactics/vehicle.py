from enum import Enum
from logging import getLogger

from numpy.random import default_rng
from shapely import LineString
from shapely.geometry import Point

from .position import Position
from .road_network import RoadNetwork

logger = getLogger(__name__)

MIN_REACHABLE_NODES_RATIO_FOR_ASSIGNABLE = 0.5  # Default value, adjust as needed


class VehicleStatus(Enum):
    ASSIGNABLE = 0  # Vehicle can take part in the plan
    TOO_CLOSE_TO_LKP = 1  # Vehicle is too close to the last known position
    UNAVAILABLE = 2  # Not used for now but a vehicle might not be available
    ASSIGNED = 3  # Vehicle that was ASSIGNABLE has been assigned
    UNASSIGNED = 4  # Vehicle that was ASSIGNABLE has NOT been assigned


# @dataclass
class Vehicle:
    def __init__(self, network: RoadNetwork, id_vehicle: int, position: Position):
        self.id: int = id_vehicle  #: Unique id representing a vehicle
        self.network: RoadNetwork = network
        self.position: Position = position
        self.status: VehicleStatus = VehicleStatus.ASSIGNABLE
        self.times_to_nodes: dict[int, int] = {}
        self.paths_to_nodes: dict[int, list[int]] = {}

    @classmethod
    def from_point(cls, network: RoadNetwork, id_vehicle: int, point: Point, on_node=False) -> "Vehicle":
        position = network.create_position_from_point(point, on_node=on_node)
        return cls(network, id_vehicle, position)

    def __repr__(self):
        return (
            f"Vehicle: id={self.id}, lat={self.position.point.y}, long={self.position.point.x}, "
            f"u={self.position.u}, v={self.position.v}"
        )

    def set_travel_times(self) -> None:
        self.times_to_nodes, self.paths_to_nodes = self.network.get_times_and_paths_from_position(self.position)

    @classmethod
    def get_time_matrix(cls, vehicles: dict[int, "Vehicle"], candidate_nodes: list[int]) -> list[list[int]]:
        return [[int(vehicle.times_to_nodes[node]) for node in candidate_nodes] for vehicle in vehicles.values()]

    @classmethod
    def get_random_vehicles(
        cls, network: RoadNetwork, nb_vehicles: int, on_node=False, seed=None
    ) -> dict[int, "Vehicle"]:
        rng = default_rng(seed)
        return {
            v_id: Vehicle(network, v_id, position)
            for v_id, position in zip(
                rng.integers(1000, 10000, nb_vehicles),
                network.get_random_positions(nb_vehicles, on_node=on_node, seed=seed),
            )
        }


class VehicleAssignment:
    def __init__(
        self,
        network: "RoadNetwork",
        vehicle: Vehicle,
        destination_node: int,
        time_to_dest: int,
        adv_time_to_dest: int,
        score: int,
    ):
        self.vehicle: Vehicle = vehicle
        self.destination_node: int = destination_node
        self.destination_point: Point = network.node_to_point(destination_node)
        self.time_to_dest: int = time_to_dest
        self.adv_time_to_dest: int = adv_time_to_dest
        self.score = score
        self.trajectory_geom: LineString = network.to_linestring(
            self.vehicle.paths_to_nodes[destination_node], pos_before=self.vehicle.position
        )

    def __repr__(self):
        return (
            f"Vehicle: id={self.vehicle.id} is assigned to node {self.destination_node} "
            f"and will get there in {self.time_to_dest} seconds"
        )
