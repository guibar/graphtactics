import logging

from geopandas import GeoDataFrame
from ortools.sat.python import cp_model
from ortools.sat.python.cp_model import IntVar
from pandas import Index

from .adversary import CandidateNodes
from .road_network import RoadNetwork
from .vehicle import Vehicle, VehicleAssignment, VehicleStatus

MAX_TIME_TO_SOLVE = 30

logger = logging.getLogger(__name__)


class Planner:
    def __init__(self, network: RoadNetwork, vehicles: dict[int, Vehicle], candidate_nodes: CandidateNodes):
        self.network = network
        self.vehicles: dict[int, Vehicle] = vehicles
        self.assignable_vids: list[int] = [
            v_id for v_id in self.vehicles if self.vehicles[v_id].status == VehicleStatus.ASSIGNABLE
        ]
        self.candidate_nodes: CandidateNodes = candidate_nodes

    def plan_interception(self, time_margin: int = 0) -> "Plan":
        """
        Generate the optimal interception plan.

        This method uses the OR-Tools solver to assign vehicles to interception nodes
        in order to maximize the total interception score. It updates the status and
        assignment of each vehicle.
        """

        scores_n: list[int] = list(self.candidate_nodes.node_scores.values())
        adv_paths_to_n: list[list[int]] = self.candidate_nodes.paths_as_indices
        adv_times_to_n: list[int] = list(self.candidate_nodes.times_to_nodes.values())
        times_v_n: list[list[int]] = Vehicle.get_time_matrix(self.vehicles, self.candidate_nodes.get_candidate_nodes())
        num_vehicles: int = len(times_v_n)
        num_nodes: int = len(times_v_n[0])

        plan: Plan = Plan(len(self.assignable_vids))

        # No vehicles, so no solution to find and nothing more to do
        if len(self.assignable_vids) == 0:
            return plan

        # The model
        model = cp_model.CpModel()

        # IntVars are actually booleans (NewBoolVar) or constants (NewConstant)
        veh_at_node: list[list[IntVar]] = [[]] * num_vehicles
        for v_i in range(num_vehicles):
            veh_at_node[v_i]: list[IntVar] = []  # pyright: ignore[reportInvalidTypeForm]
            for n_j in range(num_nodes):
                # If our vehicle v_i can reach this node before the adversary, it's a boolean variable.
                if adv_times_to_n[n_j] - times_v_n[v_i][n_j] - time_margin > 0:
                    veh_at_node[v_i].append(model.NewBoolVar(f"x[v={v_i},n={n_j}]"))
                # Otherwise, this assignment is excluded and we can set the value to constant 0
                else:
                    veh_at_node[v_i].append(model.NewConstant(0))

        # _____________ Constraints  ____________

        # C1: A vehicle is assigned to at most one node
        for v_i in range(num_vehicles):
            model.Add(sum(veh_at_node[v_i][n_j] for n_j in range(num_nodes)) <= 1)

        # C2: A node is assigned to at most one vehicle
        for n_j in range(num_nodes):
            model.Add(sum(veh_at_node[v_i][n_j] for v_i in range(num_vehicles)) <= 1)

        # C3: The number of vehicles on a shortest path cannot be greater than 1.
        for sp_index in range(len(adv_paths_to_n)):
            model.Add(
                sum(veh_at_node[v_i][n_j] for v_i in range(num_vehicles) for n_j in adv_paths_to_n[sp_index]) <= 1
            )

        # _____________ End Constraints  ____________

        # Objective: maximize the sum of scores of assigned (monitored) nodes
        objective_terms = [
            scores_n[n_j] * veh_at_node[v_i][n_j] for v_i in range(num_vehicles) for n_j in range(num_nodes)
        ]
        model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = MAX_TIME_TO_SOLVE
        status = solver.Solve(model)

        def convert_indices_to_ids(v_i: int, n_j: int) -> tuple[Vehicle, int]:
            return self.vehicles[self.assignable_vids[v_i]], self.candidate_nodes.get_candidate_node(n_j)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            logger.info(f"The total score of the plan is:  {solver.ObjectiveValue()}")
            for v_i in range(num_vehicles):
                for n_j in range(num_nodes):
                    if solver.BooleanValue(veh_at_node[v_i][n_j]):
                        v_a = VehicleAssignment(
                            self.network,
                            *convert_indices_to_ids(v_i, n_j),
                            times_v_n[v_i][n_j],
                            adv_times_to_n[n_j],
                            scores_n[n_j],
                        )
                        plan.assignments.append(v_a)
                        logger.info(
                            f"Vehicle {v_a.vehicle.id}({v_i}) must go to node {v_a.destination_node}({n_j}).\n"
                            f"It will arrive {adv_times_to_n[n_j] - times_v_n[v_i][n_j]} seconds"
                            f" before the adversary and contributes {scores_n[n_j]} points to the total score."
                        )
                        self.vehicles[self.assignable_vids[v_i]].status = VehicleStatus.ASSIGNED
                        break
                else:
                    self.vehicles[self.assignable_vids[v_i]].status = VehicleStatus.UNASSIGNED
        else:
            raise Exception("No plan was found")

        plan.solution_score = solver.ObjectiveValue()

        return plan


class Plan:
    def __init__(self, nb_assignable_vehicles: int):
        self.assignments: list[VehicleAssignment] = []
        self.solution_score: float = 0
        self.nb_assignable_vehicles: int = nb_assignable_vehicles

    def get_stats(self):
        """
        Calculate statistics about the generated plan.

        Returns:
            A dictionary containing various statistics such as number of escape nodes,
            candidate nodes, score, vehicle assignments, and time margins.
        """

        times_to_dest = [va.time_to_dest for va in self.assignments]
        time_margins = [va.adv_time_to_dest - va.time_to_dest for va in self.assignments]

        return {
            "score": self.solution_score,
            "nb_vehicles": self.nb_assignable_vehicles,
            "nb_assignments": len(self.assignments),
            "time_margin_stats": (
                min(time_margins),
                int(sum(time_margins) / len(self.assignments)),
                max(time_margins),
            ),
            "time_to_dest_stats": (
                min(times_to_dest),
                int(sum(times_to_dest) / len(self.assignments)),
                max(times_to_dest),
            ),
        }

    def get_assignments_as_gdf(self) -> GeoDataFrame:
        return GeoDataFrame(
            [
                [
                    va.vehicle.id,
                    va.trajectory_geom,
                    va.vehicle.position.u,
                    va.destination_node,
                    va.time_to_dest,
                    va.adv_time_to_dest,
                    va.score,
                ]
                for va in self.assignments
            ],
            crs="EPSG:4326",
            columns=Index(
                [
                    "vid",
                    "geometry",
                    "origin",
                    "destination",
                    "travel_time",
                    "time_margin",
                    "score",
                ]
            ),
        )

    def get_destinations_as_gdf(self) -> GeoDataFrame:
        return GeoDataFrame(
            [
                [
                    va.vehicle.id,
                    va.destination_point,
                ]
                for va in self.assignments
            ],
            crs="EPSG:4326",
            columns=Index(["vid", "geometry"]),
        )
