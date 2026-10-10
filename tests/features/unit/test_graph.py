from __future__ import annotations

import unittest

from specromancy.graph import reachable_from, strongly_connected_components


class GraphUtilityTests(unittest.TestCase):
    def test_reachable_from_does_not_depend_on_vertex_names(self) -> None:
        edges = {"alpha": {"beta"}, "beta": {"gamma"}, "gamma": set(), "other": set()}
        self.assertEqual(reachable_from("alpha", edges), {"alpha", "beta", "gamma"})

    def test_strongly_connected_components_find_self_and_multi_node_cycles(self) -> None:
        edges = {
            "alpha": {"beta"},
            "beta": {"alpha", "gamma"},
            "gamma": {"gamma"},
            "other": set(),
        }
        components = set(strongly_connected_components(edges, edges))
        self.assertEqual(
            components,
            {frozenset({"alpha", "beta"}), frozenset({"gamma"}), frozenset({"other"})},
        )


if __name__ == "__main__":
    unittest.main()

