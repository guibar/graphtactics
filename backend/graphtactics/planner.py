import logging

from geopandas import GeoDataFrame
from ortools.sat.python import cp_model
from ortools.sat.python.cp_model import IntVar
from pandas import Index

from .adversary import TravelData
from .road_network import RoadNetwork
from .scenario import Scenario
from .vehicle import Vehicle, VehicleAssignment, VehicleStatus

MAX_TIME_TO_SOLVE = 30

logger = logging.getLogger(__name__)


class Planner:
    def __init__(self, network: RoadNetwork, scenario: Scenario):
        self.network = network
        self.vehicles: dict[int, Vehicle] = scenario.vehicles
        self.assignable_vids: list[int] = []  # maps an int from 0 to (number of assignable -1) vehicles to vid
        self.travel_data: TravelData = scenario.adversary.travel_data
        self.candidate_nodes = scenario.adversary.candidate_nodes

        for vehicle in self.vehicles.values():
            # Don't bother calculating travel times for vehicles that are too close to the action
            if self.travel_data.times_to_nodes.get(vehicle.position.u, 1) <= 0:
                logger.debug(
                    f"Vehicle {vehicle.id} will not be assigned to the plan because the adversary has passed it."
                )
                vehicle.status = VehicleStatus.TOO_CLOSE_TO_LKP
            else:
                # this is ugly the status gets set in set_travel_times if not enough points are reachable
                vehicle.set_travel_times()
                if vehicle.status == VehicleStatus.ASSIGNABLE:
                    self.assignable_vids.append(vehicle.id)

    def plan_interception(self, time_margin: int = 0) -> "Plan":
        """
        Generate the optimal interception plan.

        This method uses the OR-Tools solver to assign vehicles to interception nodes
        in order to maximize the total interception score. It updates the status and
        assignment of each vehicle.
        """
        # No vehicles, so no solution to find and nothing more to do
        if len(self.assignable_vids) == 0:
            return Plan(len(self.assignable_vids))

        node_scores: list[int] = self.candidate_nodes.node_scores
        adv_paths_to_nodes: list[list[int]] = self.candidate_nodes.paths_as_seq_indices
        adv_times_to_nodes: list[int] = self.candidate_nodes.times_to_nodes

        times_v_n: list[list[int]] = Vehicle.get_time_matrix(
            {i: self.vehicles[i] for i in self.assignable_vids},
            self.candidate_nodes.node_osmids,
        )
        num_vehicles: int = len(times_v_n)
        num_nodes: int = len(times_v_n[0])

        plan: Plan = Plan(len(self.assignable_vids))

        # The model
        model = cp_model.CpModel()

        # IntVars are actually booleans (NewBoolVar) or constants (NewConstant)
        vehicule_node_matrix: list[list[IntVar]] = [[]] * num_vehicles
        for vehicule_row_i in range(num_vehicles):
            vehicule_node_matrix[vehicule_row_i] = []
            for node_column_j in range(num_nodes):
                # If our vehicle v_i can reach this node before the adversary, it's a boolean variable.
                if adv_times_to_nodes[node_column_j] - times_v_n[vehicule_row_i][node_column_j] - time_margin > 0:
                    vehicule_node_matrix[vehicule_row_i].append(
                        model.NewBoolVar(f"x[v={vehicule_row_i},n={node_column_j}]")
                    )
                # Otherwise, this assignment is excluded and we can set the value to constant 0
                else:
                    vehicule_node_matrix[vehicule_row_i].append(model.NewConstant(0))

        # _____________ Constraints  ____________

        # C1: A vehicle is assigned to at most one node
        for vehicule_row_i in range(num_vehicles):
            model.Add(sum(vehicule_node_matrix[vehicule_row_i][n_j] for n_j in range(num_nodes)) <= 1)

        # C2: A node is assigned to at most one vehicle
        for n_j in range(num_nodes):
            model.Add(sum(vehicule_node_matrix[v_i][n_j] for v_i in range(num_vehicles)) <= 1)

        # C3: The number of vehicles on a shortest path cannot be greater than 1.
        for sp_index in range(len(adv_paths_to_nodes)):
            model.Add(
                sum(
                    vehicule_node_matrix[v_i][n_j]
                    for v_i in range(num_vehicles)
                    for n_j in adv_paths_to_nodes[sp_index]
                )
                <= 1
            )

        # _____________ End Constraints  ____________

        # Objective: maximize the sum of scores of assigned (monitored) nodes
        objective_terms = [
            node_scores[n_j] * vehicule_node_matrix[v_i][n_j] for v_i in range(num_vehicles) for n_j in range(num_nodes)
        ]
        model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = MAX_TIME_TO_SOLVE
        status = solver.Solve(model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            logger.info(f"The total score of the plan is:  {solver.ObjectiveValue()}")
            for vehicule_row_i in range(num_vehicles):
                for n_j in range(num_nodes):
                    if solver.BooleanValue(vehicule_node_matrix[vehicule_row_i][n_j]):
                        v_a = VehicleAssignment(
                            self.network,
                            self.vehicles[self.assignable_vids[vehicule_row_i]],
                            self.candidate_nodes.node_osmids[n_j],
                            times_v_n[vehicule_row_i][n_j],
                            adv_times_to_nodes[n_j],
                            node_scores[n_j],
                        )
                        plan.assignments.append(v_a)
                        logger.info(
                            f"Vehicle {v_a.vehicle.id}({vehicule_row_i}) must go to node {v_a.destination_node}({n_j}).\n"
                            f"It will arrive {adv_times_to_nodes[n_j] - times_v_n[vehicule_row_i][n_j]} seconds"
                            f" before the adversary and contributes {node_scores[n_j]} points to the total score."
                        )
                        self.vehicles[self.assignable_vids[vehicule_row_i]].status = VehicleStatus.ASSIGNED
                        break
                else:
                    self.vehicles[self.assignable_vids[vehicule_row_i]].status = VehicleStatus.UNASSIGNED
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
                min(time_margins) if time_margins else 0,
                int(sum(time_margins) / len(self.assignments)) if time_margins else 0,
                max(time_margins) if time_margins else 0,
            ),
            "time_to_dest_stats": (
                min(times_to_dest) if times_to_dest else 0,
                int(sum(times_to_dest) / len(self.assignments)) if times_to_dest else 0,
                max(times_to_dest) if times_to_dest else 0,
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
