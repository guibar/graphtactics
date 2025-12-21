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
    def __init__(self, network: RoadNetwork, lk_point: Point, last_time_seen: datetime, time_elapsed: timedelta):
        self.network: RoadNetwork = network
        self.lkp_position: Position = self.network.create_position_from_point(lk_point, on_node=True)
        if not self.network.has_in_boundary(self.lkp_position):
            raise ValueError(
                f"(Latitude: {lk_point.y:.3f}, Longitude: {lk_point.x:.3f}) is not a valid position"
                + " for the last known position of the adversary since it corresponds to a node outside"
                + " of the road network."
            )
        self.last_time_seen: datetime = last_time_seen
        self.time_elapsed: timedelta = time_elapsed
        self.travel_data: TravelData = TravelData(self.network, self, time_elapsed)
        self.candidate_nodes: CandidateNodes = CandidateNodes(self.travel_data)

    def get_stats(self) -> dict[str, int]:
        return {
            "nb_escape_nodes": len(self.travel_data.escape_nodes),
            "nb_njois": len(self.travel_data.get_njois()),
            "nb_candidate_nodes": len(self.candidate_nodes.get_candidate_nodes()),
            "max_possible_score": sum(
                [self.candidate_nodes.node_scores[njoi] for njoi in self.travel_data.get_njois()]
            ),
        }

    def __repr__(self):
        return f"Adversary: lkp={self.lkp_position}, last_time_seen={self.last_time_seen}"


class TravelData:
    def __init__(self, network: RoadNetwork, adversary: Adversary, time_elapsed: timedelta):
        self.network = network
        self.adversary = adversary
        self.escape_nodes: list[int] = network.get_escape_nodes()

        self.times_to_nodes: dict[int, int] = {}  # 10 -> 10s to reach the node; -10 -> node was reached 10s ago
        self.paths_to_nodes: dict[int, list[int]] = {}
        self.paths_to_e_nodes_past: dict[int, list[int]] = {}
        self.paths_to_e_nodes_future: dict[int, list[int]] = {}
        self.exact_positions: dict[
            int, Point
        ] = {}  # associate an escape node to the exact point where the adversary is estimated to be
        self.set_travel_times_and_paths(time_elapsed)
        self.set_past_and_future_paths()

    def set_travel_times_and_paths(self, time_elapsed: timedelta) -> None:
        # times_from_lkp_to_nodes is a dict of node to time in seconds
        times_from_lkp_to_nodes, self.paths_to_nodes = self.network.get_times_and_paths_from(
            self.adversary.lkp_position.u
        )
        # time to node in seconds, negative times mean is how long ago the node was potentially reached
        self.times_to_nodes = {k: v - int(time_elapsed.total_seconds()) for k, v in times_from_lkp_to_nodes.items()}

    def set_past_and_future_paths(self):
        # For each Escape Node (en)
        for e_n in self.escape_nodes:
            # find first escape node in the path
            first_escape_node = None
            for node in self.paths_to_nodes[e_n]:
                if node in self.escape_nodes:
                    first_escape_node = node
                    break

            # only deals with this path if e_n is the first escape node in the path
            if first_escape_node == e_n:
                times_along_path: list[int] = [self.times_to_nodes[node] for node in self.paths_to_nodes[e_n]]

                # Find the index of smallest positive times_along_path. This is the index of NJOI and is the first
                # node where we can intercept the adversary. times_along_path[njoi] is the time at which
                # the adversary will reach the NJOI. If all times are negative, the escape node is already passed
                # and index_of_njoi is len(times_along_path) and times_along_path[njoi] is undefined.
                index_of_njoi = bisect_right(times_along_path, 0)

                # Set paths to past and future nodes. If the escape node is already passed, the future path is empty.
                self.paths_to_e_nodes_past[e_n] = self.paths_to_nodes[e_n][:index_of_njoi]
                self.paths_to_e_nodes_future[e_n] = self.paths_to_nodes[e_n][index_of_njoi:]

                if index_of_njoi == 0:
                    raise ValueError(f"Past path is empty for path {self.paths_to_nodes[e_n]}. This should not happen.")
                # adversary has passed the escape node
                # we cannot map the exact position on the graph as it might be outside of the network
                # so we extrapolate the point based on the last two nodes
                if index_of_njoi == len(times_along_path):
                    pointA = self.network.node_to_point(self.paths_to_nodes[e_n][-2])
                    pointB = self.network.node_to_point(self.paths_to_nodes[e_n][-1])
                    time_from_A_to_B = times_along_path[-1] - times_along_path[-2]
                    ratio = -times_along_path[-2] / time_from_A_to_B

                    self.exact_positions[e_n] = Point(
                        pointA.x + (pointB.x - pointA.x) * ratio,
                        pointA.y + (pointB.y - pointA.y) * ratio,
                    )
                else:
                    self.exact_positions[e_n] = self.network.get_edge_position_after_time(
                        self.paths_to_e_nodes_past[e_n][-1],
                        self.paths_to_e_nodes_future[e_n][0],
                        -times_along_path[index_of_njoi - 1],
                    )
            else:
                logging.info(
                    f"The path leading to {e_n} will not be processed here because it is a continuation of the path"
                    + f"leading to {first_escape_node} and will be covered with that other path."
                )

    def set_positions_along_routes(self) -> None:
        for e_node in self.paths_to_e_nodes_future:
            past_path = self.paths_to_e_nodes_past[e_node]
            future_path = self.paths_to_e_nodes_future[e_node]
            if len(past_path) == 0:
                raise ValueError(f"Past path is empty for path {self.paths_to_nodes[e_node]}. This should not happen.")
            if len(future_path) == 0:  # adversary has passed the escape node
                self.present = past_path[-1] + (past_path[-2] - past_path[-1]) / 2  # add a distance in the direction
            else:
                self.exact_positions[e_node] = self.network.get_edge_position_after_time(
                    past_path[-1], future_path[0], -self.times_to_nodes[past_path[-1]]
                )

    def get_last_edge_value(self, e_node: int) -> int:
        # this is the common case where there are a least 2 nodes before reaching the escape node
        if len(self.paths_to_e_nodes_future[e_node]) > 1:
            return self.network.get_edge_hw_as_int(
                (self.paths_to_e_nodes_future[e_node][-2], self.paths_to_e_nodes_future[e_node][-1])
            )
        # this is the case where there is only one node before reaching the escape node,
        # we assess the edge between NJII and NJOI
        elif len(self.paths_to_e_nodes_future[e_node]) == 1 and len(self.paths_to_e_nodes_past[e_node]) >= 1:
            return self.network.get_edge_hw_as_int(
                (self.paths_to_e_nodes_past[e_node][-1], self.paths_to_e_nodes_future[e_node][0])
            )
        # this is the case where the escape node has been passed, it is unblockable so we return 0
        elif len(self.paths_to_e_nodes_future[e_node]) == 0:
            return 0
        # this is a hypothetical case where there is 1 future node and 0 past nodes. Should not happen
        else:
            raise ValueError(
                f"Future path is {self.paths_to_e_nodes_future[e_node]}\n"
                f"Past path is {self.paths_to_e_nodes_past[e_node]}"
            )

    def get_njois(self) -> set[int]:
        """Return the set of all first nodes in paths_to_e_nodes_future."""
        return {path[0] for path in self.paths_to_e_nodes_future.values() if path}

    def get_njiis(self) -> set[int]:
        """Return the set of all last nodes in paths_to_e_nodes_past."""
        return {path[-1] for path in self.paths_to_e_nodes_past.values() if path}

    # Define a more precise isochrone
    def get_isochrone(self) -> Polygon:
        # no need to sort if there are less than 3 points
        if len(self.exact_positions) < 3:
            return Polygon(self.exact_positions.values())
        point_list: list[Point] = [p for p in self.exact_positions.values()]
        # find the approximate center of the polygon
        cx, cy = sum(p.x for p in point_list) / len(point_list), sum(p.y for p in point_list) / len(point_list)
        # sort the points by angle from the center
        point_list.sort(key=lambda p: atan2(p.y - cy, p.x - cx))
        return Polygon(point_list)


class CandidateNodes:
    score_path_factor: int = 40
    node_position_factor: int = 1

    def __init__(self, travel_data: TravelData):
        # {osmid: score}, the values function as an ordered set
        self.node_scores: dict[int, int] = {}
        # {osmid: index}
        self.node_lookup: dict[int, int] = {}
        # paths as numbers from 0 to len(candidate_nodes)
        self.paths_as_indices: list[list[int]] = []
        # {osmid: time}
        self.times_to_nodes: dict[int, int] = {}

        for e_node in travel_data.paths_to_e_nodes_future.keys():
            path_as_indices = []
            for n_index, node_on_path in enumerate(travel_data.paths_to_e_nodes_future[e_node]):
                # If this node has never been encountered, we create entries for it in the dictionaries and lists
                if node_on_path not in self.node_lookup.keys():
                    # we penalize the node based on its distance from the NJOI, this means all else being equal,
                    # we prioritize a node closer to the NJOI
                    # actually this should be a function of the time waited rather than the index
                    self.node_scores[node_on_path] = -n_index * self.node_position_factor

                    # and we associate the osmid (node_on_path) to its position in the list derived from node_scores.
                    self.node_lookup[node_on_path] = len(self.node_lookup)
                    # add the time to this node in the appropriate order
                    self.times_to_nodes[node_on_path] = travel_data.times_to_nodes[node_on_path]

                # in any case, we add this score to its existing score
                self.node_scores[node_on_path] += travel_data.get_last_edge_value(e_node) * self.score_path_factor
                path_as_indices.append(self.node_lookup[node_on_path])
            self.paths_as_indices.append(path_as_indices)

    def get_candidate_node(self, index: int) -> int:
        return list(self.node_lookup.keys())[index]

    def get_candidate_nodes(self) -> list[int]:
        return list(self.node_lookup.keys())
