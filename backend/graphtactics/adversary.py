import logging
from bisect import bisect_right
from datetime import datetime, timedelta
from math import atan2

from shapely import Polygon
from shapely.geometry import Point

from .position import Position
from .road_network import RoadNetwork

logger = logging.getLogger(__name__)


class Adversary:
    """Represents the adversary that we are trying to intercept as it moves on the road network.

    The class models an adversary that was last seen at a specific location and time,
    and calculates possible positions, travel paths, and candidate interception nodes based on
    the elapsed time since the last sighting. Only the time_elapsed really matters for the
    purpose of the interception but we have added the last_time_seen for similarity with a real situation.

    Attributes:
        network (RoadNetwork): The road network the adversary is moving through.
        lkp_position (Position): Last known position of the adversary on the network.
        last_time_seen (datetime): Timestamp when the adversary was last observed.
        time_elapsed (timedelta): Time that has elapsed since the last sighting.
        travel_data (TravelData): Computed travel times and paths to escape nodes.
        candidate_nodes (CandidateNodes): Scored candidate nodes for potential interception.
    """

    def __init__(self, network: RoadNetwork, lk_point: Point, last_time_seen: datetime, time_elapsed: timedelta):
        """Initialize an Adversary instance.

        Args:
            network: The road network the adversary is moving through.
            lk_point: Geographic point (longitude, latitude) of the last known position.
            last_time_seen: Timestamp when the adversary was last observed.
            time_elapsed: Time duration since the last sighting.

        The lk_point will be snapped to the nearest node of the road network by conversion into a Position.
        TravelData and CandidateNodes are also calculated within the execution of this constructor.

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
        self.time_elapsed: timedelta = time_elapsed
        self.travel_data: TravelData = TravelData(self.network, self.lkp_position, time_elapsed)
        self.candidate_nodes: CandidateNodes = CandidateNodes(self.travel_data)

    def get_stats(self) -> dict[str, int]:
        """Get statistics about the adversary travel options.

        Returns:
            Dictionary containing:
                - nb_escape_nodes: Number of escape nodes we suppose the adversary might want to reach
                - nb_njois: Number of Nodes Just Outside the Isochrone (first interception points).
                - nb_candidate_nodes: Number of graph nodes where we can potentially intercept the adversary.
                - max_possible_score: Maximum possible score if we manage to watch all NJOIs.
        """
        return {
            "nb_escape_nodes": len(self.network.get_escape_nodes()),
            "nb_njois": len(self.travel_data.get_njois()),
            "nb_candidate_nodes": len(self.candidate_nodes.node_osmids),
            "max_possible_score": sum(
                [
                    self.candidate_nodes.node_scores[self.candidate_nodes.osmid_to_seq_idx[njoi]]
                    for njoi in self.travel_data.get_njois()
                ]
            ),
        }

    def __repr__(self):
        """
        Returns:
            String describing the adversary's last known position and time seen.
        """
        return f"Adversary: lkp={self.lkp_position}, last_time_seen={self.last_time_seen}"


class TravelData:
    """Manages travel time and path data for an adversary in a road network.

    This class computes and stores travel times, paths, and exact positions assuming the adversary is
    trying to reach one of the escape nodes as fast as possible. It calculates both past (already traveled)
    and future (yet to be traveled) path segments to each escape node and the exact position where the adversary
    might be located on these paths.

    Attributes:
        network (RoadNetwork): The road network.
        lkp_position (Position): The last known position of the adversary.
        times_to_nodes (dict[int, int]): Time in seconds to reach each node
                        (time>0 -> time to reach node |  time<0 -> time since passing node).
        paths_to_nodes (dict[int, list[int]]): ids of nodes to traverse to reach each node from the last known position.
        e_node_to_past_path (dict[int, list[int]]): key = en (escape node id);
                                                    value = ids of nodes already traversed to reach en.
        e_node_to_future_path (dict[int, list[int]]): key = en (escape node id);
                                                      value = ids of nodes to be traversed to reach en.
        exact_positions (dict[int, Position | Point]): key = en (escape node id);
                                                       value = either:
            - the position on the edge connecting the last visited node to the first upcoming node to reach en.
            - a Point if the adversary is too far out and can't be sure to be placed on the network.
    """

    def __init__(self, network: RoadNetwork, lkp_position: Position, time_elapsed: timedelta):
        """Initialize TravelData for an adversary.

        Args:
            network: The road network.
            lkp_position: The last known position of the adversary.
            time_elapsed: Time elapsed since the adversary was last seen.
        """
        self.network = network
        self.lkp_position = lkp_position
        self.time_elapsed = time_elapsed
        self.times_to_nodes: dict[int, int] = {}  # 10 -> 10s to reach the node; -10 -> node was reached 10s ago
        self.paths_to_nodes: dict[int, list[int]] = {}
        self.e_node_to_past_path: dict[int, list[int]] = {}  # only the first escape node on a path has an entry here
        self.e_node_to_future_path: dict[int, list[int]] = {}  # only the first escape node on a path has an entry here
        self.exact_positions: dict[int, Position | Point] = {}  # adversary exact position on its way to an escape node

        self.set_travel_times_and_paths()
        self.set_past_and_future_paths()

    def set_travel_times_and_paths(self) -> None:
        """Calculate travel times and paths from the last known position to all nodes.

        Computes the time to reach each node from the adversary's last known position,
        adjusted for the elapsed time. Negative times indicate nodes that would have been reached in the past.
        """
        times_to_nodes, self.paths_to_nodes = self.network.get_times_and_paths_from_position(self.lkp_position)

        # subtract the time that has passed from the time it takes to reach each node
        self.times_to_nodes = {k: v - int(self.time_elapsed.total_seconds()) for k, v in times_to_nodes.items()}

    def set_past_and_future_paths(self):
        """Split paths to escape nodes into past and future segments.

        For each escape node, and each path leading to it:
        1. Identifies if the escape node is the escape node on the path. If not ignore it  since a path only
        needs to be processed once. Only first escape nodes on a path will be found in the keys of:
           * e_node_to_past_path,
           * e_node_to_future_path
           * exact_positions.
        2. Identifies the first node on the path that has not been reached yet (NJOI = Node just outside Isochrone).
            All nodes after this one are interception candidate nodes.
        3. Splits the path into past (already visited nodes) and future (yet to visit nodes) segments.
        4. Calculates the exact position on the edge connecting past and future nodes.
            If the escape node has already been passed, we extrapolate a geographical position but we don't try
            to place it on the network as we might not have that part of the network in our graph.

        """

        # For each Escape Node (en)
        for e_n in self.network.get_escape_nodes():
            # find first escape node in the path
            first_escape_node = None
            for node in self.paths_to_nodes[e_n]:
                if node in self.network.get_escape_nodes():
                    first_escape_node = node
                    break

            # only deals with this path if e_n is the first escape node in the path
            if e_n == first_escape_node:
                times_along_path: list[int] = [self.times_to_nodes[node] for node in self.paths_to_nodes[e_n]]

                # Find the index of smallest positive times_along_path. This is the index of NJOI and is the first
                # node where we can intercept the adversary. times_along_path[njoi] is the time at which
                # the adversary will reach the NJOI. If all times are negative, the escape node is already passed
                # and index_of_njoi is len(times_along_path) and times_along_path[njoi] is undefined.
                index_of_njoi = bisect_right(times_along_path, 0)

                # Set paths to past and future nodes. If the escape node is already passed, the future path is empty.
                self.e_node_to_past_path[e_n] = self.paths_to_nodes[e_n][:index_of_njoi]
                self.e_node_to_future_path[e_n] = self.paths_to_nodes[e_n][index_of_njoi:]

                # Since we don't allow the lkp to be an outer node, there should be at least an edge connecting the
                # lkp to th escape node.
                if index_of_njoi == 0:
                    raise ValueError(f"Past path is empty for path {self.paths_to_nodes[e_n]}. This should not happen.")

                # adversary has passed the escape node
                if index_of_njoi == len(times_along_path):
                    pointA = self.network.node_to_point(self.paths_to_nodes[e_n][-2])
                    pointB = self.network.node_to_point(self.paths_to_nodes[e_n][-1])
                    time_from_A_to_B = times_along_path[-1] - times_along_path[-2]
                    ratio = -times_along_path[-2] / time_from_A_to_B

                    # we extrapolate the (latitude, longitude) based on the last two nodes
                    # and we store the exact position as a Point (not a Position)
                    self.exact_positions[e_n] = Point(
                        pointA.x + (pointB.x - pointA.x) * ratio,
                        pointA.y + (pointB.y - pointA.y) * ratio,
                    )
                else:
                    # we store the exact position as a Position (not a Point)
                    self.exact_positions[e_n] = self.network.get_edge_position_after_time(
                        self.e_node_to_past_path[e_n][-1],
                        self.e_node_to_future_path[e_n][0],
                        -times_along_path[index_of_njoi - 1],
                    )
            else:
                logging.info(
                    f"The path leading to {e_n} will not be processed here because it is a continuation"
                    + f" of the path leading to {first_escape_node} and will be covered with that other path."
                )

    def get_last_edge_value(self, e_node: int) -> int:
        """The highway value of the last edge leading to an escape node is used to set the score of all
        the nodes on the path leading to the escape node.

        The highway value represents the importance/capacity of the road.
        1. Escape node passed: Returns 0 as the node is unblockable.
        2. Returns the highway value of the last edge leading to the escape node.

        Args:
            e_node: The escape node identifier.

        Returns:
            Integer highway value of the last edge, or 0 if the escape node was passed.
        """

        # this is the case where the escape node has been passed, it is unblockable so we return 0
        if len(self.e_node_to_future_path[e_node]) == 0:
            return 0
        # we return the highway value of the last edge leading to the escape node
        else:
            e_nodes_path = self.e_node_to_past_path[e_node] + self.e_node_to_future_path[e_node]
            return self.network.get_edge_hw_as_int((e_nodes_path[-2], e_nodes_path[-1]))

    def get_njois(self) -> set[int]:
        """Return the set of all first nodes in paths_to_e_nodes_future."""
        return {path[0] for path in self.e_node_to_future_path.values() if path}

    def get_isochrone(self) -> Polygon:
        # no need to sort if there are less than 3 points
        point_list: list[Point] = [p.point if isinstance(p, Position) else p for p in self.exact_positions.values()]

        # find the approximate center of the polygon
        centre_x, centre_y = (
            sum(p.x for p in point_list) / len(point_list),
            sum(p.y for p in point_list) / len(point_list),
        )

        # sort the points by angle from the center
        point_list.sort(key=lambda p: atan2(p.y - centre_y, p.x - centre_x))
        centre: Point = Point(
            sum(p.x for p in point_list) / len(point_list),
            sum(p.y for p in point_list) / len(point_list),
        )
        # sort the points by angle from the center
        point_list.sort(key=lambda p: atan2(p.y - centre.y, p.x - centre.x))
        return Polygon(point_list)


class CandidateNodes:
    """Determine relative scores for candidate nodes for adversary interception.

    This class scores all nodes along paths to escape nodes based on:
    - The highway value of the last edge to the escape node (weighted by score_path_factor).
    - The node's position along the path (closer to NJOI is better, weighted by node_position_factor).

    Attributes:
        score_path_factor (int): Weight multiplier for the highway value in scoring (default: 40).
        node_position_factor (int): Weight multiplier for node position penalty (default: 1).
        node_scores (dict[int, int]): Mapping of node osmid to their computed scores.
        node_lookup (dict[int, int]): Mapping of node osmid to their index in the candidate list.
        paths_as_indices (list[list[int]]): Paths represented as lists of candidate node indices.
        times_to_nodes (dict[int, int]): Time to reach each candidate node.
    """

    LAST_EDGE_FACTOR: int = 80
    TIME_FACTOR: int = 1
    TIME_CONSTANT: int = 600  # 10 minutes gives a neutral time score

    def __init__(self, travel_data: TravelData):
        """Initialize candidate nodes from travel data.

        Processes all future paths to escape nodes, scoring each node based on:
        - Its distance from the NJOI (nodes closer to NJOI are prioritized).
        - The highway value of the last edge to the escape node.

        Args:
            travel_data: Travel data containing paths and times to escape nodes.
        """

        self.node_scores: list[int] = []
        self.node_osmids: list[int] = []
        # {osmid: index}
        self.osmid_to_seq_idx: dict[int, int] = {}
        # paths as numbers from 0 to len(candidate_nodes)
        self.paths_as_seq_indices: list[list[int]] = []
        # {osmid: time}
        self.times_to_nodes: list[int] = []

        for e_node in travel_data.e_node_to_future_path.keys():
            path_as_seq_indices = []
            for n_osmid in travel_data.e_node_to_future_path[e_node]:
                # If this node has never been encountered, we create entries for it in the dictionaries and lists
                if n_osmid not in self.osmid_to_seq_idx.keys():
                    # We include this node in node_lookup, and increase the lists accordingly
                    self.osmid_to_seq_idx[n_osmid] = len(self.osmid_to_seq_idx)
                    self.node_osmids.append(n_osmid)
                    self.node_scores.append(0)

                    # add the time to this node in the appropriate order
                    self.times_to_nodes.append(travel_data.times_to_nodes[n_osmid])

                # the score is based on the highway value of the last edge to the escape node
                # and the time to reach the node
                self.node_scores[self.osmid_to_seq_idx[n_osmid]] += (
                    travel_data.get_last_edge_value(e_node) * self.LAST_EDGE_FACTOR
                    + max(self.TIME_CONSTANT - travel_data.times_to_nodes[n_osmid], 0) * self.TIME_FACTOR
                )

                # we create a version of the path that refers to nodes by their sequential index
                path_as_seq_indices.append(self.osmid_to_seq_idx[n_osmid])
            self.paths_as_seq_indices.append(path_as_seq_indices)
