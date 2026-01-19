from graphtactics.planner import Plan
from graphtactics.vehicle import VehicleAssignment


class MockAssignment(VehicleAssignment):
    def __init__(self, time_to_dest: float, adv_time_to_dest: float):
        self.time_to_dest = time_to_dest
        self.adv_time_to_dest = adv_time_to_dest


def test_stats_rounding():
    plan = Plan(nb_assignable_vehicles=1)
    # Simple mock assignment
    va = MockAssignment(time_to_dest=123.456, adv_time_to_dest=200.789)
    plan.assignments.append(va)

    stats = plan.get_stats()

    # 200.789 - 123.456 = 77.333 -> 77.3
    assert stats["time_margin_stats"] == (77.3, 77.3, 77.3)
    # 123.456 -> 123.5
    assert stats["time_to_dest_stats"] == (123.5, 123.5, 123.5)


def test_stats_rounding_multiple():
    plan = Plan(nb_assignable_vehicles=2)

    va1 = MockAssignment(time_to_dest=10.111, adv_time_to_dest=20.222)  # margin 10.111
    va2 = MockAssignment(time_to_dest=30.333, adv_time_to_dest=50.555)  # margin 20.222

    plan.assignments = [va1, va2]
    stats = plan.get_stats()

    assert stats["time_margin_stats"] == (10.1, 15.2, 20.2)
    assert stats["time_to_dest_stats"] == (10.1, 20.2, 30.3)
