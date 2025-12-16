import logging
from bisect import bisect_right
from datetime import datetime, timedelta

from shapely.geometry import Point

from .road_network import RoadNetwork

logger = logging.getLogger(__name__)


class Adversary:
    def __init__(self, network: RoadNetwork, lk_point: Point, last_time_seen: datetime, time_elapsed: timedelta):
        self.network = network
        self.lkp_position = self.network.create_position_from_point(lk_point)
        self.last_time_seen = last_time_seen
        self.time_elapsed = time_elapsed
        self.travel_data: TravelData = TravelData(self.network, self, time_elapsed)
        self.candidate_nodes = CandidateNodes(self.travel_data)

    def has_passed(self, node: int) -> bool:
        if node in self.travel_data.times_to_nodes:
            return self.travel_data.times_to_nodes[node] <= 0
        return False

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

        self.times_from_lkp_to_nodes: dict[int, int] = {}
        self.times_to_nodes: dict[int, int] = {}
        self.paths_to_nodes: dict[int, list[int]] = {}
        self.paths_to_e_nodes_past: dict[int, list[int]] = {}
        self.paths_to_e_nodes_future: dict[int, list[int]] = {}

        self.find_all_travel_times_and_paths(time_elapsed)
        self.find_past_future_to_e_nodes()

    def find_all_travel_times_and_paths(self, time_elapsed: timedelta) -> None:
        # times_from_lkp_to_nodes is a dict of node to time in seconds
        self.times_from_lkp_to_nodes, self.paths_to_nodes = self.network.get_times_and_paths_from(
            self.adversary.lkp_position.u
        )
        # time to node in seconds, negative times mean is how long ago the node was potentially reached
        self.times_to_nodes = {
            k: v - int(time_elapsed.total_seconds()) for k, v in self.times_from_lkp_to_nodes.items()
        }

    def find_past_future_to_e_nodes(self):
        # For each Escape Node (en)
        for e_n in self.escape_nodes:
            full_path_to_e_n = self.paths_to_nodes[e_n]
            # If the point just before the Escape Node is not in the inner zone, we ignore this Escape Node.
            # Otherwise, we might have Escape Nodes reached by Shortest Paths passing through
            # another Escape Node first.
            if self.network.is_inner(full_path_to_e_n[-2]):
                times_along_path: list[int] = [self.times_to_nodes[node] for node in full_path_to_e_n]

                # find in the index of the first node the adversary has not yet reached
                index_of_njoi = bisect_right(times_along_path, 0)

                self.paths_to_e_nodes_past[e_n] = full_path_to_e_n[:index_of_njoi]
                self.paths_to_e_nodes_future[e_n] = full_path_to_e_n[index_of_njoi:]

            else:
                logging.info(
                    f"The path leading to {e_n} is not processed here because  {full_path_to_e_n[-2]} "
                    "is not inner and it will be dealt with in some other iteration."
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
