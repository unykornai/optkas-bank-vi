"""
Deal Lifecycle State Machine
==============================
Tracks a deal through its institutional lifecycle:

  DRAFT → REVIEW → CONDITIONALLY_APPROVED → APPROVED → EXECUTED → CLOSED
                                    ↘ BLOCKED (can return to REVIEW)

State transitions are gated by policy and compliance conditions.
Every transition is audit-logged.

This is what turns a document generator into a deal execution platform.
Without lifecycle tracking, you have files.
With lifecycle tracking, you have institutional memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from engine.schema_loader import ROOT_DIR
from engine.policy_engine import PolicyEngine
from engine._icons import ICON_CHECK, ICON_CROSS, ICON_WARN


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEALS_DIR = ROOT_DIR / "output" / "deals"


# ---------------------------------------------------------------------------
# State Model
# ---------------------------------------------------------------------------

class DealState(str, Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    CONDITIONALLY_APPROVED = "CONDITIONALLY_APPROVED"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    EXECUTED = "EXECUTED"
    CLOSED = "CLOSED"


# Valid transitions
TRANSITIONS: dict[DealState, set[DealState]] = {
    DealState.DRAFT: {DealState.REVIEW},
    DealState.REVIEW: {DealState.CONDITIONALLY_APPROVED, DealState.BLOCKED},
    DealState.CONDITIONALLY_APPROVED: {DealState.APPROVED, DealState.BLOCKED, DealState.REVIEW},
    DealState.APPROVED: {DealState.EXECUTED, DealState.BLOCKED},
    DealState.BLOCKED: {DealState.REVIEW},
    DealState.EXECUTED: {DealState.CLOSED},
    DealState.CLOSED: set(),
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class StateTransition:
    """Record of a single state transition."""
    from_state: str
    to_state: str
    timestamp: str
    actor: str
    reason: str
    gate_check: dict[str, Any] = field(default_factory=dict)


@dataclass
class DealRecord:
    """Persistent record of a deal's lifecycle."""
    deal_id: str
    transaction_type: str
    entity_name: str
    counterparty_name: str
    state: str = DealState.DRAFT.value
    created_at: str = ""
    updated_at: str = ""
    transitions: list[StateTransition] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    @property
    def state_enum(self) -> DealState:
        return DealState(self.state)

    @property
    def is_terminal(self) -> bool:
        return self.state_enum in (DealState.CLOSED,)

    @property
    def is_blocked(self) -> bool:
        return self.state_enum == DealState.BLOCKED

    @property
    def can_execute(self) -> bool:
        return self.state_enum == DealState.APPROVED

    def available_transitions(self) -> list[str]:
        return [s.value for s in TRANSITIONS.get(self.state_enum, set())]

    def summary(self) -> str:
        state_icons = {
            "DRAFT": ICON_WARN,
            "REVIEW": ICON_WARN,
            "CONDITIONALLY_APPROVED": ICON_WARN,
            "APPROVED": ICON_CHECK,
            "BLOCKED": ICON_CROSS,
            "EXECUTED": ICON_CHECK,
            "CLOSED": ICON_CHECK,
        }
        icon = state_icons.get(self.state, "?")

        lines = [
            f"DEAL LIFECYCLE -- {self.deal_id}",
            f"State:         {icon} {self.state}",
            f"Transaction:   {self.transaction_type}",
            f"Entity:        {self.entity_name}",
            f"Counterparty:  {self.counterparty_name}",
            f"Created:       {self.created_at}",
            f"Updated:       {self.updated_at}",
            f"Transitions:   {len(self.transitions)}",
            f"Available:     {', '.join(self.available_transitions()) or 'NONE (terminal)'}",
            "",
        ]

        if self.transitions:
            lines.append("TRANSITION HISTORY:")
            for t in self.transitions:
                lines.append(f"  {t.timestamp}: {t.from_state} -> {t.to_state}")
                lines.append(f"    Actor: {t.actor} | Reason: {t.reason}")
                if t.gate_check:
                    for k, v in t.gate_check.items():
                        lines.append(f"    Gate: {k} = {v}")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "deal_id": self.deal_id,
            "transaction_type": self.transaction_type,
            "entity_name": self.entity_name,
            "counterparty_name": self.counterparty_name,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "transitions": [
                {
                    "from_state": t.from_state,
                    "to_state": t.to_state,
                    "timestamp": t.timestamp,
                    "actor": t.actor,
                    "reason": t.reason,
                    "gate_check": t.gate_check,
                }
                for t in self.transitions
            ],
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Deal Lifecycle Manager
# ---------------------------------------------------------------------------

class DealLifecycleManager:
    """
    Manages deal state transitions with policy-driven gates.
    """

    def __init__(self, deals_dir: Path | None = None) -> None:
        self._deals_dir = deals_dir or DEALS_DIR
        self._deals_dir.mkdir(parents=True, exist_ok=True)
        self.policy = PolicyEngine()

    def create_deal(
        self,
        deal_id: str,
        transaction_type: str,
        entity_name: str,
        counterparty_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> DealRecord:
        """Create a new deal in DRAFT state."""
        deal = DealRecord(
            deal_id=deal_id,
            transaction_type=transaction_type,
            entity_name=entity_name,
            counterparty_name=counterparty_name,
            metadata=metadata or {},
        )
        self._save(deal)
        return deal

    def transition(
        self,
        deal_id: str,
        to_state: str,
        actor: str = "system",
        reason: str = "",
        *,
        compliance_score: int | None = None,
        opinion_grade: str | None = None,
        checklist_clear: bool | None = None,
        risk_tier: str | None = None,
        force: bool = False,
    ) -> DealRecord:
        """
        Transition a deal to a new state.

        Gate checks are performed based on the target state.
        Use force=True to override gates (audit-logged).
        """
        deal = self.load_deal(deal_id)
        target = DealState(to_state)

        # Validate transition is allowed
        if target not in TRANSITIONS.get(deal.state_enum, set()):
            raise ValueError(
                f"Cannot transition from {deal.state} to {to_state}. "
                f"Available: {deal.available_transitions()}"
            )

        # Gate checks
        gate_results: dict[str, Any] = {}

        if target == DealState.CONDITIONALLY_APPROVED:
            gate_results = self._gate_review_to_conditional(
                compliance_score, opinion_grade, risk_tier
            )
        elif target == DealState.APPROVED:
            gate_results = self._gate_conditional_to_approved(
                checklist_clear, opinion_grade
            )
        elif target == DealState.EXECUTED:
            gate_results = self._gate_approved_to_executed(
                checklist_clear
            )

        # Check if any gate failed
        gate_blocked = any(
            not v.get("passed", True) for v in gate_results.values()
            if isinstance(v, dict)
        )

        if gate_blocked and not force:
            # Auto-transition to BLOCKED
            target = DealState.BLOCKED
            reason = reason or "Gate check failed. See gate_check details."

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        transition = StateTransition(
            from_state=deal.state,
            to_state=target.value,
            timestamp=now,
            actor=actor,
            reason=reason or f"Transition to {target.value}",
            gate_check=gate_results,
        )

        deal.state = target.value
        deal.updated_at = now
        deal.transitions.append(transition)

        self._save(deal)
        return deal

    def load_deal(self, deal_id: str) -> DealRecord:
        """Load a deal record from disk."""
        path = self._deal_path(deal_id)
        if not path.exists():
            raise FileNotFoundError(f"Deal not found: {deal_id}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        deal = DealRecord(
            deal_id=data["deal_id"],
            transaction_type=data["transaction_type"],
            entity_name=data["entity_name"],
            counterparty_name=data["counterparty_name"],
            state=data["state"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            metadata=data.get("metadata", {}),
        )

        for t in data.get("transitions", []):
            deal.transitions.append(StateTransition(
                from_state=t["from_state"],
                to_state=t["to_state"],
                timestamp=t["timestamp"],
                actor=t["actor"],
                reason=t["reason"],
                gate_check=t.get("gate_check", {}),
            ))

        return deal

    def list_deals(self) -> list[DealRecord]:
        """List all deals."""
        deals = []
        for path in self._deals_dir.glob("deal_*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                deal = self.load_deal(data["deal_id"])
                deals.append(deal)
            except Exception:
                pass
        return deals

    # --- Gate checks ---

    def _gate_review_to_conditional(
        self,
        compliance_score: int | None,
        opinion_grade: str | None,
        risk_tier: str | None,
    ) -> dict[str, Any]:
        """Gate: REVIEW → CONDITIONALLY_APPROVED"""
        gates: dict[str, Any] = {}

        if compliance_score is not None:
            gates["compliance_score"] = {
                "value": compliance_score,
                "threshold": 50,
                "passed": compliance_score >= 50,
            }

        if opinion_grade is not None:
            blocked_grades = {"ADVERSE"}
            if self.policy.opinion.get("unable_to_opine_blocks_signature", True):
                blocked_grades.add("UNABLE_TO_OPINE")
            gates["opinion_grade"] = {
                "value": opinion_grade,
                "blocked_grades": list(blocked_grades),
                "passed": opinion_grade not in blocked_grades,
            }

        if risk_tier is not None:
            gates["risk_tier"] = {
                "value": risk_tier,
                "max_allowed": "HIGH",
                "passed": risk_tier != "CRITICAL",
            }

        return gates

    def _gate_conditional_to_approved(
        self,
        checklist_clear: bool | None,
        opinion_grade: str | None,
    ) -> dict[str, Any]:
        """Gate: CONDITIONALLY_APPROVED → APPROVED"""
        gates: dict[str, Any] = {}

        if checklist_clear is not None:
            gates["checklist_clear"] = {
                "value": checklist_clear,
                "required": True,
                "passed": checklist_clear is True,
            }

        if opinion_grade is not None and self.policy.adverse_blocks_signature():
            gates["opinion_not_adverse"] = {
                "value": opinion_grade,
                "passed": opinion_grade != "ADVERSE",
            }

        return gates

    def _gate_approved_to_executed(
        self,
        checklist_clear: bool | None,
    ) -> dict[str, Any]:
        """Gate: APPROVED → EXECUTED"""
        gates: dict[str, Any] = {}

        if checklist_clear is not None:
            gates["final_checklist_clear"] = {
                "value": checklist_clear,
                "required": True,
                "passed": checklist_clear is True,
            }

        return gates

    # --- Persistence ---

    def _deal_path(self, deal_id: str) -> Path:
        slug = deal_id.replace(" ", "_").replace("-", "_").lower()
        return self._deals_dir / f"deal_{slug}.json"

    def _save(self, deal: DealRecord) -> None:
        path = self._deal_path(deal.deal_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(deal.to_dict(), f, indent=2, default=str, ensure_ascii=False)
