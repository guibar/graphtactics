from __future__ import annotations

import logging
from enum import IntEnum
from typing import override

from anytree import NodeMixin

logger = logging.getLogger(__name__)


class CoverStatus(IntEnum):
    """Status of a node regarding its protection or interceptability.

    The status is propagated up the tree:
    - UNCOVERED: Neither this node nor its children are protected.
    - MIXED: Some branches under this node are covered, others are not.
    - COVERED: This node or all its descendants are protected.
    """

    UNCOVERED = 0
    MIXED = 1
    COVERED = 2


class TreeNode(NodeMixin):
    """Represent a node in the escape tree of an adversary.

    A TreeNode matches a graph node (via osmid) but belongs to a tree structure
    where each path from the root to a leaf represents a possible escape route.
    Nodes are shared across multiple routes and are not duplicated

    Attributes:
        osmid: The OpenStreetMap identifier for the corresponding road network node.
        time_reached: Time for the adversary to reach this node (seconds).
        score: The score the control of this node would contribute to the total score.
        is_njoi: True if this is a Node Just Outside the Isochrone i.e. is the first with a >0 time_reached.
        cover: Current coverage status (UNCOVERED, MIXED, or COVERED).
        is_control_node: True if the plan directs a vehicle to this node.
        id: Sequential ID assigned to candidate nodes, used by the optimization solver
            in order to arrange nodes into a matrix.
    """

    # instance attributes
    osmid: int
    time_reached: float
    score: int
    is_njoi: bool
    cover: CoverStatus = CoverStatus.UNCOVERED
    is_control_node: bool = False
    id: int | None

    def __init__(
        self,
        osmid: int,
        parent: TreeNode | None,
        time_reached: float,
        score: int,
        is_njoi: bool,
        candidate_id: int | None = None,
    ) -> None:
        """Initialize a TreeNode.

        Args:
            osmid: OSM ID of the node.
            parent: Parent node in the escape tree.
            time_reached: Time reached by the adversary.
            score: Cumulative score for this node.
            is_njoi: Whether this is the first node reached in the 'future'.
            candidate_id: Optional sequential ID for optimization.
        """
        self.osmid = osmid
        self.parent = parent
        self.time_reached = time_reached
        self.score = score
        self.is_njoi = is_njoi
        self.id = candidate_id

    @override
    def __str__(self) -> str:
        return (
            f"Tree node for OSMID {self.osmid}.\n"
            f" score: {self.score}\n"
            f" time_reached: {self.time_reached}\n"
            f" is_njoi: {self.is_njoi}\n"
            f" cover: {self.cover.name}\n"
            f" is_control_point: {self.is_control_node}"
        )

    def is_candidate_node(self) -> bool:
        """Filter function for finding nodes with an id assigned."""
        return self.id is not None

    def get_path(self, node_down: TreeNode) -> list[TreeNode]:
        """Get the sequence of nodes from this node down to a descendant.

        Args:
            node_down: The target descendant node.

        Returns:
            List of nodes starting from self and ending at node_down.
        Raises:
            ValueError: If node_down is not actually a descendant of self.
        """
        if self != node_down and self not in node_down.ancestors:
            raise ValueError(f"Node {self.osmid} is not an ancestor of Node {node_down.osmid}")
        path_to_root = node_down.path
        return list(path_to_root[path_to_root.index(self) :])

    def non_overlapping_segments(self) -> list[list[TreeNode]]:
        """Decompose the subtree under self into a set of disjoint paths.

        This is useful for rendering the tree as multiple LineStrings without
        double-drawing any lines. It uses a DFS strategy where the first child
        continues an existing path and subsequent children start new segments.

        Returns:
            A list of paths, where each path is a list of TreeNodes.
        """
        non_overlapping_paths: list[list[TreeNode]] = []

        def dfs_and_split(node: TreeNode, current_path: list[TreeNode]):
            # Add the current node to the path segment
            current_path.append(node)

            if node.is_leaf:
                # Leaf reached: save the current segment
                non_overlapping_paths.append(current_path)
                return

            # Depth First Search:
            # 1. The first child continues the current path segment.
            dfs_and_split(node.children[0], current_path)

            # 2. Every subsequent child starts a NEW path segment.
            # We start the new segment with the current node ('self' in this context)
            # so that the edge from current node to the child is correctly captured.
            for child in node.children[1:]:
                dfs_and_split(child, [node])

        # Start the recursion with an empty list for the root path
        dfs_and_split(self, [])

        return non_overlapping_paths

    def categorize_segments(self) -> dict[str, list[list[TreeNode]]]:
        """
        Partition the tree edges into categorized non-overlapping path segments.

        This uses subtree_as_non_overlapping_paths() to get all paths,
        then slices each path at category boundaries.

        Categories:
        - "uncovered": edges where destination.cover is not COVERED
        - "before_control": edges where destination.cover is COVERED but are before a control
        - "after_control": edges where destination has a control node as ancestor

        Returns:
            Dict mapping category names to lists of path segments.
            Each segment is a list of TreeNodes representing a path.
            Boundary nodes appear in both adjacent segments for visual continuity.
        """
        all_paths = self.non_overlapping_segments()

        result: dict[str, list[list[TreeNode]]] = {
            "uncovered": [],
            "before_control": [],
            "after_control": [],
        }

        for path in all_paths:
            sliced = self._slice_path_by_category(path)
            for cat in result:
                result[cat].extend(sliced[cat])

        return result

    def _get_edge_category(self, edge_end_node: TreeNode) -> str:
        """Determine category of an edge based on its destination node.

        Categories:
        - "uncovered": edge leads to an uncovered node
        - "before_control": edge leads to a covered node with no control node ancestor
          (including edges TO control nodes themselves)
        - "after_control": edge leads to a node that has a control node as ancestor
        """
        # an edge is covered only if its destination node is covered
        if edge_end_node.cover != CoverStatus.COVERED:
            return "uncovered"
        elif any(ancestor.is_control_node for ancestor in edge_end_node.ancestors):
            return "after_control"
        else:
            return "before_control"

    def _slice_path_by_category(self, path: list[TreeNode]) -> dict[str, list[list[TreeNode]]]:
        """Take a single path and slice it where the edge category changes.

        Given a path [A, B, C, D, E] where edges A→B, B→C are "uncovered"
        and C→D, D→E are "before_control", this produces:
          - "uncovered": [[A, B, C]]
          - "before_control": [[C, D, E]]

        Note that the boundary node C appears in both segments to ensure
        visual continuity when rendering as LineStrings.
        """
        result: dict[str, list[list[TreeNode]]] = {
            "uncovered": [],
            "before_control": [],
            "after_control": [],
        }

        if len(path) < 2:
            return result

        # Initialize with the first node and determine category from first edge
        current_segment = [path[0]]
        current_category = self._get_edge_category(path[1])

        # Walk through each node (starting from index 1, the destination of first edge)
        for i in range(1, len(path)):
            edge_end_node = path[i]
            new_category = self._get_edge_category(edge_end_node)

            if new_category != current_category:
                # Category changed - save the current segment and start a new one
                result[current_category].append(current_segment)
                # Include the boundary node in the new segment for continuity
                current_segment = [path[i - 1]]
                current_category = new_category

            current_segment.append(edge_end_node)

        # Don't forget to save the last segment
        result[current_category].append(current_segment)
        return result
