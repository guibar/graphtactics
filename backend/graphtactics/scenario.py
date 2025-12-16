import logging
import os
from datetime import datetime, timedelta

from shapely.geometry import Point

from .adversary import Adversary
from .road_network import RoadNetwork
from .vehicle import Vehicle, VehicleStatus

logger = logging.getLogger(__name__)


class Scenario:
    """
    This class encapsulates the fields and methods proper to an interception plan.

    Class Attributes:
        min_reachable_nodes_ratio_for_assignable: The minimum ratio of reachable nodes for a vehicle to be considered
        assignable
        save_plans: Whether to save plan data to GeoPackage files

    Attributes:
        adversary: Adversary object containing the last known position and time seen.
        vehicles: Dictionary of available vehicles, keyed by their ID.
        time_elapsed: Time elapsed since the adversary was seen at the LKP.
        filepath: Optional path to save the plan data (GeoPackage).
    """

    min_reachable_nodes_ratio_for_assignable: float = 0.5
    save_plans: bool = os.environ.get("NEO_SAVE_PLANS", default="True") == "True"

    def __init__(
        self,
        network: RoadNetwork,
        lk_point: Point,
        last_time_seen: datetime,
        vehicles: dict[int, Vehicle],
        time_elapsed: timedelta,
    ):
        """
        Initialize the InterceptionPlan with provided inputs and initialize
        all needed variables.
        """
        self.graph_name: str = network.name
        self.time_elapsed: timedelta = time_elapsed
        self.time_now: datetime = last_time_seen + time_elapsed
        self.adversary: Adversary = Adversary(network, lk_point, last_time_seen, time_elapsed)
        self.vehicles: dict[int, Vehicle] = vehicles

        for vehicle in self.vehicles.values():
            # Don't bother calculating travel times for vehicles that are too close to the action
            if self.adversary.has_passed(vehicle.position.u):
                logger.debug(
                    f"Vehicle {vehicle.id} will not be assigned to the plan because the adversary has passed it."
                )
                vehicle.status = VehicleStatus.TOO_CLOSE_TO_LKP
            else:
                vehicle.set_travel_times()


class TooLateForThisPathException(Exception):
    pass
