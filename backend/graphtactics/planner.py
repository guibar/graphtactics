"""
Optimization engine for vehicle interception planning.

This module uses OR-Tools (Constraint Programming) to solve the multi-vehicle
assignment problem. The goal is to assign police vehicles to specific road
network nodes to intercept an adversary, maximizing the total interception
score while respecting time constraints and path coverage rules.
"""

from __future__ import annotations

import logging
from typing import Any

from ortools.sat.python import cp_model
from ortools.sat.python.cp_model import IntVar

from graphtactics.road_network import RoadNetwork

from .config import MAX_SPEED_M_PER_SECOND
from .escape_model import EscapeModel
from .scenario import Scenario
from .utils import distance
from .vehicle import Vehicle, VehicleAssignment, VehicleStatus

# Maximum time (in seconds) allowed for the solver to find a solution
MAX_TIME_TO_SOLVE = 30
logger = logging.getLogger(__name__)


class Planner:
    """Orchestrates the optimization process to assign vehicles to interception points.

    Attributes:
        network: The underlying road network.
        vehicles: Dictionary of all available vehicles in the scenario.
        assignable_vids: IDs of vehicles that passed the proximity filter.
        time_margin: Safety buffer (seconds) the vehicle must arrive before the adversary.
        escape_model: The computed model of potential adversary behavior.
        plan: The resulting interception plan maximizing the total interception score.
    """

    def __init__(self, network: RoadNetwork, scenario: Scenario):
        """Initialize the planner with scenario data.

        Args:
            network: RoadNetwork instance.
            scenario: The current tactical situation (adversary LKP + vehicle locations).
        """
        self.network: RoadNetwork = network
        self.vehicles: dict[int, Vehicle] = scenario.vehicles
        self.assignable_vids: list[int] = []
        self.time_margin: int = scenario.time_margin
        self.escape_model: EscapeModel = scenario.adversary.escape_model
        self.plan: Plan | None = None

    def plan_interception(self) -> Plan:
        """Generate the optimal interception plan using Constraint Programming.

        The optimization process involves:
        1. Filtering: Identifying which vehicles can realistically participate.
        2. Matrix Building: Computing travel times from each assignable vehicle to each candidate node.
        3. CP Model: Defining variables, constraints, and the objective function.
        4. Solving: Invoking the OR-Tools SAT solver.
        5. Post-processing: Updating node/vehicle statuses and finalizing the Plan object.

        Returns:
            A Plan object containing assignments and performance stats.

        Raises:
            Exception: If the solver fails to find even a feasible (sub-optimal) solution.
        """
        # Reset assignable vehicles list in case this is called multiple times
        self.assignable_vids = []

        # 1. Filtering: Eliminate vehicles that could have been passed by the adversary
        # if we assume it travels at MAX_SPEED_M_PER_SECOND
        for vehicle in self.vehicles.values():
            # Estimate if the adversary could have already passed the vehicle's position
            dist_to_lkp = distance(self.escape_model.lk_point, vehicle.point)
            approx_adv_speed = dist_to_lkp / self.escape_model.time_elapsed

            if approx_adv_speed < MAX_SPEED_M_PER_SECOND:
                logger.debug(
                    f"Vehicle {vehicle.id} bypassed: Adversary likely past this location "
                    f"(speed={approx_adv_speed:.1f}m/s)."
                )
                vehicle.status = VehicleStatus.TOO_CLOSE_TO_LKP
            else:
                # Calculate internal Dijkstra distance/time for this vehicle to the whole network
                vehicle.set_travel_times()
                self.assignable_vids.append(vehicle.id)

        # Handle edge case: no resources available
        if len(self.assignable_vids) == 0:
            logger.warning("No assignable vehicles found for this scenario.")
            self.plan = Plan(0)
            return self.plan

        # Prepare data for the CP model
        candidate_nodes = self.escape_model.candidate_nodes
        node_scores: list[int] = [node.score for node in candidate_nodes]
        adv_times_to_nodes: list[float] = [node.time_reached for node in candidate_nodes]

        # adv_paths_to_nodes identifies which candidate nodes belong to the same escape route
        adv_paths_to_nodes: list[list[int]] = self.escape_model.get_paths_as_seq_indices()

        # Build the cost matrix (Vehicle x Node)
        times_v_n: list[list[int]] = Vehicle.get_time_matrix(
            {i: self.vehicles[i] for i in self.assignable_vids},
            [node.osmid for node in candidate_nodes],
        )
        num_vehicles: int = len(times_v_n)
        num_nodes: int = len(times_v_n[0])

        plan = Plan(num_vehicles)

        # 3. Model Definition using OR-Tools CP-SAT
        model = cp_model.CpModel()

        # variables[v][n] is a boolean: 1 if vehicle v is assigned to node n, 0 otherwise
        vehicle_node_matrix: list[list[IntVar]] = [[] for _ in range(num_vehicles)]

        for v_i in range(num_vehicles):
            for n_j in range(num_nodes):
                # Reachability Condition:
                # This vehicle can potentially be assigned to this node
                if adv_times_to_nodes[n_j] - times_v_n[v_i][n_j] - self.time_margin > 0:
                    var = model.NewBoolVar(f"x[v={v_i},n={n_j}]")
                    vehicle_node_matrix[v_i].append(var)
                else:
                    # This vehicle should not be assigned to this node
                    vehicle_node_matrix[v_i].append(model.NewConstant(0))

        # --- Constraints ---

        # Constraint 1: Each vehicle can be assigned to AT MOST one interception point.
        for v_i in range(num_vehicles):
            model.Add(sum(vehicle_node_matrix[v_i]) <= 1)

        # Constraint 2: Each node can be assigned AT MOST one vehicle (no redundant monitoring).
        for n_j in range(num_nodes):
            model.Add(sum(vehicle_node_matrix[v_i][n_j] for v_i in range(num_vehicles)) <= 1)

        # Constraint 3: Branch Coverage Efficiency.
        # We don't want multiple vehicles on the same linear escape path.
        for path_indices in adv_paths_to_nodes:
            model.Add(sum(vehicle_node_matrix[v_i][n_j] for v_i in range(num_vehicles) for n_j in path_indices) <= 1)

        # --- Objective Function ---
        # Goal: Maximize the total score of monitored nodes.
        # Higher scores are typically assigned to nodes closer to the LKP or on major roads.
        objective_terms: list[Any] = []
        for v_i in range(num_vehicles):
            for n_j in range(num_nodes):
                objective_terms.append(node_scores[n_j] * vehicle_node_matrix[v_i][n_j])

        model.Maximize(sum(objective_terms))

        # 4. Solving
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = MAX_TIME_TO_SOLVE
        status = solver.Solve(model)

        # 5. Post-processing Results if a solution was found
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.info(f"Plan found with total score: {solver.ObjectiveValue()}")

            for v_i in range(num_vehicles):
                assigned = False
                for n_j in range(num_nodes):
                    if solver.BooleanValue(vehicle_node_matrix[v_i][n_j]):
                        # Successful assignment! Create the rich domain object.
                        v_a = VehicleAssignment(
                            self.network,
                            self.vehicles[self.assignable_vids[v_i]],
                            candidate_nodes[n_j].osmid,
                            times_v_n[v_i][n_j],
                            adv_times_to_nodes[n_j],
                            node_scores[n_j],
                        )
                        plan.assignments.append(v_a)

                        # Update domain statuses
                        self.vehicles[self.assignable_vids[v_i]].status = VehicleStatus.ASSIGNED
                        self.escape_model.set_as_control_node(v_a.destination_node)

                        logger.info(
                            f"VID {v_a.vehicle.id} -> Node {v_a.destination_node}. "
                            f"Margin: {v_a.adv_time_to_dest - v_a.time_to_dest:.1f}s, Score: {v_a.score}"
                        )
                        assigned = True
                        break

                if not assigned:
                    self.vehicles[self.assignable_vids[v_i]].status = VehicleStatus.UNASSIGNED
        else:
            logger.error("Solver failed to find a valid interception plan.")
            raise Exception("No feasible plan found within time constraints.")

        # Finalize the visual model state (which parts of the tree are now covered)
        self.escape_model.set_cover_status()
        plan.solution_score = solver.ObjectiveValue()
        self.plan = plan
        return self.plan


class Plan:
    """Represents the results of an optimization run.

    Attributes:
        assignments: List of vehicles and their target interception nodes.
        solution_score: Total score achieved by the solver.
        nb_assignable_vehicles: Total number of vehicles that were considered.
    """

    def __init__(self, nb_assignable_vehicles: int):
        """Initialize an empty plan.

        Args:
            nb_assignable_vehicles: Count of vehicles eligible for assignment.
        """
        self.assignments: list[VehicleAssignment] = []
        self.solution_score: float = 0
        self.nb_assignable_vehicles: int = nb_assignable_vehicles

    def get_stats(self) -> dict[str, Any]:
        """Calculate performance and tactical statistics about the plan.

        Returns:
            Dictionary containing:
                - score: Total plan score.
                - nb_vehicles: Number of assignable vehicles.
                - nb_assignments: Number of successful assignments.
                - time_margin_stats: (min, avg, max) time buffer before adversary.
                - time_to_dest_stats: (min, avg, max) travel time for police vehicles.
        """
        times_to_dest = [va.time_to_dest for va in self.assignments]
        time_margins = [va.adv_time_to_dest - va.time_to_dest for va in self.assignments]

        return {
            "score": self.solution_score,
            "nb_vehicles": self.nb_assignable_vehicles,
            "nb_assignments": len(self.assignments),
            "time_margin_stats": (
                round(min(time_margins), 1) if time_margins else 0,
                round(sum(time_margins) / len(self.assignments), 1) if time_margins else 0,
                round(max(time_margins), 1) if time_margins else 0,
            ),
            "time_to_dest_stats": (
                round(min(times_to_dest), 1) if times_to_dest else 0,
                round(sum(times_to_dest) / len(self.assignments), 1) if times_to_dest else 0,
                round(max(times_to_dest), 1) if times_to_dest else 0,
            ),
        }
