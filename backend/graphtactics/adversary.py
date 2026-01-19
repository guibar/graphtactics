from __future__ import annotations

import logging
from datetime import datetime

from shapely.geometry import Point

from graphtactics.escape_model import EscapeModel

from .position import Position
from .road_network import RoadNetwork

logger = logging.getLogger(__name__)


class Adversary:
    """Represents the adversary that we are trying to intercept as it moves on the road network.

    The class models an adversary that was last seen at a specific location and time.
    This is a pure data object containing only the problem inputs.

    Attributes:
        network (RoadNetwork): The road network the adversary is moving through.
        lkp_position (Position): Last known position of the adversary on the network.
        last_time_seen (datetime): Timestamp when the adversary was last observed.
        time_elapsed (int): Time that has elapsed since the last sighting.
    """

    def __init__(self, network: RoadNetwork, lk_point: Point, last_time_seen: datetime, time_elapsed: int):
        """Initialize an Adversary instance.

        Args:
            network: The road network the adversary is moving through.
            lk_point: Geographic point (longitude, latitude) of the last known position.
            last_time_seen: Timestamp when the adversary was last observed.
            time_elapsed: Time duration since the last sighting.

        The lk_point will be snapped to the nearest node of the road network by conversion into a Position.

        Raises:
            ValueError: If the last known point is not within the road network boundary.
        """
        self.network: RoadNetwork = network
        self.lkp_position: Position = self.network.create_position_from_point(lk_point, on_node=False)
        if not self.network.has_in_boundary(self.lkp_position):
            raise ValueError(
                f"(Latitude: {lk_point.y:.3f}, Longitude: {lk_point.x:.3f}) is not a valid position"
                + " for the last known position of the adversary since it corresponds to a node outside"
                + " of the road network."
            )
        self.last_time_seen: datetime = last_time_seen
        self.time_elapsed: int = time_elapsed
        self.escape_model: EscapeModel = EscapeModel(network, lk_point, time_elapsed)

    def __repr__(self):
        """
        Returns:
            String describing the adversary's last known position and time seen.
        """
        return f"Adversary: lkp={self.lkp_position}, last_time_seen={self.last_time_seen}"
