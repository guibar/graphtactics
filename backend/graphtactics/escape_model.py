from __future__ import annotations

import logging
from itertools import pairwise
from math import exp
from typing import NamedTuple

from anytree import PostOrderIter, PreOrderIter, findall_by_attr
from shapely.geometry import Point

from graphtactics.tree_node import TreeNode

from .config import SCORE_LAST_EDGE_FACTOR, SCORE_TIME_CONSTANT, SCORE_TIME_FACTOR
from .position import Position
from .road_network import RoadNetwork
from .tree_node import CoverStatus

logger = logging.getLogger(__name__)


# Named tuple for candidate node information
class CandidateNode(NamedTuple):
    """Information about a node where an adversary can be intercepted.

    Attributes:
        id: Sequential identifier for the candidate node starting at 0 and used by the Planner.
        osmid: OpenStreetMap identifier of the node.
        time_reached: Time at which the adversary reaches the node (seconds).
        score: Score added to the total score if we control this node.
    """

    id: int
    osmid: int
    time_reached: float
    score: int


class EscapeModel:
    # Instance attributes
    network: RoadNetwork
    lk_point: Point
    lk_position: Position | None
    time_elapsed: int

    tree_dict: dict[int, TreeNode]
    times_to_nodes: dict[int, float]
    paths_to_nodes: dict[int, list[int]]
    candidate_nodes: list[CandidateNode]
    _candidate_node_counter: int

    def __init__(self, network: RoadNetwork, lk_point: Point, time_elapsed: int):
        """Initialize EscapeModel for an adversary.

        Args:
            network: The road network.
            lk_point: The last known position of the adversary.
            time_elapsed: Time elapsed since the adversary was last seen.
        """
        self.network = network
        self.time_elapsed = time_elapsed
        self.lk_point = lk_point
        self.lk_position = None
        self.times_to_nodes = {}
        self.paths_to_nodes = {}

        self.tree_dict = {}
        self.candidate_nodes = []
        self._candidate_node_counter = 0

        self.njois: list[TreeNode] | None = None
        self.escape_nodes_uncovered: list[int] | None = None
        self.escape_nodes_covered: list[int] | None = None

        self.build_lkp_rooted_tree()
        self.set_candidate_nodes()

    def build_lkp_rooted_tree(self) -> None:
        """Build a tree of possible escape paths starting from the last known position.
        This method which is central to the project:
        1. Calculates travel times and paths (routes) from the LKP to all reachable escape nodes.
        2. Creates a representation of all the paths that we think the adversary could take.
            * Given that each path is the shortest to a different escape node, the overall structure fits into a tree
        3. Identifies on each branch of the tree, the 'Nodes Just Outside the Isochrone' (NJOIs) which are the
            first nodes the adversary hasn't reached yet (time > 0). Only nodes after the NJOIs are candidates
            for interception.
        4. Calculates and accumulates scores for each candidate node based how close to the LKP the point is and
            the typology of the road that is the last segment of this path.
        """
        self.lk_position, self.times_to_nodes, self.paths_to_nodes = self.network.get_times_and_paths_from_position(
            self.lk_point, self.time_elapsed, ens_as_sink=True
        )
        # Fake root node representing the starting position (LKP)
        self.times_to_nodes[0] = -self.time_elapsed

        for escape_node_osmid in self.network.escape_nodes:
            if escape_node_osmid in self.paths_to_nodes:
                path = self.paths_to_nodes[escape_node_osmid]

                # Base score for the nodes on this escape path, based on the importance of the last edge
                if len(path) > 1:
                    en_score_value = self.network.get_edge_hw_as_int(path[-2], path[-1]) * SCORE_LAST_EDGE_FACTOR
                # The escape node could be lkp_position.u or lkp_position.v, in which case u or v works as path[-2]
                else:
                    en_score_value = (
                        self.network.get_edge_hw_as_int(self.lk_position.u, self.lk_position.v) * SCORE_LAST_EDGE_FACTOR
                    )

                # The root of the tree is the only node that is not a proper OSM node and we set osmid=0
                # It corresponds to the last known position.
                njoi: int | None = None
                for prev_osmid, curr_osmid in pairwise([None, 0, *path]):
                    assert curr_osmid is not None
                    time_to_curr_osmid = self.times_to_nodes[curr_osmid]
                    if time_to_curr_osmid > 0:
                        score = en_score_value + int(exp(-time_to_curr_osmid / SCORE_TIME_CONSTANT) * SCORE_TIME_FACTOR)
                        # If this is the first node with a positive time value ...
                        if not njoi:
                            njoi = curr_osmid
                            # This is true since curr_osmid cannot be 0 (time_to_0 = -time_elapsed)
                            assert prev_osmid is not None
                    else:
                        score = 0

                    # Create tree node if it's the first time we encounter this graph node
                    if curr_osmid not in self.tree_dict:
                        # Assign a candidate_id if this node is reachable after the adversary with positive score
                        candidate_id = None
                        if score > 0:
                            candidate_id = self._candidate_node_counter
                            self._candidate_node_counter += 1

                        self.tree_dict[curr_osmid] = TreeNode(
                            curr_osmid,
                            parent=self.tree_dict[prev_osmid] if prev_osmid is not None else None,
                            time_reached=time_to_curr_osmid,
                            score=score,
                            is_njoi=(njoi == curr_osmid),
                            candidate_id=candidate_id,
                        )
                    else:
                        # If node already exists (found on some earlier path), add the score from this path
                        self.tree_dict[curr_osmid].score += score

    def set_candidate_nodes(self) -> None:
        """Traverse the tree rooted at node 0 and collect node information.

        Traverses the tree starting from the root node (osmid=0) collecting
        information about all candidate nodes.

        Returns:
            None
        """
        # Collect all nodes that have an id attribute (candidate nodes for interception)
        self.candidate_nodes = [
            CandidateNode(node.id, node.osmid, node.time_reached, node.score)
            for node in PreOrderIter(self.tree_dict[0], filter_=TreeNode.is_candidate_node)
        ]

        # Sort by id in increasing order
        self.candidate_nodes.sort(key=lambda node: node.id)
        assert len(self.candidate_nodes) == self._candidate_node_counter

    def get_paths_as_seq_indices(self) -> list[list[int]]:
        """Get paths to escape nodes represented as ids as given to candidate nodes (not osmids).
        This is used by the planner to express the constraint that we don't want to be assigning
        vehicles to nodes which are on the same path to an escape node.

        This iterates on all the paths from njois to escape nodes which is were the candidate nodes
        are located. One njoi can lead to multiple escape nodes but an escape node can only be
        reached from one njoi.

        Returns:
            A list of lists, where each inner list contains the IDs (in reverse order,
            from escape node towards root) of nodes along the path.
        """
        results: list[list[int]] = []
        for njoi_node in findall_by_attr(self.tree_dict[0], True, name="is_njoi"):
            for escape_node in njoi_node.leaves:
                results.append([node.id for node in njoi_node.get_path(escape_node)])
        return results

    def set_as_control_node(self, node_osmid: int) -> None:
        """Mark a node and all its descendants the status COVERED expressing the fact that the adversary
        will be intercepted if it tries to reach these nodes.

        Args:
            node_osmid: The osmid of the node to mark as controlled.
        """
        control_node = self.tree_dict[node_osmid]
        control_node.is_control_node = True
        # Mark this node and all its descendants as covered
        for node in PreOrderIter(control_node):
            node.cover = CoverStatus.COVERED

    def set_cover_status(self) -> None:
        """Set the cover status for all nodes in the tree. This is essentially used by the PlanGeometry
        to represent the paths according to their status.

        The leaves are either COVERED or UNCOVERED. Going up from them, a node is COVERED if all its
        children are COVERED, UNCOVERED if all its children are UNCOVERED, and MIXED otherwise.

        Returns:
            None
        """
        for node in PostOrderIter(self.tree_dict[0]):
            if not node.is_leaf:
                if all(child.cover == CoverStatus.COVERED for child in node.children):
                    node.cover = CoverStatus.COVERED
                elif all(child.cover == CoverStatus.UNCOVERED for child in node.children):
                    node.cover = CoverStatus.UNCOVERED
                else:
                    node.cover = CoverStatus.MIXED

    def get_njois(self) -> list[TreeNode]:
        """Get the Nodes Just Outside the Isochrone.

        These are nodes that represent the first possible interception points
        along each escape path. Every such node has already been identified with is_njoi=True
        when building the tree.

        Returns:
            List of TreeNode objects marked as NJOIs.
        """
        if self.njois is None:
            self.njois = list[TreeNode](findall_by_attr(self.tree_dict[0], True, name="is_njoi"))
        return self.njois

    def get_stats(self) -> dict[str, int]:
        """Get statistics about the adversary escape options.

        Returns:
            Dictionary containing:
                - nb_escape_nodes: Number of escape nodes we suppose the adversary might want to reach
                - nb_njois: Number of Nodes Just Outside the Isochrone (first interception points).
                - nb_candidate_nodes: Number of graph nodes where we can potentially intercept the adversary.
                - max_possible_score: Maximum possible score if we manage to watch all NJOIs.
        """

        return {
            "nb_escape_nodes": len(self.tree_dict[0].leaves),
            "nb_njois": len(self.get_njois()),
            "nb_candidate_nodes": len(self.candidate_nodes),
            # need to avoid KeyError on njoi = escape node = exact position
            "max_possible_score": sum(node.score for node in self.get_njois()),
        }
