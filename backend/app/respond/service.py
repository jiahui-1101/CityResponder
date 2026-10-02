"""Composition of Part 4 routing, dispatch, and physical-response services."""

from collections.abc import Mapping
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.dispatch.matrix import (
    DispatchInput,
    DispatchMatrixPolicy,
    DispatchRecommendation,
    build_dispatch_recommendation,
)
from app.fusion.schemas import FusionSourceReference
from app.physical_actions.execution import (
    PhysicalSequenceExecutionResult,
    build_safe_default_specs,
    execute_ack_gated_sequence,
    execute_safe_default_specs_once,
)
from app.physical_actions.mapper import PhysicalActionPlan
from app.physical_actions.schemas import DEFAULT_ACTUATOR_NODE_ID
from app.physical_actions.sequence import PhysicalCommandSequence, sequence_physical_actions
from app.routing.cost import EdgeCostResult, calculate_edge_cost
from app.routing.evidence import RoadEdgeEvidence
from app.routing.factors import RoutingFactorEvaluation, RoutingFactorPolicy, evaluate_routing_factors
from app.routing.graph import ActiveRoutingGraphProjection, build_active_routing_graph
from app.routing.route import RouteCalculationResult, RoutingHeuristicPolicy, calculate_route
from app.routing.safety import EdgeSafetyDecision, IRBlockagePolicy, IRSample, evaluate_edge_safety
from app.routing.persistence import persist_versioned_route
from app.routing.topology import RoutingTopology
from app.routing.versioning import VersionedRoute, version_route
from app.severity.decision import IncidentDecision


class RespondPhaseInput(BaseModel):
    """Explicit inputs and policy boundaries for one Respond-phase run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    incident_decision: IncidentDecision
    operator_actions: list[Any] = Field(default_factory=list)
    person_in_hazard: bool | None = None
    topology: RoutingTopology
    edge_evidence: dict[str, RoadEdgeEvidence] = Field(default_factory=dict)
    ir_samples_by_edge: dict[str, list[IRSample]] = Field(default_factory=dict)
    routing_factor_policy: Any | None = None
    ir_blockage_policy: Any | None = None
    source_node_id: str
    destination_node_id: str
    previous_route: VersionedRoute | None = None
    dispatch_matrix_policy: Any | None = None
    db: Session | None = None
    persist_route: bool = True
    execute_physical: bool = False
    routing_heuristic_policy: Any | None = None
    audit_references: list[FusionSourceReference] = Field(default_factory=list)


class ActiveGraphSummary(BaseModel):
    """Compact graph summary without embedding the mutable NetworkX object."""

    node_count: int
    edge_count: int
    included_edge_ids: list[str]
    excluded_edge_ids: list[str]
    unresolved_edge_ids: list[str]
    missing_cost_edge_ids: list[str]


class RespondPhaseResult(BaseModel):
    """Complete auditable result of one Respond-phase orchestration."""

    status: str
    incident_decision_id: str
    routing_factor_evaluations: dict[str, RoutingFactorEvaluation] = Field(default_factory=dict)
    edge_safety_decisions: dict[str, EdgeSafetyDecision] = Field(default_factory=dict)
    edge_cost_results: dict[str, EdgeCostResult] = Field(default_factory=dict)
    active_graph_summary: ActiveGraphSummary | None = None
    route_calculation: RouteCalculationResult | None = None
    versioned_route: VersionedRoute | None = None
    route_persisted: bool = False
    dispatch_recommendation: DispatchRecommendation | None = None
    physical_action_plan: PhysicalActionPlan | None = None
    physical_command_sequence: PhysicalCommandSequence | None = None
    physical_execution: PhysicalSequenceExecutionResult | None = None
    safe_default_trigger: str | None = None
    routing_duration_ms: float | None = None
    total_duration_ms: float
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_references: list[FusionSourceReference] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime


class RespondOrchestrationService:
    """Stateless coordinator that reuses existing Part 4 components."""

    def run(self, request: RespondPhaseInput) -> RespondPhaseResult:
        started_at = datetime.now(timezone.utc)
        started_clock = perf_counter()
        base = {
            "incident_decision_id": request.incident_decision.decision_id,
            "started_at": started_at,
            "audit_references": list(request.audit_references),
        }
        # Apply Operator manual override logic (DISPATCH-03a)
        effective_confirmed = request.incident_decision.incident_confirmed
        effective_severity = request.incident_decision.final_severity
        
        latest_action = request.operator_actions[-1] if request.operator_actions else None
        
        if latest_action is not None:
            if getattr(latest_action, "action", None) == "CONFIRM" or getattr(latest_action, "resulting_operator_outcome", None) == "CONFIRM":
                effective_confirmed = True
                if effective_severity is None:
                    effective_severity = "MEDIUM"
            elif getattr(latest_action, "action", None) in ("REJECT", "CANCEL") or getattr(latest_action, "resulting_operator_outcome", None) in ("REJECT", "CANCEL"):
                effective_confirmed = False

        if effective_confirmed is not True:
            # If manually rejected or cancelled, trigger cancellation hardware specs
            safe_default_trigger = None
            if latest_action is not None and getattr(latest_action, "action", None) in ("REJECT", "CANCEL"):
                safe_default_trigger = getattr(latest_action, "action", "REJECTED")
                
            execution = None
            sequence = None
            if safe_default_trigger and request.execute_physical and request.db:
                from app.physical_actions.execution import build_cancellation_specs
                from app.physical_actions.schemas import DEFAULT_ACTUATOR_NODE_ID
                from app.physical_actions.sequence import PhysicalCommandSequence
                from uuid import uuid4
                specs = build_cancellation_specs(
                    target_node_id=DEFAULT_ACTUATOR_NODE_ID,
                    source_recommendation_id=request.incident_decision.decision_id,
                    audit_references=request.audit_references,
                    trigger_reason=safe_default_trigger,
                )
                sequence = PhysicalCommandSequence(
                    sequence_id=str(uuid4()),
                    route_id=None,
                    route_version=None,
                    recommendation_id=request.incident_decision.decision_id,
                    commands=[], # Handled purely by the specs runner
                )
                execution = _run_safe_defaults(request.db, specs, sequence.sequence_id, None)

            actor = "User" if latest_action else "System"
            reason_code = safe_default_trigger if safe_default_trigger else "NOT_CONFIRMED"
            timestamp_str = datetime.now(timezone.utc).isoformat()
            
            return self._finish(
                status="not_actionable" if not safe_default_trigger else safe_default_trigger.lower(),
                base=base,
                started_clock=started_clock,
                reasons=[f"[{timestamp_str}] | [Actor: {actor}] | [{reason_code}]"],
                safe_default_trigger=safe_default_trigger,
                execution=execution,
                sequence=sequence,
            )

        routing_started = perf_counter()
        factors: dict[str, RoutingFactorEvaluation] = {}
        safety: dict[str, EdgeSafetyDecision] = {}
        costs: dict[str, EdgeCostResult] = {}
        for edge in request.topology.edges:
            evidence = request.edge_evidence.get(edge.edge_id)
            if evidence is None:
                continue
            factor = evaluate_routing_factors(evidence, request.routing_factor_policy)
            edge_safety = evaluate_edge_safety(
                evidence,
                request.ir_samples_by_edge.get(edge.edge_id, []),
                ir_policy=request.ir_blockage_policy,
            )
            cost = calculate_edge_cost(edge, factor, edge_safety)
            factors[edge.edge_id] = factor
            safety[edge.edge_id] = edge_safety
            costs[edge.edge_id] = cost

        try:
            active = build_active_routing_graph(
                request.topology,
                list(safety.values()),
                list(costs.values()),
            )
            route_result = calculate_route(
                active,
                request.source_node_id,
                request.destination_node_id,
                heuristic_policy=request.routing_heuristic_policy,
            )
        except (TypeError, ValueError) as exc:
            return self._finish(
                status="configuration_error",
                base=base,
                started_clock=started_clock,
                factors=factors,
                safety=safety,
                costs=costs,
                reasons=[str(exc)],
                routing_duration_ms=(perf_counter() - routing_started) * 1000.0,
            )
        routing_duration_ms = (perf_counter() - routing_started) * 1000.0
        graph_summary = ActiveGraphSummary(
            node_count=active.graph.number_of_nodes(),
            edge_count=active.graph.number_of_edges(),
            included_edge_ids=active.included_edge_ids,
            excluded_edge_ids=active.excluded_edge_ids,
            unresolved_edge_ids=active.unresolved_edge_ids,
            missing_cost_edge_ids=active.missing_cost_edge_ids,
        )

        if route_result.status == "invalid_configuration":
            return self._finish(
                status="configuration_error",
                base=base,
                started_clock=started_clock,
                factors=factors,
                safety=safety,
                costs=costs,
                active_summary=graph_summary,
                route_result=route_result,
                reasons=list(route_result.reasons),
                routing_duration_ms=routing_duration_ms,
            )

        try:
            routed = version_route(route_result, request.previous_route)
        except ValueError as exc:
            return self._finish(
                status="configuration_error",
                base=base,
                started_clock=started_clock,
                factors=factors,
                safety=safety,
                costs=costs,
                active_summary=graph_summary,
                route_result=route_result,
                reasons=[str(exc)],
                routing_duration_ms=routing_duration_ms,
            )
        route_persisted = False
        if request.persist_route:
            if request.db is None:
                return self._finish(
                    status="configuration_error",
                    base=base,
                    started_clock=started_clock,
                    factors=factors,
                    safety=safety,
                    costs=costs,
                    active_summary=graph_summary,
                    route_result=route_result,
                    routed=routed,
                    reasons=["database session is required for route persistence"],
                    routing_duration_ms=routing_duration_ms,
                )
            if request.previous_route is None or routed.route_changed:
                try:
                    persist_versioned_route(request.db, routed)
                    route_persisted = True
                except ValueError as exc:
                    return self._finish(
                        status="persistence_error",
                        base=base,
                        started_clock=started_clock,
                        factors=factors,
                        safety=safety,
                        costs=costs,
                        active_summary=graph_summary,
                        route_result=route_result,
                        routed=routed,
                        reasons=[str(exc)],
                        routing_duration_ms=routing_duration_ms,
                    )

        if route_result.no_safe_route:
            specs = build_safe_default_specs(
                target_node_id=DEFAULT_ACTUATOR_NODE_ID,
                route_id=routed.route_id,
                route_version=routed.version,
                source_recommendation_id=request.incident_decision.decision_id,
                audit_references=request.audit_references,
                trigger_reason="NO_SAFE_ROUTE",
            )
            plan = PhysicalActionPlan(
                status="mapped",
                command_specs=specs,
                source_recommendation_reference=request.incident_decision.decision_id,
                route_id=routed.route_id,
                route_version=routed.version,
                reasons=["normal automated dispatch halted: NO_SAFE_ROUTE"],
                audit_references=request.audit_references,
                generated_at=datetime.now(timezone.utc),
            )
            sequence = sequence_physical_actions(plan)
            execution = None
            if request.execute_physical:
                if request.db is None:
                    return self._finish(
                        status="configuration_error",
                        base=base,
                        started_clock=started_clock,
                        factors=factors,
                        safety=safety,
                        costs=costs,
                        active_summary=graph_summary,
                        route_result=route_result,
                        routed=routed,
                        route_persisted=route_persisted,
                        plan=plan,
                        sequence=sequence,
                        safe_default_trigger="NO_SAFE_ROUTE",
                        reasons=["database session is required for physical execution"],
                        routing_duration_ms=routing_duration_ms,
                    )
                execution = _run_safe_defaults(request.db, specs, sequence.sequence_id, routed)
            return self._finish(
                status="no_safe_route_safe_default",
                base=base,
                started_clock=started_clock,
                factors=factors,
                safety=safety,
                costs=costs,
                active_summary=graph_summary,
                route_result=route_result,
                routed=routed,
                route_persisted=route_persisted,
                plan=plan,
                sequence=sequence,
                execution=execution,
                safe_default_trigger="NO_SAFE_ROUTE",
                reasons=["normal automated dispatch halted"],
                routing_duration_ms=routing_duration_ms,
            )

        dispatch_input = DispatchInput(
            incident_decision_id=request.incident_decision.decision_id,
            incident_confirmed=effective_confirmed,
            final_severity=effective_severity,
            severity_score=request.incident_decision.severity_score,
            person_in_hazard=request.person_in_hazard,
            route_id=routed.route_id,
            route_version=routed.version,
            route_status=routed.route_status,
            no_safe_route=routed.no_safe_route,
            source_references=request.audit_references,
            audit_references=request.incident_decision.audit_references,
        )
        recommendation = build_dispatch_recommendation(
            dispatch_input,
            request.dispatch_matrix_policy,
        )
        if recommendation.status != "recommended":
            return self._finish(
                status="dispatch_not_actionable",
                base=base,
                started_clock=started_clock,
                factors=factors,
                safety=safety,
                costs=costs,
                active_summary=graph_summary,
                route_result=route_result,
                routed=routed,
                route_persisted=route_persisted,
                recommendation=recommendation,
                reasons=list(recommendation.reasons),
                routing_duration_ms=routing_duration_ms,
            )

        from app.physical_actions.mapper import map_dispatch_recommendation

        plan = map_dispatch_recommendation(
            recommendation,
            route_id=routed.route_id,
            route_version=routed.version,
        )
        if plan.status not in {"mapped", "partial"}:
            return self._finish(
                status="physical_plan_not_actionable",
                base=base,
                started_clock=started_clock,
                factors=factors,
                safety=safety,
                costs=costs,
                active_summary=graph_summary,
                route_result=route_result,
                routed=routed,
                route_persisted=route_persisted,
                recommendation=recommendation,
                plan=plan,
                reasons=list(plan.reasons),
                routing_duration_ms=routing_duration_ms,
            )
        sequence = sequence_physical_actions(plan)
        execution = None
        if request.execute_physical:
            if request.db is None:
                return self._finish(
                    status="configuration_error",
                    base=base,
                    started_clock=started_clock,
                    factors=factors,
                    safety=safety,
                    costs=costs,
                    active_summary=graph_summary,
                    route_result=route_result,
                    routed=routed,
                    route_persisted=route_persisted,
                    recommendation=recommendation,
                    plan=plan,
                    sequence=sequence,
                    reasons=["database session is required for physical execution"],
                    routing_duration_ms=routing_duration_ms,
                )
            execution = _run_ack_sequence(request.db, sequence)
        return self._finish(
            status="completed_plan" if not request.execute_physical else execution.status,
            base=base,
            started_clock=started_clock,
            factors=factors,
            safety=safety,
            costs=costs,
            active_summary=graph_summary,
            route_result=route_result,
            routed=routed,
            route_persisted=route_persisted,
            recommendation=recommendation,
            plan=plan,
            sequence=sequence,
            execution=execution,
            reasons=[],
            routing_duration_ms=routing_duration_ms,
        )

    def _finish(self, *, status: str, base: dict[str, Any], started_clock: float, **values: Any) -> RespondPhaseResult:
        aliases = {
            "factors": "routing_factor_evaluations",
            "safety": "edge_safety_decisions",
            "costs": "edge_cost_results",
            "active_summary": "active_graph_summary",
            "route_result": "route_calculation",
            "routed": "versioned_route",
            "recommendation": "dispatch_recommendation",
            "plan": "physical_action_plan",
            "sequence": "physical_command_sequence",
            "execution": "physical_execution",
        }
        for source, target in aliases.items():
            if source in values:
                values[target] = values.pop(source)
        values.setdefault("reasons", [])
        values.setdefault("warnings", [])
        values.setdefault("total_duration_ms", (perf_counter() - started_clock) * 1000.0)
        values.setdefault("completed_at", datetime.now(timezone.utc))
        values["status"] = status
        return RespondPhaseResult(**base, **values)


def _run_ack_sequence(db: Session, sequence: PhysicalCommandSequence) -> PhysicalSequenceExecutionResult:
    import asyncio

    return asyncio.run(execute_ack_gated_sequence(db, sequence))


def _run_safe_defaults(db: Session, specs: list[Any], sequence_id: str, route: VersionedRoute | None = None) -> PhysicalSequenceExecutionResult:
    import asyncio

    return asyncio.run(
        execute_safe_default_specs_once(
            db,
            specs,
            sequence_id=sequence_id,
            route_id=route.route_id if route else None,
            route_version=route.version if route else None,
        )
    )


def run_respond_phase(request: RespondPhaseInput) -> RespondPhaseResult:
    """Convenience wrapper for the stateless Respond orchestrator."""

    return RespondOrchestrationService().run(request)
