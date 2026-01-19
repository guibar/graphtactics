import pytest

from graphtactics.tree_node import CoverStatus, TreeNode


def test_subtree_single_node():
    """Test with a single node."""
    node0 = TreeNode(osmid=0, parent=None, time_reached=0.0, score=10, is_njoi=False)
    paths = node0.non_overlapping_segments()
    assert len(paths) == 1
    assert [n.osmid for n in paths[0]] == [0]


def test_subtree_linear_path():
    """Test with a linear tree (linked list)."""
    node0 = TreeNode(osmid=0, parent=None, time_reached=0.0, score=10, is_njoi=False)
    node1 = TreeNode(osmid=1, parent=node0, time_reached=0.0, score=10, is_njoi=False)
    node2 = TreeNode(osmid=2, parent=node1, time_reached=0.0, score=10, is_njoi=False)

    paths = node0.non_overlapping_segments()

    assert len(paths) == 1
    assert [n.osmid for n in paths[0]] == [0, 1, 2]
    assert node2.is_leaf


@pytest.fixture
def basic_tree() -> dict[int, TreeNode]:
    """Provides a basic tree structure for testing.
    Structure:
    node0 (root, osmid 0, MIXED)
      - node1 (osmid 1, is_njoi=True, MIXED)
        - node3 (osmid 3, MIXED)
          - node4 (osmid 4, COVERED, is_control=True)
              - node6 (osmid 6, COVERED)
              - node7 (osmid 7, COVERED)
          - node5 (osmid 5, UNCOVERED)
      - node2 (osmid 2, is_control=True, COVERED)
    """
    tree_dict: dict[int, TreeNode] = {}

    tree_dict[0] = TreeNode(osmid=0, parent=None, time_reached=0.0, score=10, is_njoi=False)
    tree_dict[1] = TreeNode(osmid=1, parent=tree_dict[0], time_reached=0.0, score=10, is_njoi=True)
    tree_dict[2] = TreeNode(osmid=2, parent=tree_dict[0], time_reached=0.0, score=10, is_njoi=False)
    tree_dict[3] = TreeNode(osmid=3, parent=tree_dict[1], time_reached=0.0, score=10, is_njoi=False)
    tree_dict[4] = TreeNode(osmid=4, parent=tree_dict[3], time_reached=0.0, score=10, is_njoi=False)
    tree_dict[5] = TreeNode(osmid=5, parent=tree_dict[3], time_reached=0.0, score=10, is_njoi=False)
    tree_dict[6] = TreeNode(osmid=6, parent=tree_dict[4], time_reached=0.0, score=10, is_njoi=False)
    tree_dict[7] = TreeNode(osmid=7, parent=tree_dict[4], time_reached=0.0, score=10, is_njoi=False)

    tree_dict[0].cover = CoverStatus.MIXED
    tree_dict[1].cover = CoverStatus.MIXED
    tree_dict[2].cover = CoverStatus.COVERED
    tree_dict[3].cover = CoverStatus.MIXED
    tree_dict[4].cover = CoverStatus.COVERED
    tree_dict[5].cover = CoverStatus.UNCOVERED
    tree_dict[6].cover = CoverStatus.COVERED
    tree_dict[7].cover = CoverStatus.COVERED

    tree_dict[2].is_control_node = True
    tree_dict[4].is_control_node = True

    return tree_dict


def test_non_overlapping(basic_tree: dict[int, TreeNode]):
    """Test the decomposition of a tree into non-overlapping paths."""

    # Method to test
    paths = basic_tree[0].non_overlapping_segments()

    # Convert to OSMIDs for easy comparison
    osmid_paths = [[n.osmid for n in path] for path in paths]

    # Verify results
    assert len(osmid_paths) == 4
    assert [0, 1, 3, 4, 6] in osmid_paths
    assert [3, 5] in osmid_paths
    assert [4, 7] in osmid_paths
    assert [0, 2] in osmid_paths


def set_cover_status_bottom_up(root: TreeNode) -> None:
    """
    Replicate the bottom-up cover propagation from EscapeModel.set_cover_status().
    This ensures realistic cover status on test trees.
    """
    from anytree import PostOrderIter

    for node in PostOrderIter(root):
        if not node.is_leaf:
            if all(child.cover == CoverStatus.COVERED for child in node.children):
                node.cover = CoverStatus.COVERED
            elif all(child.cover == CoverStatus.UNCOVERED for child in node.children):
                node.cover = CoverStatus.UNCOVERED
            else:
                node.cover = CoverStatus.MIXED


def set_as_control_node(node: TreeNode) -> None:
    """
    Replicate EscapeModel.set_as_control_node() - marks node and all descendants as COVERED.
    """
    from anytree import PreOrderIter

    node.is_control_node = True
    for n in PreOrderIter(node):
        n.cover = CoverStatus.COVERED


class TestSubtreeAsNonOverlappingPaths:
    """Test the basic non-overlapping paths algorithm on simple trees."""

    def setup_method(self):
        """Reset the counter before each test."""
        TreeNode.candidate_node_counter = 0

    def test_linear_tree(self):
        """
        Test a simple linear tree: A -> B -> C
        Should produce one path: [A, B, C]
        """
        a = TreeNode(osmid=1, parent=None, time_reached=0, score=10, is_njoi=False)
        b = TreeNode(osmid=2, parent=a, time_reached=10, score=10, is_njoi=True)
        _c = TreeNode(osmid=3, parent=b, time_reached=20, score=10, is_njoi=False)

        paths = a.non_overlapping_segments()

        assert len(paths) == 1
        assert [n.osmid for n in paths[0]] == [1, 2, 3]

    def test_simple_fork(self):
        """
        Test a fork:
              A
             / \
            B   C
        Should produce two paths: [A, B] and [A, C]
        Each edge appears exactly once, A appears in both.
        """
        a = TreeNode(osmid=1, parent=None, time_reached=0, score=10, is_njoi=False)
        _b = TreeNode(osmid=2, parent=a, time_reached=10, score=10, is_njoi=True)
        _c = TreeNode(osmid=3, parent=a, time_reached=15, score=10, is_njoi=True)

        paths = a.non_overlapping_segments()

        assert len(paths) == 2
        # First path continues with first child
        assert [n.osmid for n in paths[0]] == [1, 2]
        # Second path starts fresh from A
        assert [n.osmid for n in paths[1]] == [1, 3]

    def test_all_edges_covered_exactly_once(self):
        """
        Verify that counting edges across all paths equals the tree's edge count.
              A
             /|\
            B C D
              |
              E
        4 edges total: A-B, A-C, A-D, C-E
        """
        a = TreeNode(osmid=1, parent=None, time_reached=0, score=10, is_njoi=False)
        _b = TreeNode(osmid=2, parent=a, time_reached=10, score=10, is_njoi=True)
        c = TreeNode(osmid=3, parent=a, time_reached=15, score=10, is_njoi=False)
        _d = TreeNode(osmid=4, parent=a, time_reached=20, score=10, is_njoi=True)
        _e = TreeNode(osmid=5, parent=c, time_reached=25, score=10, is_njoi=True)

        paths = a.non_overlapping_segments()

        # Count edges: each path of length n has n-1 edges
        total_edges = sum(len(path) - 1 for path in paths)
        assert total_edges == 4


class TestCategorizedSegmentsIntegration:
    """
    Integration tests using realistic tree configurations.

    All trees follow the real cover propagation rules:
    1. Set control nodes first (marks node + descendants as COVERED)
    2. Run bottom-up propagation (creates MIXED at branch points)

    Tests use TreeNode.categorize_tree_segments() directly.
    """

    def setup_method(self):
        """Reset the counter before each test."""
        TreeNode.candidate_node_counter = 0

    def test_all_uncovered_no_control_nodes(self):
        """
        No control nodes set - all paths are uncovered.
        
              0(U)
             / \
          1(U)  2(U)
        
        Should produce 2 segments, both "uncovered".
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-10, score=0, is_njoi=False)
        n1 = TreeNode(osmid=1, parent=root, time_reached=10, score=10, is_njoi=True)
        n2 = TreeNode(osmid=2, parent=root, time_reached=15, score=10, is_njoi=True)

        # No control nodes - run propagation (all stay UNCOVERED)
        set_cover_status_bottom_up(root)

        assert root.cover == CoverStatus.UNCOVERED
        assert n1.cover == CoverStatus.UNCOVERED
        assert n2.cover == CoverStatus.UNCOVERED

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 2
        assert len(categorized["before_control"]) == 0
        assert len(categorized["after_control"]) == 0

    def test_one_branch_controlled_at_leaf(self):
        """
        Control node at a leaf - one branch covered, one uncovered.
        
              0(M)          <- MIXED (has both covered and uncovered children)
             / \
          1(U)  2(C)*       <- 2 is control node (leaf)
        
        Should produce:
        - [0, 1] as "uncovered"
        - [0, 2] as "before_control" (edge TO the control node)
        
        Note: There's no "after_control" because 2 is a leaf - nothing comes after it.
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-10, score=0, is_njoi=False)
        n1 = TreeNode(osmid=1, parent=root, time_reached=10, score=10, is_njoi=True)
        n2 = TreeNode(osmid=2, parent=root, time_reached=15, score=10, is_njoi=True)

        # Set n2 as control node, then propagate
        set_as_control_node(n2)
        set_cover_status_bottom_up(root)

        assert root.cover == CoverStatus.MIXED
        assert n1.cover == CoverStatus.UNCOVERED
        assert n2.cover == CoverStatus.COVERED
        assert n2.is_control_node

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 1
        assert len(categorized["before_control"]) == 1
        assert len(categorized["after_control"]) == 0

        # Check paths
        assert [n.osmid for n in categorized["uncovered"][0]] == [0, 1]
        assert [n.osmid for n in categorized["before_control"][0]] == [0, 2]

    def test_control_node_in_middle_of_path(self):
        """
        Control node in the middle - creates before_control and after_control segments.

              0(M)
              |
              1(C)         <- first COVERED node (before_control)
              |
              2(C)*        <- CONTROL NODE
              |
              3(C)         <- after_control

        Should produce:
        - [0, 1, 2] as "before_control" (path TO control node)
        - [2, 3] as "after_control" (path FROM control node)
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-10, score=0, is_njoi=False)
        n1 = TreeNode(osmid=1, parent=root, time_reached=10, score=10, is_njoi=True)
        n2 = TreeNode(osmid=2, parent=n1, time_reached=20, score=10, is_njoi=False)
        n3 = TreeNode(osmid=3, parent=n2, time_reached=30, score=10, is_njoi=False)

        # Set n2 as control node (n2 and n3 become COVERED), then propagate
        set_as_control_node(n2)
        set_cover_status_bottom_up(root)

        assert root.cover == CoverStatus.COVERED  # Single path, all covered
        assert n1.cover == CoverStatus.COVERED
        assert n2.cover == CoverStatus.COVERED
        assert n2.is_control_node
        assert n3.cover == CoverStatus.COVERED

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 0
        assert len(categorized["before_control"]) == 1
        assert len(categorized["after_control"]) == 1

        before_seg = categorized["before_control"][0]
        after_seg = categorized["after_control"][0]

        # before_control ends at control node
        assert [n.osmid for n in before_seg] == [0, 1, 2]

        # after_control starts at control node
        assert [n.osmid for n in after_seg] == [2, 3]

    def test_fork_with_one_controlled_branch(self):
        """
        Fork where one branch is controlled, one is not.
        
              0(M)
             / \
          1(U)  2(C)*      <- 2 is control node with descendants
                |
                3(C)
        
        Should produce:
        - [0, 1] as "uncovered"
        - [0, 2] as "before_control" (edge TO control node)
        - [2, 3] as "after_control" (edge FROM control node)
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-10, score=0, is_njoi=False)
        n1 = TreeNode(osmid=1, parent=root, time_reached=10, score=10, is_njoi=True)
        n2 = TreeNode(osmid=2, parent=root, time_reached=15, score=10, is_njoi=True)
        n3 = TreeNode(osmid=3, parent=n2, time_reached=25, score=10, is_njoi=False)

        set_as_control_node(n2)
        set_cover_status_bottom_up(root)

        assert root.cover == CoverStatus.MIXED
        assert n1.cover == CoverStatus.UNCOVERED
        assert n2.cover == CoverStatus.COVERED
        assert n2.is_control_node
        assert n3.cover == CoverStatus.COVERED

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 1
        assert len(categorized["before_control"]) == 1
        assert len(categorized["after_control"]) == 1

        # Verify paths
        assert [n.osmid for n in categorized["uncovered"][0]] == [0, 1]
        assert [n.osmid for n in categorized["before_control"][0]] == [0, 2]
        assert [n.osmid for n in categorized["after_control"][0]] == [2, 3]

    def test_complex_tree_realistic(self):
        """
        Complex realistic tree with control node deeper in one branch.
        
                 0(M)
                / \
             1(U)  2(M)          <- 2 is MIXED (has uncovered and covered children)
                  / \
               3(U)  4(C)        <- path to control
                     |
                     5(C)*       <- CONTROL NODE
                     |
                     6(C)
        
        Expected segments:
        - [0, 1]: uncovered (first branch)
        - [0, 2, 3]: uncovered (second branch, uncovered subtree)
        - [2, 4, 5]: before_control (path TO control node)
        - [5, 6]: after_control (path FROM control node)
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-10, score=0, is_njoi=False)
        n1 = TreeNode(osmid=1, parent=root, time_reached=10, score=10, is_njoi=True)
        n2 = TreeNode(osmid=2, parent=root, time_reached=5, score=0, is_njoi=False)
        n3 = TreeNode(osmid=3, parent=n2, time_reached=15, score=10, is_njoi=True)
        n4 = TreeNode(osmid=4, parent=n2, time_reached=20, score=10, is_njoi=True)
        n5 = TreeNode(osmid=5, parent=n4, time_reached=30, score=10, is_njoi=False)
        n6 = TreeNode(osmid=6, parent=n5, time_reached=40, score=10, is_njoi=False)

        # Set n5 as control node, then propagate
        set_as_control_node(n5)
        set_cover_status_bottom_up(root)

        # Verify realistic cover status
        assert root.cover == CoverStatus.MIXED
        assert n1.cover == CoverStatus.UNCOVERED
        assert n2.cover == CoverStatus.MIXED  # Has both uncovered (n3) and covered (n4) children
        assert n3.cover == CoverStatus.UNCOVERED
        assert n4.cover == CoverStatus.COVERED  # All children covered
        assert n5.cover == CoverStatus.COVERED
        assert n5.is_control_node
        assert n6.cover == CoverStatus.COVERED

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 2, f"Expected 2 uncovered, got {len(categorized['uncovered'])}"
        assert len(categorized["before_control"]) == 1, (
            f"Expected 1 before_control, got {len(categorized['before_control'])}"
        )
        assert len(categorized["after_control"]) == 1, (
            f"Expected 1 after_control, got {len(categorized['after_control'])}"
        )

        # Verify total edges = 6 (tree has 7 nodes, so 6 edges)
        all_segments = categorized["uncovered"] + categorized["before_control"] + categorized["after_control"]
        total_edges = sum(len(seg) - 1 for seg in all_segments)
        assert total_edges == 6, f"Expected 6 edges, got {total_edges}"

        # Verify specific paths
        before_seg = categorized["before_control"][0]
        after_seg = categorized["after_control"][0]

        assert before_seg[-1].osmid == 5, "before_control should end at control node"
        assert after_seg[0].osmid == 5, "after_control should start at control node"

    def test_multiple_control_nodes(self):
        """
        Multiple control nodes on different branches.
        
              0(C)          <- COVERED (all children covered)
             / \
          1(C)*  2(C)*     <- Both are control nodes
          |      |
          3(C)   4(C)
        
        Should produce:
        - [0, 1] as "before_control" (edge to control node 1)
        - [1, 3] as "after_control" (edge from control node 1)
        - [0, 2] as "before_control" (edge to control node 2)
        - [2, 4] as "after_control" (edge from control node 2)
        
        Note: root is COVERED (not MIXED) because all its children are covered,
        but it still has before_control edges because there's no control ancestor.
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-10, score=0, is_njoi=False)
        n1 = TreeNode(osmid=1, parent=root, time_reached=10, score=10, is_njoi=True)
        n2 = TreeNode(osmid=2, parent=root, time_reached=15, score=10, is_njoi=True)
        _n3 = TreeNode(osmid=3, parent=n1, time_reached=20, score=10, is_njoi=False)
        _n4 = TreeNode(osmid=4, parent=n2, time_reached=25, score=10, is_njoi=False)

        set_as_control_node(n1)
        set_as_control_node(n2)
        set_cover_status_bottom_up(root)

        assert root.cover == CoverStatus.COVERED  # All children covered
        assert n1.is_control_node
        assert n2.is_control_node

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 0
        assert len(categorized["before_control"]) == 2, (
            f"Expected 2 before_control, got {len(categorized['before_control'])}"
        )
        assert len(categorized["after_control"]) == 2, (
            f"Expected 2 after_control, got {len(categorized['after_control'])}"
        )

        # Verify total edges = 4 (tree has 5 nodes, so 4 edges)
        all_segments = categorized["uncovered"] + categorized["before_control"] + categorized["after_control"]
        total_edges = sum(len(seg) - 1 for seg in all_segments)
        assert total_edges == 4, f"Expected 4 edges, got {total_edges}"


class TestCategorizedSegmentsEdgeCases:
    """
    Edge cases that might occur in real EscapeModel trees.
    """

    def setup_method(self):
        """Reset the counter before each test."""
        TreeNode.candidate_node_counter = 0

    def test_root_with_negative_time_uncovered_children(self):
        """
        Root has negative time (past), children have positive time.
        This mirrors the real tree where root (osmid=0) is at -time_elapsed.
        
              0(U) t=-300    <- Root at past time
             / \
          1(U) t=50  2(U) t=80   <- Children at future time, both are njois
        
        All uncovered, so all segments should be "uncovered".
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-300, score=0, is_njoi=False)
        _n1 = TreeNode(osmid=1, parent=root, time_reached=50, score=10, is_njoi=True)
        _n2 = TreeNode(osmid=2, parent=root, time_reached=80, score=10, is_njoi=True)

        set_cover_status_bottom_up(root)

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 2
        assert len(categorized["before_control"]) == 0
        assert len(categorized["after_control"]) == 0

        # Check that root appears in paths
        assert categorized["uncovered"][0][0].osmid == 0
        assert categorized["uncovered"][1][0].osmid == 0

    def test_control_node_is_njoi(self):
        """
        The control node is also the njoi (first intercept point).
        This is common when a vehicle can reach an njoi.

              0(M) t=-300
              |
              1(C)* t=50    <- CONTROL NODE and NJOI
              |
              2(C) t=100

        Should produce:
        - [0, 1] as "before_control"
        - [1, 2] as "after_control"
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-300, score=0, is_njoi=False)
        n1 = TreeNode(osmid=1, parent=root, time_reached=50, score=10, is_njoi=True)
        _n2 = TreeNode(osmid=2, parent=n1, time_reached=100, score=10, is_njoi=False)

        set_as_control_node(n1)
        set_cover_status_bottom_up(root)

        assert n1.is_njoi
        assert n1.is_control_node

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 0
        assert len(categorized["before_control"]) == 1
        assert len(categorized["after_control"]) == 1

        assert [n.osmid for n in categorized["before_control"][0]] == [0, 1]
        assert [n.osmid for n in categorized["after_control"][0]] == [1, 2]

    def test_deep_tree_with_control_far_from_root(self):
        """
        A deeper tree where control node is several levels down.

              0(M) t=-300
              |
              1(M) t=-100   <- Still in the past (between root and njoi)
              |
              2(M) t=50     <- NJOI
              |
              3(C) t=100    <- Covered (will become before_control)
              |
              4(C)* t=150   <- CONTROL NODE
              |
              5(C) t=200

        Should produce:
        - [0, 1, 2, 3, 4] as "before_control"
        - [4, 5] as "after_control"
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-300, score=0, is_njoi=False)
        n1 = TreeNode(osmid=1, parent=root, time_reached=-100, score=0, is_njoi=False)
        n2 = TreeNode(osmid=2, parent=n1, time_reached=50, score=10, is_njoi=True)
        n3 = TreeNode(osmid=3, parent=n2, time_reached=100, score=10, is_njoi=False)
        n4 = TreeNode(osmid=4, parent=n3, time_reached=150, score=10, is_njoi=False)
        _n5 = TreeNode(osmid=5, parent=n4, time_reached=200, score=10, is_njoi=False)

        set_as_control_node(n4)
        set_cover_status_bottom_up(root)

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 0
        assert len(categorized["before_control"]) == 1
        assert len(categorized["after_control"]) == 1

        assert [n.osmid for n in categorized["before_control"][0]] == [0, 1, 2, 3, 4]
        assert [n.osmid for n in categorized["after_control"][0]] == [4, 5]

    def test_mixed_node_between_uncovered_and_covered(self):
        """
        A path that goes through uncovered nodes, then hits a MIXED node,
        then continues to covered nodes.
        
              0(M) t=-300
              |
              1(U) t=-100    <- Uncovered
              |
              2(M) t=50      <- MIXED (NJOI) - has uncovered and covered children
             / \
          3(U)  4(C)         <- One uncovered leaf, one covered branch
                |
                5(C)*        <- CONTROL NODE
                |
                6(C)
        
        Expected:
        - [0, 1, 2, 3]: uncovered
        - [2, 4, 5]: before_control
        - [5, 6]: after_control
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-300, score=0, is_njoi=False)
        n1 = TreeNode(osmid=1, parent=root, time_reached=-100, score=0, is_njoi=False)
        n2 = TreeNode(osmid=2, parent=n1, time_reached=50, score=10, is_njoi=True)
        n3 = TreeNode(osmid=3, parent=n2, time_reached=100, score=10, is_njoi=False)
        n4 = TreeNode(osmid=4, parent=n2, time_reached=120, score=10, is_njoi=False)
        n5 = TreeNode(osmid=5, parent=n4, time_reached=180, score=10, is_njoi=False)
        n6 = TreeNode(osmid=6, parent=n5, time_reached=240, score=10, is_njoi=False)

        set_as_control_node(n5)
        set_cover_status_bottom_up(root)

        # Verify cover status
        assert root.cover == CoverStatus.MIXED
        assert n1.cover == CoverStatus.MIXED
        assert n2.cover == CoverStatus.MIXED
        assert n3.cover == CoverStatus.UNCOVERED
        assert n4.cover == CoverStatus.COVERED
        assert n5.cover == CoverStatus.COVERED
        assert n5.is_control_node
        assert n6.cover == CoverStatus.COVERED

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 1, f"Got {len(categorized['uncovered'])}: {categorized['uncovered']}"
        assert len(categorized["before_control"]) == 1, f"Got {len(categorized['before_control'])}"
        assert len(categorized["after_control"]) == 1, f"Got {len(categorized['after_control'])}"

        # Check paths
        uncovered_osmids = [n.osmid for n in categorized["uncovered"][0]]
        before_osmids = [n.osmid for n in categorized["before_control"][0]]
        after_osmids = [n.osmid for n in categorized["after_control"][0]]

        assert uncovered_osmids == [0, 1, 2, 3], f"Got {uncovered_osmids}"
        assert before_osmids == [2, 4, 5], f"Got {before_osmids}"
        assert after_osmids == [5, 6], f"Got {after_osmids}"

    def test_single_edge_segments(self):
        """
        A case where each category has only single-edge segments.
        
              0(M) t=-300
             /|\
          1(U) 2(C)* 3(C)*
        
        Should produce:
        - [0, 1]: uncovered (single edge)
        - [0, 2]: before_control (single edge to control node leaf)
        - [0, 3]: before_control (single edge to control node leaf)
        """
        root = TreeNode(osmid=0, parent=None, time_reached=-300, score=0, is_njoi=False)
        _n1 = TreeNode(osmid=1, parent=root, time_reached=50, score=10, is_njoi=True)
        n2 = TreeNode(osmid=2, parent=root, time_reached=80, score=10, is_njoi=True)
        n3 = TreeNode(osmid=3, parent=root, time_reached=100, score=10, is_njoi=True)

        set_as_control_node(n2)
        set_as_control_node(n3)
        set_cover_status_bottom_up(root)

        categorized = root.categorize_segments()

        assert len(categorized["uncovered"]) == 1
        assert len(categorized["before_control"]) == 2
        assert len(categorized["after_control"]) == 0  # Control nodes are leaves

        assert [n.osmid for n in categorized["uncovered"][0]] == [0, 1]
